from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tomllib
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


SUPPORTED_BACKENDS = {"pnpm_global", "uv_tool"}


def _expand_path(raw_path: str) -> Path:
    return Path(raw_path).expanduser()


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=check,
        capture_output=True,
        text=True,
    )


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
    result = _run([str(executable), *(args or ["--version"])], check=False)
    if result.returncode != 0:
        return ""
    return (result.stdout or result.stderr).strip()


def _status_pnpm(component: ResolvedComponent) -> dict:
    executable = component.executable_path
    version = _command_version(executable, component.backend.get("version_args", ["--version"]))
    desired = component.backend["pinned_version"]
    installed = executable.exists()
    healthy = installed and desired in version
    return {
        "installed": installed,
        "healthy": healthy,
        "detail": version or f"missing executable: {executable}",
        "action": ["pnpm", "add", "-g", f'{component.backend["package_name"]}@{desired}'],
    }


def _status_uv_tool(component: ResolvedComponent) -> dict:
    executable = component.executable_path
    version = _command_version(executable, component.backend.get("version_args", ["--version"]))
    desired = component.backend["pinned_version"]
    installed = executable.exists()
    healthy = installed and (not version or desired in version)
    detail = version or f"missing executable: {executable}; expected {component.backend['package_name']}=={desired}"
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


def component_status(component: ResolvedComponent) -> dict:
    kind = component.backend["kind"]
    if kind == "pnpm_global":
        return _status_pnpm(component)
    if kind == "uv_tool":
        return _status_uv_tool(component)
    raise ValueError(f"unsupported backend kind: {kind}")


def update_component(component: ResolvedComponent) -> list[str]:
    action = component_status(component)["action"]
    _run(action, check=True)
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


def ensure_license_acknowledged(
    component: ResolvedComponent,
    *,
    accept_license: bool,
    non_interactive: bool,
) -> dict | None:
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
        print(bundle["text"])
        reply = input("Type 'accept' to continue: ").strip().lower()
        if reply != "accept":
            raise RuntimeError(f"license acknowledgement declined for {component.name}")

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
