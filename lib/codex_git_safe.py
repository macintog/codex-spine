from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - stock Python 3.9 fallback
    from toml_compat import tomllib
import unicodedata
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


UTC = timezone.utc

from codex_git_environment import BLOCK_END, BLOCK_START, active_managed_repo_root, managed_links, shared_git_hooks_path, shell_source_targets
from codex_git_scratch import (
    SCRATCH_RESCUE_ROOT,
    SCRATCH_ROOT,
    automation_cwds,
    dir_size,
    is_ephemeral_checkout_path,
    is_scratch_path,
    load_index_registry,
    load_registry,
    prune_empty_scratch_dirs,
    prune_empty_parent_dirs,
    recent_session_cwds,
    save_index_registry,
    save_registry,
    scratch_id_for_path,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKTREE_DIR = ".codex-worktrees"
PUSH_HELPER_ENV = "CODEX_GITEA_PUSH_HELPER"
PR_HELPER_ENV = "CODEX_GITEA_PR_HELPER"
PR_FINALIZE_HELPER_ENV = "CODEX_GITEA_PR_FINALIZE_HELPER"
PROJECT_CHECKPOINT_HELPER_ENV = "CODEX_PROJECT_CHECKPOINT_HELPER"
STATE_SCHEMA_VERSION = 9
REPAIR_GRACE_PERIOD = timedelta(hours=0)
PUBLISH_SAFE_STATES = {
    "ready_to_finish",
    "ready_to_push",
    "published_for_review",
    "review_pending",
    "ready_for_integration",
    "complete",
}
_CONTROL_LOCKS: dict[Path, tuple[Any, int, int]] = {}
_CONTROL_THREAD_LOCKS: dict[Path, threading.RLock] = {}


@contextmanager
def _integration_lock(common_dir: Path):
    """Serialize control-plane state and integration, safely across nested helpers."""
    lock_path = common_dir / "codex-git-safe" / "integration.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_key = lock_path.resolve(strict=False)
    owner = threading.get_ident()
    thread_lock = _CONTROL_THREAD_LOCKS.setdefault(lock_key, threading.RLock())
    thread_lock.acquire()
    try:
        held = _CONTROL_LOCKS.get(lock_key)
        if held is None:
            lock_file = lock_path.open("a+", encoding="utf-8")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            _CONTROL_LOCKS[lock_key] = (lock_file, 0, owner)
        lock_file, depth, lock_owner = _CONTROL_LOCKS[lock_key]
        if lock_owner != owner:
            raise RuntimeError("codex-git-safe control-plane lock owner changed unexpectedly")
        _CONTROL_LOCKS[lock_key] = (lock_file, depth + 1, owner)
        try:
            yield
        finally:
            lock_file, depth, lock_owner = _CONTROL_LOCKS[lock_key]
            if depth == 1:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
                del _CONTROL_LOCKS[lock_key]
            else:
                _CONTROL_LOCKS[lock_key] = (lock_file, depth - 1, lock_owner)
    finally:
        thread_lock.release()


class GitSafeError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        blockers: list[str] | None = None,
        data: dict[str, Any] | None = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.blockers = blockers or [message]
        self.data = data or {}
        self.exit_code = exit_code


@dataclass(frozen=True)
class WorktreeEntry:
    path: Path
    branch: str | None
    head: str | None
    detached: bool
    locked: str | None
    prunable: str | None


@dataclass(frozen=True)
class RepoState:
    cwd: Path
    repo_root: Path
    git_dir: Path
    common_dir: Path
    branch: str | None
    head: str
    detached: bool
    upstream: str | None
    worktrees: list[WorktreeEntry]
    dirty: bool
    staged: int
    unstaged: int
    untracked: int


@dataclass(frozen=True)
class AuthorityAssessment:
    default_branch: str | None
    default_ref: str | None
    current_branch: str | None
    current_vs_default: str | None
    current_is_default_branch: bool
    current_has_local_only_state: bool
    current_is_authoritative_default: bool
    reason: str


@dataclass(frozen=True)
class ManagedChange:
    branch: str | None
    authoritative_branch: str | None
    lifecycle: str
    checkout_path: str | None
    mode: str | None
    created_at: str | None
    updated_at: str | None
    phase: str = "working"
    parking_ref: str | None = None
    bundle_path: str | None = None
    integrated_tip: str | None = None
    canonical_dirty_fingerprint: str | None = None
    task_class: str = "ordinary"
    ignored_output_baseline: dict[str, str] | None = None
    published_tip: str | None = None
    base_tip: str | None = None
    review_remote: str | None = None
    review_ref: str | None = None
    review_url: str | None = None
    selected_refs: tuple[str, ...] = ()
    start_tip: str | None = None
    validation_summary: str | None = None
    checkpoint_generation: int | None = None
    checkpoint_updated_at: str | None = None
    registration_origin: str = "manual"
    task_class_provisional: bool = False


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_now() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(timestamp: str | None) -> datetime | None:
    if not timestamp:
        return None
    normalized = timestamp.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _managed_state_path(common_dir: Path) -> Path:
    return common_dir / "codex-git-safe" / "state.json"


def _lifecycle_config(repo_root: Path) -> dict[str, Any]:
    """Read optional repo-owned lifecycle declarations; absent/malformed is inert."""
    path = repo_root / ".codex" / "git-lifecycle.toml"
    if not path.exists():
        return {}
    try:
        loaded = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise GitSafeError(f"invalid lifecycle config: {path}: {exc}")
    return loaded if isinstance(loaded, dict) else {}


def _thread_closeout_mode(repo_root: Path) -> str:
    section = _lifecycle_config(repo_root).get("workflow", {})
    mode = section.get("thread_closeout", "integrate") if isinstance(section, dict) else "integrate"
    if mode not in {"integrate", "pull_request"}:
        raise GitSafeError("workflow.thread_closeout must be 'integrate' or 'pull_request'")
    return mode


def _integration_task_classes(repo_root: Path) -> set[str]:
    section = _lifecycle_config(repo_root).get("workflow", {})
    values = section.get("integration_task_classes", ["integration"]) if isinstance(section, dict) else ["integration"]
    if not isinstance(values, list) or not values or not all(isinstance(item, str) for item in values):
        raise GitSafeError("workflow.integration_task_classes must be a non-empty string array")
    return {_normalize_task_class(item) for item in values}


def _is_integration_task(repo_root: Path, task_class: str) -> bool:
    return task_class in _integration_task_classes(repo_root)


def _declared_ignored_task_outputs(repo_root: Path) -> list[str]:
    section = _lifecycle_config(repo_root).get("ignored_outputs", {})
    globs = section.get("task_relevant_globs", []) if isinstance(section, dict) else []
    if not isinstance(globs, list) or not all(isinstance(item, str) and item for item in globs):
        raise GitSafeError("ignored_outputs.task_relevant_globs must be an array of non-empty strings")
    return list(globs)


def _declared_ignored_output_paths(repo_root: Path) -> list[str]:
    globs = _declared_ignored_task_outputs(repo_root)
    if not globs:
        return []
    proc = _run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "--", *globs],
        cwd=repo_root,
    )
    if proc.returncode != 0:
        raise GitSafeError(proc.stderr.strip() or proc.stdout.strip() or "could not inspect declared ignored outputs")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _ignored_output_snapshot(repo_root: Path) -> dict[str, str]:
    """Fingerprint declared ignored outputs without exposing their contents."""
    snapshot: dict[str, str] = {}
    for relative in _declared_ignored_output_paths(repo_root):
        path = repo_root / relative
        if path.is_symlink():
            snapshot[relative] = f"symlink:{os.readlink(path)}"
            continue
        if not path.is_file():
            snapshot[relative] = "other"
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        snapshot[relative] = f"sha256:{digest.hexdigest()}"
    return snapshot


def _ignored_output_delta(repo_root: Path, baseline: dict[str, str] | None) -> list[dict[str, str]]:
    current = _ignored_output_snapshot(repo_root)
    if baseline is None:
        return [{"path": path, "change": "unbaselined"} for path in sorted(current)]
    delta: list[dict[str, str]] = []
    for path in sorted(set(baseline) | set(current)):
        before = baseline.get(path)
        after = current.get(path)
        if before == after:
            continue
        change = "created" if before is None else "deleted" if after is None else "modified"
        delta.append({"path": path, "change": change})
    return delta


def _normalize_task_class(value: str | None) -> str:
    task_class = (value or "ordinary").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", task_class):
        raise GitSafeError("task class must be 1-64 URL-safe characters")
    return task_class


def _normalize_check_task_class(value: str) -> str:
    if value == "*":
        return value
    return _normalize_task_class(value)


def _declared_closeout_checks(repo_root: Path) -> list[dict[str, Any]]:
    section = _lifecycle_config(repo_root).get("closeout", {})
    checks = section.get("checks", []) if isinstance(section, dict) else []
    if not isinstance(checks, list):
        raise GitSafeError("closeout.checks must be an array of tables")
    normalized: list[dict[str, Any]] = []
    for check in checks:
        if not isinstance(check, dict):
            raise GitSafeError("each closeout check must be a table")
        name = check.get("name")
        command = check.get("command")
        task_classes = check.get("task_classes", ["ordinary"])
        if not isinstance(name, str) or not name.strip():
            raise GitSafeError("closeout check name must be a non-empty string")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            raise GitSafeError(f"closeout check {name!r} command must be a non-empty string array")
        if not isinstance(task_classes, list) or not task_classes or not all(isinstance(item, str) for item in task_classes):
            raise GitSafeError(f"closeout check {name!r} task_classes must be a non-empty string array")
        normalized.append({"name": name.strip(), "command": list(command), "task_classes": [_normalize_check_task_class(item) for item in task_classes]})
    return normalized


def _semantic_closeout_results(repo_root: Path, task_class: str) -> list[dict[str, Any]]:
    state = _repo_state(repo_root)
    assessment = _authority_assessment(state)
    authoritative_branch = assessment.default_branch or _branch_name_from_ref(
        assessment.default_ref, repo_root=repo_root
    )
    canonical_checkout = state.common_dir.parent if state.common_dir.name == ".git" else repo_root
    replacements = {
        "{task_checkout}": str(repo_root),
        "{repo_root}": str(repo_root),
        "{canonical_checkout}": str(canonical_checkout),
        "{authoritative_branch}": authoritative_branch or "",
        "{authoritative_ref}": assessment.default_ref or "",
    }
    results: list[dict[str, Any]] = []
    for check in _declared_closeout_checks(repo_root):
        if "*" not in check["task_classes"] and task_class not in check["task_classes"]:
            continue
        command: list[str] = []
        invalid_placeholder = None
        for argument in check["command"]:
            rendered = argument
            for placeholder, value in replacements.items():
                rendered = rendered.replace(placeholder, value)
            unknown = re.search(r"\{[A-Za-z][A-Za-z0-9_]*\}", rendered)
            if unknown:
                invalid_placeholder = unknown.group(0)
                break
            command.append(rendered)
        if invalid_placeholder is not None:
            results.append({
                "name": check["name"],
                "command": check["command"],
                "ok": False,
                "error": f"unknown closeout placeholder: {invalid_placeholder}",
            })
            continue
        try:
            proc = subprocess.run(
                command, cwd=str(repo_root), check=False, capture_output=True,
                text=True, timeout=30,
            )
            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()
            results.append({
                "name": check["name"], "command": command, "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                **({"stdout": stdout[:4000]} if stdout else {}),
                **({"stderr": stderr[:4000]} if stderr else {}),
            })
        except subprocess.TimeoutExpired:
            results.append({"name": check["name"], "command": command, "ok": False, "error": "timed out after 30 seconds"})
        except OSError as exc:
            results.append({"name": check["name"], "command": command, "ok": False, "error": str(exc)})
    return results


def _load_managed_state(common_dir: Path) -> dict[str, Any]:
    # goal_broker_transactions is retained only so older state files round-trip
    # without destructive schema migration. No current command consumes it.
    path = _managed_state_path(common_dir)
    if not path.exists():
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "active_change": None,
            "active_changes": [],
            "parked_changes": [],
            "retired_changes": [],
            "submitted_changes": [],
            "integrated_changes": [],
            "goal_broker_transactions": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "active_change": None,
            "active_changes": [],
            "parked_changes": [],
            "retired_changes": [],
            "submitted_changes": [],
            "integrated_changes": [],
            "goal_broker_transactions": [],
        }
    payload.setdefault("schema_version", STATE_SCHEMA_VERSION)
    payload.setdefault("active_change", None)
    payload.setdefault("active_changes", [])
    payload.setdefault("parked_changes", [])
    payload.setdefault("retired_changes", [])
    payload.setdefault("submitted_changes", [])
    payload.setdefault("integrated_changes", [])
    payload.setdefault("goal_broker_transactions", [])
    for item in payload["submitted_changes"]:
        if isinstance(item, dict) and not item.get("queue_id"):
            queue_identity = "\0".join(
                str(item.get(key) or "") for key in ("review_url", "review_ref", "published_tip")
            )
            item["queue_id"] = hashlib.sha256(queue_identity.encode("utf-8")).hexdigest()[:16]
    return payload


