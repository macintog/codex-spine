from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import tomllib


HOME = Path.home()
USER = os.environ.get("USER") or HOME.name
REPO_ROOT = Path(__file__).resolve().parents[1]

CONFIG_FRAGMENT_PATHS = [
    REPO_ROOT / "codex/config/00-base.toml",
    REPO_ROOT / "codex/config/30-skills.toml",
]
LOCAL_CONFIG_EXAMPLE = REPO_ROOT / "codex/config/90-local.toml.example"
LOCAL_CONFIG_OVERLAY = REPO_ROOT / "codex/config/90-local.toml"
LOCAL_ENV_EXAMPLE = REPO_ROOT / "shell/codex.local.env.example"
LOCAL_ENV_FILE = REPO_ROOT / "shell/codex.local.env"
COMPONENTS_PATH = REPO_ROOT / "COMPONENTS.toml"
MAINTAINED_COMPONENTS_PATH = REPO_ROOT / "MAINTAINED_COMPONENTS.toml"

LIVE_CONFIG_PATH = HOME / ".codex/config.toml"
LAUNCH_AGENTS_DIR = HOME / "Library/LaunchAgents"
QMD_CHAT_LAUNCH_AGENT_NAME = "codex-spine.qmd-codex-chat.plist"
QMD_CHAT_LAUNCH_AGENT_LABEL = "codex-spine.qmd-codex-chat"
LEGACY_QMD_CHAT_LAUNCH_AGENT_NAMES = [
    "io.codex.spine.qmd-codex-chat.plist",
]
LEGACY_QMD_CHAT_LAUNCH_AGENT_LABELS = [
    "io.codex.spine.qmd-codex-chat",
]
LIVE_QMD_CHAT_LAUNCH_AGENT_PATH = LAUNCH_AGENTS_DIR / QMD_CHAT_LAUNCH_AGENT_NAME
LAUNCH_AGENT_TEMPLATE_PATH = REPO_ROOT / "launchd" / QMD_CHAT_LAUNCH_AGENT_NAME

STATE_DIR = REPO_ROOT / ".state"
COMPONENT_STATE_PATH = STATE_DIR / "components.toml"
LICENSES_DIR = STATE_DIR / "licenses"

BLOCK_START = "# >>> codex-spine managed >>>"
BLOCK_END = "# <<< codex-spine managed <<<"
JCODEMUNCH_MCP_BLOCK_START = "# >>> codex-spine jcodemunch-mcp managed >>>"
JCODEMUNCH_MCP_BLOCK_END = "# <<< codex-spine jcodemunch-mcp managed <<<"

REQUIRED_CLIS = [
    "git",
    "rg",
    "python3",
    "node",
    "pnpm",
    "uv",
    "jq",
]

TEXT_SECRET_PATTERNS = [
    re.compile(r"sk-or-v1-[A-Za-z0-9_-]+"),
    re.compile(r"ghp_[A-Za-z0-9]+"),
]

PRIVATE_REFERENCE_PATTERNS = [
    re.compile(r"/Users/" r"ryand"),
    re.compile(r"\ballthe" r"plex\b"),
    re.compile(r"\bcitadel\.mordor\b"),
    re.compile(r"\bmcp-" r"plex\b"),
    re.compile(r"\bcom\.ryand\b"),
]

REQUIRED_PUBLIC_DOC_PATHS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "LICENSE",
    REPO_ROOT / "ARCHITECTURE.md",
    REPO_ROOT / "SECURITY.md",
    REPO_ROOT / "CHANGELOG.md",
    REPO_ROOT / "codex/AGENTS.md",
]

FORBIDDEN_PUBLIC_ROOT_PATHS = [
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "PROJECT_SPINE.md",
    REPO_ROOT / "CHECKPOINT.md",
    REPO_ROOT / "QA_MATRIX.md",
]

