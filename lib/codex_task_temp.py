from __future__ import annotations

from contextlib import nullcontext

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import uuid
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from codex_git_scratch import is_ephemeral_checkout_path


JOURNAL_FIELD = "temporary_artifacts"
MARKER_NAME = ".codex-task-temp-owner.json"
MARKER_SCHEMA_VERSION = 2


class TaskTempError(RuntimeError):
    pass


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_temp_root() -> Path:
    return Path("/private/tmp" if sys.platform == "darwin" else "/tmp")


def durable_temp_root(common_dir: Path) -> Path:
    """Derive durable disposable storage from the repository's persistent owner."""
    common_dir = _validate_base_root(common_dir)
    root = common_dir / "codex-git-safe" / "temporary-artifacts"
    if is_ephemeral_checkout_path(root):
        raise TaskTempError(f"durable temporary storage must be outside OS temporary roots: {root}")
    return root


def _entry_storage_root(entry: dict[str, Any], *, base_root: Path | None) -> Path:
    if entry.get("schema_version") == 1:
        if "storage" in entry:
            raise TaskTempError("legacy temporary artifact cannot select another storage kind")
        expected = base_root or default_temp_root()
    elif entry.get("schema_version") == 2 and entry.get("storage") == "durable":
        expected = durable_temp_root(Path(entry["owner"]["common_dir"]))
    else:
        raise TaskTempError("managed temporary artifact has unsupported storage or schema")
    if Path(str(entry.get("storage_root", ""))) != expected:
        raise TaskTempError(f"owned temporary root has a noncanonical storage parent: {entry.get('storage_root')}")
    return _validate_base_root(expected)


def owner_identity(record: dict[str, Any], *, common_dir: Path) -> dict[str, str]:
    checkout = record.get("checkout_identity") or record.get("checkout_path")
    branch = record.get("branch")
    created_at = record.get("created_at")
    start_tip = record.get("start_tip")
    if not all(isinstance(item, str) and item for item in (checkout, branch, created_at, start_tip)):
        raise TaskTempError("managed task record lacks exact creation ownership")
    return {
        "common_dir": str(common_dir.resolve(strict=True)),
        "checkout_identity": str(Path(checkout).resolve(strict=False)),
        "branch": branch,
        "created_at": created_at,
        "start_tip": start_tip,
    }