def _save_managed_state(common_dir: Path, payload: dict[str, Any]) -> None:
    path = _managed_state_path(common_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["schema_version"] = STATE_SCHEMA_VERSION
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def _managed_change_from_payload(payload: dict[str, Any] | None) -> ManagedChange | None:
    if not payload:
        return None
    return ManagedChange(
        branch=payload.get("branch"),
        authoritative_branch=payload.get("authoritative_branch"),
        lifecycle=payload.get("lifecycle", "working"),
        checkout_path=payload.get("checkout_path"),
        mode=payload.get("mode"),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
        phase=payload.get("phase") or payload.get("lifecycle", "working"),
        parking_ref=payload.get("parking_ref"),
        bundle_path=payload.get("bundle_path"),
        integrated_tip=payload.get("integrated_tip"),
        canonical_dirty_fingerprint=payload.get("canonical_dirty_fingerprint"),
        task_class=_normalize_task_class(payload.get("task_class")),
        ignored_output_baseline=payload.get("ignored_output_baseline") if isinstance(payload.get("ignored_output_baseline"), dict) else None,
        published_tip=payload.get("published_tip"),
        base_tip=payload.get("base_tip"),
        review_remote=payload.get("review_remote"),
        review_ref=payload.get("review_ref"),
        review_url=payload.get("review_url"),
        selected_refs=tuple(item for item in payload.get("selected_refs", []) if isinstance(item, str)),
        start_tip=payload.get("start_tip"),
        validation_summary=payload.get("validation_summary"),
        checkpoint_generation=(
            payload.get("checkpoint_generation")
            if isinstance(payload.get("checkpoint_generation"), int)
            else None
        ),
        checkpoint_updated_at=payload.get("checkpoint_updated_at"),
        registration_origin=(
            payload.get("registration_origin")
            if payload.get("registration_origin") in {"manual", "session_start"}
            else "manual"
        ),
        task_class_provisional=payload.get("task_class_provisional") is True,
    )


def _set_active_change(
    state: RepoState,
    *,
    branch: str | None,
    authoritative_branch: str | None,
    lifecycle: str,
    checkout_path: Path | None,
    mode: str | None,
    parking_ref: str | None = None,
    bundle_path: str | None = None,
    phase: str | None = None,
    integrated_tip: str | None = None,
    canonical_dirty_fingerprint: str | None = None,
    task_class: str | None = None,
    ignored_output_baseline: dict[str, str] | None = None,
    published_tip: str | None = None,
    base_tip: str | None = None,
    review_remote: str | None = None,
    review_ref: str | None = None,
    review_url: str | None = None,
    selected_refs: list[str] | tuple[str, ...] | None = None,
    start_tip: str | None = None,
    validation_summary: str | None = None,
    checkpoint_generation: int | None = None,
    checkpoint_updated_at: str | None = None,
    registration_origin: str | None = None,
    task_class_provisional: bool | None = None,
) -> None:
    with _integration_lock(state.common_dir):
        payload = _load_managed_state(state.common_dir)
        checkout_key = _checkout_identity(checkout_path)
        existing = next(
            (item for item in payload.get("active_changes", []) if _payload_checkout_identity(item) == checkout_key),
            None,
        )
        # `active_change` is a legacy convenience pointer, never an ownership
        # source.  Inheriting it here would transfer timestamps/phases between
        # concurrent checkout identities.
        current = _managed_change_from_payload(existing)
        created_at = current.created_at if current else _iso_now()
        change_payload = {
            "branch": branch,
            "authoritative_branch": authoritative_branch,
            "lifecycle": lifecycle,
            "checkout_path": str(checkout_path) if checkout_path is not None else None,
            "checkout_identity": checkout_key,
            "mode": mode,
            "created_at": created_at,
            "updated_at": _iso_now(),
            "parking_ref": parking_ref,
            "bundle_path": bundle_path,
            "phase": phase or (current.phase if current else lifecycle),
            "integrated_tip": integrated_tip if integrated_tip is not None else (current.integrated_tip if current else None),
            "canonical_dirty_fingerprint": canonical_dirty_fingerprint if canonical_dirty_fingerprint is not None else (current.canonical_dirty_fingerprint if current else None),
            "task_class": _normalize_task_class(task_class if task_class is not None else (current.task_class if current else None)),
            "ignored_output_baseline": ignored_output_baseline if ignored_output_baseline is not None else (current.ignored_output_baseline if current else None),
            "published_tip": published_tip if published_tip is not None else (current.published_tip if current else None),
            "base_tip": base_tip if base_tip is not None else (current.base_tip if current else None),
            "review_remote": review_remote if review_remote is not None else (current.review_remote if current else None),
            "review_ref": review_ref if review_ref is not None else (current.review_ref if current else None),
            "review_url": review_url if review_url is not None else (current.review_url if current else None),
            "selected_refs": list(selected_refs if selected_refs is not None else (current.selected_refs if current else ())),
            "start_tip": start_tip if start_tip is not None else (current.start_tip if current else None),
            "validation_summary": validation_summary if validation_summary is not None else (current.validation_summary if current else None),
            "checkpoint_generation": checkpoint_generation if checkpoint_generation is not None else (current.checkpoint_generation if current else None),
            "checkpoint_updated_at": checkpoint_updated_at if checkpoint_updated_at is not None else (current.checkpoint_updated_at if current else None),
            "registration_origin": registration_origin if registration_origin is not None else (current.registration_origin if current else "manual"),
            "task_class_provisional": task_class_provisional if task_class_provisional is not None else (current.task_class_provisional if current else False),
        }
        changes = [item for item in payload.get("active_changes", []) if _payload_checkout_identity(item) != checkout_key]
        changes.append(change_payload)
        payload["active_changes"] = changes
        payload["active_change"] = change_payload
        _save_managed_state(state.common_dir, payload)


def _clear_active_change_unlocked(state: RepoState, *, branch: str | None = None, checkout_path: Path | None = None) -> None:
    payload = _load_managed_state(state.common_dir)
    current = _managed_active_change(state, _authority_assessment(state)) if branch is None else None
    target_branch = branch or (current.branch if current is not None else None)
    target_identity = _checkout_identity(checkout_path) if checkout_path is not None else (
        _checkout_identity(Path(current.checkout_path)) if current and current.checkout_path else None
    )
    if target_identity is not None:
        payload["active_changes"] = [
            item for item in payload.get("active_changes", []) if _payload_checkout_identity(item) != target_identity
        ]
    elif target_branch is not None:
        payload["active_changes"] = [
            item for item in payload.get("active_changes", []) if item.get("branch") != target_branch
        ]
    legacy = payload.get("active_change") or {}
    if (
        (target_identity is not None and _payload_checkout_identity(legacy) == target_identity)
        or (target_identity is None and target_branch is not None and legacy.get("branch") == target_branch)
    ):
        payload["active_change"] = None
    _save_managed_state(state.common_dir, payload)


def _clear_active_change(state: RepoState, *, branch: str | None = None, checkout_path: Path | None = None) -> None:
    with _integration_lock(state.common_dir):
        _clear_active_change_unlocked(state, branch=branch, checkout_path=checkout_path)


def _record_retired_change(state: RepoState, change: ManagedChange) -> None:
    with _integration_lock(state.common_dir):
        payload = _load_managed_state(state.common_dir)
        identity = _checkout_identity(Path(change.checkout_path)) if change.checkout_path else None
        record = {
            "branch": change.branch, "authoritative_branch": change.authoritative_branch,
            "checkout_path": change.checkout_path, "checkout_identity": identity, "mode": change.mode,
            "task_class": change.task_class,
            "integrated_tip": change.integrated_tip,
            "selected_refs": list(change.selected_refs),
            "validation_summary": change.validation_summary,
            "checkpoint_generation": change.checkpoint_generation,
            "checkpoint_updated_at": change.checkpoint_updated_at,
            "created_at": change.created_at, "updated_at": _iso_now(), "lifecycle": "retired", "phase": "retired",
        }
        payload["retired_changes"] = [item for item in payload.get("retired_changes", []) if _payload_checkout_identity(item) != identity]
        payload["retired_changes"].append(record)
        _save_managed_state(state.common_dir, payload)


def _submitted_change_record(change: ManagedChange) -> dict[str, Any]:
    queue_identity = "\0".join((change.review_url or "", change.review_ref or "", change.published_tip or ""))
    record = {
        "queue_id": hashlib.sha256(queue_identity.encode("utf-8")).hexdigest()[:16],
        "branch": change.branch,
        "authoritative_branch": change.authoritative_branch,
        "task_class": change.task_class,
        "published_tip": change.published_tip,
        "base_tip": change.base_tip,
        "review_remote": change.review_remote,
        "review_ref": change.review_ref,
        "review_url": change.review_url,
        "validation_summary": change.validation_summary,
        "checkpoint_generation": change.checkpoint_generation,
        "checkpoint_updated_at": change.checkpoint_updated_at,
        "created_at": change.created_at,
        "submitted_at": _iso_now(),
        "lifecycle": "ready_for_integration",
    }
    return {key: value for key, value in record.items() if value is not None}


def _record_submitted_change(state: RepoState, change: ManagedChange) -> dict[str, Any]:
    with _integration_lock(state.common_dir):
        payload = _load_managed_state(state.common_dir)
        record = _submitted_change_record(change)
        published_tip = record.get("published_tip")
        review_ref = record.get("review_ref")
        matching_reviews = [
            (index, item)
            for index, item in enumerate(payload.get("submitted_changes", []))
            if (isinstance(review_ref, str) and review_ref and item.get("review_ref") == review_ref)
        ]
        if matching_reviews:
            _, latest_review = max(
                matching_reviews,
                key=lambda indexed: (str(indexed[1].get("submitted_at") or ""), indexed[0]),
            )
            stable_queue_id = latest_review.get("queue_id")
            if isinstance(stable_queue_id, str) and stable_queue_id:
                record["queue_id"] = stable_queue_id
        submitted = [
            item
            for item in payload.get("submitted_changes", [])
            if item.get("published_tip") != published_tip
            and item.get("branch") != change.branch
            and item.get("queue_id") != record.get("queue_id")
            and not (isinstance(review_ref, str) and review_ref and item.get("review_ref") == review_ref)
        ]
        submitted.append(record)
        payload["submitted_changes"] = submitted
        _save_managed_state(state.common_dir, payload)
        return record


def _reconcile_integrated_submissions(
    state: RepoState,
    authoritative_branch: str,
    selected_refs: tuple[str, ...],
) -> list[dict[str, Any]]:
    with _integration_lock(state.common_dir):
        payload = _load_managed_state(state.common_dir)
        selected_ref_set = set(selected_refs)
        remaining: list[dict[str, Any]] = []
        integrated = list(payload.get("integrated_changes", []))
        newly_integrated: list[dict[str, Any]] = []
        for item in payload.get("submitted_changes", []):
            if item.get("review_ref") not in selected_ref_set:
                remaining.append(item)
                continue
            tip = item.get("published_tip")
            if not isinstance(tip, str) or not _is_ancestor(tip, authoritative_branch, cwd=state.repo_root):
                remaining.append(item)
                continue
            record = {**item, "lifecycle": "integrated", "integrated_at": _iso_now()}
            integrated = [existing for existing in integrated if existing.get("published_tip") != tip]
            integrated.append(record)
            newly_integrated.append(record)
        payload["submitted_changes"] = remaining
        payload["integrated_changes"] = integrated
        _save_managed_state(state.common_dir, payload)
        return newly_integrated


def _integrated_submission_candidates(
    state: RepoState,
    authoritative_branch: str,
    selected_refs: tuple[str, ...],
) -> list[dict[str, Any]]:
    payload = _load_managed_state(state.common_dir)
    selected_ref_set = set(selected_refs)
    return [
        item
        for item in payload.get("submitted_changes", [])
        if item.get("review_ref") in selected_ref_set
        and isinstance(item.get("published_tip"), str)
        and _is_ancestor(item["published_tip"], authoritative_branch, cwd=state.repo_root)
    ]


def _gitea_review_urls_match_remote(remote_url: str, review_urls: list[str]) -> bool:
    """Recognize only same-repository Gitea web PR URLs over HTTP(S)."""
    remote = urlparse(remote_url)
    try:
        remote_port = remote.port
    except ValueError:
        return False
    if remote.scheme not in {"http", "https"} or not remote.hostname:
        return False
    repo_path = remote.path.removesuffix(".git").rstrip("/")
    if not repo_path or not review_urls:
        return False
    for review_url in review_urls:
        review = urlparse(review_url)
        try:
            review_port = review.port
        except ValueError:
            return False
        if (
            review.scheme not in {"http", "https"}
            or review.hostname != remote.hostname
            or review_port != remote_port
        ):
            return False
        suffix = review.path[len(repo_path):] if review.path.startswith(repo_path) else ""
        if not re.fullmatch(r"/pulls/[1-9][0-9]*/?", suffix):
            return False
    return True


def _finalize_integrated_gitea_reviews(
    state: RepoState,
    records: list[dict[str, Any]],
    authoritative_tip: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[tuple[str, str]]] = {}
    for item in records:
        remote = item.get("review_remote")
        url = item.get("review_url")
        tip = item.get("published_tip")
        if isinstance(remote, str) and isinstance(url, str) and url and isinstance(tip, str):
            grouped.setdefault(remote, []).append((url, tip))
    results: list[dict[str, Any]] = []
    for remote, entries in sorted(grouped.items()):
        remote_url_proc = _run(["git", "remote", "get-url", remote], cwd=state.repo_root)
        if remote_url_proc.returncode != 0:
            raise GitSafeError(f"could not resolve review remote for hosted finalization: {remote}")
        remote_url = remote_url_proc.stdout.strip()
        urls = [url for url, _tip in entries]
        # Provider detection is exact and fail-closed: SSH remotes, host
        # mismatches, and other providers' PR URL shapes remain external.
        if not _gitea_review_urls_match_remote(remote_url, urls):
            results.append({"remote": remote, "state": "external_provider", "review_urls": urls})
            continue
        args = ["--remote", remote, "--commit", authoritative_tip, "--json"]
        for url, tip in entries:
            args.extend(["--pr-url", url, "--pr-head", tip])
        proc = _delegate_helper_process(
            PR_FINALIZE_HELPER_ENV,
            "codex-gitea-pr-finalize.sh",
            args,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise GitSafeError((proc.stderr or proc.stdout or "Gitea pull request finalization failed").strip())
        try:
            payload = json.loads((proc.stdout or "").strip())
        except json.JSONDecodeError as exc:
            raise GitSafeError("Gitea pull request finalization returned invalid JSON") from exc
        results.append(payload)
    return results


def _append_parked_change(state: RepoState, change: ManagedChange) -> None:
    with _integration_lock(state.common_dir):
        payload = _load_managed_state(state.common_dir)
        parked = [item for item in payload.get("parked_changes", []) if item.get("branch") != change.branch]
        parked.append(
            {
                "branch": change.branch,
                "authoritative_branch": change.authoritative_branch,
                "lifecycle": "parked",
                "checkout_path": change.checkout_path,
                "mode": change.mode,
                "task_class": change.task_class,
                "ignored_output_baseline": change.ignored_output_baseline,
                "created_at": change.created_at,
                "updated_at": _iso_now(),
                "parking_ref": change.parking_ref,
                "bundle_path": change.bundle_path,
            }
        )
        payload["parked_changes"] = parked
        legacy_active_change = payload.get("active_change")
        if isinstance(legacy_active_change, dict) and legacy_active_change.get("branch") == change.branch:
            payload["active_change"] = None
        _save_managed_state(state.common_dir, payload)


def _scratch_checkout_path(repo_root: Path, branch: str) -> Path:
    digest = hashlib.sha1(f"{repo_root}:{branch}".encode("utf-8")).hexdigest()[:8]
    return SCRATCH_ROOT / digest / repo_root.name


def _json_dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _print_json(payload: Any) -> None:
    print(_json_dump(payload))


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = False,
    text: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        check=check,
        capture_output=True,
        text=text,
    )


def _git(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = _run(["git", *args], cwd=cwd, check=False)
    if check and proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip() or "git command failed"
        raise GitSafeError(stderr)
    return proc


def _git_output(args: list[str], *, cwd: Path | None = None) -> str:
    return _git(args, cwd=cwd).stdout.strip()


def _git_bytes(args: list[str], *, cwd: Path) -> bytes:
    """Bytes-safe Git output for preservation proofs; never decode file content."""
    proc = subprocess.run(["git", *args], cwd=str(cwd), check=False, capture_output=True, text=False)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip() or "git command failed"
        raise GitSafeError(detail)
    return proc.stdout


def _comparison_path(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _resolve_path(path_value: str | None, *, base: Path) -> Path | None:
    if path_value is None:
        return None
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _checkout_identity(path: Path | None) -> str | None:
    """The checkout path is the task identity; branch names are only metadata."""
    return str(path.expanduser().resolve(strict=False)) if path is not None else None


def _payload_checkout_identity(payload: dict[str, Any]) -> str | None:
    raw = payload.get("checkout_identity") or payload.get("checkout_path")
    return _checkout_identity(Path(raw)) if raw else None


def _is_disposable_codex_worktree(state: RepoState) -> bool:
    """Only app-created linked worktrees are eligible for automatic adoption."""
    app_root = (Path.home() / ".codex" / "worktrees").resolve(strict=False)
    return (
        (state.detached or bool(state.branch and state.branch.startswith("codex/")))
        and state.git_dir.resolve(strict=False) != state.common_dir.resolve(strict=False)
        and _is_inside(state.repo_root.resolve(strict=False), app_root)
        and _worktree_entry_for_path(state, state.repo_root) is not None
    )


def _adoption_branch(state: RepoState, topic: str | None = None) -> str:
    # App worktrees normally live at ~/.codex/worktrees/<id>/<repo>.  Include a
    # short path digest so separate app worktrees with the same visible id do
    # not silently share a branch.
    worktree_id = _slugify(state.repo_root.parent.name)
    slug = _slugify(topic or state.repo_root.name)
    digest = hashlib.sha1(_checkout_identity(state.repo_root).encode("utf-8")).hexdigest()[:8]
    return f"codex/{worktree_id}-{slug}-{digest}"


def _provisional_task_class_promotion_blockers(
    state: RepoState,
    change: ManagedChange,
    requested_task_class: str,
) -> list[str]:
    blockers: list[str] = []
    current_tip = _ref_commit("HEAD", cwd=state.repo_root)
    if change.registration_origin != "session_start" or not change.task_class_provisional:
        blockers.append("the existing task class was not provisionally assigned at session start")
    if change.task_class != "ordinary":
        blockers.append(f"the provisional task class is not ordinary: {change.task_class}")
    if requested_task_class not in _integration_task_classes(state.repo_root):
        blockers.append(f"requested task class is not a configured integration class: {requested_task_class}")
    if state.dirty:
        blockers.append("the checkout already has content changes")
    if change.start_tip is None or current_tip != change.start_tip:
        blockers.append(
            f"checkout HEAD no longer matches the recorded start tip: {current_tip} != {change.start_tip or 'missing'}"
        )
    if change.lifecycle != "working" or change.phase != "working":
        blockers.append(f"the task already advanced beyond working: {change.lifecycle}/{change.phase}")
    if change.published_tip or change.review_ref or change.review_url or change.selected_refs:
        blockers.append("the task already carries publication or integration state")
    return blockers


def _adopt_current_worktree(
    state: RepoState,
    *,
    topic: str | None,
    task_class: str | None,
    apply: bool,
    if_eligible: bool = False,
    provisional_ordinary: bool = False,
) -> dict[str, Any]:
    """Register one app-owned worktree; attach it only when it is detached."""
    if provisional_ordinary and task_class is not None and _normalize_task_class(task_class) != "ordinary":
        raise GitSafeError("provisional session adoption can only assign the ordinary task class")
    if is_ephemeral_checkout_path(state.repo_root):
        raise GitSafeError(
            "adopt-current refuses a worktree under temporary storage",
            blockers=[
                f"move the checkout out of temporary storage before adoption: {state.repo_root}",
                "managed task worktrees belong under the durable ~/.codex/worktrees root",
            ],
        )
    assessment = _authority_assessment(state)
    existing = _managed_active_change(state, assessment)
    if not _is_disposable_codex_worktree(state):
        if if_eligible:
            return {
                "command": "adopt-current",
                "ok": True,
                "eligible": False,
                "existing": False,
                "checkout_path": str(state.repo_root),
                "actions": [],
            }
        raise GitSafeError(
            "adopt-current only accepts a Codex app worktree on detached HEAD or a codex/* branch",
            blockers=["run it from an app-created linked worktree under ~/.codex/worktrees"],
        )
    if existing is not None:
        requested_task_class = _normalize_task_class(task_class) if task_class is not None else existing.task_class
        promoted = False
        if requested_task_class != existing.task_class:
            promotion_blockers = _provisional_task_class_promotion_blockers(
                state,
                existing,
                requested_task_class,
            )
            if promotion_blockers:
                raise GitSafeError(
                    "adopt-current cannot change the task class of this existing registration",
                    blockers=[
                        f"existing task class: {existing.task_class}",
                        f"requested task class: {requested_task_class}",
                        *promotion_blockers,
                    ],
                )
            if apply:
                _set_active_change(
                    state,
                    branch=existing.branch,
                    authoritative_branch=existing.authoritative_branch,
                    lifecycle=existing.lifecycle,
                    checkout_path=state.repo_root,
                    mode=existing.mode,
                    phase=existing.phase,
                    task_class=requested_task_class,
                    task_class_provisional=False,
                )
                existing = _managed_active_change(
                    _repo_state(state.repo_root),
                    _authority_assessment(_repo_state(state.repo_root)),
                ) or existing
                promoted = True
        actions: list[str] = []
        if promoted:
            actions.append(f"promoted provisional task class to {requested_task_class}")
        if existing.mode != "worktree" and apply:
            # This exact checkout identity was registered by an older lifecycle
            # schema before app worktrees had explicit ownership.  Preserve its
            # branch, phase, and timestamps; only correct the ownership mode.
            with _integration_lock(state.common_dir):
                payload = _load_managed_state(state.common_dir)
                identity = _checkout_identity(state.repo_root)
                for item in payload.get("active_changes", []):
                    if _payload_checkout_identity(item) == identity:
                        item["mode"] = "worktree"
                        if _payload_checkout_identity(payload.get("active_change") or {}) == identity:
                            payload["active_change"] = item
                        _save_managed_state(state.common_dir, payload)
                        break
            existing = ManagedChange(
                branch=existing.branch, authoritative_branch=existing.authoritative_branch,
                lifecycle=existing.lifecycle, checkout_path=existing.checkout_path, mode="worktree",
                created_at=existing.created_at, updated_at=existing.updated_at, phase=existing.phase,
                parking_ref=existing.parking_ref, bundle_path=existing.bundle_path,
                integrated_tip=existing.integrated_tip,
                canonical_dirty_fingerprint=existing.canonical_dirty_fingerprint,
                task_class=existing.task_class,
                ignored_output_baseline=existing.ignored_output_baseline,
                registration_origin=existing.registration_origin,
                task_class_provisional=existing.task_class_provisional,
            )
            actions.append("normalized legacy app-worktree registration to mode=worktree")
        hook_posture = _ensure_adopted_hook_guard(_repo_state(state.repo_root)) if apply else None
        if hook_posture and hook_posture["status"] == "installed":
            actions.append("installed managed pre-commit guard")
        return {"command": "adopt-current", "ok": True, "eligible": True, "existing": True, "branch": existing.branch,
                "checkout_path": existing.checkout_path, "phase": existing.phase, "task_class": existing.task_class,
                "start_tip": existing.start_tip, "task_class_provisional": existing.task_class_provisional,
                "hook_posture": hook_posture, "actions": actions}
    if state.dirty:
        raise GitSafeError(
            "adopt-current cannot prove a clean isolation baseline after edits exist",
            blockers=["adopt the app worktree before the first edit or generated write"],
        )
    branch = state.branch or _adoption_branch(state, topic)
    if state.branch is None and _run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=state.repo_root).returncode == 0:
        raise GitSafeError(f"adoption branch already exists: {branch}")
    actions: list[str] = []
    hook_posture: dict[str, Any] | None = None
    if apply:
        if state.detached:
            proc = _run(["git", "switch", "-c", branch], cwd=state.repo_root)
            if proc.returncode != 0:
                raise GitSafeError(proc.stderr.strip() or proc.stdout.strip() or "could not attach adoption branch")
        refreshed = _repo_state(state.repo_root)
        _set_active_change(
            refreshed,
            branch=branch,
            authoritative_branch=assessment.default_branch or _branch_name_from_ref(assessment.default_ref, repo_root=state.repo_root),
            lifecycle="working",
            checkout_path=refreshed.repo_root,
            mode="worktree",
            phase="working",
            task_class=_normalize_task_class(task_class),
            ignored_output_baseline=_ignored_output_snapshot(refreshed.repo_root),
            start_tip=_ref_commit("HEAD", cwd=refreshed.repo_root),
            registration_origin="session_start" if provisional_ordinary else "manual",
            task_class_provisional=provisional_ordinary,
        )
        actions.append(f"adopted Codex app worktree on {branch}")
        hook_posture = _ensure_adopted_hook_guard(refreshed)
        if hook_posture["status"] == "installed":
            actions.append("installed managed pre-commit guard")
    return {"command": "adopt-current", "ok": True, "eligible": True, "existing": False, "branch": branch,
            "checkout_path": str(state.repo_root), "phase": "working", "task_class": _normalize_task_class(task_class),
            "start_tip": _ref_commit("HEAD", cwd=state.repo_root), "task_class_provisional": provisional_ordinary,
            "hook_posture": hook_posture, "actions": actions}


def _test_stop_after(phase: str) -> None:
    """Deterministic crash point for lifecycle fixture tests; inert in normal use."""
    if os.environ.get("CODEX_GIT_SAFE_TEST_STOP_AFTER") == phase:
        raise GitSafeError(f"test stop after persisted phase {phase}", blockers=[f"resume from {phase}"], exit_code=75)


def _ensure_adopted_hook_guard(state: RepoState) -> dict[str, Any]:
    """Install the managed guard only into an otherwise unconfigured repo."""
    managed_override = os.environ.get("CODEX_GIT_SAFE_MANAGED_HOOKS_PATH")
    managed = (Path(managed_override).expanduser() if managed_override else shared_git_hooks_path()).resolve(strict=False)
    pre_commit = managed / "pre-commit"
    if not pre_commit.is_file() or not os.access(pre_commit, os.X_OK):
        return {"status": "unavailable", "managed_path": str(managed), "note": "managed pre-commit guard is unavailable"}
    proc = _run(["git", "config", "--local", "--get", "core.hooksPath"], cwd=state.repo_root)
    if proc.returncode == 1 or not proc.stdout.strip():
        set_proc = _run(["git", "config", "--local", "core.hooksPath", str(managed)], cwd=state.repo_root)
        if set_proc.returncode != 0:
            return {"status": "warning", "managed_path": str(managed), "note": set_proc.stderr.strip() or "could not configure managed hook guard"}
        return {"status": "installed", "managed_path": str(managed)}
    configured = proc.stdout.strip()
    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        candidate = state.repo_root / candidate
    if candidate.resolve(strict=False) == managed:
        return {"status": "managed", "managed_path": str(managed)}
    return {"status": "custom", "configured_path": configured, "managed_path": str(managed), "note": "preserved existing repo-local core.hooksPath"}


def _status_path_from_line(line: str) -> str:
    raw = line[3:] if len(line) > 3 else ""
    if " -> " in raw:
        raw = raw.split(" -> ", 1)[1]
    return raw.strip()


def _ignore_status_line(line: str) -> bool:
    if not line.startswith("??"):
        return False
    raw_path = _status_path_from_line(line)
    return raw_path == DEFAULT_WORKTREE_DIR or raw_path.startswith(f"{DEFAULT_WORKTREE_DIR}/")


def _status_lines(cwd: Path) -> list[str]:
    status_output = _git_output(["status", "--porcelain=v1"], cwd=cwd)
    return [line for line in status_output.splitlines() if line.strip() and not _ignore_status_line(line)]


def _short_ref(ref: str | None) -> str | None:
    if ref is None:
        return None
    for prefix in ("refs/heads/", "refs/remotes/"):
        if ref.startswith(prefix):
            return ref[len(prefix) :]
    return ref


def _is_inside(path: Path, maybe_parent: Path) -> bool:
    try:
        path.relative_to(maybe_parent)
        return True
    except ValueError:
        return False


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip(".-_")
    return slug or "topic"


def _normalize_branch_name(topic: str) -> str:
    raw = topic.strip()
    if not raw:
        raise GitSafeError("topic is required")

    parts = [part for part in raw.split("/") if part.strip()]
    cleaned = [_slugify(part) for part in parts]
    branch = "/".join(part for part in cleaned if part)
    if not branch:
        raise GitSafeError("topic could not be normalized into a branch name")
    if "/" not in raw:
        branch = f"codex/{branch}"
    return branch


def _branch_slug(branch: str) -> str:
    return _slugify(branch.replace("/", "-"))


def _worktree_root_for_branch(repo_root: Path, branch: str) -> Path:
    return _scratch_checkout_path(repo_root, branch)


def _repo_state(cwd: Path) -> RepoState:
    repo_root_text = _git_output(["rev-parse", "--show-toplevel"], cwd=cwd)
    if not repo_root_text:
        raise GitSafeError("current directory is not inside a git repository")
    repo_root = Path(repo_root_text).resolve()

    git_dir = Path(_git_output(["rev-parse", "--absolute-git-dir"], cwd=cwd)).resolve()
    common_dir_raw = Path(_git_output(["rev-parse", "--git-common-dir"], cwd=cwd))
    # Git is allowed to return a relative common-dir. Resolve it relative to
    # the queried repository, never this Python process's unrelated cwd.
    common_dir = (common_dir_raw if common_dir_raw.is_absolute() else repo_root / common_dir_raw).resolve()

    branch = None
    detached = False
    branch_result = _run(["git", "symbolic-ref", "-q", "--short", "HEAD"], cwd=repo_root)
    if branch_result.returncode == 0:
        branch = branch_result.stdout.strip() or None
    else:
        detached = True

    head = _git_output(["rev-parse", "--short", "HEAD"], cwd=repo_root)
    upstream = None
    if branch is not None:
        upstream_result = _run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=repo_root,
        )
        if upstream_result.returncode == 0:
            upstream = upstream_result.stdout.strip() or None

    status_lines = _status_lines(repo_root)
    status = "\n".join(status_lines)
    dirty = bool(status)
    staged = 0
    unstaged = 0
    untracked = 0
    for line in status_lines:
        if line.startswith("??"):
            untracked += 1
            continue
        if len(line) >= 2:
            if line[0] != " ":
                staged += 1
            if line[1] != " ":
                unstaged += 1

    worktrees = _parse_worktree_list(_git_output(["worktree", "list", "--porcelain"], cwd=repo_root))
    return RepoState(
        cwd=cwd,
        repo_root=repo_root,
        git_dir=git_dir,
        common_dir=common_dir,
        branch=branch,
        head=head,
        detached=detached,
        upstream=upstream,
        worktrees=worktrees,
        dirty=dirty,
        staged=staged,
        unstaged=unstaged,
        untracked=untracked,
    )


def _preflight_payload(cwd: Path) -> tuple[dict[str, Any], int]:
    """Read-only worktree provisioning gate; intentionally usable outside Git."""
    root_proc = _run(["git", "rev-parse", "--show-toplevel"], cwd=cwd)
    if root_proc.returncode != 0:
        return ({
            "command": "preflight", "ok": False, "ready_for_worktree": False,
            "cwd": str(cwd), "git_repository": False,
            "blockers": ["current directory is not inside a Git repository; initialize Git separately before requesting a worktree"],
        }, 1)
    repo_root = Path(root_proc.stdout.strip()).resolve()
    head_proc = _run(["git", "rev-parse", "--verify", "HEAD"], cwd=repo_root)
    if head_proc.returncode != 0:
        return ({
            "command": "preflight", "ok": False, "ready_for_worktree": False,
            "cwd": str(cwd), "git_repository": True, "repo_root": str(repo_root),
            "initial_commit_exists": False,
            "blockers": ["repository has no initial commit; create one before requesting a worktree"],
        }, 1)
    state = _repo_state(repo_root)
    assessment = _authority_assessment(state)
    authoritative_branch = assessment.default_branch or _branch_name_from_ref(assessment.default_ref, repo_root=repo_root)
    ephemeral_worktrees = _ephemeral_worktree_records(state)
    canonical_paths = [
        str(entry.path) for entry in state.worktrees
        if authoritative_branch is not None and entry.branch == authoritative_branch
    ]
    # Provisioning starts from the committed authoritative line; dirt is
    # evidence to report, not a reason to pretend the Git project is invalid.
    authoritative_commit = _ref_commit(assessment.default_ref, cwd=repo_root) if assessment.default_ref else None
    usable = bool(authoritative_branch and authoritative_commit) and not ephemeral_worktrees
    blockers: list[str] = []
    if authoritative_branch is None:
        blockers.append("could not infer the authoritative/default branch")
    blockers.extend(_ephemeral_worktree_blockers(state))
    payload = {
        "command": "preflight", "ok": usable, "ready_for_worktree": usable,
        "cwd": str(cwd), "git_repository": True, "repo_root": str(repo_root),
        "initial_commit_exists": True, "authoritative_branch": authoritative_branch,
        "authoritative_ref": assessment.default_ref, "canonical_checkout_paths": canonical_paths,
        "authoritative_commit": authoritative_commit,
        "dirty": state.dirty, "authoritative_checkout_dirty": any(_path_status_counts(Path(path))["dirty"] for path in canonical_paths),
        "blockers": blockers,
    }
    if not canonical_paths:
        payload["notes"] = ["no checkout is currently on the authoritative branch; provisioning will use the verified authoritative ref"]
    if ephemeral_worktrees:
        payload["ephemeral_worktrees"] = ephemeral_worktrees
    return payload, 0 if usable else 1


def _parse_worktree_list(payload: str) -> list[WorktreeEntry]:
    entries: list[WorktreeEntry] = []
    current: dict[str, Any] = {}

    def flush() -> None:
        nonlocal current
        if not current:
            return
        path = Path(current["path"]).resolve()
        entries.append(
            WorktreeEntry(
                path=path,
                branch=_short_ref(current.get("branch")),
                head=current.get("head"),
                detached=bool(current.get("detached")),
                locked=current.get("locked"),
                prunable=current.get("prunable"),
            )
        )
        current = {}

    for line in payload.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            flush()
            current["path"] = value
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = value
        elif key == "detached":
            current["detached"] = True
        elif key == "locked":
            current["locked"] = value or "true"
        elif key == "prunable":
            current["prunable"] = value or "true"
    flush()
    return entries


def _ephemeral_worktree_records(state: RepoState) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in state.worktrees:
        if not is_ephemeral_checkout_path(entry.path):
            continue
        record: dict[str, Any] = {
            "path": str(entry.path),
            "exists": entry.path.exists(),
            "detached": entry.detached,
        }
        if entry.branch is not None:
            record["branch"] = entry.branch
        if entry.head is not None:
            record["head"] = entry.head
        if entry.locked is not None:
            record["locked"] = entry.locked
        if entry.prunable is not None:
            record["prunable"] = entry.prunable
        records.append(record)
    return records


def _ephemeral_worktree_blockers(state: RepoState) -> list[str]:
    return [
        f"registered Git worktree uses forbidden temporary storage: {item['path']}"
        for item in _ephemeral_worktree_records(state)
    ]


def _ephemeral_worktree_repair_records(
    state: RepoState,
    *,
    authoritative_ref: str | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    base_records = {item["path"]: item for item in _ephemeral_worktree_records(state)}
    for entry in state.worktrees:
        if not is_ephemeral_checkout_path(entry.path):
            continue
        record = base_records[str(entry.path)]
        record["safe_to_prune"] = False
        if entry.path.exists():
            record["reason"] = "temporary worktree path still exists and may contain data"
            records.append(record)
            continue
        if not entry.prunable:
            record["reason"] = "Git has not marked the missing worktree metadata prunable"
            records.append(record)
            continue
        if entry.head is None:
            record["reason"] = "missing worktree has no recorded HEAD to prove preserved"
            records.append(record)
            continue

        candidate_refs = [entry.branch, authoritative_ref]
        for ref in dict.fromkeys(item for item in candidate_refs if item):
            try:
                preserved_tip = _ref_commit(ref, cwd=state.repo_root)
            except GitSafeError:
                continue
            if not _is_ancestor(entry.head, preserved_tip, cwd=state.repo_root):
                continue
            record["safe_to_prune"] = True
            record["preserved_by"] = ref
            record["reason"] = "missing worktree HEAD is preserved by a durable Git ref"
            break
        if not record["safe_to_prune"]:
            record["reason"] = "missing worktree HEAD is not proven preserved by its branch or authoritative line"
        records.append(record)
    return records


def _ref_commit(ref: str, *, cwd: Path) -> str:
    result = _run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=cwd)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or f"invalid ref: {ref}"
        raise GitSafeError(stderr)
    return result.stdout.strip()


def _is_ancestor(ancestor: str, descendant: str, *, cwd: Path) -> bool:
    result = _run(["git", "merge-base", "--is-ancestor", ancestor, descendant], cwd=cwd)
    return result.returncode == 0


def _patch_equivalent_to_ref(branch: str, preserved_ref: str, *, cwd: Path) -> bool:
    result = _run(["git", "cherry", preserved_ref, branch], cwd=cwd)
    if result.returncode != 0:
        return False
    return all(line.startswith("-") for line in result.stdout.splitlines() if line.strip())


def _resolve_base_ref(
    state: RepoState,
    explicit_base: str | None,
    *,
    target_branch: str | None,
) -> str:
    if explicit_base:
        return explicit_base

    if target_branch is not None:
        branch_upstream = _run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{target_branch}@{{u}}"],
            cwd=state.repo_root,
        )
        if branch_upstream.returncode == 0:
            inferred = branch_upstream.stdout.strip()
            if inferred:
                return inferred

    if target_branch is not None and target_branch == state.branch and state.upstream:
        return state.upstream

    origin_head = _run(
        ["git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"],
        cwd=state.repo_root,
    )
    if origin_head.returncode == 0:
        inferred = origin_head.stdout.strip()
        if inferred:
            return inferred

    if state.branch:
        return state.branch

    raise GitSafeError("could not infer a base ref; pass --base explicitly")


def _worktree_path_for_entry(entries: list[WorktreeEntry], branch: str | None) -> Path | None:
    if branch is None:
        return None
    matches = [entry.path for entry in entries if entry.branch == branch]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise GitSafeError(
            f"branch '{branch}' is checked out in multiple worktrees; cleanup cannot guess a target"
        )
    return None


def _authoritative_control_checkout(
    state: RepoState,
    authoritative_branch: str,
    *,
    exclude_path: Path,
) -> Path | None:
    """Find a checkout that is actually on the authoritative branch."""
    normalized = _branch_name_from_ref(authoritative_branch, repo_root=state.repo_root) or authoritative_branch
    exact = _worktree_path_for_entry(state.worktrees, normalized)
    if (
        exact is not None
        and exact.resolve(strict=False) != exclude_path.resolve(strict=False)
        and not is_ephemeral_checkout_path(exact)
    ):
        return exact
    return None


def _repository_control_checkout(
    state: RepoState,
    *,
    exclude_path: Path,
) -> Path | None:
    """Find a persistent checkout from which task-only retirement is safe."""
    excluded = exclude_path.resolve(strict=False)
    candidates = [
        entry.path
        for entry in state.worktrees
        if (
            entry.path.resolve(strict=False) != excluded
            and entry.path.is_dir()
            and not is_ephemeral_checkout_path(entry.path)
        )
    ]
    if not candidates:
        return None

    primary = state.common_dir.parent.resolve(strict=False) if state.common_dir.name == ".git" else None
    if primary is not None:
        for candidate in candidates:
            if candidate.resolve(strict=False) == primary:
                return candidate

    return sorted(candidates, key=lambda path: (is_scratch_path(path), str(path)))[0]


def _branch_checked_out_elsewhere(
    state: RepoState,
    branch: str,
    *,
    exclude_path: Path | None = None,
) -> list[Path]:
    excluded = exclude_path.resolve() if exclude_path is not None else state.repo_root
    return [
        entry.path
        for entry in state.worktrees
        if entry.branch == branch and entry.path != excluded
    ]


def _reclaim_clean_worktrees_for_branch(
    state: RepoState,
    branch: str,
    *,
    exclude_path: Path | None = None,
) -> list[str]:
    actions: list[str] = []
    excluded = exclude_path.resolve() if exclude_path is not None else None
    for entry in state.worktrees:
        if entry.branch != branch:
            continue
        if excluded is not None and entry.path == excluded:
            continue
        if entry.locked:
            raise GitSafeError(f"branch '{branch}' is checked out in a locked worktree: {entry.path}")
        status_counts = _path_status_counts(entry.path)
        if status_counts["dirty"]:
            raise GitSafeError(f"branch '{branch}' is checked out in a dirty worktree: {entry.path}")
        remove_proc = _run(["git", "worktree", "remove", str(entry.path)], cwd=state.repo_root)
        if remove_proc.returncode != 0:
            detail = remove_proc.stderr.strip() or remove_proc.stdout.strip() or f"could not remove worktree {entry.path}"
            raise GitSafeError(detail)
        actions.append(f"removed clean worktree {entry.path} from {branch}")
        if is_scratch_path(entry.path):
            actions.extend(_remove_index_registry_paths({entry.path}))
            _remove_registry_paths({entry.path})
    return actions


def _worktree_entry_for_path(state: RepoState, worktree_path: Path) -> WorktreeEntry | None:
    for entry in state.worktrees:
        if entry.path == worktree_path.resolve():
            return entry
    return None


def _current_worktree_is_inside_target(current: Path, target: Path | None) -> bool:
    if target is None:
        return False
    return _is_inside(current.resolve(), target.resolve())


def _unique_commits(base_ref: str, branch_ref: str, *, cwd: Path) -> list[str]:
    result = _run(["git", "rev-list", f"{base_ref}..{branch_ref}"], cwd=cwd)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "could not compute unique commits"
        raise GitSafeError(stderr)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _branch_name_from_ref(ref: str | None, *, repo_root: Path | None = None) -> str | None:
    if ref is not None and ref.startswith("refs/remotes/"):
        remote_ref = ref[len("refs/remotes/") :]
        _, separator, branch = remote_ref.partition("/")
        return branch if separator else remote_ref
    short = _short_ref(ref)
    if short is None:
        return None
    if short.startswith("refs/"):
        return short
    remote, separator, branch = short.partition("/")
    if separator and repo_root is not None and remote in _remote_names(repo_root):
        return branch
    return short


def _path_status_counts(path: Path) -> dict[str, int | bool]:
    status_lines = _status_lines(path)
    dirty = bool(status_lines)
    staged = 0
    unstaged = 0
    untracked = 0
    for line in status_lines:
        if line.startswith("??"):
            untracked += 1
            continue
        if len(line) >= 2:
            if line[0] != " ":
                staged += 1
            if line[1] != " ":
                unstaged += 1
    return {
        "dirty": dirty,
        "staged_changes": staged,
        "unstaged_changes": unstaged,
        "untracked_files": untracked,
    }


def _default_ref_with_local_authority(state: RepoState, branch_name: str, remote_ref: str) -> str:
    """Keep committed local default history when its tracking ref is stale."""
    local_ref = f"refs/heads/{branch_name}"
    if _run(["git", "show-ref", "--verify", "--quiet", local_ref], cwd=state.repo_root).returncode != 0:
        return remote_ref
    local_tip = _ref_commit(branch_name, cwd=state.repo_root)
    remote_tip = _ref_commit(remote_ref, cwd=state.repo_root)
    if local_tip and (not remote_tip or not _is_ancestor(local_tip, remote_tip, cwd=state.repo_root)):
        return branch_name
    return remote_ref


def _default_branch_ref(state: RepoState) -> tuple[str | None, str | None]:
    origin_head = _run(
        ["git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"],
        cwd=state.repo_root,
    )
    if origin_head.returncode == 0:
        inferred = origin_head.stdout.strip()
        if inferred:
            branch_name = _branch_name_from_ref(inferred, repo_root=state.repo_root)
            # Never discard an ahead local default line merely because no
            # checkout currently occupies it.  The remote tracking ref is
            # usable only when it is at least as new as that local authority.
            if branch_name:
                return branch_name, _default_ref_with_local_authority(state, branch_name, inferred)
            return branch_name, inferred

    for branch_name in ("main", "master", "trunk"):
        local_ref = f"refs/heads/{branch_name}"
        if _run(["git", "show-ref", "--verify", "--quiet", local_ref], cwd=state.repo_root).returncode == 0:
            remote_ref = f"refs/remotes/origin/{branch_name}"
            if _run(["git", "show-ref", "--verify", "--quiet", remote_ref], cwd=state.repo_root).returncode == 0:
                return branch_name, _default_ref_with_local_authority(state, branch_name, f"origin/{branch_name}")
            return branch_name, branch_name

    if state.upstream:
        return _branch_name_from_ref(state.upstream, repo_root=state.repo_root), state.upstream

    if state.branch:
        return state.branch, state.branch

    return None, None


def _authority_assessment(state: RepoState) -> AuthorityAssessment:
    default_branch, default_ref = _default_branch_ref(state)
    current_branch = state.branch
    current_vs_default = None
    current_is_default_branch = bool(current_branch and default_branch and current_branch == default_branch)
    current_has_local_only_state = state.dirty
    current_is_authoritative_default = False
    reason = "no current branch"

    if current_branch and default_ref:
        current_tip = _ref_commit(current_branch, cwd=state.repo_root)
        default_tip = _ref_commit(default_ref, cwd=state.repo_root)
        if current_tip == default_tip:
            current_vs_default = "same"
        elif _is_ancestor(default_tip, current_tip, cwd=state.repo_root):
            current_vs_default = "ahead"
        elif _is_ancestor(current_tip, default_tip, cwd=state.repo_root):
            current_vs_default = "behind"
        else:
            current_vs_default = "diverged"

        if current_vs_default in {"ahead", "diverged"}:
            current_has_local_only_state = True

        if current_is_default_branch:
            current_is_authoritative_default = True
            if current_has_local_only_state:
                reason = "current default branch carries local-only state"
            else:
                reason = "current default branch matches the inferred default line"
        elif current_has_local_only_state:
            reason = "current branch carries local-only state but is not the inferred default branch"
        else:
            reason = "current branch does not carry local-only state and is not the inferred default branch"
    elif current_branch:
        current_has_local_only_state = state.dirty
        current_is_authoritative_default = state.dirty
        if state.dirty:
            reason = "no inferred default line; current branch is the only local line with state"
        else:
            reason = "no inferred default line; current branch is clean"

    return AuthorityAssessment(
        default_branch=default_branch,
        default_ref=default_ref,
        current_branch=current_branch,
        current_vs_default=current_vs_default,
        current_is_default_branch=current_is_default_branch,
        current_has_local_only_state=current_has_local_only_state,
        current_is_authoritative_default=current_is_authoritative_default,
        reason=reason,
    )


def _start_source_plan(
    state: RepoState,
    *,
    explicit_base: str | None,
    from_current: bool,
) -> tuple[str, str, list[str], list[str]]:
    blockers: list[str] = []
    notes: list[str] = []
    assessment = _authority_assessment(state)

    if explicit_base:
        return explicit_base, "explicit-base", blockers, notes

    if from_current:
        if state.branch:
            return state.branch, "from-current", blockers, notes
        return "HEAD", "from-current", blockers, notes

    if assessment.current_is_authoritative_default and assessment.current_has_local_only_state and state.branch:
        return state.branch, "authoritative-current", blockers, notes

    if assessment.current_has_local_only_state and not assessment.current_is_authoritative_default:
        blockers.append(
            "current branch carries local-only state but is not the inferred authoritative default line; pass --from-current or --base explicitly"
        )
        if assessment.default_ref:
            return assessment.default_ref, "ambiguous-current", blockers, notes
        if state.branch:
            return state.branch, "ambiguous-current", blockers, notes
        raise GitSafeError("could not infer a base ref; pass --base explicitly")

    if assessment.default_ref:
        return assessment.default_ref, "default-ref", blockers, notes

    if state.branch:
        return state.branch, "current-branch-fallback", blockers, notes

    raise GitSafeError("could not infer a base ref; pass --base explicitly")


