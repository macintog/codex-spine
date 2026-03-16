from __future__ import annotations

import json
import hashlib
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
from toml_compat import tomllib


HOME = Path.home()
USER = os.environ.get("USER") or HOME.name
REPO_ROOT = Path(__file__).resolve().parents[1]

CONFIG_FRAGMENT_PATHS = [
    REPO_ROOT / "codex/config/00-base.toml",
    REPO_ROOT / "codex/config/20-codex-spine-mcps.toml",
]
LOCAL_CONFIG_EXAMPLE = REPO_ROOT / "codex/config/90-local.toml.example"
LOCAL_CONFIG_OVERLAY = REPO_ROOT / "codex/config/90-local.toml"
ADOPTED_CONFIG_OVERLAY = REPO_ROOT / "codex/config/80-adopted.toml"
LOCAL_ENV_EXAMPLE = REPO_ROOT / "shell/codex.local.env.example"
LOCAL_ENV_FILE = REPO_ROOT / "shell/codex.local.env"
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
    re.compile(r"/Users/[A-Za-z0-9._-]+"),
    re.compile(r"(?:https?://|ssh://|git@)[a-z0-9.-]+\.local(?::\d+)?", re.IGNORECASE),
    re.compile(r"\b[a-z0-9.-]+\.local:\d+\b", re.IGNORECASE),
]

PUBLIC_SURFACE_REFERENCE_PATTERNS = [
    *PRIVATE_REFERENCE_PATTERNS,
]

REQUIRED_PUBLIC_DOC_PATHS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "LICENSE",
    REPO_ROOT / "ARCHITECTURE.md",
    REPO_ROOT / "SECURITY.md",
    REPO_ROOT / "CHANGELOG.md",
    REPO_ROOT / "codex/AGENTS.md",
    REPO_ROOT / "codex/TOOLING.md",
]

FORBIDDEN_PUBLIC_ROOT_PATHS = [
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "PROJECT_CONTINUITY.md",
    REPO_ROOT / "PROJECT_SPINE.md",
    REPO_ROOT / "CHECKPOINT.md",
    REPO_ROOT / "QA_RUNBOOK.md",
    REPO_ROOT / "QA_MATRIX.md",
]

FORBIDDEN_PUBLIC_DOC_PATTERNS = {
    "PROJECT_SPINE.md": re.compile(r"\bPROJECT_SPINE\.md\b"),
    "QA_RUNBOOK.md": re.compile(r"\bQA_RUNBOOK\.md\b"),
    "QA_MATRIX.md": re.compile(r"\bQA_MATRIX\.md\b"),
    "make backup": re.compile(r"\bmake backup\b", re.IGNORECASE),
    "private Gitea": re.compile(r"\bprivate Gitea\b", re.IGNORECASE),
}

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


@dataclass(frozen=True)
class ConfigWritePlan:
    allow_unmanaged_replace: bool
    backup_path: Path | None = None
    adopted_overlay_path: Path | None = None


