from __future__ import annotations

import hashlib
import os
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
    LICENSES_DIR,
    MAINTAINED_COMPONENTS_PATH,
    REPO_ROOT,
    enabled_component_record,
    now_iso,
    relative_to_repo,
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


def _command_available(command: str) -> bool:
    if "/" in command or command.startswith("~"):
        return _expand_path(command).exists()
    return shutil.which(command) is not None


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
            for field_name in ("package_name", "pinned_version"):
                if not isinstance(backend.get(field_name), str) or not backend[field_name].strip():
                    errors.append(
                        f"backend must define {field_name}: components.{component_name}.backends.{backend_name}.{field_name}"
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
            if backend.get("license_source_url") and not backend.get("license_start_marker"):
                errors.append(
                    "licensed backend must define license_start_marker: "
                    f"components.{component_name}.backends.{backend_name}.license_start_marker"
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
    desired = component.backend["pinned_version"]
    installed = executable.exists()
    healthy = installed and desired in version
    health_detail = ""
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
            else version or health_detail or f"missing executable: {executable}"
        ),
        "action": ["pnpm", "add", "-g", f'{component.backend["package_name"]}@{desired}'],
    }


def _status_uv_tool(component: ResolvedComponent) -> dict:
    executable = component.executable_path
    desired = component.backend["pinned_version"]
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
        elif desired not in version_text:
            healthy = False
            probe_detail = f"expected {component.backend['package_name']}=={desired}, got {version_text or 'unknown version'}"
    health_args = component.backend.get("health_args")
    if healthy and installed and health_args:
        probe = _command_probe(executable, health_args, env=_pnpm_env())
        if not bool(probe["ok"]):
            healthy = False
            probe_detail = str(probe["detail"])
    expected = f"expected {component.backend['package_name']}=={desired}"
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
            f'{component.backend["package_name"]}=={desired}',
        ],
    }


def _uvx_base_command(component: ResolvedComponent) -> list[str]:
    package_name = component.backend["package_name"]
    desired = component.backend["pinned_version"]
    tool_name = str(component.backend.get("tool_name", package_name))
    return [component.executable_command, "--from", f"{package_name}=={desired}", tool_name]


def _status_uvx_tool(component: ResolvedComponent) -> dict:
    command = component.executable_command
    package_name = component.backend["package_name"]
    desired = component.backend["pinned_version"]
    installed = _command_available(command)
    healthy = installed
    version_text = ""
    probe_detail = ""
    version_args = component.backend.get("version_args", ["--version"])
    if installed and version_args:
        probe = _command_probe_args(_uvx_base_command(component) + version_args)
        version_text = str(probe["output"])
        if not bool(probe["ok"]):
            healthy = False
            probe_detail = str(probe["detail"])
        elif desired not in version_text:
            healthy = False
            probe_detail = f"expected {package_name}=={desired}, got {version_text or 'unknown version'}"
    health_args = component.backend.get("health_args")
    if healthy and installed and health_args:
        probe = _command_probe_args(_uvx_base_command(component) + health_args)
        if not bool(probe["ok"]):
            healthy = False
            probe_detail = str(probe["detail"])
    expected = f"expected {package_name}=={desired} via {command}"
    detail = _combine_detail(version_text, probe_detail) or (
        expected if installed else f"missing command: {command}; {expected}"
    )
    return {
        "installed": installed,
        "healthy": healthy,
        "detail": detail,
        "action": _uvx_base_command(component) + version_args,
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
            return [f"{component.name}: validated pinned uvx invocation"]
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


def fetch_license_terms(component: ResolvedComponent) -> dict | None:
    source_url = component.backend.get("license_source_url")
    if not source_url:
        return None
    with urllib.request.urlopen(source_url, timeout=20) as response:
        source_text = response.read().decode("utf-8")

    extracted = source_text
    start_marker = component.backend.get("license_start_marker")
    if start_marker:
        start_index = extracted.find(start_marker)
        if start_index < 0:
            raise RuntimeError(f"license start marker not found for {component.name}: {start_marker!r}")
        extracted = extracted[start_index:]

    end_marker = component.backend.get("license_end_marker")
    if end_marker:
        end_index = extracted.find(end_marker)
        if end_index >= 0:
            extracted = extracted[:end_index]

    extracted = extracted.strip() + "\n"
    sha256 = hashlib.sha256(extracted.encode("utf-8")).hexdigest()
    return {
        "source_url": source_url,
        "text": extracted,
        "sha256": sha256,
    }


def record_license_acknowledgement(component: ResolvedComponent, bundle: dict) -> dict:
    version = component.backend["pinned_version"]
    terms_path = LICENSES_DIR / component.name / f"{version}.txt"
    terms_path.parent.mkdir(parents=True, exist_ok=True)
    terms_path.write_text(bundle["text"], encoding="utf-8")

    state = load_component_state()
    enabled = state.setdefault("enabled", {})
    enabled[component.name] = {
        "version": version,
        "license_source_url": bundle["source_url"],
        "license_sha256": bundle["sha256"],
        "terms_path": relative_to_repo(terms_path),
        "acknowledged_at": now_iso(),
    }
    write_component_state(state)
    return bundle


def ensure_license_acknowledged(
    component: ResolvedComponent,
    *,
    accept_license: bool,
    non_interactive: bool,
) -> dict | None:
    if not component.backend.get("license_source_url"):
        return None

    if not accept_license and not non_interactive:
        try:
            input("Press Return to fetch and review the pinned upstream terms: ")
        except EOFError as exc:
            raise RuntimeError(f"Stopped before fetching the upstream terms. {component.name} was not enabled.") from exc
    _progress(f"Fetching pinned upstream terms for {component.name}...")
    bundle = fetch_license_terms(component)
    if bundle is None:
        return None

    version = component.backend["pinned_version"]
    terms_path = LICENSES_DIR / component.name / f"{version}.txt"
    terms_path.parent.mkdir(parents=True, exist_ok=True)
    terms_path.write_text(bundle["text"], encoding="utf-8")

    existing = enabled_component_record(component.name)
    already_acknowledged = (
        existing.get("version") == version
        and existing.get("license_sha256") == bundle["sha256"]
        and existing.get("terms_path") == relative_to_repo(terms_path)
    )
    if already_acknowledged:
        return bundle

    if non_interactive and not accept_license:
        raise RuntimeError(
            f"{component.name} requires explicit license acknowledgement. Re-run with --accept-license."
        )

    if not accept_license:
        print(f"Retrieved upstream terms for {component.name} {version} from {bundle['source_url']}\n")
        _page_terms_text(bundle["text"])
        while True:
            try:
                reply = _read_accept_or_escape(
                    "Type 'accept' to continue, or press Esc to skip jCodeMunch MCP for now: "
                ).strip().lower()
            except EOFError as exc:
                raise RuntimeError(f"Stopped before acknowledging the upstream terms. {component.name} was not enabled.") from exc
            if reply == "accept":
                break
            if reply in {"skip", "s", "no", "n", "q", "quit", "\x1b"}:
                raise RuntimeError(f"Skipped enabling {component.name} for now.")
            if not reply:
                if _prompt_yes_no("Skip enabling jCodeMunch MCP for now?", default=False):
                    raise RuntimeError(f"Skipped enabling {component.name} for now.")
                continue
            print("Please type 'accept' or press Esc.")

    return record_license_acknowledgement(component, bundle)


def _page_terms_text(text: str) -> None:
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
            raise RuntimeError("Stopped reviewing the upstream terms before the end. jCodeMunch MCP was not enabled.")