def _start_mode_plan(
    state: RepoState,
    *,
    mode: str,
    base_ref: str,
    source_strategy: str,
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    notes: list[str] = []
    resolved_mode = mode
    auto_requested = mode == "auto"

    if resolved_mode == "auto":
        # Ordinary mutating work always starts in an isolated checkout.  A
        # clean canonical checkout is not permission to switch it to a topic
        # branch; doing so destroys the baseline that yeet later proves.
        resolved_mode = "worktree"

    if resolved_mode == "worktree" and state.dirty:
        if source_strategy == "from-current" or auto_requested:
            notes.append("dirty changes stay in the current checkout; the new isolated checkout starts from the selected committed line")
        else:
            blockers.append("current checkout is dirty; pass --from-current to confirm an isolated checkout from the current committed line or use branch mode")

    return resolved_mode, blockers, notes


def _changed_paths_between(base_ref: str, head_ref: str, *, cwd: Path) -> set[str]:
    return _normalized_changed_paths([f"{base_ref}..{head_ref}"], cwd=cwd)


def _dirty_paths(path: Path) -> set[str]:
    dirty_paths: set[str] = set()
    for line in _status_lines(path):
        if not line.strip():
            continue
        raw = _status_path_from_line(line)
        if raw:
            dirty_paths.add(raw)
    return dirty_paths


def _normalized_changed_paths(args: list[str], *, cwd: Path) -> set[str]:
    """Return every changed endpoint, including both sides of a rename."""
    try:
        proc = _run(["git", "diff", "--name-status", "-z", "-M", *args], cwd=cwd)
    except UnicodeDecodeError as exc:
        raise GitSafeError(f"non-UTF-8 changed path prevents dirty-target preservation: {exc}")
    if proc.returncode != 0:
        raise GitSafeError(proc.stderr.strip() or "could not enumerate changed paths")
    fields = proc.stdout.split("\0")
    paths: set[str] = set()
    index = 0
    while index < len(fields) and fields[index]:
        status = fields[index]
        index += 1
        if index >= len(fields):
            raise GitSafeError("could not parse changed-path status")
        paths.add(fields[index])
        index += 1
        if status[:1] in {"R", "C"}:
            if index >= len(fields):
                raise GitSafeError("could not parse rename/copy destination")
            paths.add(fields[index])
            index += 1
    folded: dict[str, str] = {}
    for item in paths:
        key = _comparison_path(item)
        if key in folded and folded[key] != item:
            raise GitSafeError("Unicode-normalized case-folded changed-path collision prevents dirty-target preservation")
        folded[key] = item
    return set(folded)


def _file_manifest_entry(path: Path, *, relative: str) -> dict[str, str]:
    try:
        stat = path.lstat()
    except OSError as exc:
        raise GitSafeError(f"cannot fingerprint untracked path {relative}: {exc}")
    if not path.is_file() or path.is_symlink():
        raise GitSafeError(f"untracked path is not a regular readable file: {relative}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise GitSafeError(f"cannot read untracked path {relative}: {exc}")
    return {"path": relative, "type": "file", "mode": oct(stat.st_mode & 0o7777), "sha256": digest.hexdigest()}


def _dirty_fingerprint(path: Path) -> dict[str, Any]:
    """Fingerprint only preservation-safe ordinary Git dirt; otherwise fail closed."""
    git_dir = Path(_git_output(["rev-parse", "--absolute-git-dir"], cwd=path))
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG", "rebase-merge", "rebase-apply"):
        if (git_dir / marker).exists():
            raise GitSafeError(f"special Git operation prevents dirty-target preservation: {marker}")
    if _run(["git", "ls-files", "--stage", "--", ".gitmodules"], cwd=path).stdout.strip():
        raise GitSafeError("submodule configuration prevents dirty-target preservation")
    modes = _git_output(["ls-files", "--stage"], cwd=path)
    if any(line.startswith("160000 ") for line in modes.splitlines()):
        raise GitSafeError("submodule entry prevents dirty-target preservation")
    flags = _git_output(["ls-files", "-v"], cwd=path)
    if any(line[:1] == "S" or line[:1].islower() for line in flags.splitlines() if line):
        raise GitSafeError("skip-worktree or assume-unchanged entry prevents dirty-target preservation")
    staged_paths = _normalized_changed_paths(["--cached"], cwd=path)
    unstaged_paths = _normalized_changed_paths([], cwd=path)
    untracked_bytes = _git_bytes(["ls-files", "--others", "--exclude-standard", "-z"], cwd=path)
    manifest: list[dict[str, str]] = []
    try:
        untracked_paths = [item.decode("utf-8", errors="strict") for item in untracked_bytes.split(b"\0") if item]
    except UnicodeDecodeError as exc:
        raise GitSafeError(f"non-UTF-8 untracked path prevents dirty-target preservation: {exc}")
    for relative in sorted(untracked_paths):
        candidate = path / relative
        if candidate.is_dir() and not candidate.is_symlink():
            for nested in sorted(candidate.rglob("*")):
                if nested.name == ".git" or nested.is_dir() and (nested / ".git").exists():
                    raise GitSafeError(f"nested repository prevents dirty-target preservation: {relative}")
            raise GitSafeError(f"untracked directory prevents dirty-target preservation: {relative}")
        manifest.append(_file_manifest_entry(candidate, relative=relative))
    # Keep raw Git output strictly local to this calculation.  It can contain
    # source text or secrets, so JSON payloads retain only fixed digests.
    status_bytes = _git_bytes(["status", "--porcelain=v2", "-z", "--untracked-files=all"], cwd=path)
    staged_bytes = _git_bytes(["diff", "--cached", "--binary", "--full-index"], cwd=path)
    unstaged_bytes = _git_bytes(["diff", "--binary", "--full-index"], cwd=path)
    normalized_untracked = {_comparison_path(item["path"]) for item in manifest}
    payload = {
        "status_sha256": hashlib.sha256(status_bytes).hexdigest(),
        "staged_diff_sha256": hashlib.sha256(staged_bytes).hexdigest(),
        "unstaged_diff_sha256": hashlib.sha256(unstaged_bytes).hexdigest(),
        "dirty_paths": sorted(staged_paths | unstaged_paths | normalized_untracked), "untracked": manifest,
    }
    comparison_paths = staged_paths | unstaged_paths | normalized_untracked
    raw_paths = list(staged_paths | unstaged_paths) + [item["path"] for item in manifest]
    seen: dict[str, str] = {}
    for raw in raw_paths:
        normalized = _comparison_path(raw)
        if normalized in seen and seen[normalized] != raw:
            raise GitSafeError("Unicode-normalized case-folded dirty-path collision prevents preservation")
        seen[normalized] = raw
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"digest": hashlib.sha256(encoded).hexdigest(), "paths": comparison_paths, "proof": payload}


def _managed_active_change(state: RepoState, assessment: AuthorityAssessment) -> ManagedChange | None:
    payload = _load_managed_state(state.common_dir)
    identity = _checkout_identity(state.repo_root)
    for item in payload.get("active_changes", []):
        managed = _managed_change_from_payload(item)
        if managed is None:
            continue
        if _payload_checkout_identity(item) == identity:
            return managed
    return None


def _managed_active_checkout_paths(state: RepoState) -> set[Path]:
    payload = _load_managed_state(state.common_dir)
    paths: set[Path] = set()
    for item in payload.get("active_changes", []):
        identity = _payload_checkout_identity(item)
        if identity is not None:
            paths.add(Path(identity).resolve(strict=False))
    return paths


def _registered_scratch_paths(state: RepoState) -> set[Path]:
    registry = load_registry()
    paths: set[Path] = set()
    for path_value, item in registry.get("entries", {}).items():
        resolved = Path(path_value).expanduser().resolve(strict=False)
        if not is_scratch_path(resolved):
            continue
        repo_root_value = item.get("repo_root")
        if repo_root_value:
            candidate_repo_root = Path(str(repo_root_value)).expanduser().resolve(strict=False)
            if candidate_repo_root != state.repo_root.resolve(strict=False):
                continue
        elif resolved.name != state.repo_root.name:
            continue
        paths.add(resolved)
    for entry in state.worktrees:
        if is_scratch_path(entry.path):
            paths.add(entry.path.resolve(strict=False))
    repo_name = state.repo_root.name
    if SCRATCH_ROOT.exists():
        for candidate in SCRATCH_ROOT.glob(f"*/{repo_name}"):
            paths.add(candidate.resolve(strict=False))
    return paths


def _live_managed_link_leaks(repo_root: Path) -> list[str]:
    leaks: list[str] = []
    for link in managed_links(repo_root):
        if not link.live_path.is_symlink():
            continue
        target = link.live_path.resolve(strict=False)
        if is_scratch_path(target):
            leaks.append(f"{link.live_path} -> {target}")
    managed_block_pattern = re.compile(
        re.escape(BLOCK_START) + r"(?P<body>.*?)" + re.escape(BLOCK_END),
        re.S,
    )
    for dotfile in shell_source_targets().keys():
        if not dotfile.exists():
            continue
        try:
            content = dotfile.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in managed_block_pattern.finditer(content):
            for candidate in re.findall(r"(/[^'\"\s\]]+)", match.group("body")):
                target = Path(candidate).expanduser().resolve(strict=False)
                if is_scratch_path(target):
                    leaks.append(f"{dotfile} -> {target}")
    return leaks


def _live_owner_mutation_blockers(state: RepoState) -> list[str]:
    blockers: list[str] = []
    try:
        _, _, active_repo_root_errors = active_managed_repo_root()
    except RuntimeError as exc:
        blockers.append(str(exc))
        active_repo_root_errors = []
    blockers.extend(active_repo_root_errors)
    blockers.extend(
        f"managed live path still points into temporary checkout state: {leak}"
        for leak in _live_managed_link_leaks(state.repo_root)
    )
    return blockers


def _remote_names(repo_root: Path) -> list[str]:
    return [line.strip() for line in _git_output(["remote"], cwd=repo_root).splitlines() if line.strip()]


def _git_config_values(repo_root: Path, key: str) -> list[str]:
    proc = _run(["git", "config", "--get-all", key], cwd=repo_root)
    if proc.returncode not in {0, 1}:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"git config --get-all {key} failed"
        raise GitSafeError(detail)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _remote_url(repo_root: Path, remote: str) -> str | None:
    proc = _run(["git", "remote", "get-url", remote], cwd=repo_root)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _keeper_remote_targets(state: RepoState, authoritative_branch: str | None) -> list[dict[str, str]]:
    if not authoritative_branch:
        return []
    candidates: list[tuple[str, str]] = []
    lifecycle_config = _lifecycle_config(state.repo_root)
    keeper_config = lifecycle_config.get("keeper", {}) if isinstance(lifecycle_config.get("keeper", {}), dict) else {}
    declared_remotes = keeper_config.get("remotes", [])
    if not isinstance(declared_remotes, list) or not all(isinstance(item, str) and item for item in declared_remotes):
        raise GitSafeError("keeper.remotes must be an array of non-empty remote names")
    configured_names = set(_remote_names(state.repo_root))
    missing_declared = [remote for remote in declared_remotes if remote not in configured_names]
    if missing_declared:
        raise GitSafeError(
            "declared keeper remote is not configured",
            blockers=[f"missing declared keeper remote: {remote}" for remote in missing_declared],
        )
    for remote in declared_remotes:
        candidates.append((remote, authoritative_branch))
    for remote in _git_config_values(state.repo_root, "codex.keeperRemote"):
        candidates.append((remote, authoritative_branch))
    for key in ("codex.privateBackupRemote", "remote.pushDefault"):
        for remote in _git_config_values(state.repo_root, key):
            candidates.append((remote, authoritative_branch))
    if state.upstream:
        remote, separator, branch = state.upstream.partition("/")
        if separator and branch == authoritative_branch:
            candidates.append((remote, branch))
    if "origin" in _remote_names(state.repo_root):
        candidates.append(("origin", authoritative_branch))

    targets: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for remote, branch in candidates:
        url = _remote_url(state.repo_root, remote)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        targets.append({"remote": remote, "branch": branch, "url": url})
    return targets


def _keeper_tracking_status(state: RepoState, authoritative_branch: str | None) -> list[dict[str, Any]]:
    if not authoritative_branch:
        return []
    local_head = _ref_commit(authoritative_branch, cwd=state.repo_root)
    statuses: list[dict[str, Any]] = []
    for target in _keeper_remote_targets(state, authoritative_branch):
        tracking_ref = f"refs/remotes/{target['remote']}/{target['branch']}"
        proc = _run(["git", "rev-parse", "--verify", f"{tracking_ref}^{{commit}}"], cwd=state.repo_root)
        remote_head = proc.stdout.strip() if proc.returncode == 0 else None
        relation = "missing"
        if remote_head == local_head:
            relation = "same"
        elif remote_head and _is_ancestor(remote_head, local_head, cwd=state.repo_root):
            relation = "ahead"
        elif remote_head and _is_ancestor(local_head, remote_head, cwd=state.repo_root):
            relation = "behind"
        elif remote_head:
            relation = "diverged"
        statuses.append(
            {
                **target,
                "tracking_ref": tracking_ref,
                "local_head": local_head,
                "remote_head": remote_head,
                "relation": relation,
                "preserved": relation == "same",
            }
        )
    return statuses


def _push_and_verify_keeper_remotes(state: RepoState, authoritative_branch: str, *, canonical_dirty_fingerprint: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    if state.dirty and canonical_dirty_fingerprint is None:
        raise GitSafeError("git magic requires a clean committed authoritative line before pushing")
    if state.dirty:
        current = _dirty_fingerprint(state.repo_root)["digest"]
        if current != canonical_dirty_fingerprint:
            raise GitSafeError("canonical dirty fingerprint changed before keeper push")
    local_head = _ref_commit(authoritative_branch, cwd=state.repo_root)
    targets = _keeper_remote_targets(state, authoritative_branch)
    if not targets:
        raise GitSafeError("git magic requires at least one configured keeper remote")
    actions: list[str] = []
    proofs: list[dict[str, Any]] = []
    for target in targets:
        remote = target["remote"]
        branch = target["branch"]
        push_proc = _run(
            ["git", "push", remote, f"refs/heads/{authoritative_branch}:refs/heads/{branch}"],
            cwd=state.repo_root,
        )
        if push_proc.returncode != 0:
            detail = push_proc.stderr.strip() or push_proc.stdout.strip() or f"git push {remote} failed"
            raise GitSafeError(detail)
        actions.append(f"pushed {authoritative_branch} to keeper {remote}/{branch}")
        verify_proc = _run(
            ["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"],
            cwd=state.repo_root,
        )
        if verify_proc.returncode != 0:
            detail = verify_proc.stderr.strip() or verify_proc.stdout.strip() or f"git ls-remote {remote} failed"
            raise GitSafeError(detail)
        remote_head = verify_proc.stdout.split()[0] if verify_proc.stdout.strip() else None
        verified = remote_head == local_head
        proof = {**target, "local_head": local_head, "remote_head": remote_head, "verified": verified}
        proofs.append(proof)
        if not verified:
            raise GitSafeError(
                f"keeper remote head did not match after push: {remote}/{branch}",
                data={"remote_proof": proof},
            )
        actions.append(f"verified keeper head {remote}/{branch} at {local_head}")
    return proofs, actions


def _integrated_dirty_proof(state: RepoState, change: ManagedChange, authoritative_branch: str) -> str | None:
    """Re-prove the narrow dirty-canonical exception for task closeout only."""
    if not _is_ancestor(change.branch or "", authoritative_branch, cwd=state.repo_root):
        raise GitSafeError("integrated task tip is not preserved by the authoritative branch")
    if not state.dirty:
        return None
    if change.integrated_tip and _ref_commit(authoritative_branch, cwd=state.repo_root) != change.integrated_tip:
        raise GitSafeError("authoritative tip changed after task integration")
    fingerprint = _dirty_fingerprint(state.repo_root)
    if change.canonical_dirty_fingerprint:
        if fingerprint["digest"] != change.canonical_dirty_fingerprint:
            raise GitSafeError("canonical dirty fingerprint changed after integration")
        return fingerprint["digest"]
    # One-time migration baseline for pre-proof integrated records.  The task
    # must already be fully contained and its historical diff must not touch
    # current dirty paths; no canonical mutation occurs on this recovery path.
    merge_base = _git_output(["merge-base", change.branch or "", authoritative_branch], cwd=state.repo_root)
    task_paths = _changed_paths_between(merge_base, change.branch or "", cwd=state.repo_root)
    overlap = task_paths & fingerprint["paths"]
    if overlap:
        raise GitSafeError("legacy integrated task overlaps canonical dirty paths", blockers=[f"overlap: {path}" for path in sorted(overlap)])
    return fingerprint["digest"]


def _remote_tracking_ref_exists(repo_root: Path, remote: str, branch: str) -> bool:
    return (
        _run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}"],
            cwd=repo_root,
        ).returncode
        == 0
    )


def _safe_remote_for_parking(repo_root: Path) -> str | None:
    candidates: list[str] = []
    for key in ("codex.privateBackupRemote", "remote.pushDefault"):
        value = _run(["git", "config", "--get", key], cwd=repo_root).stdout.strip()
        if value:
            candidates.append(value)
    candidates.extend(_remote_names(repo_root))

    seen: set[str] = set()
    for remote in candidates:
        if not remote or remote in seen:
            continue
        seen.add(remote)
        url = _run(["git", "remote", "get-url", remote], cwd=repo_root).stdout.strip()
        if not url:
            continue
        if "://" in url or url.startswith("git@") or url.startswith("ssh://"):
            return remote
    return None


def _scratch_entry_for_path(state: RepoState, path: Path) -> WorktreeEntry | None:
    resolved = path.resolve(strict=False)
    for entry in state.worktrees:
        if entry.path.resolve(strict=False) == resolved:
            return entry
    return None


def _index_registry_projects() -> set[Path]:
    payload = load_index_registry()
    return {
        Path(project).expanduser().resolve(strict=False)
        for project in payload.get("projects", [])
        if project
    }


def _index_registry_without(paths_to_remove: set[Path]) -> dict[str, Any]:
    payload = load_index_registry()
    keep_projects = []
    for project in payload.get("projects", []):
        resolved = Path(project).expanduser().resolve(strict=False)
        if resolved not in paths_to_remove:
            keep_projects.append(str(resolved))
    payload["projects"] = sorted(dict.fromkeys(keep_projects))
    return payload


def _upsert_registry_entry(path: Path, payload: dict[str, Any]) -> None:
    registry = load_registry()
    entries = dict(registry.get("entries", {}))
    entries[str(path.resolve(strict=False))] = payload
    registry["entries"] = entries
    save_registry(registry)


def _remove_registry_paths(paths: set[Path]) -> None:
    registry = load_registry()
    entries = dict(registry.get("entries", {}))
    for path in paths:
        entries.pop(str(path.resolve(strict=False)), None)
    registry["entries"] = entries
    save_registry(registry)


def _worktree_mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def _scratch_residue_entries(state: RepoState, assessment: AuthorityAssessment) -> list[dict[str, Any]]:
    authoritative_ref = assessment.default_ref or assessment.default_branch
    index_projects = _index_registry_projects()
    automation_paths = automation_cwds()
    recent_session_paths = recent_session_cwds()
    active_change = _managed_active_change(state, assessment)
    active_checkout = Path(active_change.checkout_path).resolve(strict=False) if active_change and active_change.checkout_path else None
    managed_active_checkouts = _managed_active_checkout_paths(state)
    now = _utc_now()
    results: list[dict[str, Any]] = []

    for path in sorted(_registered_scratch_paths(state)):
        item: dict[str, Any] = {
            "id": scratch_id_for_path(path) or _branch_slug(str(path)),
            "path": str(path),
            "exists": path.exists(),
            "registered_in_index": path in index_projects,
            "active": False,
            "classification": "needs_investigation",
            "reason": "scratch path is missing evidence",
            "bytes": dir_size(path),
            "locked": False,
            "prunable": False,
            "branch": None,
            "head": None,
            "clean": True,
            "staged_changes": 0,
            "unstaged_changes": 0,
            "untracked_files": 0,
            "status_short": [],
            "untracked_paths": [],
            "has_uncommitted_changes": False,
            "has_local_only_commits": False,
            "preserved_on_authoritative": None,
            "preservation_status": "unknown",
            "recent_session_activity": False,
            "reclaim_deadline_at": None,
            "parking_result": None,
            "age_hours": None,
            "grace_pending": False,
        }
        entry = _scratch_entry_for_path(state, path)
        if entry is not None:
            item["locked"] = bool(entry.locked)
            item["prunable"] = bool(entry.prunable)
            item["branch"] = entry.branch
            item["head"] = entry.head
        if path.exists():
            recent_session_activity = any(session_path == path or _is_inside(session_path, path) for session_path in recent_session_paths)
            item["active"] = (
                _is_inside(state.cwd, path)
                or path == state.cwd
                or path == state.repo_root
                or path in automation_paths
                or recent_session_activity
                or path in managed_active_checkouts
                or bool(item["locked"])
            )
            item["recent_session_activity"] = recent_session_activity
            try:
                status_lines = _status_lines(path)
                status_counts = _path_status_counts(path)
            except GitSafeError:
                item["clean"] = False
                item["has_uncommitted_changes"] = True
                item["has_local_only_commits"] = True
                item["classification"] = "needs_investigation"
                item["reason"] = "scratch path exists but is not a usable Git checkout"
                mtime = _worktree_mtime(path)
                if mtime is not None:
                    item["age_hours"] = round((now - mtime).total_seconds() / 3600, 1)
                    reclaim_at = mtime + REPAIR_GRACE_PERIOD
                    item["reclaim_deadline_at"] = reclaim_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                results.append(item)
                continue
            item["clean"] = not bool(status_counts["dirty"])
            item["staged_changes"] = status_counts["staged_changes"]
            item["unstaged_changes"] = status_counts["unstaged_changes"]
            item["untracked_files"] = status_counts["untracked_files"]
            item["status_short"] = status_lines
            item["untracked_paths"] = [
                line[3:]
                for line in status_lines
                if line.startswith("?? ")
            ]
            item["has_uncommitted_changes"] = bool(status_counts["dirty"])
            if authoritative_ref:
                try:
                    head_ref = _git_output(["rev-parse", "--verify", "HEAD"], cwd=path)
                    authoritative_tip = _ref_commit(authoritative_ref, cwd=state.repo_root)
                    item["head"] = head_ref
                    preserved = _is_ancestor(head_ref, authoritative_tip, cwd=state.repo_root)
                    item["preserved_on_authoritative"] = preserved
                    item["has_local_only_commits"] = not preserved
                    item["preservation_status"] = "authoritative" if preserved else "topic_only"
                except GitSafeError:
                    item["preserved_on_authoritative"] = None
                    item["has_local_only_commits"] = True
                    item["preservation_status"] = "unknown"
            mtime = _worktree_mtime(path)
            if mtime is not None:
                item["age_hours"] = round((now - mtime).total_seconds() / 3600, 1)
                reclaim_at = mtime + REPAIR_GRACE_PERIOD
                item["reclaim_deadline_at"] = reclaim_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        else:
            item["classification"] = "safe_to_delete"
            item["reason"] = "scratch path no longer exists; only metadata cleanup remains"
            results.append(item)
            continue

        reclaimable_by_age = False
        mtime = _worktree_mtime(path)
        if mtime is not None:
            reclaimable_by_age = now - mtime >= REPAIR_GRACE_PERIOD

        if item["active"]:
            if path == active_checkout or path in {state.cwd, state.repo_root}:
                item["classification"] = "current_task"
                item["reason"] = "temporary checkout belongs to the current task"
            else:
                item["classification"] = "concurrent_task"
                item["reason"] = "temporary checkout belongs to another active task"
        elif item["clean"] and item["preserved_on_authoritative"]:
            if reclaimable_by_age:
                item["classification"] = "safe_to_delete"
                item["reason"] = "temporary checkout is clean, preserved, and older than the reclaim grace period"
            else:
                item["classification"] = "needs_investigation"
                item["grace_pending"] = True
                deadline = item.get("reclaim_deadline_at") or "the reclaim deadline"
                item["reason"] = (
                    "temporary checkout is clean and preserved but still inside the reclaim grace period "
                    f"(eligible after {deadline})"
                )
        elif item["has_uncommitted_changes"] or item["has_local_only_commits"]:
            item["classification"] = "auto_park_then_delete"
            item["reason"] = "temporary checkout carries unpublished state and should be parked before deletion"
        else:
            item["classification"] = "needs_investigation"
            item["reason"] = "temporary checkout needs manual investigation"
        results.append(item)

    _sync_scratch_registry(state, results)
    return results


def _scratch_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    safe = [item for item in entries if item["classification"] == "safe_to_delete"]
    autopark = [item for item in entries if item["classification"] == "auto_park_then_delete"]
    grace_pending = [item for item in entries if item.get("grace_pending")]
    needs = [
        item
        for item in entries
        if item["classification"] == "needs_investigation" and not item.get("grace_pending")
    ]
    return {
        "total_count": len(entries),
        "safe_count": len(safe),
        "auto_park_count": len(autopark),
        "decision_count": len(needs),
        "grace_pending_count": len(grace_pending),
        "bytes": sum(int(item.get("bytes", 0)) for item in entries),
        "safe_paths": [item["path"] for item in safe],
        "auto_park_paths": [item["path"] for item in autopark],
        "needs_investigation_paths": [item["path"] for item in needs],
        "grace_pending_paths": [item["path"] for item in grace_pending],
    }


def _sync_scratch_registry(state: RepoState, entries: list[dict[str, Any]]) -> None:
    for item in entries:
        path = Path(item["path"]).resolve(strict=False)
        if not is_scratch_path(path):
            continue
        entry_payload = {
            "id": item.get("id"),
            "repo_root": str(state.repo_root),
            "status": item.get("classification"),
            "branch": item.get("branch"),
            "head": item.get("head"),
            "active": item.get("active"),
            "clean": item.get("clean"),
            "staged_changes": item.get("staged_changes"),
            "unstaged_changes": item.get("unstaged_changes"),
            "untracked_files": item.get("untracked_files"),
            "status_short": item.get("status_short"),
            "untracked_paths": item.get("untracked_paths"),
            "classification": item.get("classification"),
            "reason": item.get("reason"),
            "bytes": item.get("bytes"),
            "last_seen_at": _iso_now(),
            "preservation_status": item.get("preservation_status"),
            "reclaim_deadline_at": item.get("reclaim_deadline_at"),
            "grace_pending": item.get("grace_pending", False),
            "recent_session_activity": item.get("recent_session_activity", False),
            "parking_result": item.get("parking_result"),
            "registered_in_index": item.get("registered_in_index"),
        }
        existing = load_registry().get("entries", {}).get(str(path), {})
        if existing.get("created_at") and "created_at" not in entry_payload:
            entry_payload["created_at"] = existing["created_at"]
        elif "created_at" not in entry_payload:
            entry_payload["created_at"] = _iso_now()
        _upsert_registry_entry(path, {**existing, **entry_payload})


def _residue_requires_operator_decision(entries: list[dict[str, Any]]) -> bool:
    for item in entries:
        if item["classification"] != "needs_investigation":
            continue
        if item.get("grace_pending"):
            continue
        if item.get("active"):
            return True
        if item.get("has_uncommitted_changes") or item.get("has_local_only_commits"):
            return True
        if item.get("preserved_on_authoritative") is not True:
            return True
    return False


def _residue_grace_pending(entries: list[dict[str, Any]]) -> bool:
    return any(item.get("grace_pending") for item in entries)


def _repo_lifecycle_state(
    state: RepoState,
    assessment: AuthorityAssessment,
    active_change: ManagedChange | None,
    residue: list[dict[str, Any]],
) -> tuple[str, str, bool, str]:
    summary = _scratch_summary(residue)
    if active_change and active_change.lifecycle == "parked":
        return "parked", "topic_only", False, "This change is parked on purpose."
    if active_change and active_change.lifecycle == "published_for_review":
        return (
            "published_for_review",
            "topic_only",
            True,
            "This change is published for review but not landed; land it after review or park it before default closeout.",
        )
    if active_change and active_change.lifecycle == "review_pending":
        return (
            "review_pending",
            "topic_remote",
            False,
            "The topic branch is preserved remotely; rerun yeet to confirm its ready review and retire the task.",
        )
    if active_change and active_change.lifecycle == "ready_for_integration":
        return (
            "ready_for_integration",
            "topic_remote",
            False,
            "The pull request is ready for a project integration thread; end may retire only this local task.",
        )
    if active_change and active_change.phase in {"integrated_local", "pushed_verified", "checkpoint_updated"}:
        note = (
            "The authoritative line is updated and remote proof is pending; rerun yeet to verify and retire this task."
            if active_change.phase == "integrated_local"
            else "The authoritative line is verified remotely; rerun yeet to retire this task."
        )
        return "ready_to_push", "authoritative_only", False, note
    authoritative_branch = (active_change.authoritative_branch if active_change else None) or assessment.default_branch or _branch_name_from_ref(
        assessment.default_ref,
        repo_root=state.repo_root,
    )
    if active_change and active_change.branch and active_change.branch != authoritative_branch:
        if _residue_requires_operator_decision(residue) or _live_managed_link_leaks(state.repo_root):
            return "attention_required", "unknown", True, "Repair needs investigation before this change can collapse cleanly."
        if state.dirty:
            return "working", "topic_only", False, "Commit the active change before finishing it."
        if summary["safe_count"] or summary["auto_park_count"] or _residue_grace_pending(residue):
            return "ready_to_finish", "topic_only", False, "Finish will preserve this change and reclaim leftover temporary checkout state."
        return "ready_to_finish", "topic_only", False, "Finish will preserve this change on the ground-truth line."
    if _residue_requires_operator_decision(residue) or _live_managed_link_leaks(state.repo_root):
        return "attention_required", "unknown", True, "Repair needs investigation before the repo can collapse cleanly."
    if summary["safe_count"] or summary["auto_park_count"] or _residue_grace_pending(residue):
        return "repair_needed", "authoritative_only", False, "Run repair to reclaim leftover temporary checkout state."
    if state.detached:
        return "attention_required", "unknown", True, "Detached HEAD needs repair or parking before closeout."
    keeper_status = _keeper_tracking_status(state, authoritative_branch)
    if not keeper_status:
        return "attention_required", "unknown", True, "The authoritative line has no configured keeper remote."
    if any(item["relation"] in {"behind", "diverged"} for item in keeper_status):
        return "attention_required", "unknown", True, "A keeper remote has history that must be reconciled before closeout."
    if any(not item["preserved"] for item in keeper_status):
        return "ready_to_push", "authoritative_only", False, "Push and verify the authoritative line on every keeper remote."
    return "complete", "cleanup_complete", False, "The authoritative line is clean and there is no blocking residue."


