#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ supplies tomllib
    tomllib = None


PACKET_FILES = ("AGENTS.md", "PROJECT_CONTINUITY.md", "CHECKPOINT.md")
REQUIRED_HEADINGS = {
    "PROJECT_CONTINUITY.md": (
        "Purpose",
        "User / Operator Job",
        "Success Criteria",
        "Non-Goals",
        "Current Product Strategy",
        "Workstream Map",
        "Stable Constraints / Invariants",
        "Authority Map",
    ),
}
CHECKPOINT_HEADING_PROFILES = {
    "current": {
        "Scope And Freshness",
        "Current State And Focus",
        "Decisions And Unknowns",
        "Validation Evidence",
        "Known Traps / Do Not Repeat",
        "Next Safe Step",
        "References And Sensitivity",
    },
    "legacy": {
        "Current Focus",
        "Why Current Focus Matters",
        "Open Blockers / Decisions",
        "Validation Evidence",
        "Next Safe Step",
        "Archive References",
    },
}
SCAFFOLD_MARKERS = (
    "Replace every angle-bracket",
    "<repo-specific execution rule>",
    "<repo-specific validation rule>",
    "<current workstream or stop condition>",
    "<What the project exists to do",
)
PLACEHOLDER_PATTERN = re.compile(r"<(?:(?:YYYY|repo|workspace|product|program|branch|commit|release|dataset|runtime|path|surface|workstream|specific|current|what|who|concrete|tempting|assumption|evidence|durable|themed|command)[^>\n]*)>", re.IGNORECASE)
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
PERSONAL_PATH_PATTERN = re.compile(r"(?:/Users/[^/\s]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
)
ADVISORY_WORD_LIMITS = {
    "AGENTS.md": 300,
    "PROJECT_CONTINUITY.md": 900,
    "CHECKPOINT.md": 500,
}


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def resolve_root(path_text: str) -> Path:
    candidate = Path(path_text).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    return candidate


def finding(code: str, severity: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "path": path, "message": message}


def heading_names(text: str) -> set[str]:
    return {
        match.group(1).strip()
        for match in re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE)
    }