def _owner_key(owner: dict[str, str]) -> str:
    encoded = json.dumps(owner, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _marker_payload(entry: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "schema_version": entry["schema_version"],
        "artifact_id": entry["id"],
        "nonce": entry["nonce"],
        "owner": entry["owner"],
    }
    if entry["schema_version"] == 2:
        payload.update({"storage": entry["storage"], "storage_root": entry["storage_root"]})
    return payload


def _marker_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_marker_file(path: Path, entry: dict[str, Any]) -> None:
    if path.is_symlink() or not path.is_file():
        raise TaskTempError(f"owned temporary root marker is missing or unsafe: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TaskTempError(f"cannot read owned temporary root marker {path}: {exc}") from exc
    if payload != _marker_payload(entry) or _marker_digest(payload) != entry.get("marker_sha256"):
        raise TaskTempError(f"owned temporary root marker changed: {path}")


def _validate_entry_shape(entry: dict[str, Any]) -> None:
    try:
        artifact_id = str(uuid.UUID(str(entry.get("id", ""))))
    except ValueError as exc:
        raise TaskTempError("managed temporary artifact has an invalid id") from exc
    if artifact_id != entry.get("id"):
        raise TaskTempError("managed temporary artifact id is not canonical")
    nonce = entry.get("nonce")
    label = entry.get("label")
    owner_key = entry.get("owner_key")
    if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise TaskTempError("managed temporary artifact has an invalid nonce")
    if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", label):
        raise TaskTempError("managed temporary artifact has an invalid label")
    if not isinstance(owner_key, str) or not re.fullmatch(r"[0-9a-f]{64}", owner_key):
        raise TaskTempError("managed temporary artifact has an invalid owner key")
    if not isinstance(entry.get("owner"), dict) or _owner_key(entry["owner"]) != owner_key:
        raise TaskTempError("managed temporary artifact owner key changed")


def _validate_base_root(base_root: Path) -> Path:
    if not base_root.is_absolute():
        raise TaskTempError("temporary storage root must be absolute")
    if base_root.is_symlink():
        raise TaskTempError(f"temporary storage root must not be a symlink: {base_root}")
    try:
        resolved = base_root.resolve(strict=True)
    except OSError as exc:
        raise TaskTempError(f"cannot resolve temporary storage root {base_root}: {exc}") from exc
    if resolved != base_root:
        raise TaskTempError(f"temporary storage root is aliased: {base_root} -> {resolved}")
    if not resolved.is_dir():
        raise TaskTempError(f"temporary storage root is not a directory: {resolved}")
    return resolved


def _validate_owned_root(path: Path, *, base_root: Path, entry: dict[str, Any]) -> os.stat_result:
    _validate_entry_shape(entry)
    canonical_root = _validate_base_root(base_root)
    expected_name = (
        f"codex-task-{str(entry.get('owner_key', ''))[:12]}-"
        f"{entry.get('label', '')}-{str(entry.get('nonce', ''))[:12]}"
    )
    if not path.is_absolute() or path.parent != canonical_root or path.name != expected_name:
        raise TaskTempError(f"owned temporary root escaped its canonical parent: {path}")
    if path.is_symlink():
        raise TaskTempError(f"owned temporary root became a symlink: {path}")
    try:
        root_stat = path.lstat()
    except OSError as exc:
        raise TaskTempError(f"cannot inspect owned temporary root {path}: {exc}") from exc
    if not stat.S_ISDIR(root_stat.st_mode):
        raise TaskTempError(f"owned temporary root is no longer a directory: {path}")
    if root_stat.st_uid != os.getuid():
        raise TaskTempError(f"owned temporary root has a different filesystem owner: {path}")
    if stat.S_IMODE(root_stat.st_mode) & 0o077:
        raise TaskTempError(f"owned temporary root permissions are too broad: {path}")
    expected_device = entry.get("device")
    expected_inode = entry.get("inode")
    if expected_device is not None and (root_stat.st_dev != expected_device or root_stat.st_ino != expected_inode):
        raise TaskTempError(f"owned temporary root identity changed: {path}")
    marker = path / MARKER_NAME
    sidecar = canonical_root / f".codex-task-temp-{entry['id']}.owner"
    marker_path = marker if marker.is_file() and not marker.is_symlink() else sidecar
    _validate_marker_file(marker_path, entry)
    return root_stat


def tree_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    root_device = path.lstat().st_dev
    paths = [path]
    paths.extend(sorted(path.rglob("*"), key=lambda item: str(item.relative_to(path))))
    for candidate in paths:
        item_stat = candidate.lstat()
        if item_stat.st_dev != root_device:
            raise TaskTempError(f"owned temporary root crosses a mounted filesystem: {candidate}")
        if not (stat.S_ISDIR(item_stat.st_mode) or stat.S_ISREG(item_stat.st_mode) or stat.S_ISLNK(item_stat.st_mode)):
            raise TaskTempError(f"owned temporary root contains an unsupported special file: {candidate}")
        relative = "." if candidate == path else str(candidate.relative_to(path))
        target = os.readlink(candidate) if stat.S_ISLNK(item_stat.st_mode) else ""
        digest.update(
            f"{relative}\0{item_stat.st_mode}\0{item_stat.st_dev}\0{item_stat.st_ino}\0"
            f"{item_stat.st_size}\0{item_stat.st_mtime_ns}\0{item_stat.st_ctime_ns}\0{target}\n".encode()
        )
    return digest.hexdigest()


def assert_not_live(path: Path) -> None:
    try:
        result = subprocess.run(
            ["lsof", "+D", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TaskTempError(f"cannot prove temporary root is unused: {path}: {exc}") from exc
    if result.stderr.strip():
        raise TaskTempError(f"cannot prove temporary root is unused: {path}: {result.stderr.strip()}")
    if result.returncode == 0 and result.stdout.strip():
        raise TaskTempError(f"temporary root is live in another process: {path}")
    if result.returncode not in (0, 1):
        raise TaskTempError(f"cannot prove temporary root is unused: {path}: lsof exit {result.returncode}")


def _save_entry(
    load_state: Callable[[], dict[str, Any]],
    save_state: Callable[[dict[str, Any]], None],
    entry: dict[str, Any],
) -> None:
    payload = load_state()
    entries = list(payload.get(JOURNAL_FIELD, []))
    if not all(isinstance(item, dict) for item in entries):
        raise TaskTempError("managed temporary artifact journal is invalid")
    entries = [item for item in entries if item.get("id") != entry["id"]]
    entries.append(entry)
    payload[JOURNAL_FIELD] = entries
    save_state(payload)


def allocate_root(
    *,
    owner: dict[str, str],
    common_dir: Path,
    label: str,
    load_state: Callable[[], dict[str, Any]],
    save_state: Callable[[dict[str, Any]], None],
    base_root: Path | None = None,
    storage: str = "temporary",
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", label):
        raise TaskTempError("label must contain 1-48 letters, digits, hyphens, or underscores")
    if str(common_dir.resolve(strict=True)) != owner.get("common_dir"):
        raise TaskTempError("temporary storage common directory differs from task owner")
    if storage == "durable":
        if base_root is not None:
            raise TaskTempError("durable storage does not accept an alternate parent")
        durable_root = durable_temp_root(common_dir)
        durable_root.parent.mkdir(mode=0o700, exist_ok=True)
        _validate_base_root(durable_root.parent)
        durable_root.mkdir(mode=0o700, exist_ok=True)
        canonical_root = _validate_base_root(durable_root)
        parent_stat = canonical_root.stat()
        if parent_stat.st_uid != os.getuid() or stat.S_IMODE(parent_stat.st_mode) & 0o077:
            raise TaskTempError(f"durable temporary storage has unsafe ownership or permissions: {canonical_root}")
    elif storage == "temporary":
        canonical_root = _validate_base_root(base_root or default_temp_root())
    else:
        raise TaskTempError(f"unsupported temporary storage kind: {storage}")
    artifact_id = str(uuid.uuid4())
    nonce = uuid.uuid4().hex
    owner_key = _owner_key(owner)
    path = canonical_root / f"codex-task-{owner_key[:12]}-{label}-{nonce[:12]}"
    entry: dict[str, Any] = {
        "schema_version": MARKER_SCHEMA_VERSION if storage == "durable" else 1,
        "id": artifact_id,
        "nonce": nonce,
        "label": label,
        "path": str(path),
        "storage_root": str(canonical_root),
        "owner": owner,
        "owner_key": owner_key,
        "disposition": "delete_on_yeet",
        "phase": "allocating",
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }
    if storage == "durable":
        entry["storage"] = storage
    _save_entry(load_state, save_state, entry)
    try:
        path.mkdir(mode=0o700)
        marker_payload = _marker_payload(entry)
        marker = path / MARKER_NAME
        marker_fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(marker_fd, "w", encoding="utf-8") as handle:
            json.dump(marker_payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        directory_fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        root_stat = path.lstat()
        entry.update(
            {
                "phase": "active",
                "device": root_stat.st_dev,
                "inode": root_stat.st_ino,
                "marker_sha256": _marker_digest(marker_payload),
                "updated_at": _iso_now(),
            }
        )
        _save_entry(load_state, save_state, entry)
    except Exception as exc:
        entry.update({"phase": "allocation_failed", "error": str(exc), "updated_at": _iso_now()})
        _save_entry(load_state, save_state, entry)
        raise TaskTempError(f"temporary root allocation failed; ownership journal retained for {path}: {exc}") from exc
    return dict(entry)


def entries_for_owner(payload: dict[str, Any], owner: dict[str, str]) -> list[dict[str, Any]]:
    entries = payload.get(JOURNAL_FIELD, [])
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
        raise TaskTempError("managed temporary artifact journal is invalid")
    owner_key = _owner_key(owner)
    return [dict(item) for item in entries if item.get("owner_key") == owner_key and item.get("owner") == owner]


def status_for_owner(
    payload: dict[str, Any],
    owner: dict[str, str],
    *,
    base_root: Path | None = None,
) -> dict[str, Any]:
    if base_root is not None:
        _validate_base_root(base_root)
    artifacts: list[dict[str, Any]] = []
    for entry in entries_for_owner(payload, owner):
        _validate_entry_shape(entry)
        path = Path(str(entry.get("path", "")))
        canonical_root = _entry_storage_root(entry, base_root=base_root)
        sidecar = canonical_root / f".codex-task-temp-{entry['id']}.owner"
        observation = dict(entry)
        observation["exists"] = path.exists() or path.is_symlink()
        observation["sidecar_exists"] = sidecar.exists() or sidecar.is_symlink()
        observation["identity_matches"] = False
        if observation["exists"]:
            try:
                _validate_owned_root(path, base_root=canonical_root, entry=entry)
                observation["identity_matches"] = True
            except TaskTempError as exc:
                observation["identity_error"] = str(exc)
        artifacts.append(observation)
    pending = [
        item for item in artifacts
        if item.get("phase") != "deleted" or item.get("exists") or item.get("sidecar_exists")
    ]
    return {"artifacts": artifacts, "pending_count": len(pending), "deleted_count": len(artifacts) - len(pending)}


def cleanup_owned_roots(
    *,
    owner: dict[str, str],
    common_dir: Path,
    load_state: Callable[[], dict[str, Any]],
    save_state: Callable[[dict[str, Any]], None],
    live_check: Callable[[Path], None] = assert_not_live,
    base_root: Path | None = None,
    state_transaction: Callable[[], Any] = nullcontext,
) -> dict[str, Any]:
    def save_entry(entry: dict[str, Any]) -> None:
        with state_transaction():
            _save_entry(load_state, save_state, entry)

    if str(common_dir.resolve(strict=True)) != owner.get("common_dir"):
        raise TaskTempError("temporary storage common directory differs from task owner")
    entries = entries_for_owner(load_state(), owner)
    actions: list[str] = []
    receipts: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda item: str(item.get("path", ""))):
        _validate_entry_shape(entry)
        path = Path(str(entry.get("path", "")))
        canonical_root = _entry_storage_root(entry, base_root=base_root)
        storage_root = canonical_root
        sidecar = storage_root / f".codex-task-temp-{entry.get('id')}.owner"
        if entry.get("disposition") != "delete_on_yeet":
            raise TaskTempError(f"owned temporary root is protected from deletion: {path}")
        if entry.get("phase") == "deleted":
            if path.exists() or path.is_symlink():
                raise TaskTempError(f"deleted temporary root path was recreated: {path}")
            if sidecar.exists() or sidecar.is_symlink():
                raise TaskTempError(f"deleted temporary root retained its ownership sidecar: {sidecar}")
            receipts.append(dict(entry.get("cleanup") or {}))
            continue
        if entry.get("phase") in {"allocating", "allocation_failed"} and not (path.exists() or path.is_symlink()):
            entry.update(
                {
                    "phase": "deleted",
                    "updated_at": _iso_now(),
                    "cleanup": {"status": "never_created", "completed_at": _iso_now()},
                }
            )
            save_entry(entry)
            receipts.append(dict(entry["cleanup"]))
            continue
        if (
            entry.get("phase") in {"allocating", "allocation_failed"}
            and entry.get("device") is None
            and (path.exists() or path.is_symlink())
        ):
            _validate_entry_shape(entry)
            expected_name = f"codex-task-{entry['owner_key'][:12]}-{entry['label']}-{entry['nonce'][:12]}"
            if path.parent != canonical_root or path.name != expected_name or path.is_symlink() or not path.is_dir():
                raise TaskTempError(f"incomplete temporary root allocation has an unsafe path: {path}")
            reserved_stat = path.lstat()
            if reserved_stat.st_uid != os.getuid() or stat.S_IMODE(reserved_stat.st_mode) & 0o077:
                raise TaskTempError(f"incomplete temporary root allocation has unsafe ownership or permissions: {path}")
            if any(path.iterdir()):
                raise TaskTempError(f"incomplete temporary root allocation contains unknown content: {path}")
            path.rmdir()
            entry.update(
                {
                    "phase": "deleted",
                    "updated_at": _iso_now(),
                    "cleanup": {"status": "incomplete_allocation_removed", "completed_at": _iso_now()},
                }
            )
            save_entry(entry)
            actions.append(f"removed incomplete exact task-owned temporary root {path}")
            receipts.append(dict(entry["cleanup"]))
            continue
        if entry.get("phase") in {"deleting", "cleanup_failed", "root_deleted"} and not (path.exists() or path.is_symlink()):
            _validate_base_root(storage_root)
            if sidecar.exists() or sidecar.is_symlink():
                _validate_marker_file(sidecar, entry)
                try:
                    sidecar.unlink()
                except OSError as exc:
                    raise TaskTempError(f"cannot remove temporary root ownership sidecar {sidecar}: {exc}") from exc
            elif entry.get("phase") != "root_deleted":
                raise TaskTempError(f"deleted temporary root lacks its exact ownership sidecar: {sidecar}")
            entry["cleanup"].update({"status": "deleted", "completed_at": _iso_now(), "resumed_after_absent_root": True})
            entry.update({"phase": "deleted", "updated_at": _iso_now()})
            save_entry(entry)
            receipts.append(dict(entry["cleanup"]))
            continue
        if entry.get("phase") not in {"active", "allocating", "deleting", "cleanup_failed", "allocation_failed"}:
            raise TaskTempError(f"owned temporary root has unsupported lifecycle phase: {path}: {entry.get('phase')}")
        if entry.get("device") is None or entry.get("inode") is None or entry.get("marker_sha256") is None:
            raise TaskTempError(f"owned temporary root lacks completed creation proof: {path}")
        prior_phase = entry.get("phase")
        if sidecar.exists() or sidecar.is_symlink():
            if prior_phase not in {"deleting", "cleanup_failed"}:
                raise TaskTempError(f"temporary root ownership sidecar unexpectedly exists: {sidecar}")
            _validate_marker_file(sidecar, entry)
        root_stat = _validate_owned_root(path, base_root=storage_root, entry=entry)
        live_check(path)
        fingerprint = tree_fingerprint(path)
        estimated_bytes = sum(
            candidate.lstat().st_size
            for candidate in path.rglob("*")
            if not candidate.is_symlink() and candidate.is_file()
        )
        cleanup = {
            "status": "deleting",
            "planned_at": _iso_now(),
            "device": root_stat.st_dev,
            "inode": root_stat.st_ino,
            "fingerprint": fingerprint,
            "estimated_bytes": estimated_bytes,
        }
        entry.update({"phase": "deleting", "cleanup": cleanup, "updated_at": _iso_now()})
        save_entry(entry)
        try:
            current_stat = _validate_owned_root(path, base_root=storage_root, entry=entry)
            if (current_stat.st_dev, current_stat.st_ino) != (cleanup["device"], cleanup["inode"]):
                raise TaskTempError(f"owned temporary root identity changed immediately before deletion: {path}")
            live_check(path)
            if tree_fingerprint(path) != cleanup["fingerprint"]:
                raise TaskTempError(f"owned temporary root contents changed immediately before deletion: {path}")
            if not getattr(shutil.rmtree, "avoids_symlink_attacks", False):
                raise TaskTempError("platform shutil.rmtree cannot avoid symlink attacks")
            marker = path / MARKER_NAME
            if sidecar.exists() or sidecar.is_symlink():
                _validate_marker_file(sidecar, entry)
            else:
                os.replace(marker, sidecar)
            cleanup["marker_sidecar"] = str(sidecar)
            entry["cleanup"] = cleanup
            save_entry(entry)
            shutil.rmtree(path)
            if path.exists() or path.is_symlink():
                raise TaskTempError(f"owned temporary root still exists after deletion: {path}")
            cleanup.update({"status": "root_deleted", "root_deleted_at": _iso_now()})
            entry.update({"phase": "root_deleted", "cleanup": cleanup, "updated_at": _iso_now()})
            save_entry(entry)
        except Exception as exc:
            if not (path.exists() or path.is_symlink()) and cleanup.get("status") == "root_deleted":
                entry.update({"phase": "root_deleted", "cleanup": cleanup, "updated_at": _iso_now()})
            else:
                cleanup.update({"status": "failed", "failed_at": _iso_now(), "error": str(exc)})
                entry.update({"phase": "cleanup_failed", "cleanup": cleanup, "updated_at": _iso_now()})
            save_entry(entry)
            raise TaskTempError(f"temporary root cleanup stopped; receipt retained for {path}: {exc}") from exc
        cleanup.update({"status": "deleted", "completed_at": _iso_now()})
        try:
            sidecar.unlink()
        except OSError as exc:
            raise TaskTempError(
                f"temporary root is deleted but its resumable ownership sidecar remains: {sidecar}: {exc}"
            ) from exc
        entry.update({"phase": "deleted", "cleanup": cleanup, "updated_at": _iso_now()})
        save_entry(entry)
        actions.append(f"deleted exact task-owned temporary root {path}")
        receipts.append(dict(cleanup))
    return {"verified": True, "actions": actions, "receipts": receipts, "artifact_count": len(entries)}