def _participating_workspaces(state: RepoState, residue_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    workspaces: list[dict[str, Any]] = [
        {
            "role": "current_checkout",
            "path": str(state.repo_root),
            "cwd": str(state.cwd),
            "branch": state.branch,
            "head": state.head,
            "clean": not state.dirty,
            "staged_changes": state.staged,
            "unstaged_changes": state.unstaged,
            "untracked_files": state.untracked,
            "classification": "current",
            "reason": "current checkout for this command",
        }
    ]
    for item in residue_entries:
        workspaces.append(
            {
                "role": "worker_scratch",
                "path": item["path"],
                "exists": item["exists"],
                "branch": item.get("branch"),
                "head": item.get("head"),
                "clean": item.get("clean"),
                "staged_changes": item.get("staged_changes", 0),
                "unstaged_changes": item.get("unstaged_changes", 0),
                "untracked_files": item.get("untracked_files", 0),
                "status_short": item.get("status_short", []),
                "untracked_paths": item.get("untracked_paths", []),
                "classification": item.get("classification"),
                "reason": item.get("reason"),
                "active": item.get("active"),
                "recent_session_activity": item.get("recent_session_activity"),
                "parking_result": item.get("parking_result"),
            }
        )
    return workspaces


def _status_payload(state: RepoState) -> dict[str, Any]:
    current_branch = state.branch
    branch_ref = f"refs/heads/{current_branch}" if current_branch else None
    checked_out_elsewhere = []
    if current_branch is not None:
        checked_out_elsewhere = [str(path) for path in _branch_checked_out_elsewhere(state, current_branch)]
    assessment = _authority_assessment(state)
    active_change = _managed_active_change(state, assessment)
    residue_entries = _scratch_residue_entries(state, assessment)
    residue_summary = _scratch_summary(residue_entries)
    lifecycle_state, preservation_status, requires_user_decision, state_note = _repo_lifecycle_state(
        state,
        assessment,
        active_change,
        residue_entries,
    )
    task_class = active_change.task_class if active_change is not None else "ordinary"
    semantic_checks = _semantic_closeout_results(state.repo_root, task_class) if active_change is not None else []
    failed_semantic_checks = [item for item in semantic_checks if not item.get("ok")]
    if failed_semantic_checks and lifecycle_state in {"ready_to_finish", "ready_to_push", "complete"}:
        lifecycle_state = "attention_required"
        requires_user_decision = True
        state_note = "repo-declared semantic closeout checks failed"
    ephemeral_worktrees = _ephemeral_worktree_records(state)
    if ephemeral_worktrees:
        lifecycle_state = "attention_required"
        requires_user_decision = True
        state_note = "registered Git worktree metadata points into forbidden temporary storage"
    live_owner_warnings, live_owner_errors = [], []
    try:
        _, live_owner_warnings, live_owner_errors = active_managed_repo_root()
    except RuntimeError as exc:
        live_owner_errors.append(str(exc))
    managed_link_leaks = _live_managed_link_leaks(state.repo_root)
    policy_ok = lifecycle_state in {
        "working",
        "ready_to_finish",
        "ready_to_push",
        "review_pending",
        "ready_for_integration",
        "parked",
        "complete",
    } and not live_owner_errors and not requires_user_decision and not failed_semantic_checks
    authoritative_branch = (active_change.authoritative_branch if active_change else None) or assessment.default_branch or _branch_name_from_ref(
        assessment.default_ref,
        repo_root=state.repo_root,
    )
    keeper_status = _keeper_tracking_status(state, authoritative_branch)
    payload = {
        "command": "status",
        "schema_version": STATE_SCHEMA_VERSION,
        "command_ok": True,
        "policy_ok": policy_ok,
        "ok": True,
        "repo_root": str(state.repo_root),
        "cwd": str(state.cwd),
        "git_dir": str(state.git_dir),
        "common_dir": str(state.common_dir),
        "branch": current_branch,
        "branch_ref": branch_ref,
        "detached": state.detached,
        "head": state.head,
        "upstream": state.upstream,
        "dirty": state.dirty,
        "staged_changes": state.staged,
        "unstaged_changes": state.unstaged,
        "untracked_files": state.untracked,
        "branch_checked_out_elsewhere": checked_out_elsewhere,
        "authority": {
            "default_branch": assessment.default_branch,
            "default_ref": assessment.default_ref,
            "current_branch": assessment.current_branch,
            "current_vs_default": assessment.current_vs_default,
            "current_is_default_branch": assessment.current_is_default_branch,
            "current_has_local_only_state": assessment.current_has_local_only_state,
            "current_is_authoritative_default": assessment.current_is_authoritative_default,
            "reason": assessment.reason,
        },
        "state": lifecycle_state,
        "authoritative_branch": authoritative_branch,
        "keeper_remotes": keeper_status,
        "current_change": {
            "branch": active_change.branch,
            "lifecycle": active_change.lifecycle,
            "phase": active_change.phase,
            "checkout_path": active_change.checkout_path,
            "mode": active_change.mode,
            "parking_ref": active_change.parking_ref,
            "integrated_tip": active_change.integrated_tip,
            "canonical_dirty_fingerprint": active_change.canonical_dirty_fingerprint,
            "task_class": active_change.task_class,
            "registration_origin": active_change.registration_origin,
            "task_class_provisional": active_change.task_class_provisional,
            "ignored_output_baseline": active_change.ignored_output_baseline,
            "published_tip": active_change.published_tip,
            "base_tip": active_change.base_tip,
            "review_remote": active_change.review_remote,
            "review_ref": active_change.review_ref,
            "review_url": active_change.review_url,
            "selected_refs": list(active_change.selected_refs),
            "start_tip": active_change.start_tip,
            "validation_summary": active_change.validation_summary,
            "checkpoint_generation": active_change.checkpoint_generation,
            "checkpoint_updated_at": active_change.checkpoint_updated_at,
        }
        if active_change is not None
        else None,
        "active_changes": [
            item for item in _load_managed_state(state.common_dir).get("active_changes", [])
        ],
        "submitted_changes": [
            item for item in _load_managed_state(state.common_dir).get("submitted_changes", [])
        ],
        "integrated_changes": [
            item for item in _load_managed_state(state.common_dir).get("integrated_changes", [])
        ],
        "preservation_status": preservation_status,
        "semantic_closeout": {
            "task_class": task_class,
            "ok": not failed_semantic_checks,
            "checks": semantic_checks,
        },
        "next_action": (
            "satisfy repo-declared semantic closeout checks"
            if failed_semantic_checks
            else "yeet"
            if lifecycle_state == "ready_to_finish"
            else "yeet"
            if lifecycle_state == "ready_to_push"
            else "repair --apply"
            if lifecycle_state == "repair_needed"
            else "continue"
            if lifecycle_state == "working"
            else "yeet"
            if lifecycle_state == "review_pending"
            else "yeet"
            if lifecycle_state == "ready_for_integration"
            else "none"
            if lifecycle_state == "complete"
            else "park"
            if lifecycle_state == "parked"
            else "land after review or park --apply"
            if lifecycle_state == "published_for_review"
            else "repair"
        ),
        "requires_user_decision": requires_user_decision,
        "notes": [state_note],
        "ephemeral_worktrees": ephemeral_worktrees,
        "residue": residue_summary,
        "residue_entries": residue_entries,
        "participating_workspaces": _participating_workspaces(state, residue_entries),
        "managed_link_leaks": managed_link_leaks,
        "live_owner_warnings": live_owner_warnings,
        "live_owner_errors": live_owner_errors,
    }

    try:
        start_base, source_strategy, start_blockers, start_notes = _start_source_plan(
            state,
            explicit_base=None,
            from_current=False,
        )
        resolved_mode, mode_blockers, mode_notes = _start_mode_plan(
            state,
            mode="auto",
            base_ref=start_base,
            source_strategy=source_strategy,
        )
        payload["start_recommendation"] = {
            "base": start_base,
            "source_strategy": source_strategy,
            "mode": resolved_mode,
            "requires_explicit_source": bool(start_blockers),
            "blockers": start_blockers + mode_blockers,
            "notes": start_notes + mode_notes,
        }
    except GitSafeError as exc:
        payload["start_recommendation"] = {
            "base": None,
            "source_strategy": "error",
            "mode": None,
            "requires_explicit_source": True,
            "blockers": exc.blockers,
            "notes": [],
        }

    if current_branch is not None:
        try:
            cleanup_probe = _cleanup_payload(
                state,
                branch=current_branch,
                base=None,
                worktree_path=None,
                cwd_override=None,
                delete_remote=None,
                confirm_remote_delete=None,
                preserved_ref=None,
                apply=False,
                dry_run=True,
            )
            payload["base"] = cleanup_probe.get("base")
            payload["ancestry"] = cleanup_probe.get("ancestry")
            payload["unique_commit_count"] = cleanup_probe.get("unique_commit_count")
            payload["cleanup_blockers"] = cleanup_probe.get("blockers", [])
            payload["current_cwd_inside_target_worktree"] = cleanup_probe.get("current_cwd_inside_target_worktree")
            payload["target_worktree_path"] = cleanup_probe.get("target_worktree_path")
        except GitSafeError as exc:
            payload["ok"] = False
            payload["command_ok"] = False
            payload["policy_ok"] = False
            payload["base"] = None
            payload["cleanup_blockers"] = exc.blockers
            payload["cleanup_probe_error"] = str(exc)
    else:
        payload["base"] = None
        payload["ancestry"] = None
        payload["unique_commit_count"] = None
        payload["cleanup_blockers"] = []
        payload["current_cwd_inside_target_worktree"] = False
        payload["target_worktree_path"] = None

    return payload


def _human_status(state: RepoState) -> None:
    payload = _status_payload(state)
    current_change = payload.get("current_change") or {}
    print(f"repo: {payload['repo_root']}")
    print(f"state: {payload['state']}")
    print(f"ground truth line: {payload.get('authoritative_branch') or 'unknown'}")
    print(f"current change: {current_change.get('branch') or payload['branch'] or 'none'}")
    print(f"next step: {payload['next_action']}")
    print(
        "cleanup residue: "
        f"{payload['residue']['safe_count']} safe, "
        f"{payload['residue']['auto_park_count']} park-then-delete, "
        f"{payload['residue']['grace_pending_count']} grace-pending, "
        f"{payload['residue']['decision_count']} investigate"
    )
    if payload.get("notes"):
        for note in payload["notes"]:
            print(f"note: {note}")
    if payload.get("managed_link_leaks"):
        print("live path leaks:")
        for leak in payload["managed_link_leaks"]:
            print(f"- {leak}")
    worker_workspaces = [
        workspace
        for workspace in payload.get("participating_workspaces", [])
        if workspace.get("role") != "current_checkout"
    ]
    if worker_workspaces:
        print("participating worker workspaces:")
        for workspace in worker_workspaces:
            print(
                "- "
                f"{workspace['path']}: {workspace.get('classification')}, "
                f"staged={workspace.get('staged_changes', 0)}, "
                f"unstaged={workspace.get('unstaged_changes', 0)}, "
                f"untracked={workspace.get('untracked_files', 0)}"
            )
    if payload.get("live_owner_errors"):
        print("live owner errors:")
        for error in payload["live_owner_errors"]:
            print(f"- {error}")


def _start_payload_unlocked(
    state: RepoState,
    *,
    topic: str,
    base: str | None,
    from_current: bool,
    mode: str,
    worktree_root: str | None,
    worktree_path: str | None,
    dry_run: bool,
    task_class: str,
) -> dict[str, Any]:
    branch = _normalize_branch_name(topic)
    if mode == "checkout":
        mode = "worktree"
    assessment = _authority_assessment(state)
    base_ref, source_strategy, start_blockers, start_notes = _start_source_plan(
        state,
        explicit_base=base,
        from_current=from_current,
    )
    resolved_mode, mode_blockers, mode_notes = _start_mode_plan(
        state,
        mode=mode,
        base_ref=base_ref,
        source_strategy=source_strategy,
    )
    mode_blockers.extend(_ephemeral_worktree_blockers(state))

    worktree_path_value = None
    if resolved_mode == "worktree":
        if worktree_path is not None and worktree_root is not None:
            raise GitSafeError("--worktree-root and --worktree-path are mutually exclusive")
        if worktree_path is not None:
            worktree_path_value = _resolve_path(worktree_path, base=state.repo_root)
        elif worktree_root is not None:
            worktree_path_value = _resolve_path(worktree_root, base=state.repo_root)
        else:
            worktree_path_value = _worktree_root_for_branch(state.repo_root, branch)
        if worktree_path_value is not None and is_ephemeral_checkout_path(worktree_path_value):
            mode_blockers.append(
                "managed task worktrees cannot use OS temporary storage (/tmp, /private/tmp, /var/tmp, or the configured temp directory); use the default durable ~/.codex/worktrees location"
            )

    planned = {
        "command": "start",
        "ok": True,
        "dry_run": dry_run,
        "topic": topic,
        "task_class": _normalize_task_class(task_class),
        "branch": branch,
        "base": base_ref,
        "from_current": from_current,
        "source_strategy": source_strategy,
        "mode_requested": mode,
        "mode_resolved": resolved_mode,
        "repo_root": str(state.repo_root),
        "worktree_path": str(worktree_path_value) if worktree_path_value is not None else None,
        "blockers": start_blockers + mode_blockers,
        "notes": start_notes + mode_notes,
        "actions": [],
    }

    branch_exists = _run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=state.repo_root)
    branch_present = branch_exists.returncode == 0
    worktree_entry = _worktree_entry_for_path(state, worktree_path_value) if worktree_path_value else None

    if resolved_mode == "branch":
        branch_checked_out_elsewhere = _branch_checked_out_elsewhere(state, branch)
        planned["branch_checked_out_elsewhere"] = [str(path) for path in branch_checked_out_elsewhere]
        if state.branch == branch:
            planned["existing"] = True
        elif branch_present:
            if branch_checked_out_elsewhere:
                planned["blockers"].append(f"branch '{branch}' is checked out elsewhere")
            else:
                planned["planned_command"] = ["git", "switch", branch]
        else:
            planned["planned_command"] = ["git", "switch", "-c", branch, base_ref]
    else:
        checked_out_elsewhere = _branch_checked_out_elsewhere(state, branch, exclude_path=worktree_path_value)
        planned["branch_checked_out_elsewhere"] = [str(path) for path in checked_out_elsewhere]
        if worktree_entry is not None:
            if worktree_entry.branch != branch:
                planned["blockers"].append(
                    f"checkout path already belongs to branch '{worktree_entry.branch or 'detached'}': {worktree_path_value}"
                )
            else:
                target_state = _repo_state(worktree_path_value)
                target_change = _managed_active_change(
                    target_state,
                    _authority_assessment(target_state),
                )
                requested_task_class = _normalize_task_class(task_class)
                existing_matches = bool(
                    target_change is not None
                    and target_change.mode == "worktree"
                    and target_change.checkout_path is not None
                    and _checkout_identity(Path(target_change.checkout_path)) == _checkout_identity(worktree_path_value)
                    and target_change.branch == branch
                    and target_change.task_class == requested_task_class
                    and target_change.start_tip == _ref_commit("HEAD", cwd=target_state.repo_root)
                )
                if existing_matches:
                    planned["existing"] = True
                    planned["registered_existing"] = True
                else:
                    planned["blockers"].append(
                        "checkout path is an existing linked worktree without an exact matching registration; "
                        f"run adopt-current from that clean checkout: {worktree_path_value}"
                    )
        elif worktree_path_value is None:
            planned["blockers"].append("could not resolve an isolated-checkout path")
        elif worktree_path_value.exists() and not _worktree_entry_for_path(state, worktree_path_value):
            planned["blockers"].append(f"checkout path already exists and is not registered: {worktree_path_value}")
        elif checked_out_elsewhere:
            planned["blockers"].append(f"branch '{branch}' is already checked out elsewhere")
        elif branch_present:
            planned["planned_command"] = ["git", "worktree", "add", str(worktree_path_value), branch]
        else:
            planned["planned_command"] = ["git", "worktree", "add", "-b", branch, str(worktree_path_value), base_ref]

    planned_command = planned.get("planned_command")
    if not dry_run and not planned["blockers"]:
        if planned_command:
            proc = _run(list(planned_command), cwd=state.repo_root)
            if proc.returncode != 0:
                detail = proc.stderr.strip() or proc.stdout.strip() or "start command failed"
                raise GitSafeError(detail)
            if resolved_mode == "branch":
                planned["actions"].append(f"switched to branch {branch}")
            else:
                planned["actions"].append(f"created checkout {worktree_path_value} on {branch}")
        active_checkout = worktree_path_value if resolved_mode == "worktree" else state.repo_root
        if not planned.get("registered_existing"):
            _set_active_change(
                state,
                branch=branch,
                authoritative_branch=assessment.default_branch or _branch_name_from_ref(
                    assessment.default_ref,
                    repo_root=state.repo_root,
                ),
                lifecycle="working",
                checkout_path=active_checkout,
                mode=resolved_mode,
                task_class=_normalize_task_class(task_class),
                ignored_output_baseline=_ignored_output_snapshot(active_checkout),
                start_tip=_ref_commit("HEAD", cwd=active_checkout),
            )
            if resolved_mode == "worktree" and worktree_path_value is not None:
                _upsert_registry_entry(
                    worktree_path_value,
                    {
                        "id": scratch_id_for_path(worktree_path_value) or _branch_slug(branch),
                        "repo_root": str(state.repo_root),
                        "branch": branch,
                        "status": "active",
                        "owner_kind": "managed_change",
                        "owner_id": branch,
                        "created_at": _iso_now(),
                        "last_seen_at": _iso_now(),
                        "authoritative_branch": assessment.default_branch or _branch_name_from_ref(
                            assessment.default_ref,
                            repo_root=state.repo_root,
                        ),
                        "checkout_path": str(worktree_path_value),
                    },
                )

    return planned


def _start_payload(
    state: RepoState,
    *,
    topic: str,
    base: str | None,
    from_current: bool,
    mode: str,
    worktree_root: str | None,
    worktree_path: str | None,
    dry_run: bool,
    task_class: str,
) -> dict[str, Any]:
    """Start is a single control-plane transaction, including registry ownership."""
    with _integration_lock(state.common_dir):
        return _start_payload_unlocked(
            state,
            topic=topic,
            base=base,
            from_current=from_current,
            mode=mode,
            worktree_root=worktree_root,
            worktree_path=worktree_path,
            dry_run=dry_run,
            task_class=task_class,
        )


def _land_payload(
    state: RepoState,
    *,
    branch: str | None,
    target_branch: str | None,
    source_worktree_path: str | None,
    target_worktree_path: str | None,
    preserve_target_dirty: bool,
    apply: bool,
    dry_run: bool,
) -> dict[str, Any]:
    assessment = _authority_assessment(state)
    source_branch = branch or state.branch
    if source_branch is None:
        raise GitSafeError("source branch is required when the current checkout is detached")

    default_target_branch = assessment.default_branch or _branch_name_from_ref(
        assessment.default_ref,
        repo_root=state.repo_root,
    )
    resolved_target_branch = target_branch or default_target_branch
    if resolved_target_branch is None:
        raise GitSafeError("could not infer a target branch; pass --target-branch explicitly")
    if source_branch == resolved_target_branch:
        raise GitSafeError("source and target branches are the same; land requires distinct branches")

    source_branch_ref = f"refs/heads/{source_branch}"
    target_branch_ref = f"refs/heads/{resolved_target_branch}"
    if _run(["git", "show-ref", "--verify", "--quiet", source_branch_ref], cwd=state.repo_root).returncode != 0:
        raise GitSafeError(f"branch '{source_branch}' does not exist")
    if _run(["git", "show-ref", "--verify", "--quiet", target_branch_ref], cwd=state.repo_root).returncode != 0:
        raise GitSafeError(f"branch '{resolved_target_branch}' does not exist")

    explicit_source_path = _resolve_path(source_worktree_path, base=state.repo_root) if source_worktree_path else None
    explicit_target_path = _resolve_path(target_worktree_path, base=state.repo_root) if target_worktree_path else None
    resolved_source_path = explicit_source_path or _worktree_path_for_entry(state.worktrees, source_branch)
    resolved_target_path = explicit_target_path or _worktree_path_for_entry(state.worktrees, resolved_target_branch)
    source_entry = _worktree_entry_for_path(state, resolved_source_path) if resolved_source_path else None
    target_entry = _worktree_entry_for_path(state, resolved_target_path) if resolved_target_path else None

    if explicit_source_path is not None and source_entry is None:
        raise GitSafeError(f"source worktree is not registered: {explicit_source_path}")
    if explicit_target_path is not None and target_entry is None:
        raise GitSafeError(f"target worktree is not registered: {explicit_target_path}")
    if source_entry is not None and source_entry.branch not in {None, source_branch}:
        raise GitSafeError(f"source worktree path is on branch '{source_entry.branch}', not '{source_branch}'")
    if target_entry is not None and target_entry.branch not in {None, resolved_target_branch}:
        raise GitSafeError(f"target worktree path is on branch '{target_entry.branch}', not '{resolved_target_branch}'")

    source_tip = _ref_commit(source_branch, cwd=state.repo_root)
    target_tip = _ref_commit(resolved_target_branch, cwd=state.repo_root)
    source_unique = _unique_commits(resolved_target_branch, source_branch, cwd=state.repo_root)
    target_unique = _unique_commits(source_branch, resolved_target_branch, cwd=state.repo_root)

    if source_tip == target_tip:
        ancestry_words = f"{source_branch} and {resolved_target_branch} point at the same commit"
    elif _is_ancestor(target_tip, source_tip, cwd=state.repo_root):
        ancestry_words = f"{resolved_target_branch} is an ancestor of {source_branch}"
    elif _is_ancestor(source_tip, target_tip, cwd=state.repo_root):
        ancestry_words = f"{source_branch} is already contained by {resolved_target_branch}"
    else:
        ancestry_words = f"{source_branch} and {resolved_target_branch} have diverged"

    source_status = _path_status_counts(source_entry.path) if source_entry is not None else {
        "dirty": False,
        "staged_changes": 0,
        "unstaged_changes": 0,
        "untracked_files": 0,
    }
    target_status = _path_status_counts(target_entry.path) if target_entry is not None else {
        "dirty": False,
        "staged_changes": 0,
        "unstaged_changes": 0,
        "untracked_files": 0,
    }
    target_dirty_paths = _dirty_paths(target_entry.path) if target_entry is not None and target_status["dirty"] else set()
    source_changed_paths = _changed_paths_between(resolved_target_branch, source_branch, cwd=state.repo_root)
    target_fingerprint: dict[str, Any] | None = None
    if target_status["dirty"] and preserve_target_dirty:
        target_fingerprint = _dirty_fingerprint(target_entry.path)
        target_dirty_paths = target_fingerprint["paths"]
    overlapping_dirty_paths = sorted(target_dirty_paths & source_changed_paths)

    blockers: list[str] = []
    notes: list[str] = []
    can_fast_forward = _is_ancestor(target_tip, source_tip, cwd=state.repo_root)

    if source_status["dirty"]:
        blockers.append("source worktree is dirty")
    if not can_fast_forward:
        blockers.append("target branch cannot fast-forward to the source branch")
    if target_status["dirty"] and not preserve_target_dirty:
        blockers.append("target worktree is dirty; pass --preserve-target-dirty to allow a conflict-free fast-forward")
    if target_status["dirty"] and preserve_target_dirty and overlapping_dirty_paths:
        blockers.append("target dirty paths overlap the source branch changes")
    if target_status["dirty"] and preserve_target_dirty and not overlapping_dirty_paths:
        notes.append("target dirty changes do not overlap the source branch diff; fast-forward should preserve them")

    payload = {
        "command": "land",
        "ok": not blockers,
        "dry_run": dry_run,
        "apply_requested": apply,
        "branch": source_branch,
        "target_branch": resolved_target_branch,
        "repo_root": str(state.repo_root),
        "source_tip": source_tip,
        "target_tip": target_tip,
        "ancestry": ancestry_words,
        "source_unique_commit_count": len(source_unique),
        "source_unique_commits": source_unique,
        "target_unique_commit_count": len(target_unique),
        "target_unique_commits": target_unique,
        "source_worktree_path": str(resolved_source_path) if resolved_source_path is not None else None,
        "target_worktree_path": str(resolved_target_path) if resolved_target_path is not None else None,
        "source_dirty": bool(source_status["dirty"]),
        "target_dirty": bool(target_status["dirty"]),
        "preserve_target_dirty": preserve_target_dirty,
        "overlapping_dirty_paths": overlapping_dirty_paths,
        "can_fast_forward": can_fast_forward,
        "blockers": blockers,
        "notes": notes,
        "dirty_fingerprint_before": target_fingerprint["digest"] if target_fingerprint else None,
        "dirty_fingerprint_after": None,
        "dirty_preservation_proof": target_fingerprint["proof"] if target_fingerprint else None,
        "actions": [],
    }

    if blockers:
        return payload

    if apply:
        if target_entry is not None:
            merge_proc = _run(["git", "-C", str(target_entry.path), "merge", "--ff-only", source_branch], cwd=state.repo_root)
            if merge_proc.returncode != 0:
                detail = merge_proc.stderr.strip() or merge_proc.stdout.strip() or "git merge --ff-only failed"
                raise GitSafeError(detail)
            updated_status = _path_status_counts(target_entry.path)
            payload["target_dirty"] = bool(updated_status["dirty"])
            if target_fingerprint is not None:
                post_fingerprint = _dirty_fingerprint(target_entry.path)
                payload["dirty_fingerprint_after"] = post_fingerprint["digest"]
                if post_fingerprint["digest"] != target_fingerprint["digest"]:
                    raise GitSafeError(
                        "dirty canonical fingerprint changed during fast-forward",
                        blockers=["canonical dirty state was not preserved byte-for-byte"],
                        data={"land": payload, "dirty_fingerprint_before": target_fingerprint["digest"], "dirty_fingerprint_after": post_fingerprint["digest"]},
                    )
        else:
            update_proc = _run(
                ["git", "update-ref", target_branch_ref, source_tip, target_tip],
                cwd=state.repo_root,
            )
            if update_proc.returncode != 0:
                detail = update_proc.stderr.strip() or update_proc.stdout.strip() or "git update-ref failed"
                raise GitSafeError(detail)
        payload["actions"].append(f"fast-forwarded {resolved_target_branch} to {source_branch}")

    return payload


def _cherry_pick_payload(
    state: RepoState,
    *,
    branch: str,
    target_branch: str,
    target_checkout_path: Path | None = None,
    apply: bool,
) -> dict[str, Any]:
    source_unique = list(reversed(_unique_commits(target_branch, branch, cwd=state.repo_root)))
    blockers: list[str] = []
    actions: list[str] = []

    if not source_unique:
        if not _patch_equivalent_to_ref(branch, target_branch, cwd=state.repo_root):
            blockers.append("source branch has no unique commits but is not preserved by patch-id")

    payload: dict[str, Any] = {
        "command": "cherry-pick",
        "ok": not blockers,
        "apply_requested": apply,
        "branch": branch,
        "target_branch": target_branch,
        "target_checkout_path": str(target_checkout_path) if target_checkout_path is not None else str(state.repo_root),
        "source_unique_commit_count": len(source_unique),
        "source_unique_commits": source_unique,
        "blockers": blockers,
        "actions": actions,
    }
    if blockers or not apply:
        return payload

    target_checkout = target_checkout_path or state.repo_root
    target_state = _repo_state(target_checkout)
    if target_state.branch != target_branch:
        switch_proc = _run(["git", "switch", target_branch], cwd=target_checkout)
        if switch_proc.returncode != 0:
            detail = switch_proc.stderr.strip() or switch_proc.stdout.strip() or "git switch failed"
            raise GitSafeError(detail)
        actions.append(f"switched authoritative control checkout to {target_branch}")

    if source_unique:
        pick_proc = _run(["git", "cherry-pick", *source_unique], cwd=target_checkout)
        if pick_proc.returncode != 0:
            _run(["git", "cherry-pick", "--abort"], cwd=target_checkout)
            detail = pick_proc.stderr.strip() or pick_proc.stdout.strip() or "git cherry-pick failed"
            raise GitSafeError(detail)
        actions.append(f"cherry-picked {len(source_unique)} commit(s) from {branch} onto {target_branch}")

    if not _patch_equivalent_to_ref(branch, target_branch, cwd=state.repo_root):
        raise GitSafeError("finish could not prove the source branch is preserved by patch-id")
    payload["patch_equivalent_to_target"] = True
    return payload


def _cleanup_payload(
    state: RepoState,
    *,
    branch: str | None,
    base: str | None,
    worktree_path: str | None,
    cwd_override: str | None,
    delete_remote: str | None,
    confirm_remote_delete: str | None,
    preserved_ref: str | None,
    apply: bool,
    dry_run: bool,
) -> dict[str, Any]:
    cwd = _resolve_path(cwd_override, base=state.cwd) if cwd_override else state.cwd
    if cwd is None:
        cwd = state.cwd
    if not cwd.exists():
        raise GitSafeError(f"cwd does not exist: {cwd}")

    explicit_worktree_path = _resolve_path(worktree_path, base=state.repo_root) if worktree_path else None
    target_worktree_path = explicit_worktree_path
    if target_worktree_path is None and branch is None:
        if state.branch is not None and state.repo_root in [entry.path for entry in state.worktrees]:
            target_worktree_path = state.repo_root
    elif (
        target_worktree_path is None
        and branch is not None
        and branch == state.branch
        and state.repo_root in [entry.path for entry in state.worktrees]
    ):
        target_worktree_path = state.repo_root

    target_entry = _worktree_entry_for_path(state, target_worktree_path) if target_worktree_path else None

    target_branch = branch or (target_entry.branch if target_entry is not None else state.branch)
    if target_branch is None:
        raise GitSafeError("branch is required when the current checkout is detached or the target worktree is detached")

    if branch is not None and target_entry is not None and target_entry.branch is not None and target_entry.branch != branch:
        raise GitSafeError(
            f"branch '{branch}' does not match the branch checked out in the target worktree: {target_entry.branch}"
        )
    if branch is None and target_entry is not None and target_entry.branch is None:
        raise GitSafeError("target worktree is detached; pass --branch explicitly")

    base_ref = _resolve_base_ref(state, base, target_branch=target_branch)

    branch_ref = f"refs/heads/{target_branch}"
    branch_exists = _run(["git", "show-ref", "--verify", "--quiet", branch_ref], cwd=state.repo_root).returncode == 0
    if not branch_exists:
        raise GitSafeError(f"branch '{target_branch}' does not exist")

    branch_tip = _ref_commit(target_branch, cwd=state.repo_root)
    base_tip = _ref_commit(base_ref, cwd=state.repo_root)
    unique = _unique_commits(base_ref, target_branch, cwd=state.repo_root)
    unique_commit_count = len(unique)

    if branch_tip == base_tip:
        ancestry_words = f"{target_branch} and {base_ref} point at the same commit"
    elif _is_ancestor(branch_tip, base_tip, cwd=state.repo_root):
        ancestry_words = f"{target_branch} is contained by {base_ref}"
    elif _is_ancestor(base_tip, branch_tip, cwd=state.repo_root):
        ancestry_words = f"{base_ref} is an ancestor of {target_branch}"
    else:
        ancestry_words = f"{target_branch} and {base_ref} have diverged"

    checked_out_elsewhere = _branch_checked_out_elsewhere(state, target_branch, exclude_path=target_worktree_path)
    current_inside_target = _current_worktree_is_inside_target(cwd, target_worktree_path)

    preserved_covers_branch = None
    if preserved_ref is not None:
        preserved_tip = _ref_commit(preserved_ref, cwd=state.repo_root)
        # Retirement deletes a ref, so require graph ancestry rather than
        # patch equivalence.  Equivalent patches are not durable proof that
        # every commit reachable from the topic remains reachable.
        preserved_covers_branch = _is_ancestor(branch_tip, preserved_tip, cwd=state.repo_root)

    branch_safe_to_delete = unique_commit_count == 0 or bool(preserved_covers_branch)
    remote_safe_to_delete = branch_safe_to_delete
    blockers: list[str] = []

    if current_inside_target:
        blockers.append("current cwd is inside the target worktree")
    if checked_out_elsewhere:
        blockers.append(f"branch '{target_branch}' is checked out elsewhere")
    if not branch_safe_to_delete:
        blockers.append("branch history is not fully preserved by the base or preserved ref")
    if delete_remote and not remote_safe_to_delete:
        blockers.append(
            "remote deletion requested but branch history is not fully preserved by the base or preserved ref"
        )
    if delete_remote:
        expected_confirmation = f"{delete_remote}/{target_branch}"
        if confirm_remote_delete != expected_confirmation:
            blockers.append(
                f"remote deletion requires --confirm-remote-delete {expected_confirmation}"
            )
    if explicit_worktree_path is not None and target_entry is None:
        blockers.append(f"target worktree is not registered: {explicit_worktree_path}")

    payload = {
        "command": "cleanup",
        "ok": not blockers,
        "dry_run": dry_run,
        "apply_requested": apply,
        "repo_root": str(state.repo_root),
        "cwd": str(cwd),
        "branch": target_branch,
        "branch_tip": branch_tip,
        "base": base_ref,
        "base_tip": base_tip,
        "unique_commit_count": unique_commit_count,
        "unique_commits": unique,
        "ancestry": ancestry_words,
        "branch_checked_out_elsewhere": [str(path) for path in checked_out_elsewhere],
        "current_cwd_inside_target_worktree": current_inside_target,
        "target_worktree_path": str(target_worktree_path) if target_worktree_path is not None else None,
        "preserved_ref": preserved_ref,
        "preserved_ref_preserves_branch": preserved_covers_branch,
        "branch_safe_to_delete": branch_safe_to_delete,
        "remote_delete": delete_remote,
        "remote_delete_confirmation": confirm_remote_delete,
        "remote_safe_to_delete": remote_safe_to_delete,
        "blockers": blockers,
        "actions": [],
    }

    if blockers:
        return payload

    if apply and target_entry is not None:
        target_clean = _run(["git", "-C", str(target_entry.path), "status", "--porcelain=v1"], cwd=state.repo_root)
        if target_clean.returncode != 0:
            raise GitSafeError(
                target_clean.stderr.strip() or target_clean.stdout.strip() or f"could not inspect worktree {target_entry.path}"
            )
        if target_clean.stdout.strip():
            raise GitSafeError(f"target worktree is dirty: {target_entry.path}")
        remove_proc = _run(["git", "worktree", "remove", str(target_entry.path)], cwd=state.repo_root)
        if remove_proc.returncode != 0:
            raise GitSafeError(remove_proc.stderr.strip() or remove_proc.stdout.strip() or "git worktree remove failed")
        payload["actions"].append(f"removed worktree {target_entry.path}")
        delete_proc = _run(["git", "branch", "-D", target_branch], cwd=state.repo_root)
        if delete_proc.returncode != 0:
            raise GitSafeError(delete_proc.stderr.strip() or delete_proc.stdout.strip() or "git branch -D failed")
        payload["actions"].append(f"deleted branch {target_branch}")
        if delete_remote and remote_safe_to_delete:
            remote_delete_proc = _run(["git", "push", delete_remote, "--delete", target_branch], cwd=state.repo_root)
            if remote_delete_proc.returncode != 0:
                raise GitSafeError(
                    remote_delete_proc.stderr.strip() or remote_delete_proc.stdout.strip() or "remote branch deletion failed"
                )
            payload["actions"].append(f"deleted remote branch {delete_remote}/{target_branch}")
        payload["branch_checked_out_elsewhere"] = []
        payload["current_cwd_inside_target_worktree"] = _current_worktree_is_inside_target(cwd, target_worktree_path)
        if target_worktree_path is not None and is_scratch_path(target_worktree_path):
            actions = _remove_index_registry_paths({target_worktree_path})
            _remove_registry_paths({target_worktree_path})
            payload["actions"].extend(actions)
    elif apply and not target_entry:
        delete_proc = _run(["git", "branch", "-D", target_branch], cwd=state.repo_root)
        if delete_proc.returncode != 0:
            raise GitSafeError(delete_proc.stderr.strip() or delete_proc.stdout.strip() or "git branch -D failed")
        payload["actions"].append(f"deleted branch {target_branch}")
        if delete_remote and remote_safe_to_delete:
            remote_delete_proc = _run(["git", "push", delete_remote, "--delete", target_branch], cwd=state.repo_root)
            if remote_delete_proc.returncode != 0:
                raise GitSafeError(
                    remote_delete_proc.stderr.strip() or remote_delete_proc.stdout.strip() or "remote branch deletion failed"
                )
            payload["actions"].append(f"deleted remote branch {delete_remote}/{target_branch}")

    if apply:
        _clear_active_change_unlocked(state, branch=target_branch)

    return payload