def managed_links() -> list[ManagedLink]:
    return [
        ManagedLink(HOME / ".codex/AGENTS.md", REPO_ROOT / "codex/AGENTS.md"),
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

    bold_on = "\033[1m" if sys.stdout.isatty() else ""
    bold_off = "\033[0m" if bold_on else ""
    suffix = f"[{bold_on}Y{bold_off}/n]" if default else f"[y/{bold_on}N{bold_off}]"
    reply = input(f"{prompt} {suffix} ").strip().lower()
    if not reply:
        return default
    return reply in {"y", "yes"}


def format_package_plan_prompt(
    packages: Sequence[str],
    *,
    include_homebrew: bool,
) -> str:
    lines: list[str] = [""]
    if include_homebrew:
        lines.append("First we'll install Homebrew.")
        lines.append("Then we'll install these Homebrew packages for codex-spine:")
    else:
        lines.append("We'll install these Homebrew packages for codex-spine:")
    lines.extend(f"  - {package}" for package in packages)
    lines.append("")
    lines.append("Continue?")
    return "\n".join(lines)


def homebrew_bin_path() -> Path | None:
    brew_path = shutil.which("brew", path=preferred_runtime_path())
    if brew_path:
        return Path(brew_path)
    for candidate in (Path("/opt/homebrew/bin/brew"), Path("/usr/local/bin/brew")):
        if candidate.exists():
            return candidate
    return None


def ensure_homebrew(*, non_interactive: bool) -> Path:
    brew_path = homebrew_bin_path()
    if brew_path is not None:
        return brew_path

    installer_url = "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
    if not prompt_yes_no(
        format_package_plan_prompt(
            ["python", "ripgrep", "node", "pnpm", "uv", "jq"],
            include_homebrew=True,
        ),
        default=True,
        non_interactive=non_interactive,
    ):
        raise RuntimeError(
            "codex-spine needs Homebrew plus a small set of Homebrew packages. Install Homebrew from https://brew.sh, then rerun `make install`."
        )

    with tempfile.NamedTemporaryFile(prefix="codex-spine-homebrew-", suffix=".sh", delete=False) as handle:
        installer_path = Path(handle.name)
    try:
        print(f"\n$ {shlex.join(['curl', '-fL', installer_url, '-o', str(installer_path)])}")
        download = subprocess.run(
            ["curl", "-fL", installer_url, "-o", str(installer_path)],
            check=False,
        )
        if download.returncode != 0:
            raise RuntimeError("Homebrew installer download failed. See output above for details.")

        print(f"\n$ {shlex.join(['/bin/bash', str(installer_path)])}")
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
            "Homebrew finished installing, but `brew` is still not available in this shell. Open a new shell or run the Homebrew shellenv snippet, then rerun `make install`."
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
    auto_approved = os.environ.get("CODEX_SPINE_BREW_INSTALL_APPROVED") == "1"
    if not auto_approved and not prompt_yes_no(
        format_package_plan_prompt(missing, include_homebrew=False),
        default=True,
        non_interactive=non_interactive,
    ):
        raise RuntimeError(
            f"Missing required Homebrew packages: {pretty}. Install them and rerun `make install`."
        )

    print(f"\n$ {shlex.join([str(brew_path), 'install', *missing])}")
    result = subprocess.run(
        [str(brew_path), "install", *missing],
        check=False,
        env=runtime_env(),
    )
    if result.returncode != 0:
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
    if ADOPTED_CONFIG_OVERLAY.exists():
        merged = deep_merge(merged, load_toml_file(ADOPTED_CONFIG_OVERLAY))
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


def write_generated_config(path: Path, rendered: str, *, allow_unmanaged_replace: bool = False) -> bool:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == rendered:
            return False
        if "Generated by codex-spine" not in current and not allow_unmanaged_replace:
            raise RuntimeError(
                f"refusing to overwrite unmanaged config: {path}. Rerun interactively so codex-spine can import it into codex/config/80-adopted.toml, or merge the settings you want to keep into codex/config/90-local.toml, then rerun the managed command."
            )
    write_text(path, rendered, mode=0o600)
    return True


def _remove_nested_table(data: dict, path: Sequence[str]) -> None:
    current = data
    parents: list[tuple[dict, str]] = []
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            return
        parents.append((current, key))
        current = child
    if not isinstance(current, dict):
        return
    current.pop(path[-1], None)
    for parent, key in reversed(parents):
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            parent.pop(key, None)
            continue
        break


def _strip_managed_config_tables(data: dict) -> dict:
    stripped = deepcopy(data)
    for path in (
        ("mcp_servers", "memory"),
        ("mcp_servers", "qmd_codex"),
    ):
        _remove_nested_table(stripped, path)
    return stripped


def _serialize_local_overlay_comment(lines: Sequence[str], body: str) -> str:
    comment = "\n".join(f"# {line}" if line else "#" for line in lines).rstrip()
    if not body.strip():
        return comment + "\n"
    return comment + "\n\n" + body


def _adopt_existing_config(path: Path) -> ConfigWritePlan:
    raw = path.read_text(encoding="utf-8")
    try:
        existing_data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(
            f"could not import the existing Codex config at {path}: {exc}. Fix the TOML, or move it aside and rerun `make install`."
        ) from exc

    adopted_data = _strip_managed_config_tables(existing_data)
    if ADOPTED_CONFIG_OVERLAY.exists():
        adopted_data = deep_merge(load_toml_file(ADOPTED_CONFIG_OVERLAY), adopted_data)

    if adopted_data:
        write_text(
            ADOPTED_CONFIG_OVERLAY,
            _serialize_local_overlay_comment(
                [
                    "Imported from the pre-existing ~/.codex/config.toml during codex-spine install.",
                    "This file is local-only and gitignored.",
                    "Review and trim it if you no longer need some of these carried-forward settings.",
                ],
                serialize_toml(adopted_data),
            ),
            mode=0o600,
        )

    backup_path = backup_existing(path)
    return ConfigWritePlan(
        allow_unmanaged_replace=True,
        backup_path=backup_path,
        adopted_overlay_path=ADOPTED_CONFIG_OVERLAY if adopted_data else None,
    )


def prepare_generated_config_target(path: Path, *, non_interactive: bool) -> ConfigWritePlan:
    if not path.exists():
        return ConfigWritePlan(allow_unmanaged_replace=False)
    current = path.read_text(encoding="utf-8")
    if "Generated by codex-spine" in current:
        return ConfigWritePlan(allow_unmanaged_replace=False)
    if os.environ.get("CODEX_SPINE_CONFIG_ADOPTION_APPROVED") == "1":
        return _adopt_existing_config(path)
    if non_interactive or not sys.stdin.isatty():
        raise RuntimeError(
            f"found an existing unmanaged Codex config at {path}. Rerun interactively so codex-spine can import it into codex/config/80-adopted.toml, or merge the settings you want to keep into codex/config/90-local.toml, then rerun `make install`."
        )
    if not prompt_yes_no(
        "\n".join(
            [
                "",
                "Found an existing Codex config:",
                f"  {path}",
                "",
                "codex-spine manages the memory MCP entry itself and removes any deprecated qmd_codex alias during import.",
                "To preserve the rest of your current Codex settings, it will import them into:",
                f"  {ADOPTED_CONFIG_OVERLAY}",
                "",
                "Then it will render a new live config that includes those imported settings.",
                "Continue?",
            ]
        ),
        default=True,
        non_interactive=non_interactive,
    ):
        raise RuntimeError(
            f"leaving the existing Codex config in place: {path}. If you want codex-spine to manage it later, rerun `make install` interactively or merge the settings you want to keep into codex/config/90-local.toml."
        )
    return _adopt_existing_config(path)


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


def load_maintenance_manifest() -> dict:
    content = MAINTAINED_COMPONENTS_PATH.read_text(encoding="utf-8")
    return tomllib.loads(content)


def jcodemunch_mcp_overlay_body() -> str:
    backend = (
        load_maintenance_manifest()
        .get("components", {})
        .get("jcodemunch-mcp", {})
        .get("backends", {})
        .get("codex_spine", {})
    )
    kind = str(backend.get("kind", ""))
    command = str(backend.get("executable", ""))
    package_name = str(backend.get("package_name", "jcodemunch-mcp"))
    version_spec = str(backend.get("version_spec", "")).strip()
    requirement = f"{package_name}{version_spec}"
    tool_name = str(backend.get("tool_name", package_name))
    if kind == "uvx_tool":
        args = ["tool", "run", "--from", requirement, tool_name] if command == "uv" else ["--from", requirement, tool_name]
        return f"""[mcp_servers.jcodemunch]
command = "{command}"
args = {json.dumps(args)}
enabled = true"""

    rendered_command = command.replace("~/", "__HOME__/") if command.startswith("~/") else command
    return f"""[mcp_servers.jcodemunch]
command = "{rendered_command}"
args = []
enabled = true"""


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


def _git_tracked_repo_paths() -> list[Path] | None:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        check=False,
        capture_output=True,
        text=False,
    )
    if result.returncode != 0:
        return None

    paths: list[Path] = []
    for raw_path in result.stdout.decode("utf-8", errors="replace").split("\0"):
        if not raw_path:
            continue
        paths.append(REPO_ROOT / raw_path)
    return paths


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
    tracked_paths = _git_tracked_repo_paths() if root == REPO_ROOT else None
    candidate_paths = tracked_paths if tracked_paths is not None else root.rglob("*")
    for path in candidate_paths:
        if not path.is_file():
            continue
        if ".git" in path.parts or ".state" in path.parts or "__pycache__" in path.parts or ".codex-worktrees" in path.parts:
            continue
        if path.suffix in exts or path.name in {"Makefile"} or path.parent.name in {"bin", "scripts"}:
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
