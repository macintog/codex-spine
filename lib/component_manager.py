from __future__ import annotations

import os
import re
import select
import shutil
import sys
import termios
import time
from dataclasses import dataclass
from pathlib import Path
import subprocess
from toml_compat import tomllib
import tty
import urllib.request

from codex_spine import (
    MAINTAINED_COMPONENTS_PATH,
    REPO_ROOT,
    enabled_component_names,
    now_iso,
    run,
    write_component_state,
    load_component_state,
)


SUPPORTED_BACKENDS = {"pnpm_global", "uv_tool", "uvx_tool"}
HOME = Path.home()
PREFERRED_NODE_PATHS = [
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
VERSION_TOKEN_RE = re.compile(r"\b(\d+(?:\.\d+)+)\b")
VERSION_CLAUSE_RE = re.compile(r"^\s*(<=|>=|==|!=|<|>)\s*([0-9]+(?:\.[0-9]+)*)\s*$")
TERMS_HEADING_RE = re.compile(r"^(?:>\s*)?#{1,6}\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
TERMS_HEADING_HINT_RE = re.compile(
    r"\b(license|licen[cs]e|terms|eula|agreement|commercial|free for personal use)\b",
    re.IGNORECASE,
)


def _expand_path(raw_path: str) -> Path:
    return Path(raw_path).expanduser()


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def _run_live(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        env=env,
    )


def _run_live_with_heartbeat(
    args: list[str],
    *,
    heartbeat_message: str,
    cwd: Path | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
    heartbeat_interval: float = 5.0,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        env=env,
    )
    next_heartbeat = time.monotonic() + heartbeat_interval
    while True:
        try:
            returncode = process.wait(timeout=1)
            break
        except subprocess.TimeoutExpired:
            if time.monotonic() >= next_heartbeat:
                _progress(heartbeat_message)
                next_heartbeat = time.monotonic() + heartbeat_interval

    if check and returncode != 0:
        raise subprocess.CalledProcessError(returncode, args)
    return subprocess.CompletedProcess(args, returncode)


def _progress(message: str) -> None:
    print(message, flush=True)


def _prompt_yes_no(prompt: str, *, default: bool) -> bool:
    bold_on = "\033[1m" if sys.stdout.isatty() else ""
    bold_off = "\033[0m" if bold_on else ""
    suffix = f"[{bold_on}Y{bold_off}/n]" if default else f"[y/{bold_on}N{bold_off}]"
    reply = input(f"{prompt} {suffix} ").strip().lower()
    if not reply:
        return default
    return reply in {"y", "yes"}


def _read_accept_or_escape(prompt: str) -> str:
    if not sys.stdin.isatty():
        return input(prompt)

    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    typed: list[str] = []
    sys.stdout.write(prompt)
    sys.stdout.flush()
    try:
        tty.setraw(fd)
        while True:
            ready, _, _ = select.select([sys.stdin], [], [])
            if not ready:
                continue
            char = sys.stdin.read(1)
            if char == "\x03":
                raise KeyboardInterrupt
            if char == "\x1b":
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "\x1b"
            if char in {"\r", "\n"}:
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "".join(typed)
            if char in {"\x08", "\x7f"}:
                if typed:
                    typed.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            typed.append(char)
            sys.stdout.write(char)
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)


def _prefixed_env(*prefixes: str) -> dict[str, str]:
    env = os.environ.copy()
    seen: set[str] = set()
    parts: list[str] = []
    for part in [*prefixes, *(env.get("PATH", "").split(":"))]:
        if not part or part in seen:
            continue
        parts.append(part)
        seen.add(part)
    env["PATH"] = ":".join(parts)
    return env


def _pnpm_env() -> dict[str, str]:
    env = _prefixed_env(*PREFERRED_NODE_PATHS)
    env["PNPM_HOME"] = str(HOME / "Library/pnpm")
    return env


def _first_nonempty_line(*chunks: str) -> str:
    for chunk in chunks:
        for line in chunk.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
    return ""


def _pnpm_global_workspace() -> Path | None:
    result = _run(["pnpm", "root", "-g"], check=False, env=_pnpm_env())
    if result.returncode != 0:
        return None
    root = Path((result.stdout or "").strip()).expanduser()
    if root.name == "node_modules":
        return root.parent
    return root if str(root) else None


def _command_probe(
    executable: Path,
    args: list[str],
    *,
    env: dict[str, str] | None = None,
) -> dict[str, str | bool]:
    result = _run([str(executable), *args], check=False, env=env)
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    detail = _first_nonempty_line(output, error) or f"exit {result.returncode}"
    return {
        "ok": result.returncode == 0,
        "output": output or error,
        "detail": detail,
    }


def _command_probe_args(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
) -> dict[str, str | bool]:
    result = _run(args, check=False, env=env)
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    detail = _first_nonempty_line(output, error) or f"exit {result.returncode}"
    return {
        "ok": result.returncode == 0,
        "output": output or error,
        "detail": detail,
    }


def _resolve_command(command: str, *, env: dict[str, str] | None = None) -> str | None:
    if "/" in command or command.startswith("~"):
        candidate = _expand_path(command)
        return str(candidate) if candidate.exists() else None
    search_path = None
    if env is not None:
        search_path = env.get("PATH")
    elif os.environ.get("PATH"):
        search_path = os.environ.get("PATH")
    return shutil.which(command, path=search_path)


def _command_available(command: str, *, env: dict[str, str] | None = None) -> bool:
    return _resolve_command(command, env=env) is not None


def _combine_detail(*parts: str) -> str:
    return "; ".join(part for part in parts if part)


def _prepare_pnpm_global_bin() -> None:
    pnpm_home = HOME / "Library/pnpm"
    pnpm_home.mkdir(parents=True, exist_ok=True)
    _run(["pnpm", "config", "set", "global-bin-dir", str(pnpm_home)], check=True, env=_pnpm_env())


def _rebuild_better_sqlite3(*, heartbeat_message: str, run_live_with_heartbeat_fn=None) -> bool:
    run_live_with_heartbeat_fn = run_live_with_heartbeat_fn or _run_live_with_heartbeat
    search_roots: list[Path] = [HOME / "Library/pnpm/global"]
    workspace = _pnpm_global_workspace()
    if workspace is not None and workspace not in search_roots:
        search_roots.append(workspace)

    rebuilt = False
    seen: set[Path] = set()
    for root in search_roots:
        if not root.exists():
            continue
        for candidate in root.glob("**/.pnpm/better-sqlite3@*/node_modules/better-sqlite3"):
            if candidate in seen:
                continue
            run_live_with_heartbeat_fn(
                ["pnpm", "rebuild"],
                cwd=candidate,
                check=True,
                env=_pnpm_env(),
                heartbeat_message=heartbeat_message,
            )
            rebuilt = True
            seen.add(candidate)
    return rebuilt


@dataclass(frozen=True)
class ResolvedComponent:
    name: str
    summary: str
    default_enabled: bool
    backend_name: str
    backend: dict

    @property
    def executable_path(self) -> Path:
        return _expand_path(str(self.backend["executable"]))

    @property
    def executable_command(self) -> str:
        return str(self.backend["executable"])


def load_maintenance_manifest(path: Path = MAINTAINED_COMPONENTS_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return tomllib.loads(path.read_text(encoding="utf-8"))


def validate_maintenance_manifest(path: Path = MAINTAINED_COMPONENTS_PATH) -> list[str]:
    if not path.exists():
        return [f"missing maintenance manifest: {path}"]

    try:
        data = load_maintenance_manifest(path)
    except tomllib.TOMLDecodeError as exc:
        return [f"invalid maintenance manifest TOML: {path}: {exc}"]

    errors: list[str] = []
    profiles = data.get("profiles")
    components = data.get("components")
    if not isinstance(profiles, dict) or not profiles:
        errors.append(f"maintenance manifest must define [profiles.<name>] tables: {path}")
    if not isinstance(components, dict) or not components:
        errors.append(f"maintenance manifest must define [components.<name>] tables: {path}")
        return errors

    for profile_name, profile in profiles.items():
        component_names = profile.get("components")
        if not isinstance(component_names, list) or not all(isinstance(item, str) for item in component_names):
            errors.append(f"profile components must be a list of strings: profiles.{profile_name}.components")
            continue
        for component_name in component_names:
            component = components.get(component_name)
            if not isinstance(component, dict):
                errors.append(f"profile references missing component: profiles.{profile_name}.components -> {component_name}")
                continue
            backends = component.get("backends")
            if not isinstance(backends, dict) or profile_name not in backends:
                errors.append(f"component missing backend for profile: components.{component_name}.backends.{profile_name}")

    for component_name, component in components.items():
        if not isinstance(component, dict):
            errors.append(f"component must be a table: components.{component_name}")
            continue
        if not isinstance(component.get("summary"), str) or not component["summary"].strip():
            errors.append(f"component summary must be a non-empty string: components.{component_name}.summary")
        if not isinstance(component.get("default_enabled"), bool):
            errors.append(f"component default_enabled must be boolean: components.{component_name}.default_enabled")
        backends = component.get("backends")
        if not isinstance(backends, dict) or not backends:
            errors.append(f"component must define backends: components.{component_name}.backends")
            continue
        for backend_name, backend in backends.items():
            if not isinstance(backend, dict):
                errors.append(f"backend must be a table: components.{component_name}.backends.{backend_name}")
                continue
            kind = backend.get("kind")
            if kind not in SUPPORTED_BACKENDS:
                errors.append(
                    f"unsupported backend kind: components.{component_name}.backends.{backend_name}.kind={kind!r}"
                )
                continue
            if not isinstance(backend.get("executable"), str) or not backend["executable"].strip():
                errors.append(f"backend must define executable: components.{component_name}.backends.{backend_name}.executable")
            if not isinstance(backend.get("package_name"), str) or not backend["package_name"].strip():
                errors.append(
                    f"backend must define package_name: components.{component_name}.backends.{backend_name}.package_name"
                )
            version_spec = backend.get("version_spec")
            if not isinstance(version_spec, str) or not version_spec.strip():
                errors.append(
                    f"backend optional field must be a non-empty string: components.{component_name}.backends.{backend_name}.version_spec"
                )
            elif re.search(r"(^|,)\s*==", version_spec):
                errors.append(
                    "backend version_spec must use a compatibility range or ceiling, not an exact pin: "
                    f"components.{component_name}.backends.{backend_name}.version_spec"
                )
            if "pinned_version" in backend:
                errors.append(
                    "backend must not define pinned_version; use version_spec with a compatibility range or ceiling: "
                    f"components.{component_name}.backends.{backend_name}.pinned_version"
                )
            for optional_field in ("version_args", "health_args"):
                optional_value = backend.get(optional_field)
                if optional_value is not None and (
                    not isinstance(optional_value, list)
                    or not all(isinstance(item, str) for item in optional_value)
                ):
                    errors.append(
                        "backend optional field must be a list of strings: "
                        f"components.{component_name}.backends.{backend_name}.{optional_field}"
                    )
            tool_name = backend.get("tool_name")
            if tool_name is not None and (not isinstance(tool_name, str) or not tool_name.strip()):
                errors.append(
                    f"backend optional field must be a non-empty string: components.{component_name}.backends.{backend_name}.tool_name"
                )
            mcp_server_name = backend.get("mcp_server_name")
            if mcp_server_name is not None and (not isinstance(mcp_server_name, str) or not mcp_server_name.strip()):
                errors.append(
                    "backend optional field must be a non-empty string: "
                    f"components.{component_name}.backends.{backend_name}.mcp_server_name"
                )
            requires_acknowledgement = backend.get("requires_acknowledgement")
            if requires_acknowledgement is not None and not isinstance(requires_acknowledgement, bool):
                errors.append(
                    "backend optional field must be boolean: "
                    f"components.{component_name}.backends.{backend_name}.requires_acknowledgement"
                )
            for optional_field in ("acknowledgement_group", "acknowledgement_label"):
                optional_value = backend.get(optional_field)
                if optional_value is not None and (not isinstance(optional_value, str) or not optional_value.strip()):
                    errors.append(
                        "backend optional field must be a non-empty string: "
                        f"components.{component_name}.backends.{backend_name}.{optional_field}"
                    )
            env_map = backend.get("env")
            if env_map is not None and (
                not isinstance(env_map, dict)
                or not all(isinstance(key, str) and isinstance(value, str) for key, value in env_map.items())
            ):
                errors.append(
                    "backend optional field must be a table of string values: "
                    f"components.{component_name}.backends.{backend_name}.env"
                )
            for legacy_field in ("license_source_url", "license_start_marker", "license_end_marker"):
                if legacy_field in backend:
                    errors.append(
                        "backend must not use legacy licence-bundle fields; use terms_* fields instead: "
                        f"components.{component_name}.backends.{backend_name}.{legacy_field}"
                    )
            start_marker = backend.get("terms_start_marker")
            if start_marker is not None and (not isinstance(start_marker, str) or not start_marker.strip()):
                errors.append(
                    "backend optional field must be a non-empty string: "
                    f"components.{component_name}.backends.{backend_name}.terms_start_marker"
                )
            for field_name in ("terms_start_markers", "terms_end_markers"):
                markers = backend.get(field_name)
                if markers is None:
                    continue
                if (
                    not isinstance(markers, list)
                    or not markers
                    or any(not isinstance(marker, str) or not marker.strip() for marker in markers)
                ):
                    errors.append(
                        "backend optional field must be a non-empty list of non-empty strings: "
                        f"components.{component_name}.backends.{backend_name}.{field_name}"
                    )
            if backend.get("terms_source_url") and not (
                backend.get("terms_start_marker") or backend.get("terms_start_markers")
            ):
                errors.append(
                    "terms-bearing backend must define terms_start_marker or terms_start_markers: "
                    f"components.{component_name}.backends.{backend_name}.terms_start_marker"
                )

    return errors


def resolve_components(profile_name: str = "codex_spine", path: Path = MAINTAINED_COMPONENTS_PATH) -> list[ResolvedComponent]:
    data = load_maintenance_manifest(path)
    profile = data["profiles"][profile_name]
    resolved: list[ResolvedComponent] = []
    for component_name in profile["components"]:
        component = data["components"][component_name]
        backend = component["backends"][profile_name]
        resolved.append(
            ResolvedComponent(
                name=component_name,
                summary=component["summary"],
                default_enabled=component["default_enabled"],
                backend_name=profile_name,
                backend=backend,
            )
        )
    return resolved


def component_acknowledgement_key(component: ResolvedComponent) -> str:
    group = component.backend.get("acknowledgement_group")
    if isinstance(group, str) and group.strip():
        return group.strip()
    return component.name


def component_acknowledgement_label(component: ResolvedComponent) -> str:
    label = component.backend.get("acknowledgement_label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return component.name


def acknowledgement_group_components(
    component: ResolvedComponent,
    resolved_components: list[ResolvedComponent] | None = None,
) -> list[ResolvedComponent]:
    key = component_acknowledgement_key(component)
    if key == component.name:
        return [component]

    resolved = resolved_components or resolve_components(profile_name=component.backend_name)
    group_members = [candidate for candidate in resolved if component_acknowledgement_key(candidate) == key]
    return group_members or [component]


def backend_version_spec(backend: dict) -> str:
    value = backend.get("version_spec")
    return value.strip() if isinstance(value, str) else ""


def backend_requirement(backend: dict) -> str:
    package_name = backend["package_name"]
    version_spec = backend_version_spec(backend)
    return f"{package_name}{version_spec}"


def component_requirement(component: ResolvedComponent) -> str:
    return backend_requirement(component.backend)


def component_acknowledgement_lines(component: ResolvedComponent) -> list[str]:
    related_components = acknowledgement_group_components(component)
    if len(related_components) == 1:
        return [
            f"{component.name} is an optional upstream component with its own terms.",
            f"codex-spine will run {component_requirement(component)} through {component.executable_command}.",
            "Continue only if you are comfortable with that upstream project and its terms.",
        ]

    related_names = ", ".join(member.name for member in related_components)
    lines = [
        f"{component_acknowledgement_label(component)} covers these optional upstream integrations: {related_names}.",
        "codex-spine will enable them together through the managed uv runner path:",
    ]
    lines.extend(
        f"- {component_requirement(member)} via {member.executable_command}"
        for member in related_components
    )
    lines.append("Continue only if you are comfortable with that upstream suite and its terms.")
    return lines


def _extract_reported_version(text: str) -> str:
    match = VERSION_TOKEN_RE.search(text)
    return match.group(1) if match else ""


def _parse_version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _version_satisfies_spec(version: str, spec: str) -> bool:
    current = _parse_version_tuple(version)
    for raw_clause in spec.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue
        match = VERSION_CLAUSE_RE.match(clause)
        if match is None:
            return False
        operator, raw_expected = match.groups()
        expected = _parse_version_tuple(raw_expected)
        if operator == "<" and not (current < expected):
            return False
        if operator == "<=" and not (current <= expected):
            return False
        if operator == ">" and not (current > expected):
            return False
        if operator == ">=" and not (current >= expected):
            return False
        if operator == "==" and not (current == expected):
            return False
        if operator == "!=" and not (current != expected):
            return False
    return True


def _matches_version_contract(component: ResolvedComponent, version_text: str) -> tuple[bool, str]:
    version = _extract_reported_version(version_text)
    if not version:
        return False, f"could not parse version from {version_text or 'empty output'}"

    version_spec = backend_version_spec(component.backend)
    if _version_satisfies_spec(version, version_spec):
        return True, ""
    return False, f"expected {component.backend['package_name']}{version_spec}, got {version_text or version}"


def _pnpm_requirement(component: ResolvedComponent) -> str:
    package_name = component.backend["package_name"]
    version_spec = backend_version_spec(component.backend)
    return f"{package_name}@{version_spec}"


def _command_version(executable: Path, args: list[str] | None = None) -> str:
    if not executable.exists():
        return ""
    result = _run([str(executable), *(args or ["--version"])], check=False, env=_pnpm_env())
    if result.returncode != 0:
        return ""
    return (result.stdout or result.stderr).strip()


def _status_pnpm(component: ResolvedComponent) -> dict:
    executable = component.executable_path
    version = _command_version(executable, component.backend.get("version_args", ["--version"]))
    installed = executable.exists()
    healthy = installed and bool(version)
    health_detail = ""
    if healthy:
        healthy, health_detail = _matches_version_contract(component, version)
    health_args = component.backend.get("health_args")
    if installed and health_args:
        health_result = _run([str(executable), *health_args], check=False, env=_pnpm_env())
        if health_result.returncode != 0:
            healthy = False
            health_detail = _first_nonempty_line(health_result.stderr, health_result.stdout) or "health check failed"
    return {
        "installed": installed,
        "healthy": healthy,
        "detail": (
            f"{version}; {health_detail}"
            if version and health_detail
            else version or health_detail or f"missing executable: {executable}; expected {_pnpm_requirement(component)}"
        ),
        "action": ["pnpm", "add", "-g", _pnpm_requirement(component)],
    }


def _status_uv_tool(component: ResolvedComponent) -> dict:
    executable = component.executable_path
    installed = executable.exists()
    version_text = ""
    probe_detail = ""
    healthy = installed
    version_args = component.backend.get("version_args")
    if installed and version_args:
        probe = _command_probe(executable, version_args, env=_pnpm_env())
        version_text = str(probe["output"])
        if not bool(probe["ok"]):
            healthy = False
            probe_detail = str(probe["detail"])
        else:
            healthy, probe_detail = _matches_version_contract(component, version_text)
    health_args = component.backend.get("health_args")
    if healthy and installed and health_args:
        probe = _command_probe(executable, health_args, env=_pnpm_env())
        if not bool(probe["ok"]):
            healthy = False
            probe_detail = str(probe["detail"])
    expected = f"expected {component_requirement(component)}"
    detail = _combine_detail(version_text, probe_detail) or (
        expected if installed else f"missing executable: {executable}; {expected}"
    )
    return {
        "installed": installed,
        "healthy": healthy,
        "detail": detail,
        "action": [
            "uv",
            "tool",
            "install",
            "--python",
            "python3",
            component_requirement(component),
        ],
    }


def _uvx_base_command(component: ResolvedComponent) -> list[str]:
    resolved = _resolve_command(component.executable_command, env=_pnpm_env()) or component.executable_command
    tool_name = str(component.backend.get("tool_name", component.backend["package_name"]))
    if Path(resolved).name == "uv":
        return [resolved, "tool", "run", "--from", component_requirement(component), tool_name]
    return [resolved, "--from", component_requirement(component), tool_name]


def _status_uvx_tool(component: ResolvedComponent) -> dict:
    command = component.executable_command
    installed = _command_available(command, env=_pnpm_env())
    healthy = installed
    version_text = ""
    probe_detail = ""
    version_args = component.backend.get("version_args", [])
    if installed and version_args:
        probe = _command_probe_args(_uvx_base_command(component) + version_args, env=_pnpm_env())
        version_text = str(probe["output"])
        if not bool(probe["ok"]):
            healthy = False
            probe_detail = str(probe["detail"])
        else:
            healthy, probe_detail = _matches_version_contract(component, version_text)
    health_args = component.backend.get("health_args")
    if healthy and installed and health_args:
        probe = _command_probe_args(_uvx_base_command(component) + health_args, env=_pnpm_env())
        if not bool(probe["ok"]):
            healthy = False
            probe_detail = str(probe["detail"])
        elif not version_text:
            probe_detail = f"health probe ok: {' '.join(health_args)}"
    expected = f"expected {component_requirement(component)} via {command}"
    detail = _combine_detail(version_text, probe_detail) or (
        expected if installed else f"missing command: {command}; {expected}"
    )
    action_args = version_args or health_args
    return {
        "installed": installed,
        "healthy": healthy,
        "detail": detail,
        "action": _uvx_base_command(component) + action_args,
    }


def component_status(component: ResolvedComponent) -> dict:
    kind = component.backend["kind"]
    if kind == "pnpm_global":
        return _status_pnpm(component)
    if kind == "uv_tool":
        return _status_uv_tool(component)
    if kind == "uvx_tool":
        return _status_uvx_tool(component)
    raise ValueError(f"unsupported backend kind: {kind}")


def update_component(
    component: ResolvedComponent,
    *,
    run_live_fn=None,
    run_live_with_heartbeat_fn=None,
    progress_fn=None,
) -> list[str]:
    run_live_fn = run_live_fn or _run_live
    run_live_with_heartbeat_fn = run_live_with_heartbeat_fn or _run_live_with_heartbeat
    progress_fn = progress_fn or _progress
    if component.backend["kind"] == "pnpm_global":
        _prepare_pnpm_global_bin()
    action = component_status(component)["action"]
    run_live_fn(action, check=True, env=_pnpm_env())
    progress_fn(f"{component.name}: verifying health...")
    status = component_status(component)
    if component.backend["kind"] != "pnpm_global":
        if not status["healthy"]:
            raise RuntimeError(f"{component.name} remains unhealthy after update: {status['detail']}")
        if component.backend["kind"] == "uvx_tool":
            return [f"{component.name}: validated compatible runner invocation"]
        return [f"{component.name}: installed/updated"]
    if not status["healthy"]:
        progress_fn(f"{component.name}: rebuilding native addons and rechecking health...")
        if _rebuild_better_sqlite3(
            heartbeat_message=f"{component.name}: still rebuilding native addons...",
            run_live_with_heartbeat_fn=run_live_with_heartbeat_fn,
        ):
            status = component_status(component)
    if not status["healthy"]:
        workspace = _pnpm_global_workspace()
        if workspace is not None:
            progress_fn(f"{component.name}: rebuilding the global pnpm workspace...")
            run_live_with_heartbeat_fn(
                ["pnpm", "rebuild"],
                cwd=workspace,
                check=True,
                env=_pnpm_env(),
                heartbeat_message=f"{component.name}: still rebuilding the global pnpm workspace...",
            )
            progress_fn(f"{component.name}: rechecking health after workspace rebuild...")
            status = component_status(component)
    if not status["healthy"]:
        raise RuntimeError(f"{component.name} remains unhealthy after update: {status['detail']}")
    return [f"{component.name}: installed/updated"]


def record_component_enabled(component: ResolvedComponent) -> None:
    state = load_component_state()
    enabled = state.setdefault("enabled", {})
    existing = enabled.get(component.name)
    enabled_at = existing.get("enabled_at") if isinstance(existing, dict) and existing.get("enabled_at") else now_iso()
    enabled[component.name] = {"enabled_at": enabled_at}
    write_component_state(state)


def acknowledgement_record(key: str) -> dict:
    acknowledgements = load_component_state().get("acknowledgements", {})
    if not isinstance(acknowledgements, dict):
        return {}
    record = acknowledgements.get(key)
    return record if isinstance(record, dict) else {}


def record_component_acknowledged(
    component: ResolvedComponent,
    *,
    related_components: list[ResolvedComponent] | None = None,
) -> None:
    key = component_acknowledgement_key(component)
    related = related_components or acknowledgement_group_components(component)
    state = load_component_state()
    acknowledgements = state.setdefault("acknowledgements", {})
    existing = acknowledgements.get(key)
    accepted_at = (
        existing.get("accepted_at")
        if isinstance(existing, dict) and existing.get("accepted_at")
        else now_iso()
    )
    acknowledgements[key] = {
        "accepted_at": accepted_at,
        "components": [member.name for member in related],
        "label": component_acknowledgement_label(component),
    }
    write_component_state(state)


def _extract_terms_text(source_text: str, backend: dict) -> str:
    extracted = source_text
    matched_start_marker = False
    start_markers = []
    if backend.get("terms_start_marker"):
        start_markers.append(backend["terms_start_marker"])
    start_markers.extend(backend.get("terms_start_markers", []))
    if start_markers:
        for start_marker in start_markers:
            start_index = extracted.find(start_marker)
            if start_index >= 0:
                extracted = extracted[start_index:]
                matched_start_marker = True
                break

    if not matched_start_marker:
        for match in TERMS_HEADING_RE.finditer(source_text):
            heading_text = match.group(1).strip()
            if TERMS_HEADING_HINT_RE.search(heading_text):
                extracted = source_text[match.start():]
                matched_start_marker = True
                break

    end_markers = []
    if backend.get("terms_end_marker"):
        end_markers.append(backend["terms_end_marker"])
    end_markers.extend(backend.get("terms_end_markers", []))
    for end_marker in end_markers:
        end_index = extracted.find(end_marker)
        if end_index >= 0:
            extracted = extracted[:end_index]
            break

    return extracted.strip() + "\n"


def fetch_component_terms(component: ResolvedComponent) -> dict | None:
    source_url = component.backend.get("terms_source_url")
    if not source_url:
        return None
    try:
        with urllib.request.urlopen(source_url, timeout=20) as response:
            source_text = response.read().decode("utf-8")
    except Exception as exc:  # pragma: no cover - network failure details vary by environment
        raise RuntimeError(f"could not retrieve current upstream terms for {component.name}: {exc}") from exc

    extracted = _extract_terms_text(source_text, component.backend)
    return {
        "source_url": source_url,
        "text": extracted,
    }


def _page_terms_text(text: str, *, label: str) -> None:
    lines = text.splitlines()
    page_size = max(shutil.get_terminal_size(fallback=(80, 24)).lines - 4, 8)
    total = len(lines) or 1
    start = 0
    while start < len(lines):
        end = min(start + page_size, len(lines))
        print(f"\n--- Terms {start + 1}-{end} of {total} ---")
        print("\n".join(lines[start:end]))
        start = end
        if start >= len(lines):
            break
        reply = input("\nPress Return for more, or type 'q' to stop reviewing and skip installation: ").strip().lower()
        if reply in {"q", "quit", "stop"}:
            raise RuntimeError(f"Stopped reviewing the upstream terms before the end. {label} was not enabled.")


def ensure_component_acknowledged(
    component: ResolvedComponent,
    *,
    non_interactive: bool,
) -> None:
    if not component.backend.get("requires_acknowledgement"):
        return
    related_components = acknowledgement_group_components(component)
    key = component_acknowledgement_key(component)
    enabled = enabled_component_names()
    if acknowledgement_record(key):
        return
    if component.name in enabled:
        record_component_enabled(component)
        record_component_acknowledged(component, related_components=related_components)
        return
    if any(member.name in enabled for member in related_components):
        record_component_acknowledged(component, related_components=related_components)
        return

    if non_interactive:
        raise RuntimeError(
            f"{component_acknowledgement_label(component)} requires interactive terms acknowledgement from a TTY."
        )

    bundle = fetch_component_terms(component)
    print()
    for line in component_acknowledgement_lines(component):
        print(line)
    print()
    if bundle is not None:
        print(f"Retrieved current upstream terms for {component_acknowledgement_label(component)} from {bundle['source_url']}\n")
        _page_terms_text(bundle["text"], label=component_acknowledgement_label(component))
    while True:
        try:
            reply = _read_accept_or_escape(
                "Type 'accept' to continue, or press Esc to skip for now: "
            ).strip().lower()
        except EOFError as exc:
            raise RuntimeError(
                f"Stopped before acknowledging the upstream terms. {component_acknowledgement_label(component)} was not enabled."
            ) from exc
        if reply == "accept":
            record_component_acknowledged(component, related_components=related_components)
            break
        if reply in {"skip", "s", "no", "n", "q", "quit", "\x1b"}:
            raise RuntimeError(f"Skipped enabling {component_acknowledgement_label(component)} for now.")
        if not reply:
            if _prompt_yes_no(f"Skip enabling {component_acknowledgement_label(component)} for now?", default=False):
                raise RuntimeError(f"Skipped enabling {component_acknowledgement_label(component)} for now.")
            continue
        print("Please type 'accept' or press Esc.")