def _remove_index_registry_paths(paths: set[Path]) -> list[str]:
    if not paths:
        return []
    payload = _index_registry_without(paths)
    save_index_registry(payload)
    return [f"removed stale index registration {path}" for path in sorted(paths)]


def _remove_scratch_checkout(state: RepoState, path: Path) -> list[str]:
    actions: list[str] = []
    entry = _scratch_entry_for_path(state, path)
    if entry is not None:
        remove_proc = _run(["git", "worktree", "remove", "--force", str(path)], cwd=state.repo_root)
        if remove_proc.returncode != 0 and path.exists():
            shutil.rmtree(path, ignore_errors=False)
        actions.append(f"removed temporary checkout {path}")
    elif path.exists():
        shutil.rmtree(path, ignore_errors=False)
        actions.append(f"removed temporary checkout {path}")
    prune_proc = _run(["git", "worktree", "prune"], cwd=state.repo_root)
    if prune_proc.returncode == 0:
        actions.append("pruned stale git checkout admin state")
    parent = path.parent
    if parent.exists():
        prune_empty_parent_dirs(parent, stop_at=SCRATCH_ROOT)
    return actions


def _refresh_remote_tracking_refs(repo_root: Path) -> list[str]:
    actions: list[str] = []
    for remote in _remote_names(repo_root):
        prune_proc = _run(["git", "fetch", "--prune", remote], cwd=repo_root)
        if prune_proc.returncode != 0:
            detail = prune_proc.stderr.strip() or prune_proc.stdout.strip() or "git fetch --prune failed"
            raise GitSafeError(detail)
        actions.append(f"pruned remote-tracking refs for {remote}")
    return actions


def _park_ref_name(repo_root: Path, scratch_id: str) -> str:
    return f"refs/codex/park/{repo_root.name}/{_utc_now().strftime('%Y-%m-%d')}/{scratch_id}"


