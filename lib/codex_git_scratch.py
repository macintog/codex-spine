from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from toml_compat import tomllib
except ModuleNotFoundError:  # pragma: no cover - direct module loading fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from toml_compat import tomllib


UTC = timezone.utc


HOME = Path.home()
SCRATCH_ROOT = HOME / ".codex" / "worktrees"
SCRATCH_REGISTRY_PATH = SCRATCH_ROOT / "registry.json"
SCRATCH_RESCUE_ROOT = HOME / ".codex" / "rescue" / "parked-state"
EPHEMERAL_CHECKOUT_ROOTS = tuple(
    {
        Path("/tmp").resolve(strict=False),
        Path("/private/tmp").resolve(strict=False),
        Path("/var/tmp").resolve(strict=False),
        Path("/private/var/tmp").resolve(strict=False),
        Path(tempfile.gettempdir()).resolve(strict=False),
    }
)
INDEX_REGISTRY_PATH = HOME / ".codex" / "index-registry.toml"
AUTOMATIONS_ROOT = HOME / ".codex" / "automations"
SESSIONS_ROOT = HOME / ".codex" / "sessions"
RECENT_SESSION_LOOKBACK = timedelta(hours=24)


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def load_registry() -> dict:
    if not SCRATCH_REGISTRY_PATH.exists():
        return {"schema_version": 1, "entries": {}}
    try:
        return json.loads(SCRATCH_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"schema_version": 1, "entries": {}}


def save_registry(payload: dict) -> None:
    payload = dict(payload)
    payload.setdefault("schema_version", 1)
    payload.setdefault("entries", {})
    atomic_write_text(SCRATCH_REGISTRY_PATH, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_index_registry() -> dict:
    if not INDEX_REGISTRY_PATH.exists():
        return {"version": 1, "discovery_roots": [], "projects": []}
    try:
        content = INDEX_REGISTRY_PATH.read_text(encoding="utf-8")
        if not content.strip():
            return {"version": 1, "discovery_roots": [], "projects": []}
        payload = tomllib.loads(content)
    except (tomllib.TOMLDecodeError, OSError):
        return {"version": 1, "discovery_roots": [], "projects": []}
    payload.setdefault("version", 1)
    payload.setdefault("discovery_roots", [])
    payload.setdefault("projects", [])
    return payload


def save_index_registry(payload: dict) -> None:
    version = int(payload.get("version", 1))
    discovery_roots = [str(item) for item in payload.get("discovery_roots", [])]
    projects = [str(item) for item in payload.get("projects", [])]

    lines = [f"version = {version}", "discovery_roots = ["]
    for item in discovery_roots:
        lines.append(f'  "{item}",')
    lines.append("]")
    lines.append("projects = [")
    for item in projects:
        lines.append(f'  "{item}",')
    lines.append("]")
    atomic_write_text(INDEX_REGISTRY_PATH, "\n".join(lines) + "\n")


def automation_cwds() -> set[Path]:
    results: set[Path] = set()
    if not AUTOMATIONS_ROOT.exists():
        return results
    for automation_path in AUTOMATIONS_ROOT.glob("*/automation.toml"):
        try:
            payload = tomllib.loads(automation_path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError):
            continue
        for cwd_value in payload.get("cwds", []) or []:
            try:
                results.add(Path(str(cwd_value)).expanduser().resolve(strict=False))
            except OSError:
                continue
    return results


def recent_session_cwds(*, lookback: timedelta = RECENT_SESSION_LOOKBACK, max_files: int = 200) -> set[Path]:
    results: set[Path] = set()
    if not SESSIONS_ROOT.exists():
        return results

    horizon = datetime.now(UTC) - lookback
    candidates: list[Path] = []
    for path in SESSIONS_ROOT.rglob("*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except OSError:
            continue
        if mtime < horizon:
            continue
        candidates.append(path)

    candidates.sort(
        key=lambda candidate: candidate.stat().st_mtime if candidate.exists() else 0,
        reverse=True,
    )

    for session_path in candidates[:max_files]:
        try:
            cwd_value = None
            session_started_at = None
            task_is_open = True
            with session_path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    payload_type = payload.get("type")
                    if payload_type == "event_msg":
                        event_type = (payload.get("payload") or {}).get("type")
                        if event_type == "task_started":
                            task_is_open = True
                        elif event_type in {"task_complete", "turn_aborted"}:
                            task_is_open = False
                        continue
                    if payload_type != "session_meta" or cwd_value is not None:
                        continue
                    meta = payload.get("payload", {})
                    cwd_value = meta.get("cwd")
                    if not cwd_value:
                        break
                    timestamp_value = payload.get("timestamp") or meta.get("timestamp")
                    if timestamp_value:
                        try:
                            session_started_at = datetime.fromisoformat(str(timestamp_value).replace("Z", "+00:00"))
                        except ValueError:
                            session_started_at = None
                        if session_started_at is not None and session_started_at < horizon:
                            cwd_value = None
                            break
            if cwd_value and task_is_open:
                results.add(Path(str(cwd_value)).expanduser().resolve(strict=False))
        except (OSError, json.JSONDecodeError):
            continue

    return results


def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for candidate in path.rglob("*"):
        try:
            if candidate.is_file() and not candidate.is_symlink():
                total += candidate.stat().st_size
        except OSError:
            continue
    return total


def is_scratch_path(path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(SCRATCH_ROOT)
        return True
    except ValueError:
        return False


def is_ephemeral_checkout_path(path: Path) -> bool:
    resolved = path.expanduser().resolve(strict=False)
    for root in EPHEMERAL_CHECKOUT_ROOTS:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def scratch_id_for_path(path: Path) -> str | None:
    resolved = path.resolve(strict=False)
    if not is_scratch_path(resolved):
        return None
    try:
        relative = resolved.relative_to(SCRATCH_ROOT)
    except ValueError:
        return None
    if len(relative.parts) < 2:
        return None
    return relative.parts[0]


def prune_empty_parent_dirs(path: Path, *, stop_at: Path) -> None:
    current = path.resolve(strict=False)
    stop = stop_at.resolve(strict=False)
    while current != stop:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def prune_empty_scratch_dirs() -> list[Path]:
    removed: list[Path] = []
    if not SCRATCH_ROOT.exists():
        return removed
    for candidate in sorted(SCRATCH_ROOT.iterdir()):
        if not candidate.is_dir():
            continue
        try:
            candidate.rmdir()
        except OSError:
            continue
        removed.append(candidate)
    return removed