FORBIDDEN_PUBLIC_DOC_PATTERNS = {
    "PROJECT_SPINE.md": re.compile(r"\bPROJECT_SPINE\.md\b"),
    "CHECKPOINT.md": re.compile(r"\bCHECKPOINT\.md\b"),
    "QA_MATRIX.md": re.compile(r"\bQA_MATRIX\.md\b"),
    "codex-env": re.compile(r"\bcodex-env\b"),
    "private Gitea": re.compile(r"\bprivate Gitea\b", re.IGNORECASE),
}

REQUIRED_COMPONENT_FIELDS = {
    "name",
    "summary",
    "boundary_class",
    "release_ready",
    "release_blockers",
    "install_model",
    "maintenance_model",
    "upstream_source",
    "license_mode",
    "license_source",
    "optionality",
    "formal_affiliation",
    "notes",
}

ALLOWED_BOUNDARY_CLASSES = {"public-core"}


@dataclass(frozen=True)
class ManagedLink:
    live_path: Path
    repo_path: Path


def managed_links() -> list[ManagedLink]:
    return [
        ManagedLink(HOME / ".codex/AGENTS.md", REPO_ROOT / "codex/AGENTS.md"),
        ManagedLink(HOME / ".codex/skills/github-contributor", REPO_ROOT / "skills/github-contributor"),
        ManagedLink(HOME / ".codex/skills/project-spine", REPO_ROOT / "skills/project-spine"),
        ManagedLink(HOME / ".local/bin/codex-memory-mcp", REPO_ROOT / "bin/codex-memory-mcp"),
        ManagedLink(HOME / ".local/bin/codex-memory-mcp-launcher", REPO_ROOT / "bin/codex-memory-mcp-launcher"),
        ManagedLink(HOME / ".local/bin/qmd-codex", REPO_ROOT / "bin/qmd-codex"),
        ManagedLink(HOME / ".local/bin/qmd-codex-health.sh", REPO_ROOT / "bin/qmd-codex-health.sh"),
        ManagedLink(HOME / ".local/bin/qmd-memory-latest.sh", REPO_ROOT / "bin/qmd-memory-latest.sh"),
        ManagedLink(HOME / ".local/bin/sync-codex-chat-qmd.sh", REPO_ROOT / "bin/sync-codex-chat-qmd.sh"),
    ]


def shell_source_targets() -> dict[Path, Path]:
    return {
        HOME / ".zprofile": REPO_ROOT / "shell/zprofile.codex.sh",
        HOME / ".zshrc": REPO_ROOT / "shell/zshrc.codex.sh",
        HOME / ".bash_profile": REPO_ROOT / "shell/bash_profile.codex.sh",
    }


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(
    args: list[str],
    *,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        capture_output=capture_output,
        text=text,
        cwd=str(cwd) if cwd else None,
    )


def apply_placeholders(text: str) -> str:
    replacements = {
        "__HOME__": str(HOME),
        "__REPO_ROOT__": str(REPO_ROOT),
        "__LAUNCH_AGENT_LABEL__": QMD_CHAT_LAUNCH_AGENT_LABEL,
    }
    rendered = text
    for needle, replacement in replacements.items():
        rendered = rendered.replace(needle, replacement)
    return rendered


def load_toml_file(path: Path) -> dict:
    if not path.exists():
        return {}
    content = apply_placeholders(path.read_text(encoding="utf-8"))
    if not content.strip():
        return {}
    return tomllib.loads(content)


def validate_components_registry(path: Path = COMPONENTS_PATH) -> list[str]:
    if not path.exists():
        return [f"missing component registry: {path}"]

    try:
        parsed = load_toml_file(path)
    except tomllib.TOMLDecodeError as exc:
        return [f"invalid component registry TOML: {path}: {exc}"]

    components = parsed.get("components")
    if not isinstance(components, dict) or not components:
        return [f"component registry must define at least one [components.<name>] table: {path}"]

    errors: list[str] = []
    for component_key, raw_component in components.items():
        if not isinstance(raw_component, dict):
            errors.append(f"component entry must be a table: components.{component_key}")
            continue

        missing = sorted(REQUIRED_COMPONENT_FIELDS - raw_component.keys())
        if missing:
            errors.append(
                f"component entry is missing required fields: components.{component_key}: {', '.join(missing)}"
            )
            continue

        boundary_class = raw_component.get("boundary_class")
        if boundary_class not in ALLOWED_BOUNDARY_CLASSES:
            errors.append(
                f"component entry has invalid boundary_class: components.{component_key}: {boundary_class!r}"
            )

        if not isinstance(raw_component.get("release_ready"), bool):
            errors.append(
                f"component entry field must be boolean: components.{component_key}.release_ready"
            )
        for field_name in ("release_blockers", "notes"):
            value = raw_component.get(field_name)
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                errors.append(
                    f"component entry field must be a list of strings: components.{component_key}.{field_name}"
                )

    return errors