def _create_parking_commit(path: Path) -> str:
    head = _git_output(["rev-parse", "--verify", "HEAD"], cwd=path)
    with tempfile.NamedTemporaryFile(prefix="codex-git-safe-index-", delete=False) as handle:
        temp_index = Path(handle.name)
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(temp_index)
    try:
        read_proc = subprocess.run(
            ["git", "-C", str(path), "read-tree", head],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if read_proc.returncode != 0:
            detail = read_proc.stderr.strip() or read_proc.stdout.strip() or "git read-tree failed"
            raise GitSafeError(detail)
        add_proc = subprocess.run(
            ["git", "-C", str(path), "add", "-A", "--all", "."],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if add_proc.returncode != 0:
            detail = add_proc.stderr.strip() or add_proc.stdout.strip() or "git add -A failed"
            raise GitSafeError(detail)
        tree_proc = subprocess.run(
            ["git", "-C", str(path), "write-tree"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if tree_proc.returncode != 0:
            detail = tree_proc.stderr.strip() or tree_proc.stdout.strip() or "git write-tree failed"
            raise GitSafeError(detail)
        tree = tree_proc.stdout.strip()
        commit_proc = subprocess.run(
            ["git", "-C", str(path), "commit-tree", tree, "-p", head, "-m", f"codex-git-safe park {path.name}"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if commit_proc.returncode != 0:
            detail = commit_proc.stderr.strip() or commit_proc.stdout.strip() or "git commit-tree failed"
            raise GitSafeError(detail)
        return commit_proc.stdout.strip()
    finally:
        try:
            temp_index.unlink()
        except OSError:
            pass


def _park_checkout(state: RepoState, path: Path, *, classification: str) -> tuple[str, str, str | None]:
    scratch_id = scratch_id_for_path(path) or _branch_slug(str(path))
    authoritative_ref = _authority_assessment(state).default_ref or _authority_assessment(state).default_branch
    status_counts = _path_status_counts(path) if path.exists() else {"dirty": False}
    if not path.exists():
        raise GitSafeError(f"temporary checkout does not exist: {path}")
    if status_counts["dirty"]:
        commit = _create_parking_commit(path)
    else:
        commit = _git_output(["rev-parse", "--verify", "HEAD"], cwd=path)
    park_ref = _park_ref_name(state.repo_root, scratch_id)
    update_proc = _run(["git", "update-ref", park_ref, commit], cwd=state.repo_root)
    if update_proc.returncode != 0:
        detail = update_proc.stderr.strip() or update_proc.stdout.strip() or "git update-ref failed while parking"
        raise GitSafeError(detail)
    bundle_dir = SCRATCH_RESCUE_ROOT / state.repo_root.name
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_dir / f"{_utc_now().strftime('%Y%m%d%H%M%S')}-{scratch_id}.bundle"
    bundle_proc = _run(["git", "bundle", "create", str(bundle_path), park_ref], cwd=state.repo_root)
    if bundle_proc.returncode != 0:
        detail = bundle_proc.stderr.strip() or bundle_proc.stdout.strip() or "git bundle create failed"
        raise GitSafeError(detail)
    verify_proc = _run(["git", "bundle", "verify", str(bundle_path)], cwd=state.repo_root)
    if verify_proc.returncode != 0:
        detail = verify_proc.stderr.strip() or verify_proc.stdout.strip() or "git bundle verify failed"
        raise GitSafeError(detail)
    remote_ref = None
    safe_remote = _safe_remote_for_parking(state.repo_root)
    if safe_remote:
        push_proc = _run(["git", "push", safe_remote, f"{park_ref}:{park_ref}"], cwd=state.repo_root)
        if push_proc.returncode == 0:
            remote_ref = f"{safe_remote}:{park_ref}"
    if is_scratch_path(path):
        _upsert_registry_entry(
            path,
            {
                "id": scratch_id,
                "repo_root": str(state.repo_root),
                "status": "parked",
                "classification": classification,
                "parking_ref": park_ref,
                "bundle_path": str(bundle_path),
                "last_seen_at": _iso_now(),
                "authoritative_ref": authoritative_ref,
                "parking_result": {
                    "local_ref": park_ref,
                    "remote_ref": remote_ref,
                    "bundle_path": str(bundle_path),
                    "bundle_verified": True,
                },
            },
        )
    return park_ref, str(bundle_path), remote_ref


def _repair_payload_unlocked(state: RepoState, *, apply: bool) -> dict[str, Any]:
    live_owner_blockers = _live_owner_mutation_blockers(state)
    if apply and live_owner_blockers:
        raise GitSafeError(
            "repair cannot reclaim temporary Git state while managed live paths are unresolved",
            blockers=live_owner_blockers,
        )
    assessment = _authority_assessment(state)
    residue_entries = _scratch_residue_entries(state, assessment)
    summary = _scratch_summary(residue_entries)
    authoritative_ref = assessment.default_ref or assessment.default_branch
    ephemeral_repairs = _ephemeral_worktree_repair_records(
        state,
        authoritative_ref=authoritative_ref,
    )
    unsafe_ephemeral = [item for item in ephemeral_repairs if not item["safe_to_prune"]]
    other_prunable = [
        entry
        for entry in state.worktrees
        if entry.prunable and not is_ephemeral_checkout_path(entry.path)
    ]
    actions: list[str] = []
    parked: list[dict[str, str]] = []
    safe_paths = {Path(item["path"]) for item in residue_entries if item["classification"] == "safe_to_delete"}
    park_paths = [Path(item["path"]) for item in residue_entries if item["classification"] == "auto_park_then_delete"]
    needs = [
        item
        for item in residue_entries
        if item["classification"] == "needs_investigation" and not item.get("grace_pending")
    ]

    if apply:
        if unsafe_ephemeral or other_prunable:
            blockers = [
                f"temporary worktree is not safe to prune: {item['path']} ({item['reason']})"
                for item in unsafe_ephemeral
            ]
            blockers.extend(
                f"unrelated prunable worktree requires separate review: {entry.path}"
                for entry in other_prunable
            )
            raise GitSafeError(
                "repair refuses broad Git worktree pruning without complete preservation proof",
                blockers=blockers,
            )
        if ephemeral_repairs and not unsafe_ephemeral and not other_prunable:
            prune_proc = _run(
                ["git", "worktree", "prune", "--expire", "now", "--verbose"],
                cwd=state.repo_root,
            )
            if prune_proc.returncode != 0:
                raise GitSafeError(
                    prune_proc.stderr.strip()
                    or prune_proc.stdout.strip()
                    or "could not prune preserved temporary-worktree metadata"
                )
            remaining = _ephemeral_worktree_records(_repo_state(state.repo_root))
            if remaining:
                raise GitSafeError(
                    "Git left forbidden temporary-worktree metadata after repair",
                    blockers=_ephemeral_worktree_blockers(_repo_state(state.repo_root)),
                )
            actions.extend(
                f"pruned preserved temporary-worktree metadata {item['path']}"
                for item in ephemeral_repairs
            )
        managed_payload = _load_managed_state(state.common_dir)
        retained_changes: list[dict[str, Any]] = []
        removed_changes: list[dict[str, Any]] = []
        for item in managed_payload.get("active_changes", []):
            branch = item.get("branch")
            checkout_path = Path(item["checkout_path"]).resolve(strict=False) if item.get("checkout_path") else None
            branch_exists = bool(branch) and _run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                cwd=state.repo_root,
            ).returncode == 0
            checkout_matches = False
            if checkout_path is not None and checkout_path.is_dir():
                branch_proc = _run(["git", "symbolic-ref", "-q", "--short", "HEAD"], cwd=checkout_path)
                checkout_matches = branch_proc.returncode == 0 and branch_proc.stdout.strip() == branch
            if branch_exists or checkout_matches:
                retained_changes.append(item)
            else:
                removed_changes.append(item)
        if removed_changes:
            managed_payload["active_changes"] = retained_changes
            legacy = managed_payload.get("active_change") or {}
            if any(_payload_checkout_identity(item) == _payload_checkout_identity(legacy) for item in removed_changes):
                managed_payload["active_change"] = retained_changes[-1] if retained_changes else None
            _save_managed_state(state.common_dir, managed_payload)
            for item in removed_changes:
                actions.append(f"removed impossible active change {item.get('branch') or 'unknown'}")
        for path in park_paths:
            park_ref, bundle_path, remote_ref = _park_checkout(state, path, classification="auto_park_then_delete")
            parked.append(
                {
                    "path": str(path),
                    "parking_ref": park_ref,
                    "bundle_path": bundle_path,
                    "remote_ref": remote_ref,
                }
            )
            actions.extend(_remove_scratch_checkout(state, path))
            safe_paths.add(path)
        for path in sorted(safe_paths):
            if path.exists():
                actions.extend(_remove_scratch_checkout(state, path))
        if safe_paths:
            actions.extend(_remove_index_registry_paths(safe_paths))
            _remove_registry_paths(safe_paths)
        for removed in prune_empty_scratch_dirs():
            actions.append(f"removed empty scratch bucket {removed}")

    payload = {
        "command": "repair",
        "schema_version": STATE_SCHEMA_VERSION,
        "command_ok": True,
        "policy_ok": not needs and not unsafe_ephemeral and not other_prunable,
        "ok": True,
        "repo_root": str(state.repo_root),
        "apply_requested": apply,
        "residue_entries": residue_entries,
        "residue": summary,
        "ephemeral_worktrees": ephemeral_repairs,
        "participating_workspaces": _participating_workspaces(state, residue_entries),
        "classifications": {
            "safe_to_delete": [item["path"] for item in residue_entries if item["classification"] == "safe_to_delete"],
            "auto_park_then_delete": [item["path"] for item in residue_entries if item["classification"] == "auto_park_then_delete"],
            "needs_investigation": [item["path"] for item in needs],
            "safe_ephemeral_metadata": [item["path"] for item in ephemeral_repairs if item["safe_to_prune"]],
            "unsafe_ephemeral_worktrees": [item["path"] for item in unsafe_ephemeral],
            "other_prunable_worktrees": [str(entry.path) for entry in other_prunable],
        },
        "parked": parked,
        "actions": actions,
    }
    return payload


def _repair_payload(state: RepoState, *, apply: bool) -> dict[str, Any]:
    lock = _integration_lock(state.common_dir) if apply else nullcontext()
    with lock:
        refreshed = _repo_state(state.cwd) if apply else state
        return _repair_payload_unlocked(refreshed, apply=apply)


def _finish_payload_unlocked(
    state: RepoState,
    *,
    apply: bool,
    run_semantic_checks: bool = True,
    validation_summary: str | None = None,
) -> dict[str, Any]:
    live_owner_blockers = _live_owner_mutation_blockers(state)
    if live_owner_blockers:
        raise GitSafeError(
            "finish cannot collapse the repo while managed live paths still point into temporary Git state",
            blockers=live_owner_blockers,
        )
    assessment = _authority_assessment(state)
    active_change = _managed_active_change(state, assessment)
    if active_change is None or not active_change.branch:
        raise GitSafeError("finish requires an active non-authoritative change")
    authoritative_branch = active_change.authoritative_branch or assessment.default_branch or _branch_name_from_ref(
        assessment.default_ref,
        repo_root=state.repo_root,
    )
    if authoritative_branch is None:
        raise GitSafeError("could not infer the ground-truth line")
    if state.branch == active_change.branch and state.dirty:
        raise GitSafeError("finish requires the active change to be committed")
    semantic_checks = (
        _semantic_closeout_results(state.repo_root, active_change.task_class)
        if run_semantic_checks
        else []
    )
    failed_semantic_checks = [item for item in semantic_checks if not item.get("ok")]
    if failed_semantic_checks:
        raise GitSafeError(
            "finish is blocked by repo-declared semantic closeout checks",
            blockers=[f"semantic closeout check failed: {item['name']}" for item in failed_semantic_checks],
            data={"task_class": active_change.task_class, "semantic_closeout": semantic_checks},
        )
    ignored_output_delta = _ignored_output_delta(state.repo_root, active_change.ignored_output_baseline)
    if ignored_output_delta:
        raise GitSafeError(
            "finish cannot discard declared task-relevant ignored outputs",
            blockers=[f"declared ignored task output {item['change']}: {item['path']}" for item in ignored_output_delta],
            data={"ignored_task_output_delta": ignored_output_delta},
        )

    actions: list[str] = []
    source_is_current_worktree = (
        active_change.mode == "worktree"
        and active_change.checkout_path is not None
        and Path(active_change.checkout_path).resolve(strict=False) == state.repo_root.resolve()
    )
    authoritative_checkout = _authoritative_control_checkout(
        state,
        authoritative_branch,
        exclude_path=state.repo_root,
    )
    if apply and authoritative_checkout is None:
        actions.extend(_reclaim_clean_worktrees_for_branch(state, authoritative_branch, exclude_path=state.repo_root))
        if actions:
            state = _repo_state(state.cwd)

    land_payload = _land_payload(
        state,
        branch=active_change.branch,
        target_branch=authoritative_branch,
        source_worktree_path=active_change.checkout_path if active_change.mode == "worktree" else None,
        target_worktree_path=str(authoritative_checkout) if authoritative_checkout is not None else None,
        preserve_target_dirty=True,
        apply=apply,
        dry_run=not apply,
    )
    actions.extend(land_payload.get("actions", []))
    preserve_payload: dict[str, Any] | None = None

    if not land_payload.get("ok"):
        land_blockers = set(land_payload.get("blockers", []))
        expected_non_ff_blocker = "target branch cannot fast-forward to the source branch"
        if land_blockers != {expected_non_ff_blocker}:
            raise GitSafeError(
                "finish cannot preserve the active change",
                blockers=list(land_payload.get("blockers", [])),
                data={"land": land_payload},
            )
        raise GitSafeError(
            "finish requires the task worktree to replay onto the latest authoritative line",
            blockers=["rebase or replay the task branch in its own worktree, resolve conflicts there, then retry yeet"],
            data={"land": land_payload},
        )

    control_checkout = authoritative_checkout or (state.repo_root if state.branch == authoritative_branch else None)
    if control_checkout is None and source_is_current_worktree:
        control_checkout = _repository_control_checkout(state, exclude_path=state.repo_root)
    if apply:
        integrated_tip = _ref_commit(authoritative_branch, cwd=state.repo_root)
        canonical_fingerprint = land_payload.get("dirty_fingerprint_after") or land_payload.get("dirty_fingerprint_before")
        _set_active_change(
            state, branch=active_change.branch, authoritative_branch=authoritative_branch,
            lifecycle="integrated_local", checkout_path=Path(active_change.checkout_path) if active_change.checkout_path else state.repo_root,
            mode=active_change.mode, parking_ref=active_change.parking_ref, bundle_path=active_change.bundle_path,
            phase="integrated_local",
            integrated_tip=integrated_tip,
            canonical_dirty_fingerprint=canonical_fingerprint,
            validation_summary=validation_summary,
        )
        _test_stop_after("integrated_local")
    repair_payload = _repair_payload(_repo_state(control_checkout or state.repo_root), apply=False)

    return {
        "command": "finish",
        "schema_version": STATE_SCHEMA_VERSION,
        "command_ok": True,
        "policy_ok": True,
        "ok": True,
        "repo_root": str(state.repo_root),
        "branch": active_change.branch,
        "authoritative_branch": authoritative_branch,
        "land": land_payload,
        "cherry_pick": preserve_payload,
        "cleanup_deferred": True,
        "control_checkout": str(control_checkout) if control_checkout is not None else None,
        "cleanup": None,
        "ignored_task_output_delta": ignored_output_delta,
        "semantic_closeout": semantic_checks,
        "task_class": active_change.task_class,
        "repair": repair_payload,
        "actions": actions,
    }


def _finish_payload(state: RepoState, *, apply: bool) -> dict[str, Any]:
    with _integration_lock(state.common_dir):
        return _finish_payload_unlocked(state, apply=apply)


def _review_preservation_proof(state: RepoState, change: ManagedChange) -> dict[str, Any]:
    if not change.branch or not change.published_tip or not change.review_remote or not change.review_ref:
        raise GitSafeError(
            "pull-request retirement requires recorded branch publication proof",
            blockers=["push the task branch through codex-git-safe, then create or confirm its pull request"],
        )
    local_tip = _ref_commit(change.branch, cwd=state.repo_root)
    tracking_tip = _ref_commit(change.review_ref, cwd=state.repo_root)
    if local_tip != change.published_tip or tracking_tip != change.published_tip:
        raise GitSafeError(
            "the task branch changed after its recorded pull-request publication",
            blockers=["refresh the updated task publication, then retry yeet"],
            data={"branch": change.branch, "local_tip": local_tip, "tracking_tip": tracking_tip, "published_tip": change.published_tip},
        )
    review_remote, review_branch = change.review_ref.split("/", 1)
    if review_remote != change.review_remote or not review_branch:
        raise GitSafeError("the recorded pull-request review ref is malformed")
    remote_proc = _run(
        ["git", "ls-remote", "--heads", change.review_remote, f"refs/heads/{review_branch}"],
        cwd=state.repo_root,
    )
    if remote_proc.returncode != 0:
        detail = remote_proc.stderr.strip() or remote_proc.stdout.strip() or "git ls-remote failed"
        raise GitSafeError(detail)
    remote_tip = remote_proc.stdout.split()[0] if remote_proc.stdout.strip() else ""
    if remote_tip != change.published_tip:
        raise GitSafeError(
            "the remote pull-request branch does not match the recorded task tip",
            blockers=["restore the exact task-tip publication, then retry yeet"],
            data={"branch": review_branch, "remote_tip": remote_tip, "published_tip": change.published_tip},
        )
    return {
        "branch": change.branch,
        "published_tip": change.published_tip,
        "review_remote": change.review_remote,
        "review_ref": change.review_ref,
        "review_branch": review_branch,
        "remote_tip": remote_tip,
        "verified": True,
    }


def _retire_submitted_change(
    state: RepoState,
    change: ManagedChange,
    authoritative_branch: str,
    *,
    checkpoint_file: str | None = None,
    update_checkpoint: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    proof = _review_preservation_proof(state, change)
    if change.mode == "branch":
        if state.dirty:
            raise GitSafeError("the compatibility retirement path refuses a dirty branch-mode checkout")
        switch_proc = _run(["git", "switch", authoritative_branch], cwd=state.repo_root)
        if switch_proc.returncode != 0:
            raise GitSafeError(switch_proc.stderr.strip() or switch_proc.stdout.strip() or "could not restore authoritative branch")
        control_checkout = state.repo_root
    else:
        control_checkout = _repository_control_checkout(state, exclude_path=state.repo_root)
    if control_checkout is None:
        raise GitSafeError(
            "the task cannot retire without a persistent checkout outside it",
            blockers=["restore one repository checkout outside the submitted task and retry yeet"],
        )
    control_state = _repo_state(control_checkout)
    # Compute the stable queue identity first, then update the shared
    # checkpoint before any local retirement. If interrupted, the active task
    # remains retryable at the persisted checkpoint phase.
    submission = _submitted_change_record(change)
    checkpoint = (
        _update_yeet_checkpoint(control_state, change, submission, checkpoint_file)
        if update_checkpoint
        else {"state": "compatibility_path", "updated": False}
    )
    if checkpoint.get("updated") and change.checkpoint_generation is None:
        _set_active_change(
            state,
            branch=change.branch,
            authoritative_branch=change.authoritative_branch,
            lifecycle="ready_for_integration",
            checkout_path=Path(change.checkout_path) if change.checkout_path else state.repo_root,
            mode=change.mode,
            phase="checkpoint_updated",
            checkpoint_generation=checkpoint["generation"],
            checkpoint_updated_at=_iso_now(),
        )
        state = _repo_state(state.cwd)
        change = _managed_active_change(state, _authority_assessment(state)) or change
        _test_stop_after("checkpoint_updated")
    submission = _record_submitted_change(control_state, change)
    cleanup = _cleanup_payload(
        control_state,
        branch=change.branch,
        base=authoritative_branch,
        worktree_path=change.checkout_path if change.mode == "worktree" else None,
        cwd_override=str(control_checkout),
        delete_remote=None,
        confirm_remote_delete=None,
        preserved_ref=change.review_ref,
        apply=True,
        dry_run=False,
    )
    if cleanup.get("blockers"):
        raise GitSafeError("task retirement failed after pull-request preservation", blockers=list(cleanup["blockers"]), data={"cleanup": cleanup})
    return proof, cleanup, submission, checkpoint


def _mark_review_ready_payload_unlocked(
    state: RepoState,
    *,
    review_ref: str,
    review_url: str,
    apply: bool,
) -> dict[str, Any]:
    assessment = _authority_assessment(state)
    active_change = _managed_active_change(state, assessment)
    if active_change is None or not active_change.branch:
        raise GitSafeError("review-ready requires an active task")
    if _thread_closeout_mode(state.repo_root) != "pull_request":
        raise GitSafeError("review-ready is available only in pull-request thread-closeout mode")
    if state.dirty:
        raise GitSafeError("review-ready requires a clean committed task branch")
    published_tip = _ref_commit(active_change.branch, cwd=state.repo_root)
    tracking_tip = _ref_commit(review_ref, cwd=state.repo_root)
    if tracking_tip != published_tip:
        raise GitSafeError("review ref does not preserve the current task tip")
    if not review_url.strip():
        raise GitSafeError("review URL is required")
    remote = review_ref.split("/", 1)[0] if "/" in review_ref else None
    if not remote:
        raise GitSafeError("review ref must be a remote-tracking ref such as origin/codex/topic")
    authoritative_branch = active_change.authoritative_branch or assessment.default_branch or _branch_name_from_ref(
        assessment.default_ref, repo_root=state.repo_root
    )
    base_tip = _ref_commit(authoritative_branch, cwd=state.repo_root) if authoritative_branch else None
    if apply:
        _set_active_change(
            state,
            branch=active_change.branch,
            authoritative_branch=authoritative_branch,
            lifecycle="ready_for_integration",
            checkout_path=Path(active_change.checkout_path) if active_change.checkout_path else state.repo_root,
            mode=active_change.mode,
            phase="ready_for_integration",
            published_tip=published_tip,
            base_tip=base_tip,
            review_remote=remote,
            review_ref=review_ref,
            review_url=review_url.strip(),
        )
    return {
        "command": "review-ready",
        "schema_version": STATE_SCHEMA_VERSION,
        "ok": True,
        "apply_requested": apply,
        "branch": active_change.branch,
        "published_tip": published_tip,
        "review_ref": review_ref,
        "review_url": review_url.strip(),
        "state": "ready_for_integration" if apply else "plan",
    }


def _mark_review_ready_payload(
    state: RepoState,
    *,
    review_ref: str,
    review_url: str,
    apply: bool,
) -> dict[str, Any]:
    lock = _integration_lock(state.common_dir) if apply else nullcontext()
    with lock:
        return _mark_review_ready_payload_unlocked(
            _repo_state(state.cwd),
            review_ref=review_ref,
            review_url=review_url,
            apply=apply,
        )


def _import_review_payload_unlocked(
    state: RepoState,
    *,
    review_ref: str,
    review_url: str,
    expected_tip: str | None,
    goal_id: str | None,
    thread_id: str | None,
    dependencies: list[str],
    apply: bool,
) -> dict[str, Any]:
    assessment = _authority_assessment(state)
    active_change = _managed_active_change(state, assessment)
    if active_change is None or not _is_integration_task(state.repo_root, active_change.task_class):
        raise GitSafeError(
            "review-import requires an active project integration task",
            blockers=["start or adopt a configured integration task before importing an external pull request"],
        )
    if _thread_closeout_mode(state.repo_root) != "pull_request":
        raise GitSafeError("review-import requires pull-request thread-closeout mode")
    if state.dirty:
        raise GitSafeError("review-import requires a clean integration worktree")
    if "/" not in review_ref:
        raise GitSafeError("review ref must be a remote-tracking ref such as origin/codex/topic")
    review_remote, branch = review_ref.split("/", 1)
    published_tip = _ref_commit(review_ref, cwd=state.repo_root)
    if not published_tip:
        raise GitSafeError("review ref does not resolve to a commit")
    if expected_tip and expected_tip != published_tip:
        raise GitSafeError(
            "review ref does not match the expected immutable head",
            data={"review_ref": review_ref, "expected_tip": expected_tip, "published_tip": published_tip},
        )
    remote_proc = _run(
        ["git", "ls-remote", "--heads", review_remote, f"refs/heads/{branch}"],
        cwd=state.repo_root,
    )
    if remote_proc.returncode != 0:
        raise GitSafeError(remote_proc.stderr.strip() or remote_proc.stdout.strip() or "could not verify review ref")
    remote_tip = remote_proc.stdout.split()[0] if remote_proc.stdout.strip() else ""
    if remote_tip != published_tip:
        raise GitSafeError("remote pull-request branch does not match the imported review ref")
    if not review_url.strip():
        raise GitSafeError("review URL is required")
    authoritative_branch = active_change.authoritative_branch or assessment.default_branch or _branch_name_from_ref(
        assessment.default_ref, repo_root=state.repo_root
    )
    base_tip = _ref_commit(authoritative_branch, cwd=state.repo_root) if authoritative_branch else None
    imported = ManagedChange(
        branch=branch,
        authoritative_branch=authoritative_branch,
        lifecycle="ready_for_integration",
        checkout_path=None,
        mode="imported_review",
        created_at=_iso_now(),
        updated_at=_iso_now(),
        phase="ready_for_integration",
        task_class="ordinary",
        published_tip=published_tip,
        base_tip=base_tip,
        review_remote=review_remote,
        review_ref=review_ref,
        review_url=review_url.strip(),
    )
    record = _submitted_change_record(imported)
    if goal_id:
        record["goal_id"] = goal_id
    if thread_id:
        record["thread_id"] = thread_id
    if dependencies:
        record["dependencies"] = list(dict.fromkeys(dependencies))
    if apply:
        payload = _load_managed_state(state.common_dir)
        payload["submitted_changes"] = [
            item for item in payload.get("submitted_changes", [])
            if item.get("queue_id") != record["queue_id"] and item.get("published_tip") != published_tip
        ]
        payload["submitted_changes"].append(record)
        _save_managed_state(state.common_dir, payload)
    return {
        "command": "review-import",
        "schema_version": STATE_SCHEMA_VERSION,
        "ok": True,
        "apply_requested": apply,
        "submission": record,
        "remote_tip": remote_tip,
        "state": "ready_for_integration" if apply else "plan",
    }


def _import_review_payload(state: RepoState, **kwargs: Any) -> dict[str, Any]:
    lock = _integration_lock(state.common_dir) if kwargs.get("apply") else nullcontext()
    with lock:
        return _import_review_payload_unlocked(_repo_state(state.cwd), **kwargs)


def _integrate_payload_unlocked(state: RepoState, *, source_refs: list[str], apply: bool) -> dict[str, Any]:
    assessment = _authority_assessment(state)
    active_change = _managed_active_change(state, assessment)
    if active_change is None or not active_change.branch:
        raise GitSafeError("integrate requires an active project integration task")
    if _thread_closeout_mode(state.repo_root) != "pull_request":
        raise GitSafeError("integrate requires pull-request thread-closeout mode")
    if not _is_integration_task(state.repo_root, active_change.task_class):
        raise GitSafeError(
            "integrate is restricted to a project integration task",
            blockers=["start the project/build thread with a configured integration task class"],
        )
    if state.dirty:
        raise GitSafeError("integrate requires a clean integration worktree before selecting pull requests")
    refs = list(dict.fromkeys(source_refs))
    if not refs:
        raise GitSafeError("integrate requires at least one --source-ref")
    managed = _load_managed_state(state.common_dir)
    submitted_by_selector: dict[str, dict[str, Any]] = {}
    known_by_selector: dict[str, dict[str, Any]] = {}
    for item in managed.get("integrated_changes", []):
        for key in ("review_ref", "review_url", "queue_id"):
            value = item.get(key)
            if isinstance(value, str) and value:
                known_by_selector[value] = item
    for item in managed.get("submitted_changes", []):
        for key in ("review_ref", "review_url", "queue_id"):
            value = item.get(key)
            if isinstance(value, str) and value:
                known_by_selector[value] = item
                submitted_by_selector[value] = item
    selections: list[dict[str, Any]] = []
    blockers: list[str] = []
    selected_review_refs: list[str] = []
    for source_selector in refs:
        item = submitted_by_selector.get(source_selector)
        if item is None:
            blockers.append(f"source selector is not a recorded ready pull request: {source_selector}")
            continue
        source_ref = item.get("review_ref")
        if not isinstance(source_ref, str):
            blockers.append(f"recorded pull request is missing its immutable review ref: {source_selector}")
            continue
        tip = _ref_commit(source_ref, cwd=state.repo_root)
        if tip != item.get("published_tip"):
            blockers.append(f"source ref moved after task submission: {source_ref}")
            continue
        review_remote = item.get("review_remote")
        branch = item.get("branch")
        if not isinstance(review_remote, str) or not isinstance(branch, str) or "/" not in source_ref:
            blockers.append(f"source ref is missing remote publication metadata: {source_ref}")
            continue
        source_remote, review_branch = source_ref.split("/", 1)
        if source_remote != review_remote or not review_branch:
            blockers.append(f"source ref does not match its recorded publication remote: {source_ref}")
            continue
        remote_proc = _run(
            ["git", "ls-remote", "--heads", review_remote, f"refs/heads/{review_branch}"],
            cwd=state.repo_root,
        )
        if remote_proc.returncode != 0:
            blockers.append(f"could not verify the live remote tip for {source_ref}")
            continue
        remote_tip = remote_proc.stdout.split()[0] if remote_proc.stdout.strip() else ""
        if remote_tip != tip:
            blockers.append(f"remote pull-request branch moved after task submission: {source_ref}")
            continue
        selections.append(
            {
                "source_selector": source_selector,
                "source_ref": source_ref,
                "published_tip": tip,
                "remote_tip": remote_tip,
                "branch": branch,
                **({"queue_id": item["queue_id"]} if isinstance(item.get("queue_id"), str) else {}),
                **({"dependencies": item["dependencies"]} if isinstance(item.get("dependencies"), list) else {}),
                **({"review_url": item["review_url"]} if isinstance(item.get("review_url"), str) else {}),
            }
        )
        selected_review_refs.append(source_ref)
    selected_keys = set(refs)
    selected_by_selector: dict[str, dict[str, Any]] = {}
    for selection in selections:
        selected_keys.add(selection["source_ref"])
        selected_by_selector[selection["source_ref"]] = selection
        for key in ("queue_id", "review_url"):
            value = selection.get(key)
            if isinstance(value, str):
                selected_keys.add(value)
                selected_by_selector[value] = selection
    dependency_edges: dict[str, set[str]] = {selection["source_ref"]: set() for selection in selections}
    for selection in selections:
        for dependency in selection.get("dependencies", []):
            if dependency in selected_keys:
                dependency_selection = selected_by_selector.get(dependency)
                if dependency_selection is not None:
                    dependency_edges[selection["source_ref"]].add(dependency_selection["source_ref"])
                continue
            dependency_item = known_by_selector.get(dependency)
            dependency_tip = dependency_item.get("published_tip") if dependency_item else None
            if isinstance(dependency_tip, str) and _is_ancestor(dependency_tip, active_change.branch, cwd=state.repo_root):
                continue
            blockers.append(f"selected review has an unresolved dependency: {selection['source_ref']} -> {dependency}")
    if blockers:
        raise GitSafeError("project integration selection is not safe", blockers=blockers, data={"selections": selections})
    # Merge dependencies before their dependents regardless of caller order.
    # A cycle is an invalid integration plan, never an arbitrary merge order.
    ordered_refs: list[str] = []
    ready = sorted(ref for ref, deps in dependency_edges.items() if not deps)
    while ready:
        ref = ready.pop(0)
        ordered_refs.append(ref)
        for candidate, deps in dependency_edges.items():
            if ref in deps:
                deps.remove(ref)
                if not deps and candidate not in ordered_refs and candidate not in ready:
                    ready.append(candidate)
                    ready.sort()
    if len(ordered_refs) != len(selections):
        cyclic = sorted(ref for ref, deps in dependency_edges.items() if deps)
        raise GitSafeError(
            "project integration selection contains a dependency cycle",
            blockers=[f"cyclic selected review dependency: {ref}" for ref in cyclic],
            data={"selections": selections},
        )
    selection_by_ref = {selection["source_ref"]: selection for selection in selections}
    selections = [selection_by_ref[ref] for ref in ordered_refs]
    actions: list[str] = []
    if apply:
        for selection in selections:
            source_ref = selection["source_ref"]
            if _is_ancestor(selection["published_tip"], active_change.branch, cwd=state.repo_root):
                actions.append(f"already included {source_ref}")
                continue
            merge_proc = _run(["git", "merge", "--no-ff", "--no-edit", source_ref], cwd=state.repo_root)
            if merge_proc.returncode != 0:
                detail = merge_proc.stderr.strip() or merge_proc.stdout.strip() or f"git merge {source_ref} failed"
                raise GitSafeError(
                    f"integration stopped while merging {source_ref}: {detail}",
                    blockers=["resolve or abort the merge in the integration worktree before continuing"],
                    data={"completed_actions": actions, "failed_source_ref": source_ref},
                )
            actions.append(f"merged {source_ref} into {active_change.branch}")
        selected = list(dict.fromkeys([*active_change.selected_refs, *selected_review_refs]))
        _set_active_change(
            _repo_state(state.repo_root),
            branch=active_change.branch,
            authoritative_branch=active_change.authoritative_branch,
            lifecycle="working",
            checkout_path=Path(active_change.checkout_path) if active_change.checkout_path else state.repo_root,
            mode=active_change.mode,
            phase="working",
            selected_refs=selected,
        )
    return {
        "command": "integrate",
        "schema_version": STATE_SCHEMA_VERSION,
        "ok": True,
        "apply_requested": apply,
        "branch": active_change.branch,
        "selections": selections,
        "actions": actions,
    }


def _integrate_payload(state: RepoState, *, source_refs: list[str], apply: bool) -> dict[str, Any]:
    lock = _integration_lock(state.common_dir) if apply else nullcontext()
    with lock:
        return _integrate_payload_unlocked(_repo_state(state.cwd), source_refs=source_refs, apply=apply)


def _retire_integrated_change(state: RepoState, change: ManagedChange, authoritative_branch: str, control_checkout: Path, *, canonical_dirty_fingerprint: str | None = None) -> dict[str, Any]:
    cleanup = _cleanup_payload(
        _repo_state(control_checkout), branch=change.branch, base=authoritative_branch,
        worktree_path=change.checkout_path if change.mode == "worktree" else None,
        cwd_override=str(control_checkout), delete_remote=None, confirm_remote_delete=None,
        preserved_ref=authoritative_branch, apply=True, dry_run=False,
    )
    if cleanup.get("blockers"):
        raise GitSafeError("retirement failed after keeper preservation", blockers=list(cleanup["blockers"]), data={"cleanup": cleanup})
    control_state = _repo_state(control_checkout)
    if canonical_dirty_fingerprint is not None:
        after = _dirty_fingerprint(control_state.repo_root)["digest"]
        if after != canonical_dirty_fingerprint:
            raise GitSafeError("canonical dirty fingerprint changed during task retirement")
    _record_retired_change(control_state, change)
    _clear_active_change(control_state, checkout_path=Path(change.checkout_path) if change.checkout_path else None)
    return cleanup


def _park_payload_unlocked(state: RepoState, *, apply: bool) -> dict[str, Any]:
    live_owner_blockers = _live_owner_mutation_blockers(state)
    if apply and live_owner_blockers:
        raise GitSafeError(
            "park cannot proceed while managed live paths still point into temporary Git state",
            blockers=live_owner_blockers,
        )
    assessment = _authority_assessment(state)
    active_change = _managed_active_change(state, assessment)
    if active_change is None or not active_change.branch:
        raise GitSafeError("park requires an active change")
    checkout_path = Path(active_change.checkout_path).resolve(strict=False) if active_change.checkout_path else state.repo_root
    park_ref = None
    bundle_path = None
    remote_ref = None
    actions: list[str] = []
    if apply:
        park_ref, bundle_path, remote_ref = _park_checkout(state, checkout_path, classification="parked")
        actions.append(f"parked {active_change.branch} at {park_ref}")
        authoritative_branch = active_change.authoritative_branch or assessment.default_branch or _branch_name_from_ref(
            assessment.default_ref,
            repo_root=state.repo_root,
        )
        if state.branch == active_change.branch and authoritative_branch and authoritative_branch != active_change.branch:
            switch_proc = _run(["git", "switch", authoritative_branch], cwd=state.repo_root)
            if switch_proc.returncode != 0:
                detail = switch_proc.stderr.strip() or switch_proc.stdout.strip() or "git switch failed"
                raise GitSafeError(detail)
            actions.append(f"switched current checkout to {authoritative_branch}")
    parked_change = ManagedChange(
        branch=active_change.branch,
        authoritative_branch=active_change.authoritative_branch,
        lifecycle="parked",
        checkout_path=str(checkout_path),
        mode=active_change.mode,
        created_at=active_change.created_at,
        updated_at=_iso_now(),
        parking_ref=park_ref,
        bundle_path=bundle_path,
        task_class=active_change.task_class,
        ignored_output_baseline=active_change.ignored_output_baseline,
    )
    if apply:
        _append_parked_change(state, parked_change)
        _set_active_change(
            state,
            branch=active_change.branch,
            authoritative_branch=active_change.authoritative_branch,
            lifecycle="parked",
            checkout_path=checkout_path,
            mode=active_change.mode,
            parking_ref=park_ref,
            bundle_path=bundle_path,
        )
    return {
        "command": "park",
        "schema_version": STATE_SCHEMA_VERSION,
        "command_ok": True,
        "policy_ok": True,
        "ok": True,
        "repo_root": str(state.repo_root),
        "branch": active_change.branch,
        "authoritative_branch": active_change.authoritative_branch,
        "parking_ref": park_ref,
        "bundle_path": bundle_path,
        "remote_ref": remote_ref,
        "actions": actions,
    }


def _park_payload(state: RepoState, *, apply: bool) -> dict[str, Any]:
    with _integration_lock(state.common_dir):
        return _park_payload_unlocked(state, apply=apply)


def _magic_payload_unlocked(state: RepoState, *, apply: bool) -> dict[str, Any]:
    status_before = _status_payload(state)
    lifecycle_state = status_before["state"]
    if state.dirty or lifecycle_state == "working":
        raise GitSafeError(
            "git magic requires the intended work to be committed first",
            blockers=["commit the intended work, then rerun git magic"],
            data={"status": status_before},
        )
    if lifecycle_state == "attention_required":
        raise GitSafeError(
            f"git magic is blocked while repo state is {lifecycle_state}",
            blockers=[f"resolve repo state {lifecycle_state} before git magic"],
            data={"status": status_before},
        )
    if lifecycle_state == "parked":
        return {
            "command": "magic",
            "schema_version": STATE_SCHEMA_VERSION,
            "command_ok": True,
            "policy_ok": True,
            "ok": True,
            "repo_root": str(state.repo_root),
            "apply_requested": apply,
            "result": "parked",
            "status": status_before,
            "actions": [],
        }

    actions: list[str] = []
    finish_payload: dict[str, Any] | None = None
    if lifecycle_state in {"ready_to_finish", "published_for_review"}:
        raise GitSafeError(
            "git magic is graph-wide audit and repair; use yeet for the current task or park it",
            blockers=["run yeet for task-scoped completion, or park --apply"],
            data={"status": status_before},
        )

    assessment = _authority_assessment(state)
    authoritative_branch = assessment.default_branch or _branch_name_from_ref(
        assessment.default_ref,
        repo_root=state.repo_root,
    )
    if authoritative_branch is None:
        raise GitSafeError("git magic could not infer the authoritative line")

    remote_proofs: list[dict[str, Any]] = []
    if apply:
        remote_proofs, push_actions = _push_and_verify_keeper_remotes(state, authoritative_branch)
        actions.extend(push_actions)
        actions.extend(_refresh_remote_tracking_refs(state.repo_root))
        state = _repo_state(state.repo_root)
        # Graph-wide repair has no review-selection authority. Hosted review
        # finalization and queue reconciliation belong only to the active
        # integration task's resumable closeout, scoped by selected_refs.

    repair_payload = _repair_payload(state, apply=apply)
    actions.extend(repair_payload.get("actions", []))
    final_status = _status_payload(_repo_state(state.repo_root)) if apply else status_before
    if apply and final_status.get("state") != "complete":
        raise GitSafeError(
            "git magic did not reach a complete lifecycle state",
            blockers=[f"final repo state is {final_status.get('state')}", f"next action: {final_status.get('next_action')}"],
            data={"final_status": final_status, "remote_proofs": remote_proofs},
        )
    return {
        "command": "magic",
        "schema_version": STATE_SCHEMA_VERSION,
        "command_ok": True,
        "policy_ok": True,
        "ok": True,
        "repo_root": str(state.repo_root),
        "authoritative_branch": authoritative_branch,
        "apply_requested": apply,
        "result": "complete" if apply else "plan",
        "status": status_before,
        "finish": finish_payload,
        "remote_proofs": remote_proofs,
        "repair": repair_payload,
        "final_status": final_status,
        "actions": actions,
    }


def _magic_payload(state: RepoState, *, apply: bool) -> dict[str, Any]:
    lock = _integration_lock(state.common_dir) if apply else nullcontext()
    with lock:
        return _magic_payload_unlocked(_repo_state(state.cwd), apply=apply)


def _closeout_payload_unlocked(state: RepoState, *, apply: bool, confirmed: bool) -> dict[str, Any]:
    status_payload = _status_payload(state)
    lifecycle_state = status_payload["state"]
    payload: dict[str, Any] = {
        "command": "closeout",
        "schema_version": STATE_SCHEMA_VERSION,
        "command_ok": True,
        "policy_ok": status_payload.get("policy_ok", False),
        "ok": True,
        "repo_root": str(state.repo_root),
        "state": lifecycle_state,
        "next_action": status_payload.get("next_action"),
        "apply_requested": apply,
        "confirmed": confirmed,
        "status": status_payload,
        "actions": [],
    }

    if not confirmed:
        payload["result"] = "confirmation_required"
        payload["confirmation_required"] = True
        payload["prompt"] = "Confirm end now? (yes/no)"
        return payload

    assessment = _authority_assessment(state)
    active_change = _managed_active_change(state, assessment)
    semantic_closeout = status_payload.get("semantic_closeout", {})
    if active_change is not None and semantic_closeout.get("ok") is False:
        failed = [item for item in semantic_closeout.get("checks", []) if not item.get("ok")]
        raise GitSafeError(
            "closeout is blocked by repo-declared semantic checks",
            blockers=[f"semantic closeout check failed: {item.get('name', 'unnamed')}" for item in failed],
            data={"status": status_payload},
        )
    authoritative_branch = (active_change.authoritative_branch if active_change else None) or assessment.default_branch or _branch_name_from_ref(
        assessment.default_ref, repo_root=state.repo_root
    )
    closeout_mode = _thread_closeout_mode(state.repo_root)
    if active_change is not None and closeout_mode == "pull_request" and active_change.lifecycle == "ready_for_integration":
        if authoritative_branch is None:
            raise GitSafeError("end could not infer the pull request base branch")
        proof, cleanup, submission, checkpoint = _retire_submitted_change(
            state,
            active_change,
            authoritative_branch,
        )
        control_checkout = (
            state.repo_root
            if active_change.mode == "branch"
            else _repository_control_checkout(state, exclude_path=state.repo_root)
        )
        final_state = _repo_state(control_checkout or state.repo_root)
        payload.update(
            {
                "result": "task_submitted",
                "review_proof": proof,
                "cleanup": cleanup,
                "submission": submission,
                "checkpoint": checkpoint,
                "final_status": _status_payload(final_state),
            }
        )
        return payload
    # A successful retry starts at the first incomplete persisted phase.  The
    # state record is deliberately retained until task-owned retirement ends.
    if active_change is not None and active_change.phase in {"integrated_local", "pushed_verified"}:
        if authoritative_branch is None:
            raise GitSafeError("end could not infer the authoritative line")
        authoritative_checkout = _authoritative_control_checkout(state, authoritative_branch, exclude_path=state.repo_root)
        control_checkout = authoritative_checkout
        if control_checkout is None and active_change.mode == "branch":
            # Branch-mode tasks intentionally run in the canonical checkout.
            # Once their tip is integrated, switching that checkout back to
            # the authoritative branch is safe; it is never worktree removal.
            if state.dirty:
                raise GitSafeError("end refuses to switch a dirty branch-mode checkout", blockers=[f"canonical checkout is dirty: {state.repo_root}"])
            switch_proc = _run(["git", "switch", authoritative_branch], cwd=state.repo_root)
            if switch_proc.returncode != 0:
                raise GitSafeError(switch_proc.stderr.strip() or switch_proc.stdout.strip() or "could not restore authoritative branch")
            control_checkout = state.repo_root
            payload["actions"].append(f"switched canonical checkout to {authoritative_branch}")
        if control_checkout is None:
            control_checkout = _repository_control_checkout(state, exclude_path=state.repo_root)
        if control_checkout is None:
            raise GitSafeError("end cannot retire without a persistent checkout outside the completed task", blockers=["restore or open one repository checkout outside the completed task and retry end"])
        remote_proofs: list[dict[str, Any]] = []
        proof_state = _repo_state(authoritative_checkout or state.repo_root)
        dirty_proof = _integrated_dirty_proof(proof_state, active_change, authoritative_branch)
        if active_change.integrated_tip is None or (dirty_proof is not None and active_change.canonical_dirty_fingerprint is None):
            # Persist the constrained migration baseline before touching a
            # remote, so an interruption remains resumable and auditable.
            _set_active_change(proof_state, branch=active_change.branch, authoritative_branch=authoritative_branch,
                lifecycle=active_change.lifecycle, checkout_path=Path(active_change.checkout_path), mode=active_change.mode,
                parking_ref=active_change.parking_ref, bundle_path=active_change.bundle_path, phase=active_change.phase,
                integrated_tip=_ref_commit(authoritative_branch, cwd=proof_state.repo_root), canonical_dirty_fingerprint=dirty_proof)
            active_change = _managed_active_change(_repo_state(state.repo_root), _authority_assessment(_repo_state(state.repo_root))) or active_change
        # Never trust remote proof persisted before interruption: a remote
        # may have advanced or been rewritten while this task was paused.
        remote_proofs, push_actions = _push_and_verify_keeper_remotes(proof_state, authoritative_branch, canonical_dirty_fingerprint=dirty_proof)
        payload["actions"].extend(push_actions)
        if active_change.phase != "pushed_verified":
            _set_active_change(proof_state, branch=active_change.branch, authoritative_branch=authoritative_branch,
                lifecycle="pushed_verified", checkout_path=Path(active_change.checkout_path), mode=active_change.mode,
                parking_ref=active_change.parking_ref, bundle_path=active_change.bundle_path, phase="pushed_verified")
            active_change = _managed_active_change(_repo_state(state.repo_root), _authority_assessment(_repo_state(state.repo_root))) or active_change
            _test_stop_after("pushed_verified")
        # Push itself must not alter canonical dirt; prove it again before
        # retirement, whose only mutation is task-owned worktree/ref removal.
        dirty_proof = _integrated_dirty_proof(proof_state, active_change, authoritative_branch)
        integrated_submissions: list[dict[str, Any]] = []
        hosted_review_finalization: list[dict[str, Any]] = []
        if closeout_mode == "pull_request" and _is_integration_task(state.repo_root, active_change.task_class):
            candidates = _integrated_submission_candidates(
                proof_state, authoritative_branch, active_change.selected_refs
            )
            authoritative_tip = _ref_commit(authoritative_branch, cwd=proof_state.repo_root)
            if candidates and authoritative_tip:
                hosted_review_finalization = _finalize_integrated_gitea_reviews(
                    proof_state, candidates, authoritative_tip
                )
            integrated_submissions = _reconcile_integrated_submissions(
                proof_state, authoritative_branch, active_change.selected_refs
            )
        cleanup = _retire_integrated_change(_repo_state(control_checkout), active_change, authoritative_branch, control_checkout, canonical_dirty_fingerprint=dirty_proof)
        payload.update({"result": "task_complete", "remote_proofs": remote_proofs, "cleanup": cleanup,
                        "integrated_submissions": integrated_submissions,
                        "hosted_review_finalization": hosted_review_finalization,
                        "final_status": _status_payload(_repo_state(control_checkout))})
        return payload

    if lifecycle_state in {"complete", "ready_to_finish", "ready_to_push", "repair_needed"}:
        finish_payload = None
        if lifecycle_state == "ready_to_finish":
            if (
                closeout_mode == "pull_request"
                and active_change is not None
                and not _is_integration_task(state.repo_root, active_change.task_class)
            ):
                return _submit_payload_unlocked(state, pr_args=[], apply=apply)
            finish_payload = _finish_payload(state, apply=apply)
            payload["actions"].extend(finish_payload.get("actions", []))
            # _finish persists integrated_local.  Resume through this same
            # closeout function so push is proven before any task retirement.
            resumed = _closeout_payload_unlocked(_repo_state(state.cwd), apply=apply, confirmed=True)
            resumed["finish"] = {**finish_payload, "cleanup_deferred": False}
            return resumed
        remote_proofs: list[dict[str, Any]] = []
        if apply:
            control_path = Path(finish_payload["control_checkout"]) if finish_payload else state.repo_root
            refreshed = _repo_state(control_path)
            assessment = _authority_assessment(refreshed)
            authoritative_branch = assessment.default_branch or _branch_name_from_ref(
                assessment.default_ref, repo_root=refreshed.repo_root
            )
            if authoritative_branch is None:
                raise GitSafeError("end could not infer the authoritative line")
            remote_proofs, push_actions = _push_and_verify_keeper_remotes(refreshed, authoritative_branch)
            payload["actions"].extend(push_actions)
        payload["result"] = "task_complete"
        payload["finish"] = finish_payload
        payload["push_mode"] = "keeper_remotes"
        payload["remote_proofs"] = remote_proofs
        final_control_path = Path(finish_payload["control_checkout"]) if finish_payload else state.repo_root
        payload["final_status"] = _status_payload(_repo_state(final_control_path)) if apply else status_payload
        return payload
    if lifecycle_state == "published_for_review":
        if closeout_mode == "pull_request":
            raise GitSafeError(
                "legacy review publication lacks exact pull-request retirement proof",
                blockers=["rerun task-branch push and PR publication so the current tip and remote ref are recorded"],
                data={"status": status_payload},
            )
        raise GitSafeError(
            "closeout is blocked while the current change is only published for review",
            blockers=[
                "published-for-review is not default closeout completion",
                "land the reviewed change on the authoritative line, or park --apply to keep it separate",
            ],
            data={"status": status_payload},
        )
    if lifecycle_state == "parked":
        payload["result"] = lifecycle_state
        return payload
    if lifecycle_state == "working":
        raise GitSafeError(
            "closeout is blocked while the current change is still in progress",
            blockers=[
                "closeout is blocked while the current change is still in progress",
                "commit or park the current change before closing out",
            ],
            data={"status": status_payload},
        )
    raise GitSafeError(
        "closeout is blocked until the repo lifecycle is resolved",
        blockers=[
            f"closeout is blocked while repo state is {lifecycle_state}",
            f"next action: {status_payload.get('next_action')}",
        ],
        data={"status": status_payload},
    )


def _closeout_payload(state: RepoState, *, apply: bool, confirmed: bool) -> dict[str, Any]:
    """Run all state inspection, integration, cleanup, and keeper proof under one lock."""
    lock = _integration_lock(state.common_dir) if apply else nullcontext()
    with lock:
        # Do not trust a state computed before queueing for the integration lock.
        refreshed_state = _repo_state(state.cwd)
        return _closeout_payload_unlocked(refreshed_state, apply=apply, confirmed=confirmed)


def _delegate_helper_process(
    env_name: str,
    default_name: str,
    extra_args: list[str],
    *,
    capture_output: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    helper_override = os.environ.get(env_name)
    helper_path = Path(helper_override).expanduser().resolve() if helper_override else (REPO_ROOT / "bin" / default_name)
    if not helper_path.exists():
        raise GitSafeError(f"helper not found: {helper_path}")
    return subprocess.run(
        [str(helper_path), *extra_args],
        cwd=str(cwd or Path.cwd()),
        check=False,
        capture_output=capture_output,
        text=capture_output,
    )


def _delegate_helper(env_name: str, default_name: str, extra_args: list[str]) -> int:
    return _delegate_helper_process(env_name, default_name, extra_args).returncode


def _yeet_text_input(
    *,
    value: str | None,
    file_value: str | None,
    repo_root: Path,
    label: str,
    required: bool = False,
    max_bytes: int = 131072,
) -> str | None:
    if value is not None and file_value is not None:
        raise GitSafeError(f"--{label} and --{label}-file are mutually exclusive")
    text = value
    if file_value is not None:
        path = _resolve_path(file_value, base=repo_root)
        if path is None or not path.is_file() or path.is_symlink():
            raise GitSafeError(f"--{label}-file must name a regular file")
        if path.stat().st_size > max_bytes:
            raise GitSafeError(f"--{label}-file exceeds {max_bytes} bytes")
        text = path.read_text(encoding="utf-8")
    if text is not None:
        text = text.strip()
    if required and not text:
        raise GitSafeError(
            f"yeet requires a {label.replace('-', ' ')} recorded by the working thread",
            blockers=[f"supply --{label} or --{label}-file; yeet does not run product tests"],
        )
    return text or None


def _project_checkpoint_helper() -> str:
    configured = os.environ.get(PROJECT_CHECKPOINT_HELPER_ENV)
    helper = configured or shutil.which("codex-project-checkpoint")
    if not helper:
        raise GitSafeError("codex-project-checkpoint is unavailable")
    return helper


def _project_checkpoint_resolution(repo_root: Path) -> dict[str, Any]:
    proc = _run([_project_checkpoint_helper(), "show", "--repo", str(repo_root), "--json"], cwd=repo_root)
    if proc.returncode != 0:
        raise GitSafeError(proc.stderr.strip() or proc.stdout.strip() or "could not resolve the project checkpoint")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise GitSafeError("codex-project-checkpoint returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise GitSafeError("codex-project-checkpoint returned a non-object result")
    state = payload.get("state")
    if state in {"missing", "unreadable", "identity_mismatch", "corrupt"} or payload.get("ok") is False:
        raise GitSafeError(
            "the project checkpoint is not safe to update",
            blockers=[f"checkpoint resolver state: {state or 'unknown'}"],
        )
    return payload


def _replace_checkpoint_placeholders(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        rendered = value
        for placeholder, replacement in replacements.items():
            rendered = rendered.replace(placeholder, replacement)
        return rendered
    if isinstance(value, list):
        return [_replace_checkpoint_placeholders(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_checkpoint_placeholders(item, replacements)
            for key, item in value.items()
        }
    return value


def _checkpoint_placeholders(value: Any) -> set[str]:
    if isinstance(value, str):
        return set(re.findall(r"\{\{[A-Za-z0-9_]+\}\}", value))
    if isinstance(value, list):
        return set().union(*(_checkpoint_placeholders(item) for item in value), set())
    if isinstance(value, dict):
        return set().union(*(_checkpoint_placeholders(item) for item in value.values()), set())
    return set()


def _update_yeet_checkpoint(
    state: RepoState,
    change: ManagedChange,
    submission: dict[str, Any],
    checkpoint_file: str | None,
) -> dict[str, Any]:
    resolution = _project_checkpoint_resolution(state.repo_root)
    if not resolution.get("adopted"):
        return {"state": resolution.get("state", "not_adopted"), "updated": False}
    generation = resolution.get("generation")
    if not isinstance(generation, int):
        raise GitSafeError("the adopted project checkpoint has no generation")
    if change.checkpoint_generation is not None:
        if generation < change.checkpoint_generation:
            raise GitSafeError("the current project checkpoint predates the task's recorded update")
        return {
            "state": "current",
            "updated": True,
            "generation": change.checkpoint_generation,
            "current_generation": generation,
            "idempotent": True,
        }
    if checkpoint_file is None:
        raise GitSafeError(
            "yeet requires a generation-checked project checkpoint model for this adopted repository",
            blockers=[
                "supply --checkpoint-file with the reconciled checkpoint JSON model; review fields may use {{review_url}}, {{published_tip}}, {{queue_id}}, {{review_ref}}, and {{branch}}"
            ],
        )
    template_path = _resolve_path(checkpoint_file, base=state.repo_root)
    if template_path is None or not template_path.is_file() or template_path.is_symlink():
        raise GitSafeError("--checkpoint-file must name a regular JSON model file")
    if template_path.stat().st_size > 131072:
        raise GitSafeError("--checkpoint-file exceeds 131072 bytes")
    try:
        model = json.loads(template_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GitSafeError("--checkpoint-file is not valid JSON") from exc
    replacements = {
        "{{review_url}}": str(submission.get("review_url", "")),
        "{{published_tip}}": str(submission.get("published_tip", "")),
        "{{queue_id}}": str(submission.get("queue_id", "")),
        "{{review_ref}}": str(submission.get("review_ref", "")),
        "{{branch}}": str(submission.get("branch", change.branch or "")),
    }
    rendered_model = _replace_checkpoint_placeholders(model, replacements)
    unresolved = sorted(_checkpoint_placeholders(rendered_model))
    if unresolved:
        raise GitSafeError(
            "the checkpoint model contains unsupported unresolved placeholders",
            blockers=[f"unresolved checkpoint placeholder: {item}" for item in unresolved],
        )
    state_dir = state.common_dir / "codex-git-safe"
    state_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        prefix="checkpoint-model-",
        suffix=".json",
        dir=str(state_dir),
        delete=False,
    ) as handle:
        json.dump(rendered_model, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
        rendered_path = Path(handle.name)
    try:
        proc = _run(
            [
                _project_checkpoint_helper(),
                "update",
                "--repo",
                str(state.repo_root),
                "--expected-generation",
                str(generation),
                "--file",
                str(rendered_path),
                "--json",
            ],
            cwd=state.repo_root,
        )
    finally:
        rendered_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise GitSafeError(
            proc.stderr.strip() or proc.stdout.strip() or "project checkpoint update failed",
            blockers=["re-read and reconcile the current checkpoint generation, then rerun yeet"],
        )
    try:
        updated = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise GitSafeError("project checkpoint update returned invalid JSON") from exc
    updated_generation = updated.get("generation") if isinstance(updated, dict) else None
    if updated_generation != generation + 1:
        raise GitSafeError("project checkpoint update did not advance exactly one generation")
    return {"state": "current", "updated": True, "generation": updated_generation}


def _validate_yeet_checkpoint_input(state: RepoState, checkpoint_file: str | None) -> dict[str, Any]:
    resolution = _project_checkpoint_resolution(state.repo_root)
    if not resolution.get("adopted"):
        return resolution
    if checkpoint_file is None:
        raise GitSafeError(
            "yeet requires a generation-checked project checkpoint model for this adopted repository",
            blockers=[
                "supply --checkpoint-file with the reconciled checkpoint JSON model before yeet mutates Git state"
            ],
        )
    template_path = _resolve_path(checkpoint_file, base=state.repo_root)
    if template_path is None or not template_path.is_file() or template_path.is_symlink():
        raise GitSafeError("--checkpoint-file must name a regular JSON model file")
    if template_path.stat().st_size > 131072:
        raise GitSafeError("--checkpoint-file exceeds 131072 bytes")
    try:
        model = json.loads(template_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GitSafeError("--checkpoint-file is not valid JSON") from exc
    if not isinstance(model, dict):
        raise GitSafeError("--checkpoint-file must contain a JSON object model")
    if _is_inside(template_path, state.repo_root):
        relative = str(template_path.relative_to(state.repo_root))
        status = _run(["git", "status", "--porcelain=v1", "--", relative], cwd=state.repo_root)
        if status.returncode != 0:
            raise GitSafeError("could not prove checkpoint model scope")
        if status.stdout.strip():
            raise GitSafeError(
                "a checkpoint transaction model cannot be part of the task delta",
                blockers=["place the generated checkpoint JSON outside the repository and rerun yeet"],
            )
    return resolution


def _default_yeet_subject(branch: str) -> str:
    topic = branch.removeprefix("codex/")
    words = re.sub(r"[^A-Za-z0-9]+", " ", topic).strip().lower()
    words = words or "task changes"
    return f"chore: {words}"[:72].rstrip()


def _git_operation_blockers(repo_root: Path) -> list[str]:
    blockers: list[str] = []
    operation_paths = {
        "merge": "MERGE_HEAD",
        "cherry-pick": "CHERRY_PICK_HEAD",
        "revert": "REVERT_HEAD",
        "rebase": "rebase-merge",
        "rebase apply": "rebase-apply",
    }
    for label, git_path in operation_paths.items():
        resolved = _git_output(["rev-parse", "--git-path", git_path], cwd=repo_root)
        path = Path(resolved)
        if not path.is_absolute():
            path = repo_root / path
        if path.exists():
            blockers.append(f"{label} is in progress")
    unmerged = _run(["git", "ls-files", "-u"], cwd=repo_root)
    if unmerged.returncode != 0:
        blockers.append("could not inspect the index for unmerged entries")
    elif unmerged.stdout.strip():
        blockers.append("the index contains unmerged entries")
    return blockers


def _ordinary_yeet_preflight(state: RepoState, change: ManagedChange) -> dict[str, Any]:
    blockers: list[str] = []
    if change.mode != "worktree":
        blockers.append("ordinary yeet requires a managed task worktree")
    if not change.checkout_path or Path(change.checkout_path).resolve(strict=False) != state.repo_root.resolve(strict=False):
        blockers.append("the registered task checkout does not match the current checkout")
    if not change.branch or state.branch != change.branch:
        blockers.append("the current branch does not match the registered task branch")
    if state.detached:
        blockers.append("ordinary yeet refuses detached HEAD")
    if not change.start_tip:
        blockers.append("the task has no recorded clean isolation baseline")
    elif not _is_ancestor(change.start_tip, state.head, cwd=state.repo_root):
        blockers.append("the current task tip no longer descends from its recorded isolation baseline")
    blockers.extend(_git_operation_blockers(state.repo_root))
    ignored_delta = _ignored_output_delta(state.repo_root, change.ignored_output_baseline)
    blockers.extend(
        f"declared ignored task output {item['change']}: {item['path']}"
        for item in ignored_delta
    )
    dirty_proof: dict[str, Any] | None = None
    if state.dirty:
        try:
            dirty_proof = _dirty_fingerprint(state.repo_root)
        except GitSafeError as exc:
            blockers.append(str(exc))
    has_commits = bool(change.start_tip and state.head != change.start_tip)
    if not state.dirty and not has_commits and change.lifecycle == "working":
        blockers.append("the task has no changes to publish")
    if blockers:
        raise GitSafeError(
            "ordinary yeet preconditions are not satisfied",
            blockers=blockers,
            data={"task_class": change.task_class},
        )
    return {
        "start_tip": change.start_tip,
        "head": state.head,
        "dirty": state.dirty,
        "dirty_paths": sorted(dirty_proof["paths"]) if dirty_proof else [],
        "has_commits": has_commits,
    }


def _integration_yeet_preflight(state: RepoState, change: ManagedChange) -> dict[str, Any]:
    blockers: list[str] = []
    if change.mode != "worktree":
        blockers.append("integration yeet requires a managed integration worktree")
    if not change.checkout_path or Path(change.checkout_path).resolve(strict=False) != state.repo_root.resolve(strict=False):
        blockers.append("the registered integration checkout does not match the current checkout")
    if not change.branch or state.branch != change.branch:
        blockers.append("the current branch does not match the registered integration branch")
    if state.detached:
        blockers.append("integration yeet refuses detached HEAD")
    if state.dirty:
        blockers.append("integration yeet refuses opportunistic uncommitted changes")
    blockers.extend(_git_operation_blockers(state.repo_root))
    if not change.selected_refs:
        blockers.append("integration yeet requires refs already selected through the integration transaction")
    if not change.start_tip:
        blockers.append("the integration task has no recorded clean isolation baseline")
    elif not _is_ancestor(change.start_tip, state.head, cwd=state.repo_root):
        blockers.append("the integration tip no longer descends from its recorded isolation baseline")
    selected_tips: dict[str, str] = {}
    for source_ref in change.selected_refs:
        try:
            tip = _ref_commit(source_ref, cwd=state.repo_root)
        except GitSafeError as exc:
            blockers.append(f"selected ref cannot be resolved: {source_ref}: {exc}")
            continue
        selected_tips[source_ref] = tip
        if not _is_ancestor(tip, state.head, cwd=state.repo_root):
            blockers.append(f"selected ref is not present in the integration tip: {source_ref}")
    if change.start_tip and state.head != change.start_tip:
        first_parent = _run(
            ["git", "rev-list", "--first-parent", f"{change.start_tip}..{state.head}"],
            cwd=state.repo_root,
        )
        if first_parent.returncode != 0:
            blockers.append("could not inspect integration first-parent history")
        else:
            for commit in [line for line in first_parent.stdout.splitlines() if line.strip()]:
                parents = _git_output(["show", "-s", "--format=%P", commit], cwd=state.repo_root).split()
                if len(parents) < 2:
                    blockers.append(f"integration history contains an ordinary commit: {commit}")
    if blockers:
        raise GitSafeError(
            "integration yeet preconditions are not satisfied",
            blockers=blockers,
            data={"task_class": change.task_class, "selected_refs": list(change.selected_refs)},
        )
    return {
        "start_tip": change.start_tip,
        "head": state.head,
        "selected_refs": list(change.selected_refs),
        "selected_tips": selected_tips,
    }


def _finalize_integration_yeet_unlocked(
    state: RepoState,
    change: ManagedChange,
    *,
    checkpoint_file: str | None,
    transaction: str = "selected_integration",
    reconcile_selected: bool = True,
) -> dict[str, Any]:
    authoritative_branch = change.authoritative_branch or _authority_assessment(state).default_branch
    if authoritative_branch is None:
        raise GitSafeError("integration yeet could not infer the authoritative line")
    authoritative_checkout = _authoritative_control_checkout(
        state,
        authoritative_branch,
        exclude_path=state.repo_root,
    )
    control_checkout = authoritative_checkout or _repository_control_checkout(
        state,
        exclude_path=state.repo_root,
    )
    if control_checkout is None:
        raise GitSafeError(
            "integration yeet cannot retire without a persistent checkout outside the task",
            blockers=["restore one repository checkout outside the integration task and rerun yeet"],
        )
    proof_state = _repo_state(authoritative_checkout or control_checkout)
    dirty_proof = _integrated_dirty_proof(proof_state, change, authoritative_branch)
    integrated_tip = change.integrated_tip or _ref_commit(authoritative_branch, cwd=proof_state.repo_root)
    if change.integrated_tip is None:
        _set_active_change(
            proof_state,
            branch=change.branch,
            authoritative_branch=authoritative_branch,
            lifecycle="integrated_local",
            checkout_path=Path(change.checkout_path) if change.checkout_path else state.repo_root,
            mode=change.mode,
            phase="integrated_local",
            integrated_tip=integrated_tip,
            canonical_dirty_fingerprint=dirty_proof,
        )
        change = _managed_active_change(_repo_state(state.repo_root), _authority_assessment(_repo_state(state.repo_root))) or change
    remote_proofs, actions = _push_and_verify_keeper_remotes(
        proof_state,
        authoritative_branch,
        canonical_dirty_fingerprint=dirty_proof,
    )
    if not remote_proofs:
        raise GitSafeError("integration yeet did not resolve a keeper remote")
    if change.phase not in {"pushed_verified", "checkpoint_updated"}:
        _set_active_change(
            proof_state,
            branch=change.branch,
            authoritative_branch=authoritative_branch,
            lifecycle="pushed_verified",
            checkout_path=Path(change.checkout_path) if change.checkout_path else state.repo_root,
            mode=change.mode,
            phase="pushed_verified",
        )
        change = _managed_active_change(_repo_state(state.repo_root), _authority_assessment(_repo_state(state.repo_root))) or change
        _test_stop_after("pushed_verified")
    candidates = (
        _integrated_submission_candidates(proof_state, authoritative_branch, change.selected_refs)
        if reconcile_selected
        else []
    )
    hosted_review_finalization: list[dict[str, Any]] = []
    if candidates:
        hosted_review_finalization = _finalize_integrated_gitea_reviews(
            proof_state,
            candidates,
            integrated_tip,
        )
    checkpoint_subject = {
        "branch": change.branch,
        "published_tip": integrated_tip,
        "review_ref": ",".join(change.selected_refs),
        "review_url": "",
        "queue_id": "",
    }
    checkpoint = _update_yeet_checkpoint(
        proof_state,
        change,
        checkpoint_subject,
        checkpoint_file,
    )
    if checkpoint.get("updated") and change.checkpoint_generation is None:
        _set_active_change(
            proof_state,
            branch=change.branch,
            authoritative_branch=authoritative_branch,
            lifecycle="pushed_verified",
            checkout_path=Path(change.checkout_path) if change.checkout_path else state.repo_root,
            mode=change.mode,
            phase="checkpoint_updated",
            checkpoint_generation=checkpoint["generation"],
            checkpoint_updated_at=_iso_now(),
        )
        change = _managed_active_change(_repo_state(state.repo_root), _authority_assessment(_repo_state(state.repo_root))) or change
        _test_stop_after("checkpoint_updated")
    integrated_submissions = (
        _reconcile_integrated_submissions(
            proof_state,
            authoritative_branch,
            change.selected_refs,
        )
        if reconcile_selected
        else []
    )
    dirty_proof = _integrated_dirty_proof(proof_state, change, authoritative_branch)
    cleanup = _retire_integrated_change(
        _repo_state(control_checkout),
        change,
        authoritative_branch,
        control_checkout,
        canonical_dirty_fingerprint=dirty_proof,
    )
    if reconcile_selected:
        actions.extend(
            [
                "finalized only the selected hosted reviews",
                "reconciled only the selected integration queue entries",
            ]
        )
    actions.extend(
        [
            "refreshed the adopted project checkpoint when configured",
            "retired the local task state",
        ]
    )
    return {
        "command": "yeet",
        "schema_version": STATE_SCHEMA_VERSION,
        "ok": True,
        "state": "complete",
        "transaction": transaction,
        "remote_proofs": remote_proofs,
        "hosted_review_finalization": hosted_review_finalization,
        "integrated_submissions": integrated_submissions,
        "checkpoint": checkpoint,
        "cleanup": cleanup,
        "actions": actions,
        "final_status": _status_payload(_repo_state(control_checkout)),
    }


def _commit_ordinary_yeet(
    state: RepoState,
    change: ManagedChange,
    *,
    message: str | None,
    validation_summary: str,
) -> tuple[RepoState, ManagedChange, list[str]]:
    actions: list[str] = []
    if state.dirty:
        stage = _run(["git", "add", "-A"], cwd=state.repo_root)
        if stage.returncode != 0:
            raise GitSafeError(stage.stderr.strip() or stage.stdout.strip() or "could not stage the proven task delta")
        staged = _run(["git", "diff", "--cached", "--quiet"], cwd=state.repo_root)
        if staged.returncode == 0:
            raise GitSafeError("the proven task delta produced an empty index")
        if staged.returncode != 1:
            raise GitSafeError(staged.stderr.strip() or staged.stdout.strip() or "could not inspect the staged task delta")
        commit_message = message or _default_yeet_subject(change.branch or "task")
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            prefix="codex-git-safe-yeet-message-",
            dir=str(state.common_dir / "codex-git-safe"),
            delete=False,
        ) as handle:
            handle.write(commit_message.rstrip() + "\n")
            message_path = Path(handle.name)
        try:
            commit = _run(["git", "commit", "-F", str(message_path)], cwd=state.repo_root)
        finally:
            message_path.unlink(missing_ok=True)
        if commit.returncode != 0:
            raise GitSafeError(
                commit.stderr.strip() or commit.stdout.strip() or "task commit failed",
                blockers=["the task remains staged; resolve the commit or hook failure, then rerun yeet"],
            )
        actions.append("staged the proven task delta and created its commit")
    refreshed = _repo_state(state.repo_root)
    _set_active_change(
        refreshed,
        branch=change.branch,
        authoritative_branch=change.authoritative_branch,
        lifecycle="working",
        checkout_path=Path(change.checkout_path) if change.checkout_path else refreshed.repo_root,
        mode=change.mode,
        phase="committed",
        validation_summary=validation_summary,
    )
    refreshed = _repo_state(state.repo_root)
    refreshed_change = _managed_active_change(refreshed, _authority_assessment(refreshed))
    if refreshed_change is None:
        raise GitSafeError("yeet lost the active task after committing it")
    _test_stop_after("committed")
    return refreshed, refreshed_change, actions


def _yeet_submitted_result(state: RepoState, selector: str) -> dict[str, Any]:
    managed = _load_managed_state(state.common_dir)
    matches = [
        item
        for item in managed.get("submitted_changes", [])
        if selector in {
            item.get("branch"), item.get("queue_id"), item.get("review_ref"), item.get("review_url")
        }
    ]
    if not matches:
        retired_matches = [
            item
            for item in managed.get("retired_changes", [])
            if selector in {item.get("branch"), item.get("integrated_tip")}
        ]
        if len(retired_matches) != 1:
            raise GitSafeError(
                "yeet could not resolve one retired task",
                blockers=[
                    f"submitted and integrated task selector matched {len(retired_matches)} records: {selector}"
                ],
            )
        item = retired_matches[0]
        branch = item.get("branch")
        authoritative_branch = item.get("authoritative_branch")
        integrated_tip = item.get("integrated_tip")
        if not all(isinstance(value, str) and value for value in (branch, authoritative_branch, integrated_tip)):
            raise GitSafeError("the retired integration record lacks keeper proof metadata")
        local_tip = _ref_commit(authoritative_branch, cwd=state.repo_root)
        if local_tip != integrated_tip:
            raise GitSafeError(
                "the authoritative line no longer matches the retired integration proof",
                blockers=[f"expected {integrated_tip}; observed {local_tip}"],
            )
        remote_proofs: list[dict[str, Any]] = []
        keeper_targets = _keeper_remote_targets(state, authoritative_branch)
        if not keeper_targets:
            raise GitSafeError("the retired integration proof has no configured keeper remote")
        for target in keeper_targets:
            proc = _run(
                ["git", "ls-remote", "--heads", target["remote"], f"refs/heads/{target['branch']}"],
                cwd=state.repo_root,
            )
            remote_tip = proc.stdout.split()[0] if proc.returncode == 0 and proc.stdout.strip() else ""
            proof = {**target, "local_head": local_tip, "remote_head": remote_tip, "verified": remote_tip == local_tip}
            remote_proofs.append(proof)
            if not proof["verified"]:
                raise GitSafeError(
                    "a keeper remote no longer matches the retired integration proof",
                    blockers=[f"{target['remote']}/{target['branch']} is {remote_tip or 'missing'}"],
                )
        registered = any(
            payload.get("branch") == branch
            for payload in managed.get("active_changes", [])
        )
        local_branch = _run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            cwd=state.repo_root,
        ).returncode == 0
        if registered or local_branch:
            raise GitSafeError("the integrated task still has local residue")
        checkpoint_resolution = _project_checkpoint_resolution(state.repo_root)
        if checkpoint_resolution.get("adopted") and not isinstance(item.get("checkpoint_generation"), int):
            raise GitSafeError("the retired integration record lacks adopted checkpoint proof")
        selected_integration = _is_integration_task(state.repo_root, item.get("task_class"))
        return {
            "command": "yeet",
            "schema_version": STATE_SCHEMA_VERSION,
            "ok": True,
            "state": "complete",
            "idempotent": True,
            "transaction": "selected_integration" if selected_integration else "ordinary_integration",
            "integration" if selected_integration else "completion": item,
            "remote_proofs": remote_proofs,
            "cleanup": {"verified": True, "active_registration": False, "local_branch": False},
        }
    if len(matches) != 1:
        raise GitSafeError(
            "yeet could not resolve one retired submitted task",
            blockers=[f"submitted task selector matched {len(matches)} records: {selector}"],
        )
    item = matches[0]
    branch = item.get("branch")
    remote = item.get("review_remote")
    tip = item.get("published_tip")
    if not all(isinstance(value, str) and value for value in (branch, remote, tip)):
        raise GitSafeError("the retired submission record lacks remote proof metadata")
    review_ref = item.get("review_ref")
    if not isinstance(review_ref, str) or "/" not in review_ref:
        raise GitSafeError("the retired submission record lacks a remote-tracking review ref")
    review_remote, review_branch = review_ref.split("/", 1)
    if review_remote != remote or not review_branch:
        raise GitSafeError("the retired submission record has a malformed review ref")
    remote_proc = _run(["git", "ls-remote", "--heads", remote, f"refs/heads/{review_branch}"], cwd=state.repo_root)
    remote_tip = remote_proc.stdout.split()[0] if remote_proc.returncode == 0 and remote_proc.stdout.strip() else ""
    if remote_tip != tip:
        raise GitSafeError(
            "the retired task remote tip no longer matches its submitted proof",
            blockers=[f"expected {tip}; observed {remote_tip or 'missing'}"],
        )
    registered = any(
        payload.get("branch") == branch
        for payload in _load_managed_state(state.common_dir).get("active_changes", [])
    )
    local_branch = _run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=state.repo_root).returncode == 0
    if registered or local_branch:
        raise GitSafeError(
            "the submitted task still has local residue",
            blockers=[f"active registration remains: {registered}", f"local branch remains: {local_branch}"],
        )
    checkpoint_resolution = _project_checkpoint_resolution(state.repo_root)
    if checkpoint_resolution.get("adopted") and not isinstance(item.get("checkpoint_generation"), int):
        raise GitSafeError("the retired submission record lacks adopted checkpoint proof")
    return {
        "command": "yeet",
        "schema_version": STATE_SCHEMA_VERSION,
        "ok": True,
        "state": "ready_for_integration",
        "idempotent": True,
        "submission": item,
        "review_proof": {
            "branch": branch,
            "published_tip": tip,
            "review_remote": remote,
            "review_ref": review_ref,
            "review_branch": review_branch,
            "remote_tip": remote_tip,
            "verified": True,
        },
        "cleanup": {"verified": True, "active_registration": False, "local_branch": False},
    }


def _yeet_payload_unlocked(
    state: RepoState,
    *,
    message: str | None,
    message_file: str | None,
    validation: str | None,
    validation_file: str | None,
    title: str | None,
    body_file: str | None,
    update_existing: bool,
    checkpoint_file: str | None,
    task_selector: str | None,
    apply: bool,
) -> dict[str, Any]:
    assessment = _authority_assessment(state)
    active_change = _managed_active_change(state, assessment)
    if active_change is None:
        if task_selector:
            return _yeet_submitted_result(state, task_selector)
        if _is_disposable_codex_worktree(state):
            if state.dirty:
                raise GitSafeError(
                    "yeet found an unregistered app worktree after content changes",
                    blockers=[
                        "session-start registration did not complete before the first mutation",
                        "the clean isolation baseline is no longer recoverable; the worktree was retained for read-only inspection",
                    ],
                )
            raise GitSafeError(
                "yeet found a clean app worktree whose session-start registration did not complete",
                blockers=["run adopt-current from this exact clean checkout, then retry yeet"],
            )
        raise GitSafeError(
            "yeet requires a registered task",
            blockers=["run from the managed task worktree or pass --task for an idempotent retired-task proof"],
        )
    if task_selector:
        raise GitSafeError("--task is only valid for re-proving a retired yeet from a persistent checkout")
    closeout_mode = _thread_closeout_mode(state.repo_root)
    validation_summary = _yeet_text_input(
        value=validation,
        file_value=validation_file,
        repo_root=state.repo_root,
        label="validation",
        required=True,
        max_bytes=16384,
    )
    assert validation_summary is not None
    if not re.match(r"(?i)^pass(?:ed)?(?:\s|:|-)", validation_summary):
        raise GitSafeError(
            "yeet requires an explicit passing validation record",
            blockers=["record the working thread result as PASS: <checks and result>; yeet does not run them"],
        )
    checkpoint_resolution = _validate_yeet_checkpoint_input(state, checkpoint_file)
    checkpoint_path = (
        str(_resolve_path(checkpoint_file, base=state.repo_root))
        if checkpoint_file is not None
        else None
    )
    if _is_integration_task(state.repo_root, active_change.task_class):
        scope = _integration_yeet_preflight(state, active_change)
        if not apply:
            return {
                "command": "yeet",
                "schema_version": STATE_SCHEMA_VERSION,
                "ok": True,
                "state": "plan",
                "task_class": active_change.task_class,
                "transaction": "selected_integration",
                "scope": scope,
                "actions": [
                    "fast-forward the authoritative line to the selected integration tip",
                    "push and verify each configured keeper remote",
                    "finalize only the selected hosted reviews",
                    "reconcile only the selected integration queue entries",
                    "refresh the adopted project checkpoint when configured",
                    "retire the local integration worktree, branch, and registration",
                ],
                "checkpoint": {
                    "state": checkpoint_resolution.get("state"),
                    "adopted": bool(checkpoint_resolution.get("adopted")),
                },
            }
        if active_change.phase not in {"integrated_local", "pushed_verified", "checkpoint_updated"}:
            _finish_payload_unlocked(
                state,
                apply=True,
                run_semantic_checks=False,
                validation_summary=validation_summary,
            )
            state = _repo_state(state.cwd)
            active_change = _managed_active_change(state, _authority_assessment(state)) or active_change
        result = _finalize_integration_yeet_unlocked(
            state,
            active_change,
            checkpoint_file=checkpoint_path,
        )
        result["validation_summary"] = validation_summary
        result["scope"] = scope
        return result
    scope = _ordinary_yeet_preflight(state, active_change)
    commit_message = _yeet_text_input(
        value=message,
        file_value=message_file,
        repo_root=state.repo_root,
        label="message",
    )
    if closeout_mode == "integrate":
        if not apply:
            return {
                "command": "yeet",
                "schema_version": STATE_SCHEMA_VERSION,
                "ok": True,
                "state": "plan",
                "task_class": active_change.task_class,
                "transaction": "ordinary_integration",
                "scope": scope,
                "actions": [
                    "stage and commit the proven task delta if needed",
                    "advance the authoritative line to the exact task tip",
                    "push and verify each configured keeper remote",
                    "refresh the adopted project checkpoint when configured",
                    "retire the local task worktree, branch, and registration",
                ],
                "checkpoint": {
                    "state": checkpoint_resolution.get("state"),
                    "adopted": bool(checkpoint_resolution.get("adopted")),
                },
            }
        state, active_change, actions = _commit_ordinary_yeet(
            state,
            active_change,
            message=commit_message,
            validation_summary=validation_summary,
        )
        if active_change.phase not in {"integrated_local", "pushed_verified", "checkpoint_updated"}:
            _finish_payload_unlocked(
                state,
                apply=True,
                run_semantic_checks=False,
                validation_summary=validation_summary,
            )
            state = _repo_state(state.cwd)
            active_change = _managed_active_change(state, _authority_assessment(state)) or active_change
        completed = _finalize_integration_yeet_unlocked(
            state,
            active_change,
            checkpoint_file=checkpoint_path,
            transaction="ordinary_integration",
            reconcile_selected=False,
        )
        completed["validation_summary"] = validation_summary
        completed["scope"] = scope
        completed["actions"] = [*actions, *completed.get("actions", [])]
        return completed
    pr_args: list[str] = ["--title", title or _default_yeet_subject(active_change.branch or "task")]
    if body_file:
        body_path = _resolve_path(body_file, base=state.repo_root)
        if body_path is None or not body_path.is_file() or body_path.is_symlink():
            raise GitSafeError("--body-file must name a regular file")
        pr_args.extend(["--body-file", str(body_path)])
    if update_existing:
        pr_args.append("--update-existing")
    if not apply:
        return {
            "command": "yeet",
            "schema_version": STATE_SCHEMA_VERSION,
            "ok": True,
            "state": "plan",
            "task_class": active_change.task_class,
            "transaction": "ordinary_pull_request",
            "scope": scope,
            "actions": [
                "stage and commit the proven task delta if needed",
                "push the exact task tip",
                "create or confirm one ready pull request",
                "verify the live remote tip",
                "record the integration queue entry",
                "refresh the adopted project checkpoint when configured",
                "retire the local task worktree, branch, and registration",
            ],
            "checkpoint": {
                "state": checkpoint_resolution.get("state"),
                "adopted": bool(checkpoint_resolution.get("adopted")),
            },
        }
    state, active_change, actions = _commit_ordinary_yeet(
        state,
        active_change,
        message=commit_message,
        validation_summary=validation_summary,
    )
    submitted = _submit_payload_unlocked(
        state,
        pr_args=pr_args,
        apply=True,
        checkpoint_file=checkpoint_path,
        update_checkpoint=True,
    )
    submitted["command"] = "yeet"
    submitted["transaction"] = "ordinary_pull_request"
    submitted["validation_summary"] = validation_summary
    submitted["scope"] = scope
    submitted["actions"] = [*actions, *submitted.get("actions", [])]
    return submitted


def _yeet_payload(state: RepoState, **kwargs: Any) -> dict[str, Any]:
    apply = bool(kwargs.get("apply"))
    lock = _integration_lock(state.common_dir) if apply else nullcontext()
    with lock:
        return _yeet_payload_unlocked(_repo_state(state.cwd), **kwargs)


def _submit_payload_unlocked(
    state: RepoState,
    *,
    pr_args: list[str],
    apply: bool,
    checkpoint_file: str | None = None,
    update_checkpoint: bool = False,
) -> dict[str, Any]:
    assessment = _authority_assessment(state)
    active_change = _managed_active_change(state, assessment)
    if active_change is None or not active_change.branch:
        raise GitSafeError("submit requires an active task")
    if _thread_closeout_mode(state.repo_root) != "pull_request":
        raise GitSafeError("submit requires pull-request thread-closeout mode")
    if _is_integration_task(state.repo_root, active_change.task_class):
        raise GitSafeError("submit is for ordinary work tasks, not integration tasks")
    if state.dirty:
        raise GitSafeError("submit requires a clean committed task branch")
    if active_change.lifecycle not in {"working", "review_pending", "ready_for_integration"}:
        raise GitSafeError(f"submit cannot resume task lifecycle {active_change.lifecycle}")
    if not apply:
        return {
            "command": "submit",
            "schema_version": STATE_SCHEMA_VERSION,
            "ok": True,
            "apply_requested": False,
            "state": "plan",
            "branch": active_change.branch,
            "actions": ["push exact task tip", "create or confirm pull request", "verify remote tip", "record integration queue entry", "retire local task state"],
        }

    actions: list[str] = []
    if active_change.lifecycle == "working":
        review_ref = state.upstream
        push_args: list[str] = []
        if review_ref and "/" in review_ref:
            review_remote, review_branch = review_ref.split("/", 1)
            if not review_remote or not review_branch:
                raise GitSafeError("the task upstream is not a valid remote-tracking review ref")
            if review_branch != active_change.branch:
                authoritative_branch = active_change.authoritative_branch or assessment.default_branch or _branch_name_from_ref(
                    assessment.default_ref, repo_root=state.repo_root
                )
                if review_branch == authoritative_branch:
                    # A newly isolated topic can inherit the base branch's
                    # upstream.  That relationship describes its baseline,
                    # not an existing review target.
                    review_ref = None
                else:
                    expected_review_tip = active_change.published_tip or active_change.start_tip
                    tracking_tip = _ref_commit(review_ref, cwd=state.repo_root)
                    if tracking_tip != expected_review_tip:
                        raise GitSafeError(
                            "the existing review target moved after its last managed task state",
                            blockers=["refresh or replay the task from the current review head before retrying yeet"],
                            data={"review_ref": review_ref, "tracking_tip": tracking_tip, "expected_tip": expected_review_tip},
                        )
                    remote_proc = _run(
                        ["git", "ls-remote", "--heads", review_remote, f"refs/heads/{review_branch}"],
                        cwd=state.repo_root,
                    )
                    remote_tip = remote_proc.stdout.split()[0] if remote_proc.returncode == 0 and remote_proc.stdout.strip() else ""
                    if remote_tip != expected_review_tip:
                        raise GitSafeError(
                            "the live existing review target does not match its last managed task state",
                            blockers=["refresh or replay the task from the current review head before retrying yeet"],
                            data={"review_ref": review_ref, "remote_tip": remote_tip, "expected_tip": expected_review_tip},
                        )
                    push_args = ["--destination-branch", review_branch, review_remote, active_change.branch]
        push = _delegate_helper_process(PUSH_HELPER_ENV, "codex-gitea-push.sh", push_args, capture_output=True)
        if push.returncode != 0:
            raise GitSafeError((push.stderr or push.stdout or "managed task push failed").strip())
        actions.append("pushed task branch through the managed helper")
        state = _repo_state(state.cwd)
        active_change = _managed_active_change(state, _authority_assessment(state)) or active_change
        review_ref = review_ref or state.upstream
        if not review_ref or "/" not in review_ref:
            raise GitSafeError("task push did not establish a remote-tracking review ref")
        review_remote = review_ref.split("/", 1)[0]
        published_tip = _ref_commit(active_change.branch, cwd=state.repo_root)
        tracking_tip = _ref_commit(review_ref, cwd=state.repo_root)
        if published_tip != tracking_tip:
            raise GitSafeError("task push did not preserve the exact local tip on its tracking ref")
        authoritative_branch = active_change.authoritative_branch or assessment.default_branch or _branch_name_from_ref(
            assessment.default_ref, repo_root=state.repo_root
        )
        base_tip = _ref_commit(authoritative_branch, cwd=state.repo_root) if authoritative_branch else None
        _set_active_change(
            state,
            branch=active_change.branch,
            authoritative_branch=authoritative_branch,
            lifecycle="review_pending",
            checkout_path=Path(active_change.checkout_path) if active_change.checkout_path else state.repo_root,
            mode=active_change.mode,
            phase="review_pending",
            published_tip=published_tip,
            base_tip=base_tip,
            review_remote=review_remote,
            review_ref=review_ref,
        )
        _test_stop_after("review_pending")
        state = _repo_state(state.cwd)
        active_change = _managed_active_change(state, _authority_assessment(state)) or active_change

    if active_change.lifecycle == "review_pending":
        if not active_change.review_ref or "/" not in active_change.review_ref:
            raise GitSafeError("the pending review lacks a remote-tracking review ref")
        review_remote, review_branch = active_change.review_ref.split("/", 1)
        authoritative_branch = active_change.authoritative_branch or assessment.default_branch or _branch_name_from_ref(
            assessment.default_ref, repo_root=state.repo_root
        )
        if not authoritative_branch:
            raise GitSafeError("submit could not infer the pull request base branch")
        helper_args = ["--json", *pr_args, review_remote, review_branch, authoritative_branch]
        pr = _delegate_helper_process(PR_HELPER_ENV, "codex-gitea-pr.sh", helper_args, capture_output=True)
        if pr.returncode != 0:
            raise GitSafeError((pr.stderr or pr.stdout or "managed pull request creation failed").strip())
        try:
            pr_payload = json.loads((pr.stdout or "").strip())
        except json.JSONDecodeError as exc:
            raise GitSafeError("managed pull request helper returned invalid JSON") from exc
        review_url = pr_payload.get("url") if isinstance(pr_payload, dict) else None
        if not isinstance(review_url, str) or not review_url.strip():
            raise GitSafeError("managed pull request helper did not return a review URL")
        if pr_payload.get("draft") is not False:
            raise GitSafeError(
                "managed pull request helper did not prove one ready pull request",
                blockers=["convert the matching review to ready state, then rerun yeet"],
            )
        _set_active_change(
            state,
            branch=active_change.branch,
            authoritative_branch=active_change.authoritative_branch,
            lifecycle="ready_for_integration",
            checkout_path=Path(active_change.checkout_path) if active_change.checkout_path else state.repo_root,
            mode=active_change.mode,
            phase="ready_for_integration",
            published_tip=active_change.published_tip,
            base_tip=active_change.base_tip,
            review_remote=active_change.review_remote,
            review_ref=active_change.review_ref,
            review_url=review_url.strip(),
        )
        _test_stop_after("ready_for_integration")
        actions.append("created or confirmed the pull request")
        state = _repo_state(state.cwd)
        active_change = _managed_active_change(state, _authority_assessment(state)) or active_change

    authoritative_branch = active_change.authoritative_branch or assessment.default_branch or _branch_name_from_ref(
        assessment.default_ref, repo_root=state.repo_root
    )
    if authoritative_branch is None:
        raise GitSafeError("submit could not infer the pull request base branch")
    proof, cleanup, submission, checkpoint = _retire_submitted_change(
        state,
        active_change,
        authoritative_branch,
        checkpoint_file=checkpoint_file,
        update_checkpoint=update_checkpoint,
    )
    actions.extend(["verified the exact remote review tip", "recorded the ready integration queue entry", "retired local task state"])
    control_checkout = _repository_control_checkout(state, exclude_path=state.repo_root)
    return {
        "command": "submit",
        "schema_version": STATE_SCHEMA_VERSION,
        "ok": True,
        "apply_requested": True,
        "state": "ready_for_integration",
        "review_proof": proof,
        "submission": submission,
        "checkpoint": checkpoint,
        "cleanup": cleanup,
        "actions": actions,
        "final_status": _status_payload(_repo_state(control_checkout or state.repo_root)),
    }


def _submit_payload(state: RepoState, *, pr_args: list[str], apply: bool) -> dict[str, Any]:
    lock = _integration_lock(state.common_dir) if apply else nullcontext()
    with lock:
        return _submit_payload_unlocked(_repo_state(state.cwd), pr_args=pr_args, apply=apply)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-git-safe",
        description="Conservative local git helper for Codex change lifecycle.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show a repo change-lifecycle summary.")
    status_parser.add_argument("--json", action="store_true", help="Emit JSON.")

    preflight_parser = subparsers.add_parser("preflight", help="Prove whether this directory is ready for app worktree provisioning.")
    preflight_parser.add_argument("--json", action="store_true", help="Emit JSON.")

    start_parser = subparsers.add_parser("start", help="Start a topic branch or isolated checkout.")
    start_parser.add_argument("--topic", required=True, help="Topic name or branch suffix.")
    start_parser.add_argument("--base", help="Base ref to start from.")
    start_parser.add_argument(
        "--from-current",
        action="store_true",
        help="Start from the current local line instead of the inferred default line.",
    )
    start_parser.add_argument(
        "--mode",
        choices=("auto", "branch", "checkout", "worktree"),
        default="auto",
        metavar="{auto,branch,checkout}",
    )
    start_parser.add_argument("--checkout-root", dest="worktree_root", help="Explicit isolated-checkout root path.")
    start_parser.add_argument("--checkout-path", dest="worktree_path", help="Explicit isolated-checkout path.")
    start_parser.add_argument("--worktree-root", dest="worktree_root", help=argparse.SUPPRESS)
    start_parser.add_argument("--worktree-path", dest="worktree_path", help=argparse.SUPPRESS)
    start_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    start_parser.add_argument("--dry-run", action="store_true", help="Plan only.")
    start_parser.add_argument("--task-class", default="ordinary", help="Repo-declared semantic task class. Defaults to ordinary.")

    adopt_parser = subparsers.add_parser("adopt-current", help="Attach and register this detached Codex app worktree.")
    adopt_parser.add_argument("--topic", help="Optional topic suffix for the generated branch.")
    adopt_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    adopt_parser.add_argument("--apply", action="store_true", help="Attach and register the worktree.")
    adopt_parser.add_argument("--task-class", help="Repo-declared semantic task class. Defaults to ordinary for a new registration.")
    adopt_parser.add_argument(
        "--if-eligible",
        action="store_true",
        help="Return a successful no-op outside an app-created linked worktree.",
    )
    adopt_parser.add_argument(
        "--provisional-ordinary",
        action="store_true",
        help="Mark a new session-start ordinary class as clean-state promotable.",
    )

    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help=argparse.SUPPRESS,
        description="Advanced internal cleanup verb for migration and debugging.",
    )
    cleanup_parser.add_argument("--branch", help="Branch to inspect or delete.")
    cleanup_parser.add_argument("--base", help="Base ref used for the unique-commit proof.")
    cleanup_parser.add_argument("--checkout-path", dest="worktree_path", help="Target isolated-checkout path.")
    cleanup_parser.add_argument("--worktree-path", dest="worktree_path", help=argparse.SUPPRESS)
    cleanup_parser.add_argument("--cwd", help="Override cwd used for containment checks.")
    cleanup_parser.add_argument("--delete-remote", help="Delete the branch from the named remote.")
    cleanup_parser.add_argument(
        "--confirm-remote-delete",
        help="Required exact REMOTE/BRANCH confirmation for remote branch deletion.",
    )
    cleanup_parser.add_argument("--preserved-ref", help="Ref that should already preserve the branch tip.")
    cleanup_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    cleanup_parser.add_argument("--dry-run", action="store_true", help="Report only.")
    cleanup_parser.add_argument("--apply", action="store_true", help="Apply safe cleanup mutations.")

    land_parser = subparsers.add_parser(
        "land",
        help=argparse.SUPPRESS,
        description="Advanced internal landing verb for migration and debugging.",
    )
    land_parser.add_argument("--branch", help="Source branch to land. Defaults to the current branch.")
    land_parser.add_argument("--target-branch", help="Target branch to receive the validated line.")
    land_parser.add_argument("--source-checkout-path", dest="source_worktree_path", help="Source isolated-checkout path.")
    land_parser.add_argument("--target-checkout-path", dest="target_worktree_path", help="Target authoritative checkout path.")
    land_parser.add_argument("--source-worktree-path", dest="source_worktree_path", help=argparse.SUPPRESS)
    land_parser.add_argument("--target-worktree-path", dest="target_worktree_path", help=argparse.SUPPRESS)
    land_parser.add_argument(
        "--preserve-target-dirty",
        action="store_true",
        help="Allow a conflict-free fast-forward when the target checkout has non-overlapping dirty changes.",
    )
    land_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    land_parser.add_argument("--dry-run", action="store_true", help="Report only.")
    land_parser.add_argument("--apply", action="store_true", help="Apply safe land mutations.")

    integrate_parser = subparsers.add_parser(
        "integrate",
        help="Merge selected ready pull-request refs into the current project integration task.",
    )
    integrate_parser.add_argument(
        "--source-ref",
        action="append",
        required=True,
        dest="source_refs",
        help="Recorded remote-tracking ref to include. Repeat for multiple pull requests.",
    )
    integrate_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    integrate_parser.add_argument("--apply", action="store_true", help="Apply the selected merges.")

    review_ready_parser = subparsers.add_parser(
        "review-ready",
        help="Record an externally created pull request, such as one opened through the GitHub plugin.",
    )
    review_ready_parser.add_argument("--review-ref", required=True, help="Exact remote-tracking ref preserving the task tip.")
    review_ready_parser.add_argument("--review-url", required=True, help="Pull request URL returned by the hosting provider.")
    review_ready_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    review_ready_parser.add_argument("--apply", action="store_true", help="Record the pull request as ready for integration.")

    review_import_parser = subparsers.add_parser(
        "review-import",
        help="Import an existing immutable pull request into the active project integration queue.",
    )
    review_import_parser.add_argument("--review-ref", required=True, help="Exact remote-tracking ref preserving the pull request head.")
    review_import_parser.add_argument("--review-url", required=True, help="Hosted pull request URL.")
    review_import_parser.add_argument("--expected-tip", help="Optional exact head SHA that the review ref must match.")
    review_import_parser.add_argument(
        "--goal-id",
        help="Optional historical correlation label; never used to select or authorize integration.",
    )
    review_import_parser.add_argument("--thread-id", help="Optional originating thread identifier.")
    review_import_parser.add_argument("--depends-on", action="append", default=[], dest="dependencies", help="Queue ID, PR URL, or ref that must land first. Repeat as needed.")
    review_import_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    review_import_parser.add_argument("--apply", action="store_true", help="Record the pull request as ready for integration.")

    submit_parser = subparsers.add_parser(
        "submit",
        help="Run a locked, resumable push, pull-request proof, durable queue, and local-retirement sequence.",
    )
    submit_parser.add_argument("--title", help="Optional pull request title.")
    submit_parser.add_argument("--body-file", help="Optional pull request body file.")
    submit_parser.add_argument("--update-existing", action="store_true", help="Refresh an existing matching pull request.")
    submit_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    submit_parser.add_argument("--apply", action="store_true", help="Run the resumable submission sequence.")

    yeet_parser = subparsers.add_parser(
        "yeet",
        help="Take the registered task to its configured terminal Git disposition.",
    )
    yeet_parser.add_argument("--message", help="Commit message for a remaining uncommitted task delta.")
    yeet_parser.add_argument("--message-file", help="File containing the commit message.")
    yeet_parser.add_argument(
        "--validation",
        help="Compact validation result already established by the working thread; yeet does not run tests.",
    )
    yeet_parser.add_argument("--validation-file", help="File containing the working thread's validation result.")
    yeet_parser.add_argument("--title", help="Pull request title for an ordinary task.")
    yeet_parser.add_argument("--body-file", help="Pull request body file for an ordinary task.")
    yeet_parser.add_argument(
        "--checkpoint-file",
        help="Generation-checked checkpoint JSON model required by an adopted repository.",
    )
    yeet_parser.add_argument("--update-existing", action="store_true", help="Refresh an existing matching pull request.")
    yeet_parser.add_argument(
        "--task",
        dest="task_selector",
        help="Branch, queue ID, review ref, or review URL used only to re-prove an already retired yeet.",
    )
    yeet_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    yeet_parser.add_argument("--apply", action="store_true", help="Run the resumable yeet transaction.")

    goal_broker_parser = subparsers.add_parser(
        "goal-broker",
        help="Retired; custom Goal Train Git transactions have mutation authority none.",
    )
    goal_broker_parser.add_argument("retired_arguments", nargs=argparse.REMAINDER)

    finish_parser = subparsers.add_parser("finish", help="Bless the active change onto the ground-truth line.")
    finish_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    finish_parser.add_argument("--apply", action="store_true", help="Apply the finish flow.")

    park_parser = subparsers.add_parser("park", help="Keep the active change off the ground-truth line on purpose.")
    park_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    park_parser.add_argument("--apply", action="store_true", help="Apply parking mutations.")

    repair_parser = subparsers.add_parser("repair", help="Audit or reclaim leftover temporary Git state.")
    repair_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    repair_parser.add_argument("--plan", action="store_true", help="Report the repair plan without mutating.")
    repair_parser.add_argument("--apply", action="store_true", help="Apply safe repair and auto-parking mutations.")

    magic_parser = subparsers.add_parser(
        "magic",
        help="Audit, repair, push, and verify the repository graph; it never finishes an active task.",
    )
    magic_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    magic_parser.add_argument("--apply", action="store_true", help="Apply safe graph repair and keeper verification.")

    closeout_parser = subparsers.add_parser(
        "closeout",
        help="Run the managed closeout state machine after confirmation.",
    )
    closeout_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    closeout_parser.add_argument("--apply", action="store_true", help="Apply the closeout state machine.")
    closeout_parser.add_argument("-yes", dest="yes", action="store_true", help="Confirm and apply closeout.")

    end_parser = subparsers.add_parser(
        "end",
        help="Run the managed closeout state machine after confirmation.",
    )
    end_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    end_parser.add_argument("--apply", action="store_true", help="Apply the closeout state machine.")
    end_parser.add_argument("-yes", dest="yes", action="store_true", help="Confirm and apply closeout.")

    push_parser = subparsers.add_parser("push", help="Delegate to the managed Gitea push helper.")
    push_parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed through to codex-gitea-push.sh.")

    pr_parser = subparsers.add_parser("pr", help="Delegate to the managed Gitea PR helper.")
    pr_parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed through to codex-gitea-pr.sh.")

    return parser


def _emit_error(exc: GitSafeError, *, json_output: bool, command: str | None = None) -> None:
    if json_output:
        payload = {
            "command": command,
            "ok": False,
            "error": str(exc),
            "blockers": exc.blockers,
        }
        payload.update(exc.data)
        _print_json(payload)
    else:
        print(f"codex-git-safe: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["--help"]

    if argv and argv[0] == "goal-broker":
        _emit_error(
            GitSafeError(
                "goal-broker is retired: the custom Goal Train execution plane has mutation authority none"
            ),
            json_output="--json" in argv,
            command="goal-broker",
        )
        return 2

    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "preflight":
            payload, returncode = _preflight_payload(Path.cwd().resolve())
            if args.json:
                _print_json(payload)
            else:
                print(f"ready for worktree: {'yes' if payload['ready_for_worktree'] else 'no'}")
                for blocker in payload.get("blockers", []):
                    print(f"- {blocker}")
            return returncode

        if args.command in {"push", "pr"}:
            state = _repo_state(Path.cwd().resolve())
            status_payload = _status_payload(state)
            assessment = _authority_assessment(state)
            closeout_mode = _thread_closeout_mode(state.repo_root)
            active_change = _managed_active_change(state, assessment)
            authoritative_branch = (active_change.authoritative_branch if active_change else None) or assessment.default_branch or _branch_name_from_ref(
                assessment.default_ref,
                repo_root=state.repo_root,
            )
            if state.branch != authoritative_branch and active_change is None:
                raise GitSafeError(
                    "publish helpers refuse an unregistered disposable checkout",
                    blockers=["adopt the current Codex app worktree, or start a managed task first"],
                )
            if state.dirty and active_change is None:
                raise GitSafeError(
                    "publish helpers refuse unbound canonical dirt",
                    blockers=["complete a registered task through yeet; general publish has no preservation proof"],
                )
            if status_payload["state"] not in PUBLISH_SAFE_STATES:
                raise GitSafeError(
                    "publish helpers refuse to run until the repo lifecycle is healthy",
                    blockers=[
                        f"publish is blocked while repo state is {status_payload['state']}",
                        f"next action: {status_payload['next_action']}",
                    ],
                    data={"status": status_payload},
                )
            if closeout_mode == "pull_request" and active_change is not None:
                ignored_output_delta = _ignored_output_delta(state.repo_root, active_change.ignored_output_baseline)
                if ignored_output_delta:
                    raise GitSafeError(
                        "review publication cannot discard declared task-relevant ignored outputs",
                        blockers=[f"declared ignored task output {item['change']}: {item['path']}" for item in ignored_output_delta],
                        data={"ignored_task_output_delta": ignored_output_delta},
                    )
                if args.command == "pr" and active_change.lifecycle != "review_pending":
                    raise GitSafeError(
                        "pull request creation requires a recorded task-branch push",
                        blockers=["run codex-git-safe push for the committed task branch first"],
                    )
            helper_env = PUSH_HELPER_ENV if args.command == "push" else PR_HELPER_ENV
            default_name = "codex-gitea-push.sh" if args.command == "push" else "codex-gitea-pr.sh"
            mutating_delegate = not any(item in {"-n", "--dry-run", "-h", "--help"} for item in args.args)
            capture_pr_result = (
                args.command == "pr"
                and closeout_mode == "pull_request"
                and active_change is not None
                and mutating_delegate
            )
            review_url: str | None = None
            if capture_pr_result:
                helper_args = list(args.args)
                if "--json" not in helper_args:
                    helper_args.insert(0, "--json")
                delegated = _delegate_helper_process(helper_env, default_name, helper_args, capture_output=True)
                if delegated.stdout:
                    sys.stdout.write(delegated.stdout)
                if delegated.stderr:
                    sys.stderr.write(delegated.stderr)
                returncode = delegated.returncode
                if returncode == 0 and delegated.stdout.strip():
                    try:
                        delegated_payload = json.loads(delegated.stdout)
                    except json.JSONDecodeError:
                        delegated_payload = {}
                    candidate_url = delegated_payload.get("url") if isinstance(delegated_payload, dict) else None
                    review_url = candidate_url if isinstance(candidate_url, str) and candidate_url.strip() else None
            else:
                returncode = _delegate_helper(helper_env, default_name, list(args.args))
            if returncode == 0 and mutating_delegate:
                refreshed_state = _repo_state(Path.cwd().resolve())
                refreshed_assessment = _authority_assessment(refreshed_state)
                active_change = _managed_active_change(refreshed_state, refreshed_assessment)
                authoritative_branch = (active_change.authoritative_branch if active_change else None) or refreshed_assessment.default_branch or _branch_name_from_ref(
                    refreshed_assessment.default_ref,
                    repo_root=refreshed_state.repo_root,
                )
                if active_change is not None and active_change.branch and active_change.branch != authoritative_branch:
                    checkout_path = (
                        Path(active_change.checkout_path).resolve(strict=False)
                        if active_change.checkout_path
                        else None
                    )
                    lifecycle = "published_for_review"
                    phase = "published_for_review"
                    published_tip = None
                    base_tip = None
                    review_remote = None
                    review_ref = None
                    if closeout_mode == "pull_request":
                        if args.command == "push":
                            review_ref = refreshed_state.upstream
                            if not review_ref or "/" not in review_ref:
                                raise GitSafeError("task push did not establish a remote-tracking review ref")
                            review_remote = review_ref.split("/", 1)[0]
                            published_tip = _ref_commit(active_change.branch, cwd=refreshed_state.repo_root)
                            tracking_tip = _ref_commit(review_ref, cwd=refreshed_state.repo_root)
                            if tracking_tip != published_tip:
                                raise GitSafeError("task push did not preserve the exact local tip on its tracking ref")
                            base_tip = _ref_commit(authoritative_branch, cwd=refreshed_state.repo_root) if authoritative_branch else None
                            lifecycle = "review_pending"
                            phase = "review_pending"
                        else:
                            if active_change.lifecycle != "review_pending":
                                raise GitSafeError(
                                    "pull request creation requires a recorded task-branch push",
                                    blockers=["run codex-git-safe push for the committed task branch first"],
                                )
                            _review_preservation_proof(refreshed_state, active_change)
                            lifecycle = "ready_for_integration"
                            phase = "ready_for_integration"
                    _set_active_change(
                        refreshed_state,
                        branch=active_change.branch,
                        authoritative_branch=active_change.authoritative_branch,
                        lifecycle=lifecycle,
                        checkout_path=checkout_path,
                        mode=active_change.mode,
                        parking_ref=active_change.parking_ref,
                        bundle_path=active_change.bundle_path,
                        phase=phase,
                        published_tip=published_tip,
                        base_tip=base_tip,
                        review_remote=review_remote,
                        review_ref=review_ref,
                        review_url=review_url,
                    )
            return returncode

        state = _repo_state(Path.cwd().resolve())
        if args.command == "status":
            payload = _status_payload(state)
            if args.json:
                _print_json(payload)
            else:
                _human_status(state)
            return 0

        if args.command == "repair":
            payload = _repair_payload(state, apply=bool(args.apply))
            if args.json:
                _print_json(payload)
            else:
                print(f"state: {'apply' if args.apply else 'plan'}")
                print(f"safe to delete: {payload['residue']['safe_count']}")
                print(f"auto park then delete: {payload['residue']['auto_park_count']}")
                print(f"grace pending: {payload['residue']['grace_pending_count']}")
                print(f"needs investigation: {payload['residue']['decision_count']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return 0

        if args.command == "magic":
            payload = _magic_payload(state, apply=bool(args.apply))
            if args.json:
                _print_json(payload)
            else:
                print(f"result: {payload['result']}")
                print(f"ground truth line: {payload['authoritative_branch']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return 0

        if args.command == "integrate":
            payload = _integrate_payload(state, source_refs=list(args.source_refs), apply=bool(args.apply))
            if args.json:
                _print_json(payload)
            else:
                for selection in payload.get("selections", []):
                    print(f"selected: {selection['source_ref']} at {selection['published_tip']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return 0

        if args.command == "review-ready":
            payload = _mark_review_ready_payload(
                state,
                review_ref=args.review_ref,
                review_url=args.review_url,
                apply=bool(args.apply),
            )
            if args.json:
                _print_json(payload)
            else:
                print(f"state: {payload['state']}")
                print(f"review: {payload['review_url']}")
            return 0

        if args.command == "review-import":
            payload = _import_review_payload(
                state,
                review_ref=args.review_ref,
                review_url=args.review_url,
                expected_tip=args.expected_tip,
                goal_id=args.goal_id,
                thread_id=args.thread_id,
                dependencies=list(args.dependencies),
                apply=bool(args.apply),
            )
            if args.json:
                _print_json(payload)
            else:
                print(f"state: {payload['state']}")
                print(f"queue: {payload['submission']['queue_id']}")
            return 0

        if args.command == "submit":
            pr_args: list[str] = []
            if args.title:
                pr_args.extend(["--title", args.title])
            if args.body_file:
                pr_args.extend(["--body-file", args.body_file])
            if args.update_existing:
                pr_args.append("--update-existing")
            payload = _submit_payload(state, pr_args=pr_args, apply=bool(args.apply))
            if args.json:
                _print_json(payload)
            else:
                print(f"state: {payload['state']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return 0

        if args.command == "yeet":
            payload = _yeet_payload(
                state,
                message=args.message,
                message_file=args.message_file,
                validation=args.validation,
                validation_file=args.validation_file,
                title=args.title,
                body_file=args.body_file,
                update_existing=bool(args.update_existing),
                checkpoint_file=args.checkpoint_file,
                task_selector=args.task_selector,
                apply=bool(args.apply),
            )
            if args.json:
                _print_json(payload)
            else:
                print(f"state: {payload['state']}")
                if payload.get("submission", {}).get("review_url"):
                    print(f"review: {payload['submission']['review_url']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return 0

        if args.command == "adopt-current":
            payload = _adopt_current_worktree(
                state,
                topic=args.topic,
                task_class=args.task_class,
                apply=bool(args.apply),
                if_eligible=bool(args.if_eligible),
                provisional_ordinary=bool(args.provisional_ordinary),
            )
            if args.json:
                _print_json(payload)
            else:
                print(f"branch: {payload['branch']}")
                print(f"checkout: {payload['checkout_path']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return 0

        if args.command in {"closeout", "end"}:
            stdin_confirmation = ""
            if not sys.stdin.isatty():
                try:
                    stdin_confirmation = sys.stdin.read().strip().lower()
                except OSError:
                    stdin_confirmation = ""
            confirmed = bool(args.apply) or bool(args.yes) or stdin_confirmation in {"y", "yes"}
            payload = _closeout_payload(state, apply=confirmed, confirmed=confirmed)
            if args.json:
                _print_json(payload)
            else:
                if payload.get("confirmation_required"):
                    print(payload["prompt"])
                    return 0
                print(f"state: {payload['state']}")
                print(f"result: {payload['result']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return 0

        if args.command == "finish":
            payload = _finish_payload(state, apply=bool(args.apply))
            if args.json:
                _print_json(payload)
            else:
                print(f"change: {payload['branch']}")
                print(f"ground truth line: {payload['authoritative_branch']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return 0

        if args.command == "park":
            payload = _park_payload(state, apply=bool(args.apply))
            if args.json:
                _print_json(payload)
            else:
                print(f"change: {payload['branch']}")
                print(f"parking ref: {payload['parking_ref']}")
                if payload.get("bundle_path"):
                    print(f"bundle: {payload['bundle_path']}")
            return 0

        if args.command == "start":
            payload = _start_payload(
                state,
                topic=args.topic,
                base=args.base,
                from_current=args.from_current,
                mode=args.mode,
                worktree_root=args.worktree_root,
                worktree_path=args.worktree_path,
                dry_run=args.dry_run,
                task_class=args.task_class,
            )
            if args.json:
                _print_json(payload)
                return 0
            else:
                if payload.get("blockers"):
                    print("blockers:")
                    for blocker in payload["blockers"]:
                        print(f"- {blocker}")
                else:
                    print(f"branch: {payload['branch']}")
                    if payload.get("worktree_path"):
                        print(f"checkout: {payload['worktree_path']}")
                    print(f"base: {payload['base']}")
                    print(f"source strategy: {payload['source_strategy']}")
                    mode_label = "checkout" if payload["mode_resolved"] == "worktree" else payload["mode_resolved"]
                    print(f"mode: {mode_label}")
                    if payload.get("notes"):
                        print("notes:")
                        for note in payload["notes"]:
                            print(f"- {note}")
                    if payload.get("existing"):
                        print("existing: yes")
                    elif payload.get("planned_command"):
                        print("planned: " + " ".join(map(str, payload["planned_command"])))
                return 0

        if args.command == "cleanup":
            payload = _cleanup_payload(
                state,
                branch=args.branch,
                base=args.base,
                worktree_path=args.worktree_path,
                cwd_override=args.cwd,
                delete_remote=args.delete_remote,
                confirm_remote_delete=args.confirm_remote_delete,
                preserved_ref=args.preserved_ref,
                apply=args.apply,
                dry_run=args.dry_run,
            )
            if args.json:
                _print_json(payload)
                return 0
            else:
                print(f"branch: {payload['branch']}")
                print(f"base: {payload['base']}")
                print(f"unique commits: {payload['unique_commit_count']}")
                print(f"ancestry: {payload['ancestry']}")
                print(f"branch checked out elsewhere: {'yes' if payload['branch_checked_out_elsewhere'] else 'no'}")
                print(
                    f"current cwd inside target checkout: {'yes' if payload['current_cwd_inside_target_worktree'] else 'no'}"
                )
                if payload["blockers"]:
                    print("blockers:")
                    for blocker in payload["blockers"]:
                        print(f"- {blocker}")
                if payload["actions"]:
                    print("actions:")
                    for action in payload["actions"]:
                        print(f"- {action}")
                return 0

        if args.command == "land":
            payload = _land_payload(
                state,
                branch=args.branch,
                target_branch=args.target_branch,
                source_worktree_path=args.source_worktree_path,
                target_worktree_path=args.target_worktree_path,
                preserve_target_dirty=args.preserve_target_dirty,
                apply=args.apply,
                dry_run=args.dry_run,
            )
            if args.json:
                _print_json(payload)
                return 0
            print(f"source branch: {payload['branch']}")
            print(f"target branch: {payload['target_branch']}")
            print(f"ancestry: {payload['ancestry']}")
            print(f"source unique commits: {payload['source_unique_commit_count']}")
            print(f"target unique commits: {payload['target_unique_commit_count']}")
            print(f"target dirty: {'yes' if payload['target_dirty'] else 'no'}")
            if payload["blockers"]:
                print("blockers:")
                for blocker in payload["blockers"]:
                    print(f"- {blocker}")
            if payload["notes"]:
                print("notes:")
                for note in payload["notes"]:
                    print(f"- {note}")
            if payload["actions"]:
                print("actions:")
                for action in payload["actions"]:
                    print(f"- {action}")
            return 0

    except GitSafeError as exc:
        _emit_error(exc, json_output=getattr(args, "json", False), command=getattr(args, "command", None))
        return exc.exit_code

    raise GitSafeError(f"unsupported command: {args.command}")