def frontmatter_value(text: str, key: str) -> str:
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---\n", 4)
    if end < 0:
        return ""
    match = re.search(rf"^{re.escape(key)}:\s*[\"']?([^\n\"']+)", text[4:end], flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def checkpoint_field(text: str, label: str) -> str:
    match = re.search(rf"^-\s+{re.escape(label)}:\s*(.+?)\s*$", text, flags=re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def ownership_posture(root: Path) -> str:
    cookie = root / ".codex/codex-spine.toml"
    if not cookie.exists() or tomllib is None:
        return "undetermined"
    try:
        data = tomllib.loads(cookie.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return "undetermined"
    if data.get("taken_charge") is not True:
        return "undetermined"
    posture = str(data.get("posture", "repo-local")).strip().lower()
    if posture in {"in-tree-adoption", "repo-local"}:
        return "repo-local"
    if posture in {"repo-native only", "repo-native-only"}:
        return "repo-native-only"
    return posture


def inspect_custom_declarations(root: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for relative in (Path(".codex/codex-spine.toml"), Path(".codex/indexes.toml")):
        path = root / relative
        if not path.exists():
            continue
        if tomllib is None:
            findings.append(finding("undefined-declaration", "warning", str(relative), "Environment-specific declaration exists but no TOML parser is available to validate it."))
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            findings.append(finding("invalid-declaration", "error", str(relative), "Environment-specific declaration is not valid readable TOML."))
            continue
        if relative.name == "codex-spine.toml":
            posture = ownership_posture(root)
            if posture not in {"undetermined", "repo-local", "local-overlay", "repo-native-only"}:
                findings.append(finding("undefined-posture", "warning", str(relative), "Ownership posture is not part of the portable continuity vocabulary."))
            if "format_version" not in data:
                findings.append(finding("undefined-declaration", "warning", str(relative), "Ownership declaration has no format version; use it only under an environment-defined schema."))
        elif "version" not in data:
            findings.append(finding("undefined-declaration", "warning", str(relative), "Index declaration has no version; use it only under an environment-defined schema."))
    return findings


def inspect_packet_economy(root: Path, existing: dict[str, bool]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for name, limit in ADVISORY_WORD_LIMITS.items():
        if not existing.get(name):
            continue
        try:
            words = re.findall(r"\b\w[\w'-]*\b", (root / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if len(words) > limit:
            findings.append(finding("startup-size", "warning", name, "Startup file exceeds its advisory prompt-economy threshold; review placement without trimming solely for size."))
    return findings


def inspect_duplicate_current_state(root: Path, existing: dict[str, bool]) -> list[dict[str, str]]:
    if not existing.get("PROJECT_CONTINUITY.md") or not existing.get("CHECKPOINT.md"):
        return []

    def durable_lines(path: Path) -> set[str]:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return set()
        return {
            re.sub(r"\s+", " ", line.strip()).lower()
            for line in text.splitlines()
            if line.lstrip().startswith("- ") and len(line.strip()) >= 60
        }

    if durable_lines(root / "PROJECT_CONTINUITY.md") & durable_lines(root / "CHECKPOINT.md"):
        return [finding("duplicated-state", "warning", "CHECKPOINT.md", "A long bullet is duplicated verbatim between durable authority and volatile handoff; give the fact one owner and link to it.")]
    return []


def local_link_target(root: Path, source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip()
    if target.startswith(("http://", "https://", "mailto:", "#", "data:")):
        return None
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    target = unquote(target.split("#", 1)[0])
    if not target:
        return None
    path = Path(target)
    return path if path.is_absolute() else (source.parent / path).resolve()


def inspect_packet_file(root: Path, path: Path, visibility: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    relative = str(path.relative_to(root))
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [finding("unreadable", "error", relative, "Startup file is not readable UTF-8 text.")]

    for required in REQUIRED_HEADINGS.get(path.name, ()):
        if required not in heading_names(text):
            findings.append(finding("missing-heading", "error", relative, f"Missing required heading: {required}"))

    if path.name == "CHECKPOINT.md":
        headings = heading_names(text)
        if CHECKPOINT_HEADING_PROFILES["current"].issubset(headings):
            pass
        elif CHECKPOINT_HEADING_PROFILES["legacy"].issubset(headings):
            findings.append(finding("legacy-checkpoint-shape", "warning", relative, "Checkpoint uses the legacy live-handoff shape; migrate only when its project-level contract is intentionally revised."))
        else:
            findings.append(finding("checkpoint-shape", "error", relative, "Checkpoint does not satisfy the current or read-compatible legacy heading contract."))

    if any(marker in text for marker in SCAFFOLD_MARKERS) or PLACEHOLDER_PATTERN.search(text):
        findings.append(finding("template-residue", "error", relative, "Instantiated startup file still contains scaffold text or placeholders."))

    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        findings.append(finding("secret-material", "error", relative, "Startup file contains a high-confidence secret or private-key pattern."))

    if visibility != "local-only" and PERSONAL_PATH_PATTERN.search(text):
        findings.append(finding("personal-path", "warning", relative, "Repo-shared startup file contains a personal machine path; verify that it is intentional and safe to share."))

    for raw_target in MARKDOWN_LINK_PATTERN.findall(text):
        resolved = local_link_target(root, path, raw_target)
        if resolved is not None and not resolved.exists():
            findings.append(finding("broken-link", "error", relative, f"Local pointer does not resolve: {raw_target}"))

    return findings


def inspect_state_anchor(root: Path, checkpoint_text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    anchor = " ".join(
        value
        for value in (
            frontmatter_value(checkpoint_text, "state_anchor"),
            checkpoint_field(checkpoint_text, "Worktree / branch / ref"),
            checkpoint_field(checkpoint_text, "Last verified"),
        )
        if value
    )
    working_state = (
        frontmatter_value(checkpoint_text, "working_state")
        or checkpoint_field(checkpoint_text, "Working state")
    ).lower()
    head_result = git(root, "rev-parse", "HEAD")
    if head_result.returncode != 0:
        return findings

    if not anchor:
        findings.append(finding("missing-state-anchor", "warning", "CHECKPOINT.md", "Checkpoint has no stable repository, build, dataset, deployed-version, or artifact identity to reconcile."))

    head = head_result.stdout.strip().lower()
    sha_match = re.search(r"\b[0-9a-fA-F]{7,40}\b", anchor)
    if sha_match and not head.startswith(sha_match.group(0).lower()):
        findings.append(finding("state-anchor-mismatch", "warning", "CHECKPOINT.md", "Checkpoint commit anchor does not match current HEAD; reconcile it before resuming."))

    if working_state == "clean":
        status = git(root, "status", "--porcelain=v1")
        if status.returncode == 0 and status.stdout:
            findings.append(finding("working-state-mismatch", "warning", "CHECKPOINT.md", "Checkpoint claims a clean working state but the current Git worktree is dirty."))
    return findings


def audit(root: Path) -> dict[str, object]:
    existing = {name: (root / name).exists() for name in PACKET_FILES}
    posture = ownership_posture(root)
    adopted = posture == "repo-local" or existing["PROJECT_CONTINUITY.md"] or existing["CHECKPOINT.md"]
    if not adopted and existing["AGENTS.md"]:
        posture = "undetermined"
    elif not adopted:
        posture = "repo-native-only"

    findings: list[dict[str, str]] = []
    if adopted:
        for name, present in existing.items():
            if not present:
                findings.append(finding("missing-startup-file", "error", name, "Adopted continuity packet is incomplete."))
    else:
        for name in ("PROJECT_CONTINUITY.md", "CHECKPOINT.md"):
            nested = root / "docs" / name
            if nested.exists():
                findings.append(finding("startup-location", "warning", str(nested.relative_to(root)), "Continuity-like file exists outside the root startup exceptions; verify that the native project intentionally owns this layout."))

    checkpoint_text = ""
    checkpoint_path = root / "CHECKPOINT.md"
    if checkpoint_path.exists():
        try:
            checkpoint_text = checkpoint_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            checkpoint_text = ""
    visibility = frontmatter_value(checkpoint_text, "visibility")

    for name, present in existing.items():
        if present:
            findings.extend(inspect_packet_file(root, root / name, visibility))
    if checkpoint_text:
        findings.extend(inspect_state_anchor(root, checkpoint_text))
    findings.extend(inspect_custom_declarations(root))
    findings.extend(inspect_packet_economy(root, existing))
    findings.extend(inspect_duplicate_current_state(root, existing))

    instruction_files = [
        name
        for name in ("AGENTS.md", "AGENTS.override.md")
        if (root / name).exists()
    ]
    scope = "repository" if git(root, "rev-parse", "--is-inside-work-tree").returncode == 0 else "workspace"
    result = "fail" if any(item["severity"] == "error" for item in findings) else "pass"
    return {"result": result, "scope": scope, "posture": posture, "instruction_files": instruction_files, "packet": existing, "findings": findings}


def print_human(report: dict[str, object]) -> None:
    print(f"continuity audit: {report['result']} ({report['posture']})")
    for item in report["findings"]:
        print(f"- {item['severity']}: {item['path']}: {item['message']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only continuity packet auditor.")
    parser.add_argument("--root", required=True, help="Repository, workspace, or product root")
    parser.add_argument("--json", action="store_true", help="Emit compact machine-readable output")
    args = parser.parse_args()

    report = audit(resolve_root(args.root))
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print_human(report)
    return 1 if report["result"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
