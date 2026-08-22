#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import os
from pathlib import Path
from urllib.parse import unquote

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ supplies tomllib
    tomllib = None


PACKET_FILES = ("AGENTS.md", "PROJECT_CONTINUITY.md", "CHECKPOINT.md")
RESERVED_CONTINUATION_NAMES = {"checkpoint.md", "queue.md", "next_prompt.md", "rubric.md"}
RESERVED_CONTINUATION_STEMS = {"checkpoint", "queue", "next_prompt", "next-prompt", "rubric"}
CONTINUATION_TEXT_SUFFIXES = {"", ".md", ".markdown", ".txt", ".toml", ".yaml", ".yml", ".json"}
SKIP_TREE_PARTS = {
    ".codex-artifacts",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "node_modules",
    "vendor",
}
SKILL_RESOURCE_PARTS = {"assets", "templates", "references"}
HISTORICAL_PATH_PARTS = {"archive", "archives", "archived", "history", "historical"}
CURRENT_CONTROL_HEADING = re.compile(r"^(?:(?:current|active)\s+(?:state|status|focus|task|queue|pass|work)|status)\b", re.IGNORECASE)
NEXT_CONTROL_HEADING = re.compile(r"^(?:next\s+(?:safe\s+)?(?:step|action|task|pass|prompt)|queue|work\s+order|reopen)\b", re.IGNORECASE)
DIRECTIVE_CONTROL_TEXT = re.compile(r"\b(?:resume|queue|execute|start|launch|run|next\s+thread|fresh\s+thread)\b", re.IGNORECASE)
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


def external_checkpoint_registration(root: Path) -> Path | None:
    result = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if result.returncode != 0:
        return None
    candidate = Path(result.stdout.strip()).resolve() / "codex-project-checkpoint" / "registration.json"
    return candidate if candidate.exists() else None


