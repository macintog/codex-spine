from __future__ import annotations

import json
import os
import pwd
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
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

BrewFormula = tuple[str, str]
REQUIRED_BREW_FORMULAS: list[BrewFormula] = [
    ("git", "git"),
    ("rg", "ripgrep"),
    ("python3", "python"),
    ("node", "node"),
    ("pnpm", "pnpm"),
    ("uv", "uv"),
    ("jq", "jq"),
]

PREFERRED_RUNTIME_PATHS = [
    str(HOME / ".local/bin"),
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    str(HOME / "Library/pnpm"),
    "/usr/local/bin",
    "/usr/local/sbin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
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

PUBLIC_SURFACE_REFERENCE_PATTERNS = [
    *PRIVATE_REFERENCE_PATTERNS,
    re.compile(r"\bplay" r"ground\b"),
    re.compile(r"\bcodex-" r"env\b"),
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
    "codex-" "env": re.compile(r"\bcodex-env\b"),
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


@dataclass(frozen=True)
class ShellIntegrationPlan:
    detected_path: str
    shell_name: str
    supported: bool
    warning: str | None


def managed_links() -> list[ManagedLink]:
    return [
        ManagedLink(HOME / ".codex/AGENTS.md", REPO_ROOT / "codex/AGENTS.md"),
        ManagedLink(HOME / ".codex/skills/github-contributor", REPO_ROOT / "skills/github-contributor"),
        ManagedLink(HOME / ".codex/skills/project-spine", REPO_ROOT / "skills/project-spine"),
        ManagedLink(HOME / ".local/bin/codex-memory-mcp", REPO_ROOT / "bin/codex-memory-mcp"),
        ManagedLink(HOME / ".local/bin/codex-memory-mcp-launcher", REPO_ROOT / "bin/codex-memory-mcp-launcher"),
        ManagedLink(HOME / "Library/pnpm/node", REPO_ROOT / "bin/pnpm-node"),
        ManagedLink(HOME / ".local/bin/qmd-codex", REPO_ROOT / "bin/qmd-codex"),
        ManagedLink(HOME / ".local/bin/qmd-codex-health.sh", REPO_ROOT / "bin/qmd-codex-health.sh"),
        ManagedLink(HOME / ".local/bin/qmd-memory-latest.sh", REPO_ROOT / "bin/qmd-memory-latest.sh"),
        ManagedLink(HOME / ".local/bin/sync-codex-chat-qmd.sh", REPO_ROOT / "bin/sync-codex-chat-qmd.sh"),
    ]


def zsh_source_targets() -> dict[Path, Path]:
    return {
        HOME / ".zprofile": REPO_ROOT / "shell/zprofile.codex.sh",
        HOME / ".zshrc": REPO_ROOT / "shell/zshrc.codex.sh",
    }


def shell_source_targets(plan: ShellIntegrationPlan | None = None) -> dict[Path, Path]:
    active_plan = plan or detect_shell_integration_plan()
    if not active_plan.supported:
        return {}
    return zsh_source_targets()


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def first_nonempty_line(*chunks: str) -> str:
    for chunk in chunks:
        for line in chunk.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
    return ""


def preferred_runtime_path() -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for part in [*PREFERRED_RUNTIME_PATHS, *(os.environ.get("PATH", "").split(":"))]:
        if not part or part in seen:
            continue
        parts.append(part)
        seen.add(part)
    return ":".join(parts)


def runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = preferred_runtime_path()
    return env


def run(
    args: list[str],
    *,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        capture_output=capture_output,
        text=text,
        cwd=str(cwd) if cwd else None,
        env=env,
    )


def prompt_yes_no(prompt: str, *, default: bool, non_interactive: bool) -> bool:
    if non_interactive or not sys.stdin.isatty():
        return default

    suffix = "[Y/n]" if default else "[y/N]"
    reply = input(f"{prompt} {suffix} ").strip().lower()
    if not reply:
        return default
    return reply in {"y", "yes"}


def homebrew_bin_path() -> Path | None:
    brew_path = shutil.which("brew", path=preferred_runtime_path())
    if brew_path:
        return Path(brew_path)
    for candidate in (Path("/opt/homebrew/bin/brew"), Path("/usr/local/bin/brew")):
        if candidate.exists():
            return candidate
    return None


def looks_like_clt_issue(text: str) -> bool:
    lowered = text.lower()
    needles = [
        "xcode-select: note: no developer tools were found",
        "command line tools",
        "xcrun: error",
        "active developer path",
    ]
    return any(needle in lowered for needle in needles)


def developer_tools_ready() -> bool:
    probes = [
        ["/usr/bin/xcode-select", "-p"],
        ["/usr/bin/xcrun", "--find", "git"],
    ]
    for args in probes:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
    return True


def ensure_homebrew(*, non_interactive: bool) -> Path:
    brew_path = homebrew_bin_path()
    if brew_path is not None:
        return brew_path

    installer_url = "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
    if not prompt_yes_no(
        "Homebrew is required for codex-spine. Install Homebrew now?",
        default=False,
        non_interactive=non_interactive,
    ):
        raise RuntimeError(
            "Homebrew is required. Install it from https://brew.sh and rerun `make bootstrap`."
        )

    with tempfile.NamedTemporaryFile(prefix="codex-spine-homebrew-", suffix=".sh", delete=False) as handle:
        installer_path = Path(handle.name)
    try:
        print(f"$ {shlex.join(['curl', '-fL', installer_url, '-o', str(installer_path)])}")
        download = subprocess.run(
            ["curl", "-fL", installer_url, "-o", str(installer_path)],
            check=False,
        )
        if download.returncode != 0:
            raise RuntimeError("Homebrew installer download failed. See output above for details.")

        print(f"$ {shlex.join(['/bin/bash', str(installer_path)])}")
        result = subprocess.run(
            ["/bin/bash", str(installer_path)],
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Homebrew installation failed. See output above for details.")
    finally:
        installer_path.unlink(missing_ok=True)

    brew_path = homebrew_bin_path()
    if brew_path is None:
        raise RuntimeError(
            "Homebrew install completed, but `brew` is still not available. Open a new shell or run the Homebrew shellenv snippet, then rerun `make bootstrap`."
        )
    return brew_path


def install_missing_brew_formulas(
    brew_path: Path,
    *,
    non_interactive: bool,
) -> list[str]:
    missing: list[str] = []
    for _cli_name, formula in REQUIRED_BREW_FORMULAS:
        result = run([str(brew_path), "list", "--versions", formula], check=False, env=runtime_env())
        if result.returncode != 0:
            missing.append(formula)

    if not missing:
        return []

    pretty = ", ".join(missing)
    if not prompt_yes_no(
        f"Install missing Homebrew packages now? {pretty}",
        default=True,
        non_interactive=non_interactive,
    ):
        raise RuntimeError(
            f"Missing required Homebrew packages: {pretty}. Install them and rerun `make bootstrap`."
        )

    print(f"$ {shlex.join([str(brew_path), 'install', *missing])}")
    result = subprocess.run(
        [str(brew_path), "install", *missing],
        check=False,
        env=runtime_env(),
    )
    if result.returncode != 0:
        if not developer_tools_ready():
            raise RuntimeError(
                "Homebrew dependency install failed because Apple Command Line Tools are missing or still installing. Complete the CLT install, open a new shell if needed, and rerun `make bootstrap`."
            )
        raise RuntimeError("Homebrew dependency install failed. See output above for details.")
    return missing


def detect_shell_integration_plan() -> ShellIntegrationPlan:
    detected_path = (os.environ.get("SHELL") or "").strip()
    if not detected_path:
        try:
            detected_path = pwd.getpwuid(os.getuid()).pw_shell or ""
        except KeyError:
            detected_path = ""

    shell_name = Path(detected_path).name if detected_path else ""
    if shell_name == "zsh":
        return ShellIntegrationPlan(
            detected_path=detected_path,
            shell_name=shell_name,
            supported=True,
            warning=None,
        )

    if shell_name:
        warning = (
            f"Detected login shell `{shell_name}`. codex-spine shell integration is only tested for zsh, so managed shell changes will be skipped. Add `$HOME/.local/bin` and source the repo shell fragments manually if you want shell integration."
        )
    else:
        warning = (
            "Could not determine the login shell. codex-spine shell integration is only tested for zsh, so managed shell changes will be skipped. Add `$HOME/.local/bin` and source the repo shell fragments manually if you want shell integration."
        )

    return ShellIntegrationPlan(
        detected_path=detected_path,
        shell_name=shell_name or "unknown",
        supported=False,
        warning=warning,
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


def _looks_like_prior_codex_spine_target(target: Path, repo_path: Path) -> bool:
    return target.name == repo_path.name and "codex-spine" in target.parts


def ensure_symlink(live_path: Path, repo_path: Path) -> tuple[bool, Path | None]:
    live_path.parent.mkdir(parents=True, exist_ok=True)
    if live_path.is_symlink() and live_path.resolve(strict=False) == repo_path.resolve():
        return False, None
    if live_path.exists() or live_path.is_symlink():
        if live_path.is_dir() and not live_path.is_symlink():
            raise RuntimeError(f"refusing to replace directory with symlink: {live_path}")
        if not live_path.is_symlink():
            raise RuntimeError(
                f"refusing to replace unmanaged path with symlink: {live_path}. Move it aside and rerun bootstrap."
            )
        current_target = live_path.resolve(strict=False)
        if not _looks_like_prior_codex_spine_target(current_target, repo_path):
            raise RuntimeError(
                f"refusing to replace unmanaged symlink: {live_path} -> {current_target}. Move it aside and rerun bootstrap."
            )
        live_path.unlink()
    live_path.symlink_to(repo_path)
    return True, None


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


def write_generated_config(path: Path, rendered: str) -> bool:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == rendered:
            return False
        if "Generated by codex-spine" not in current:
            raise RuntimeError(
                f"refusing to overwrite unmanaged config: {path}. Move it aside or merge it into codex/config/90-local.toml, then rerun the managed command."
            )
    write_text(path, rendered, mode=0o600)
    return True


def write_managed_launch_agent(path: Path, rendered: str) -> bool:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == rendered:
            return False
        if QMD_CHAT_LAUNCH_AGENT_LABEL not in current:
            raise RuntimeError(
                f"refusing to overwrite unmanaged LaunchAgent: {path}. Move it aside and rerun bootstrap."
            )
    write_text(path, rendered, mode=0o644)
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


def detect_private_reference_hits(text: str, *, public_surface: bool = False) -> list[str]:
    hits: list[str] = []
    patterns = PUBLIC_SURFACE_REFERENCE_PATTERNS if public_surface else PRIVATE_REFERENCE_PATTERNS
    for pattern in patterns:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def cli_available(name: str) -> bool:
    return shutil.which(name, path=preferred_runtime_path()) is not None