def deep_merge(base: dict, overlay: dict) -> dict:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, Mapping):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def render_config_data() -> dict:
    merged: dict = {}
    for fragment in CONFIG_FRAGMENT_PATHS:
        merged = deep_merge(merged, load_toml_file(fragment))
    if LOCAL_CONFIG_OVERLAY.exists():
        merged = deep_merge(merged, load_toml_file(LOCAL_CONFIG_OVERLAY))
    return merged


def format_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return json.dumps(key)


def format_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            raise TypeError("array-of-tables should be emitted separately")
        return "[" + ", ".join(format_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value: {type(value)!r}")


def serialize_toml(data: dict) -> str:
    lines: list[str] = []

    def dotted(path: list[str]) -> str:
        return ".".join(format_key(part) for part in path)

    def emit_body(path: list[str], table: dict) -> None:
        scalars: list[tuple[str, object]] = []
        children: list[tuple[str, dict]] = []
        arrays: list[tuple[str, list[dict]]] = []

        for key, value in table.items():
            if isinstance(value, dict):
                children.append((key, value))
            elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                arrays.append((key, value))
            else:
                scalars.append((key, value))

        if path:
            lines.append(f"[{dotted(path)}]")
        for key, value in scalars:
            lines.append(f"{format_key(key)} = {format_value(value)}")
        if scalars and (children or arrays):
            lines.append("")
        for index, (key, child) in enumerate(children):
            emit_body([*path, key], child)
            if index != len(children) - 1 or arrays:
                lines.append("")
        for array_index, (key, items) in enumerate(arrays):
            for item_index, item in enumerate(items):
                lines.append(f"[[{dotted([*path, key])}]]")
                for item_key, item_value in item.items():
                    if isinstance(item_value, (dict, list)):
                        raise TypeError("nested complex array-of-tables values are unsupported")
                    lines.append(f"{format_key(item_key)} = {format_value(item_value)}")
                if item_index != len(items) - 1:
                    lines.append("")
            if array_index != len(arrays) - 1:
                lines.append("")

    emit_body([], data)
    return "\n".join(lines).rstrip() + "\n"


def render_config_text() -> str:
    rendered = serialize_toml(render_config_data())
    return "# Generated by codex-spine. Do not edit by hand.\n\n" + rendered


def render_launch_agent_text() -> str:
    template = LAUNCH_AGENT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return apply_placeholders(template)


def write_text(path: Path, content: str, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def ensure_example_copy(example_path: Path, live_path: Path) -> bool:
    if live_path.exists():
        return False
    write_text(live_path, example_path.read_text(encoding="utf-8"), mode=0o644)
    return True


def backup_existing(path: Path) -> Path:
    backup_path = path.with_name(f"{path.name}.bak.{now_stamp()}")
    shutil.copy2(path, backup_path)
    return backup_path


def ensure_symlink(live_path: Path, repo_path: Path) -> tuple[bool, Path | None]:
    live_path.parent.mkdir(parents=True, exist_ok=True)
    if live_path.is_symlink() and live_path.resolve(strict=False) == repo_path.resolve():
        return False, None
    previous = None
    if live_path.exists() or live_path.is_symlink():
        previous = backup_existing(live_path)
        if live_path.is_dir() and not live_path.is_symlink():
            raise RuntimeError(f"refusing to replace directory with symlink: {live_path}")
        live_path.unlink()
    live_path.symlink_to(repo_path)
    return True, previous


def source_block(fragment_path: Path) -> str:
    quoted = shlex.quote(str(fragment_path))
    return "\n".join(
        [
            BLOCK_START,
            f"if [ -f {quoted} ]; then",
            f"  . {quoted}",
            "fi",
            BLOCK_END,
        ]
    )


def upsert_source_block(dotfile_path: Path, fragment_path: Path) -> bool:
    current = dotfile_path.read_text(encoding="utf-8") if dotfile_path.exists() else ""
    replacement = source_block(fragment_path)
    block_re = re.compile(
        rf"{re.escape(BLOCK_START)}.*?{re.escape(BLOCK_END)}",
        re.DOTALL,
    )
    if block_re.search(current):
        updated = block_re.sub(replacement, current)
    else:
        updated = current.rstrip()
        if updated:
            updated += "\n\n"
        updated += replacement + "\n"
    if updated == current:
        return False
    write_text(dotfile_path, updated, mode=0o644)
    return True


def sanitize_zshenv(path: Path) -> bool:
    if not path.exists():
        return False
    current = path.read_text(encoding="utf-8")
    stripped = current.rstrip()
    if stripped == current:
        return False
    write_text(path, stripped + "\n", mode=0o644)
    return True


def replace_managed_block(path: Path, start_marker: str, end_marker: str, body: str) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    replacement = "\n".join([start_marker, body.rstrip(), end_marker])
    block_re = re.compile(
        rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}",
        re.DOTALL,
    )
    if block_re.search(current):
        updated = block_re.sub(replacement, current)
    else:
        updated = current.rstrip()
        if updated:
            updated += "\n\n"
        updated += replacement + "\n"
    if updated == current:
        return False
    write_text(path, updated, mode=0o644)
    return True


def load_component_state() -> dict:
    if not COMPONENT_STATE_PATH.exists():
        return {}
    content = COMPONENT_STATE_PATH.read_text(encoding="utf-8")
    if not content.strip():
        return {}
    return tomllib.loads(content)


def write_component_state(data: dict) -> None:
    write_text(COMPONENT_STATE_PATH, serialize_toml(data), mode=0o600)


def enabled_component_names() -> set[str]:
    enabled = load_component_state().get("enabled", {})
    if not isinstance(enabled, dict):
        return set()
    return {name for name, value in enabled.items() if isinstance(value, dict)}


def enabled_component_record(name: str) -> dict:
    enabled = load_component_state().get("enabled", {})
    if not isinstance(enabled, dict):
        return {}
    record = enabled.get(name)
    return record if isinstance(record, dict) else {}


def relative_to_repo(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def text_file_paths(root: Path) -> list[Path]:
    exts = {
        ".md",
        ".py",
        ".sh",
        ".toml",
        ".plist",
        ".txt",
        ".rules",
    }
    results: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts or ".state" in path.parts or "__pycache__" in path.parts:
            continue
        if path.suffix in exts or path.name in {"Makefile"}:
            results.append(path)
    return sorted(results)


def public_doc_paths() -> list[Path]:
    return list(REQUIRED_PUBLIC_DOC_PATHS)


def validate_public_doc_surface() -> list[str]:
    errors: list[str] = []

    for path in REQUIRED_PUBLIC_DOC_PATHS:
        if not path.exists():
            errors.append(f"missing required public doc surface: {relative_to_repo(path)}")

    for path in FORBIDDEN_PUBLIC_ROOT_PATHS:
        if path.exists():
            errors.append(f"internal control doc should not ship in the public repo: {relative_to_repo(path)}")

    for path in public_doc_paths():
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN_PUBLIC_DOC_PATTERNS.items():
            if pattern.search(text):
                errors.append(
                    f"public doc still references internal-only repo surface: {relative_to_repo(path)}: {label}"
                )

    return errors


def detect_secret_hits(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in TEXT_SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def detect_private_reference_hits(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in PRIVATE_REFERENCE_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def cli_available(name: str) -> bool:
    return subprocess.run(
        ["/usr/bin/env", "bash", "-lc", f"command -v {shlex.quote(name)} >/dev/null"],
        check=False,
    ).returncode == 0