def resolve_external_checkpoint(root: Path) -> tuple[dict[str, object] | None, str]:
    cli = os.environ.get("CODEX_PROJECT_CHECKPOINT_BIN")
    candidates = [Path(cli).expanduser()] if cli else []
    candidates.extend([Path.home() / ".local/bin/codex-project-checkpoint", Path(__file__).resolve().parents[3] / "bin/codex-project-checkpoint"])
    executable = next((candidate for candidate in candidates if candidate.is_file()), None)
    if executable is None:
        return None, "resolver_unavailable"
    result = subprocess.run(
        [sys.executable, "-B", str(executable), "doctor", "--repo", str(root), "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    raw = result.stdout if result.returncode == 0 else result.stderr
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, "resolver_output_invalid"
    if result.returncode != 0:
        return payload if isinstance(payload, dict) else None, str(payload.get("reason", "resolver_failed")) if isinstance(payload, dict) else "resolver_failed"
    return payload if isinstance(payload, dict) else None, ""


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
    headings = {
        match.group(1).strip()
        for match in re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE)
    }
    for match in re.finditer(r"^\s*[\"']?([A-Za-z][A-Za-z0-9 _-]{1,80})[\"']?\s*[:=]", text, flags=re.MULTILINE):
        headings.add(match.group(1).replace("_", " ").replace("-", " ").strip())
    return headings


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


def is_skipped_tree_path(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    if any(part in SKIP_TREE_PARTS for part in parts):
        return True
    for index, part in enumerate(parts):
        if part == "skills" and any(resource in SKILL_RESOURCE_PARTS for resource in parts[index + 1 :]):
            return True
    return False


def leading_metadata_text(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            return text[4:end]
    lines: list[str] = []
    body_started = False
    for line in text[:4000].splitlines():
        stripped = line.strip()
        if not stripped:
            if body_started and lines:
                break
            continue
        if stripped.startswith("#") and not re.match(r"^#\s*(?:status|authority)\s*[:=]", stripped, re.IGNORECASE):
            if body_started and lines:
                break
            continue
        body_started = True
        if len(lines) >= 20:
            break
        lines.append(stripped.lstrip("#> -\t"))
    return "\n".join(lines)


def has_historical_declaration(text: str) -> bool:
    metadata = leading_metadata_text(text)
    status = re.search(r"(?:^|[.;]\s*)status\s*[:=]\s*[\"']?([^\n.;\"']+)", metadata, re.MULTILINE | re.IGNORECASE)
    authority = re.search(r"(?:^|[.;]\s*)authority\s*[:=]\s*[\"']?([^\n.;\"']+)", metadata, re.MULTILINE | re.IGNORECASE)
    if not status or not authority:
        return False
    status_value = status.group(1).strip().lower().replace("_", "-")
    authority_value = authority.group(1).strip().lower().replace("_", "-")
    historical_statuses = {"historical", "historical-only", "archived", "retired", "superseded"}
    no_authorities = {"none", "non-authoritative", "historical-only", "retired"}
    return status_value in historical_statuses and authority_value in no_authorities


def is_explicitly_historical(text: str, path: Path, root: Path) -> bool:
    relative_parts = tuple(part.lower() for part in path.relative_to(root).parts)
    if any(part in HISTORICAL_PATH_PARTS for part in relative_parts[:-1]):
        return True
    if has_historical_declaration(text):
        return True
    for parent in path.parents:
        if parent == root:
            break
        checkpoint_path = parent / "CHECKPOINT.md"
        if not checkpoint_path.is_file():
            continue
        try:
            checkpoint_text = checkpoint_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if has_historical_declaration(checkpoint_text):
            return True
    return False


def continuation_text_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in CONTINUATION_TEXT_SUFFIXES
        and not is_skipped_tree_path(path, root)
        and (is_reserved_continuation_path(path) or not bool(path.stat().st_mode & 0o111))
    )


def is_reserved_continuation_path(path: Path) -> bool:
    return path.name.lower() in RESERVED_CONTINUATION_NAMES or path.stem.lower() in RESERVED_CONTINUATION_STEMS


def complete_nested_packet(path: Path, root: Path) -> bool:
    parent = path.parent
    return parent != root and all((parent / name).is_file() for name in PACKET_FILES)


def registered_adjacent_packet(path: Path, root: Path, root_authority_text: str) -> bool:
    parent = path.parent
    if parent == root or not (parent / "PROJECT_CONTINUITY.md").is_file() or not (parent / "CHECKPOINT.md").is_file():
        return False
    project_relative = (parent / "PROJECT_CONTINUITY.md").relative_to(root).as_posix()
    checkpoint_relative = (parent / "CHECKPOINT.md").relative_to(root).as_posix()
    return project_relative in root_authority_text and checkpoint_relative in root_authority_text


def inspect_continuation_topology(root: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        root_authority_text = (root / "PROJECT_CONTINUITY.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        root_authority_text = ""

    nested_scope_roots: set[Path] = set()
    text_paths = continuation_text_paths(root)
    for path in text_paths:
        if path == root / "CHECKPOINT.md":
            continue
        if not is_reserved_continuation_path(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        if is_explicitly_historical(text, path, root):
            continue
        if path.name.lower() == "checkpoint.md" and complete_nested_packet(path, root):
            nested_scope_roots.add(path.parent)
            continue
        if path.name.lower() == "checkpoint.md" and registered_adjacent_packet(path, root, root_authority_text):
            nested_scope_roots.add(path.parent)
            continue
        relative = path.relative_to(root).as_posix()
        findings.append(finding("recursive-continuation-control", "error", relative, "Reserved continuation file is outside the one root handoff, a complete separately adopted nested project, or an explicitly historical non-authoritative scope."))

    for path in text_paths:
        if path == root / "CHECKPOINT.md" or is_reserved_continuation_path(path):
            continue
        if any(scope == path.parent or scope in path.parents for scope in nested_scope_roots):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if is_explicitly_historical(text, path, root):
            continue
        headings = heading_names(text)
        has_current = any(CURRENT_CONTROL_HEADING.search(name) for name in headings)
        has_next = any(NEXT_CONTROL_HEADING.search(name) for name in headings)
        if has_current and has_next and DIRECTIVE_CONTROL_TEXT.search(text):
            relative = path.relative_to(root).as_posix()
            findings.append(finding("renamed-continuation-control", "error", relative, "Text resource claims both current-state and successor-action authority outside the root handoff; preserve it as non-directive evidence or a separately adopted project instead."))
    return findings


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
    state_anchor = frontmatter_value(checkpoint_text, "state_anchor")
    subject_field = checkpoint_field(checkpoint_text, "Worktree / branch / ref")
    last_verified = checkpoint_field(checkpoint_text, "Last verified")
    anchor = " ".join(value for value in (state_anchor, subject_field, last_verified) if value)
    working_state = (
        frontmatter_value(checkpoint_text, "working_state")
        or checkpoint_field(checkpoint_text, "Working state")
    ).lower()
    head_result = git(root, "rev-parse", "HEAD")
    if head_result.returncode != 0:
        return findings

    if not anchor:
        findings.append(finding("missing-state-anchor", "stale", "CHECKPOINT.md", "Checkpoint has no stable repository, ref, build, dataset, deployed-version, or artifact identity to reconcile."))
        return findings

    head = head_result.stdout.strip()

    def resolve_commit(candidate: str) -> str:
        result = git(root, "rev-parse", "--verify", f"{candidate}^{{commit}}")
        return result.stdout.strip() if result.returncode == 0 else ""

    def is_ancestor(candidate: str) -> bool:
        return git(root, "merge-base", "--is-ancestor", candidate, head).returncode == 0

    subject_identity_found = False
    absolute_paths = re.findall(r"(?<![\w.-])(/[A-Za-z0-9_./-]+)", subject_field)
    for raw_path in absolute_paths:
        candidate_path = Path(raw_path).expanduser().resolve()
        if candidate_path.exists() and candidate_path.is_dir():
            subject_identity_found = True
            if candidate_path != root:
                findings.append(finding("worktree-anchor-mismatch", "stale", "CHECKPOINT.md", f"Checkpoint names worktree {candidate_path}, but the audited root is {root}."))

    ref_text = " ".join((state_anchor, subject_field))
    ref_candidates = set(re.findall(r"\brefs/(?:heads|remotes)/[A-Za-z0-9._/-]+\b", ref_text))
    ref_candidates.update(re.findall(r"\b(?:origin|upstream)/[A-Za-z0-9._/-]+\b", ref_text))
    for token in re.findall(r"[A-Za-z0-9._/-]+", ref_text):
        if "/" in token or token in {"main", "master"}:
            if resolve_commit(token):
                ref_candidates.add(token)

    current_branch_result = git(root, "branch", "--show-current")
    current_branch = current_branch_result.stdout.strip() if current_branch_result.returncode == 0 else ""
    allowed_refs = {current_branch, f"refs/heads/{current_branch}"} if current_branch else set()
    for authority_name in ("main", "master"):
        if resolve_commit(f"refs/heads/{authority_name}"):
            allowed_refs.update({authority_name, f"refs/heads/{authority_name}"})
        if resolve_commit(f"refs/remotes/origin/{authority_name}"):
            allowed_refs.update({f"origin/{authority_name}", f"refs/remotes/origin/{authority_name}"})

    for ref in sorted(ref_candidates):
        commit = resolve_commit(ref)
        if not commit:
            findings.append(finding("unresolved-ref-anchor", "stale", "CHECKPOINT.md", f"Checkpoint ref does not resolve in the audited repository: {ref}"))
            continue
        subject_identity_found = True
        if ref not in allowed_refs:
            findings.append(finding("noncurrent-ref-anchor", "stale", "CHECKPOINT.md", f"Checkpoint names non-current, non-authoritative ref {ref}; it cannot select this task."))
        if not is_ancestor(commit):
            findings.append(finding("ref-anchor-mismatch", "stale", "CHECKPOINT.md", f"Checkpoint ref {ref} at {commit} is not an ancestor of current HEAD {head}."))

    sha_candidates = set(re.findall(r"\b[0-9a-fA-F]{7,40}\b", " ".join((state_anchor, last_verified))))
    for sha in sorted(sha_candidates):
        commit = resolve_commit(sha)
        if not commit:
            if len(sha) == 40:
                findings.append(finding("unresolved-state-anchor", "stale", "CHECKPOINT.md", f"Checkpoint commit identity does not resolve in the audited repository: {sha}"))
            continue
        subject_identity_found = True
        if not is_ancestor(commit):
            findings.append(finding("state-anchor-mismatch", "stale", "CHECKPOINT.md", f"Checkpoint commit {commit} is not an ancestor of current HEAD {head}; reconcile it before resuming."))

    if not subject_identity_found:
        findings.append(finding("missing-state-anchor", "stale", "CHECKPOINT.md", "Checkpoint does not contain a resolvable worktree, authoritative ref, or commit identity."))

    if working_state == "clean":
        status = git(root, "status", "--porcelain=v1")
        if status.returncode == 0 and status.stdout:
            findings.append(finding("working-state-mismatch", "stale", "CHECKPOINT.md", "Checkpoint claims a clean working state but the current Git worktree is dirty."))
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
    external_registration = external_checkpoint_registration(root)
    checkpoint_resolution: dict[str, object] | None = None
    external_adopted = external_registration is not None
    if external_adopted:
        checkpoint_resolution, resolver_error = resolve_external_checkpoint(root)
        if checkpoint_resolution is None or checkpoint_resolution.get("ok") is not True:
            state = str((checkpoint_resolution or {}).get("state", "unreadable"))
            findings.append(finding("external-checkpoint-resolution", "error", "CHECKPOINT.md", f"Adopted external checkpoint cannot resolve: {state}/{resolver_error}. No tracked fallback is allowed."))
        elif checkpoint_resolution.get("state") not in {"current", "empty"}:
            findings.append(finding("external-checkpoint-state", "error", "CHECKPOINT.md", f"Adopted external checkpoint has unexpected state {checkpoint_resolution.get('state')}."))
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
            if name != "CHECKPOINT.md" or not external_adopted:
                findings.extend(inspect_packet_file(root, root / name, visibility))
    if checkpoint_text and not external_adopted:
        findings.extend(inspect_state_anchor(root, checkpoint_text))
    if adopted:
        findings.extend(inspect_continuation_topology(root))
    findings.extend(inspect_custom_declarations(root))
    findings.extend(inspect_packet_economy(root, existing))
    findings.extend(inspect_duplicate_current_state(root, existing))

    instruction_files = [
        name
        for name in ("AGENTS.md", "AGENTS.override.md")
        if (root / name).exists()
    ]
    scope = "repository" if git(root, "rev-parse", "--is-inside-work-tree").returncode == 0 else "workspace"
    if any(item["severity"] == "error" for item in findings):
        result = "fail"
    elif any(item["severity"] == "stale" for item in findings):
        result = "stale"
    else:
        result = "pass"
    report = {"result": result, "scope": scope, "posture": posture, "instruction_files": instruction_files, "packet": existing, "findings": findings}
    if checkpoint_resolution is not None:
        report["checkpoint_resolver"] = checkpoint_resolution
    return report


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
    return 1 if report["result"] in {"fail", "stale"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
