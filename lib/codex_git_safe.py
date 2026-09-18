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
import time
try:
    import tomllib
except ModuleNotFoundError:
    import toml_compat as tomllib
import unicodedata
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


UTC = timezone.utc

from codex_git_environment import BLOCK_END, BLOCK_START, active_managed_repo_root, managed_links, shared_git_hooks_path, shell_source_targets
from codex_git_scratch import (
    RegistryError,
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
from codex_task_temp import TaskTempError, cleanup_owned_roots, owner_identity, status_for_owner


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKTREE_DIR = ".codex-worktrees"
PUSH_HELPER_ENV = "CODEX_GITEA_PUSH_HELPER"
PR_HELPER_ENV = "CODEX_GITEA_PR_HELPER"
PR_FINALIZE_HELPER_ENV = "CODEX_GITEA_PR_FINALIZE_HELPER"
PROJECT_CHECKPOINT_HELPER_ENV = "CODEX_PROJECT_CHECKPOINT_HELPER"
STATE_SCHEMA_VERSION = 10
REPAIR_GRACE_PERIOD = timedelta(hours=0)
_CONTROL_LOCKS: dict[Path, tuple[Any, int, int]] = {}
_CONTROL_THREAD_LOCKS: dict[Path, threading.RLock] = {}


@contextmanager
def _control_lock(common_dir: Path, name: str):
    """Serialize one named resource, safely across nested helpers and processes."""
    lock_path = common_dir / "codex-git-safe" / name
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


def _integration_lock(common_dir: Path):
    # Keep the established filename for old clients and task-temp producers.
    # Normal delivery uses this only for shared metadata transactions; explicit
    # repository repair retains its separately selected exclusive coordination.
    return _control_lock(common_dir, "integration.lock")


def _keeper_lock(common_dir: Path):
    return _control_lock(common_dir, "keeper.lock")


def _task_lock(common_dir: Path, branch: str):
    identity = hashlib.sha256(branch.encode("utf-8")).hexdigest()
    return _control_lock(common_dir, f"tasks/{identity}.lock")


def _task_owner_branch(state: RepoState, branch: str) -> str:
    # Internal integration checkouts share their original transaction's owner.
    managed = _load_managed_state(state.common_dir)
    owners = {item["completion"]["owner_branch"] for item in
              [*managed["active_changes"], *managed["retired_changes"]]
              if item.get("completion") and item["completion"].get("child_branch") == branch
              and item["completion"].get("child_checkout") == str(state.repo_root)}
    if len(owners) > 1:
        raise GitSafeError("integration child has ambiguous transaction ownership")
    return next(iter(owners), branch)


@contextmanager
def _task_mutation(state: RepoState, *, branch: str | None = None):
    """All same-owner lifecycle mutations share yeet's stable branch lock."""
    owner_branch = branch or state.branch or _checkout_identity(state.repo_root)
    owner_branch = _task_owner_branch(state, owner_branch)
    with _task_lock(state.common_dir, owner_branch):
        if not state.repo_root.exists():
            raise GitSafeError("task checkout retired while waiting for its owner lock",
                data={"resume_task": owner_branch, "resume_checkout": str(state.common_dir.parent)})
        refreshed = _repo_state(state.cwd)
        if branch is None and refreshed.branch != state.branch:
            raise GitSafeError("task branch changed while waiting for its owner lock")
        yield refreshed


class GitSafeError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        blockers: list[str] | None = None,
        data: dict[str, Any] | None = None,
        exit_code: int = 1,
        result_status: str = "correctly_blocked",
    ) -> None:
        super().__init__(message)
        self.blockers = blockers or [message]
        self.data = data or {}
        self.exit_code = exit_code
        self.result_status = result_status


class GitSafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise GitSafeError(
            "invalid command invocation",
            blockers=["invalid command invocation; inspect execution.argv for the redacted argument shape"],
            exit_code=2,
            result_status="invalid_invocation",
        )


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
    review_intent: str | None = None
    publication_mode: str | None = None
    publication_attempt: dict[str, Any] | None = None
    completion: dict[str, Any] | None = None


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
    """Read optional declarations; malformed present policy must fail closed."""
    path = repo_root / ".codex" / "git-lifecycle.toml"
    try:
        loaded = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except PermissionError:
        raise
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise GitSafeError(f"invalid lifecycle config: {path}: {exc}")
    for section in ("workflow", "keeper", "closeout", "ignored_outputs"):
        if section in loaded and not isinstance(loaded[section], dict):
            raise GitSafeError(f"invalid lifecycle config: {path}: {section} must be a table")
    return loaded


def _thread_closeout_mode(repo_root: Path) -> str:
    section = _lifecycle_config(repo_root).get("workflow", {})
    mode = section.get("thread_closeout", "pull_request") if isinstance(section, dict) else "pull_request"
    if mode not in {"integrate", "pull_request"}:
        raise GitSafeError("workflow.thread_closeout must be 'integrate' or 'pull_request'")
    return mode


def _yeet_completion_mode(repo_root: Path) -> str:
    mode = _lifecycle_config(repo_root).get("workflow", {}).get("yeet_completion", "review_only")
    if mode not in ("integrate", "review_only"):
        raise GitSafeError("workflow.yeet_completion must be 'integrate' or 'review_only'")
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
        run_on_yeet = check.get("run_on_yeet", False)
        if not isinstance(name, str) or not name.strip():
            raise GitSafeError("closeout check name must be a non-empty string")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            raise GitSafeError(f"closeout check {name!r} command must be a non-empty string array")
        if not isinstance(task_classes, list) or not task_classes or not all(isinstance(item, str) for item in task_classes):
            raise GitSafeError(f"closeout check {name!r} task_classes must be a non-empty string array")
        if not isinstance(run_on_yeet, bool):
            raise GitSafeError(f"closeout check {name!r} run_on_yeet must be a boolean")
        normalized.append({"name": name.strip(), "command": list(command), "task_classes": [_normalize_check_task_class(item) for item in task_classes], "run_on_yeet": run_on_yeet})
    return normalized


def _semantic_closeout_results(repo_root: Path, task_class: str, *, yeet_only: bool = False) -> list[dict[str, Any]]:
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
        if yeet_only and not check["run_on_yeet"]:
            continue
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


def _require_yeet_closeout(state: RepoState, change: ManagedChange) -> None:
    """Run only explicitly opted-in read-only disposition gates, never product tests."""
    results = _semantic_closeout_results(state.repo_root, change.task_class, yeet_only=True)
    failed = [item for item in results if not item.get("ok")]
    if failed:
        raise GitSafeError(
            "yeet is blocked by repo-declared disposition checks",
            blockers=[f"satisfy read-only closeout check: {item['name']}" for item in failed],
            data={"semantic_closeout": results, "task_checkout": str(state.repo_root)},
        )


def _completion_roles(receipt: dict[str, Any]) -> tuple[str, ...]:
    return ("owner",) if receipt.get("version") == 2 else ("owner", "child")


def _completion_integration_branch(receipt: dict[str, Any]) -> str:
    return receipt["owner_branch"] if receipt.get("version") == 2 else receipt["child_branch"]


def _validate_completion(receipt: Any) -> None:
    if receipt is None:
        return
    if not isinstance(receipt, dict) or type(receipt.get("version")) is not int or receipt.get("version") not in (1, 2) or receipt.get("mode") != "integrate":
        raise GitSafeError("invalid task completion receipt version or mode")
    standalone = receipt["version"] == 2
    if standalone and (receipt.get("kind") != "standalone_integration" or any(key in receipt for key in ("child_checkout", "child_branch"))):
        raise GitSafeError("invalid standalone integration receipt identity")
    phases = ("integrating", "disposing", "complete") if standalone else ("preparing", "published", "awaiting_validation", "validated", "integrating", "child_retired", "complete")
    if receipt.get("phase") not in phases:
        raise GitSafeError("invalid task completion receipt phase")
    identity_keys = ("owner_checkout", "owner_branch", "control_checkout") + (() if standalone else ("child_checkout", "child_branch"))
    for key in identity_keys:
        if not isinstance(receipt.get(key), str) or not receipt[key]:
            raise GitSafeError(f"invalid task completion receipt {key}")
    checkout_keys = ("owner_checkout", "control_checkout") + (() if standalone else ("child_checkout",))
    for key in checkout_keys:
        if not Path(receipt[key]).is_absolute():
            raise GitSafeError(f"completion receipt {key} must be absolute")
    if len({_checkout_identity(Path(receipt[key])) for key in checkout_keys}) != len(checkout_keys):
        raise GitSafeError("completion receipt checkout identities must be distinct")
    for key in (("side_effect_ids",) if standalone else ("include_reviews", "side_effect_ids")):
        if not isinstance(receipt.get(key), list) or not all(isinstance(item, str) for item in receipt[key]):
            raise GitSafeError(f"invalid task completion receipt {key}")
    selections = receipt.get("selections")
    if not isinstance(selections, list):
        raise GitSafeError("invalid task completion selections")
    for item in selections:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key] for key in ("review_ref", "review_remote", "review_url", "published_tip", "queue_id")):
            raise GitSafeError("completion selection lacks immutable review identity")
        if not re.fullmatch(r"[0-9a-f]{40}", item["published_tip"]):
            raise GitSafeError("invalid completion selection tip")
    for key in ("integration_head", "integrated_tip"):
        if key in receipt and (not isinstance(receipt[key], str) or not re.fullmatch(r"[0-9a-f]{40}", receipt[key])):
            raise GitSafeError(f"invalid completion receipt {key}")
    if "replay_history" in receipt:
        history = receipt["replay_history"]
        if not standalone or not isinstance(history, list) or not history:
            raise GitSafeError("invalid standalone integration replay history")
        for index, item in enumerate(history):
            if (not isinstance(item, dict)
                    or any(not isinstance(item.get(key), str) or not re.fullmatch(r"[0-9a-f]{40}", item[key])
                           for key in ("previous_head", "head", "authoritative_head"))
                    or item["previous_head"] == item["head"]
                    or any(not isinstance(item.get(key), str) or not re.match(r"(?i)^pass(?:ed)?(?:\s|:|-)", item[key])
                           for key in ("previous_validation_summary", "validation_summary"))
                    or (index and (item["previous_head"] != history[index - 1]["head"]
                                   or item["previous_validation_summary"] != history[index - 1]["validation_summary"]))):
                raise GitSafeError("invalid standalone integration replay history entry")
        if history[-1]["head"] != receipt.get("integration_head") or history[-1]["validation_summary"] != receipt.get("validation_summary"):
            raise GitSafeError("standalone integration replay history does not match its prepared HEAD")
    for item in selections:
        if type(item.get("disposal_owned")) is not bool or item["review_ref"].split("/", 1)[0] != item["review_remote"]:
            raise GitSafeError("invalid completion selection ownership or remote")
    if len({item["review_ref"] for item in selections}) != len(selections):
        raise GitSafeError("completion selections must have distinct refs")
    if receipt["phase"] != "preparing" and not selections:
        raise GitSafeError("completion phase requires immutable selections")
    if receipt["phase"] in ("awaiting_validation", "validated", "integrating", "disposing", "child_retired", "complete") and "integration_head" not in receipt:
        raise GitSafeError("completion phase requires a prepared HEAD")
    if receipt["phase"] in ("validated", "integrating", "disposing", "child_retired", "complete"):
        summary = receipt.get("validation_summary")
        if not isinstance(summary, str) or not re.match(r"(?i)^pass(?:ed)?(?:\s|:|-)", summary):
            raise GitSafeError("completion phase requires passing integration validation")
    if receipt["phase"] in ("disposing", "child_retired", "complete") and "integrated_tip" not in receipt:
        raise GitSafeError("completion phase requires an integrated tip")
    disposal = receipt.get("disposal", [])
    if not isinstance(disposal, list):
        raise GitSafeError("invalid completion disposal receipt")
    for item in disposal:
        if not isinstance(item, dict) or item.get("state") not in ("deleting", "deleted"):
            raise GitSafeError("invalid completion disposal state")
        if not any(item.get("review_ref") == selected["review_ref"] and item.get("expected_tip") == selected["published_tip"] for selected in selections):
            raise GitSafeError("completion disposal is outside the immutable selection")
    for key in ("checkpoint_pending_generation", "checkpoint_final_generation", "checkpoint_generation", "checkpoint_pending_expected", "checkpoint_final_expected"):
        if key in receipt and (type(receipt[key]) is not int or receipt[key] < 1):
            raise GitSafeError(f"invalid completion receipt {key}")
    if "checkpoint_model_sha256" in receipt and (not isinstance(receipt["checkpoint_model_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", receipt["checkpoint_model_sha256"])):
        raise GitSafeError("invalid completion checkpoint model digest")
    if "hold" in receipt and receipt["hold"] != "explicit review-only hold":
        raise GitSafeError("invalid completion hold purpose")
    if len({item["review_ref"] for item in disposal}) != len(disposal):
        raise GitSafeError("duplicate completion disposal entry")
    reconciliation = receipt.get("ownership_reconciliation")
    if reconciliation is not None:
        if not isinstance(reconciliation, list) or not reconciliation:
            raise GitSafeError("invalid ownership reconciliation attestation")
        for item in reconciliation:
            required = (
                "attestation_id", "command", "schema_version", "recorded_at",
                "state_sha256", "review_ref", "review_remote", "review_url",
                "published_tip", "queue_id", "owner_branch", "owner_checkout",
                "integration_head", "proof_chain", "proof_sha256",
            )
            if (not isinstance(item, dict)
                    or any(not isinstance(item.get(key), str) or not item[key] for key in required
                           if key not in {"schema_version", "proof_chain", "proof_sha256"})
                    or item.get("command") != "reconcile-integration-ownership"
                    or item.get("schema_version") != 1
                    or not isinstance(item.get("proof_chain"), list)
                    or not item["proof_chain"]
                    or not all(isinstance(path, str) and Path(path).is_absolute() for path in item["proof_chain"])
                    or not isinstance(item.get("proof_sha256"), list)
                    or len(item["proof_sha256"]) != len(item["proof_chain"])
                    or not all(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
                               for digest in item["proof_sha256"])
                    or not re.fullmatch(r"[0-9a-f]{64}", item.get("state_sha256", ""))
                    or not re.fullmatch(r"[0-9a-f]{40}", item.get("integration_head", ""))
                    or not re.fullmatch(r"[0-9a-f]{40}", item.get("published_tip", ""))):
                raise GitSafeError("invalid ownership reconciliation attestation")
            if not re.fullmatch(r"[0-9a-f]{16,64}", item.get("attestation_id", "")):
                raise GitSafeError("invalid ownership reconciliation attestation identity")
        if len({item["attestation_id"] for item in reconciliation}) != len(reconciliation):
            raise GitSafeError("duplicate ownership reconciliation attestation")


def _load_managed_state(common_dir: Path) -> dict[str, Any]:
    # goal_broker_transactions is retained only so older state files round-trip
    # without destructive schema migration. No current command consumes it.
    path = _managed_state_path(common_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "active_change": None,
            "active_changes": [],
            "parked_changes": [],
            "retired_changes": [],
            "submitted_changes": [],
            "integrated_changes": [],
            "goal_broker_transactions": [],
            "temporary_artifacts": [],
        }
    except PermissionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GitSafeError(
            f"cannot read managed Git state: {path}: {exc}",
            blockers=["the existing registry was retained; inspect and recover it before lifecycle mutation"],
        ) from exc
    if not isinstance(payload, dict):
        raise GitSafeError(f"invalid managed Git state: {path}: expected a JSON object")
    if payload.get("active_change") is not None and not isinstance(payload["active_change"], dict):
        raise GitSafeError(f"invalid managed Git state: {path}: active_change must be an object or null")
    for field in ("active_changes", "parked_changes", "retired_changes", "submitted_changes", "integrated_changes"):
        if field in payload and (
            not isinstance(payload[field], list)
            or not all(isinstance(item, dict) for item in payload[field])
        ):
            raise GitSafeError(f"invalid managed Git state: {path}: {field} must be an array of objects")
        for item in payload.get(field, []):
            if item.get("review_intent") not in (None, "new", "continue"):
                raise GitSafeError(f"invalid managed Git state: {path}: review_intent")
            if item.get("publication_mode") not in (None, "continue", "finish"):
                raise GitSafeError(f"invalid managed Git state: {path}: publication_mode")
            attempt = item.get("publication_attempt")
            if attempt is not None and (not isinstance(attempt, dict) or
                    not all(isinstance(attempt.get(key), str) and attempt[key]
                            for key in ("head", "review_ref", "destination_sha256"))):
                raise GitSafeError(f"invalid managed Git state: {path}: publication_attempt")
            _validate_completion(item.get("completion"))
    if payload.get("active_change"):
        _validate_completion(payload["active_change"].get("completion"))
        if payload["active_change"].get("review_intent") not in (None, "new", "continue"):
            raise GitSafeError(f"invalid managed Git state: {path}: legacy review_intent")
    payload = _sanitize_review_url_fields(payload)
    payload.setdefault("schema_version", STATE_SCHEMA_VERSION)
    payload.setdefault("active_change", None)
    payload.setdefault("active_changes", [])
    payload.setdefault("parked_changes", [])
    payload.setdefault("retired_changes", [])
    payload.setdefault("submitted_changes", [])
    payload.setdefault("integrated_changes", [])
    payload.setdefault("goal_broker_transactions", [])
    if not isinstance(payload.get("temporary_artifacts", []), list) or not all(
        isinstance(item, dict) for item in payload.get("temporary_artifacts", [])
    ):
        raise GitSafeError(f"invalid managed Git state: {path}: temporary_artifacts must be an array of objects")
    payload.setdefault("temporary_artifacts", [])
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
    payload = _sanitize_review_url_fields(dict(payload))
    payload["schema_version"] = STATE_SCHEMA_VERSION
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    os.replace(temp_path, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


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
        review_intent=payload.get("review_intent"),
        publication_mode=payload.get("publication_mode"),
        publication_attempt=payload.get("publication_attempt"),
        completion=payload.get("completion"),
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
    review_intent: str | None = None,
    publication_mode: str | None = None,
    publication_attempt: dict[str, Any] | None = None,
    completion: dict[str, Any] | None = None,
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
            "review_intent": review_intent if review_intent is not None else (current.review_intent if current else None),
            "publication_mode": publication_mode if publication_mode is not None else (current.publication_mode if current else None),
            "publication_attempt": publication_attempt if publication_attempt is not None else (current.publication_attempt if current else None),
            "completion": completion if completion is not None else (current.completion if current else None),
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


def _record_retired_change(state: RepoState, change: ManagedChange, *, pending: bool = False) -> None:
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
            "start_tip": change.start_tip,
            "created_at": change.created_at, "updated_at": _iso_now(), "lifecycle": "retired", "phase": "retirement_pending" if pending else "retired",
            "published_tip": change.published_tip,
            "completion": change.completion,
        }
        payload["retired_changes"] = [item for item in payload.get("retired_changes", []) if _payload_checkout_identity(item) != identity]
        payload["retired_changes"].append(record)
        _save_managed_state(state.common_dir, payload)


def _submitted_change_record(change: ManagedChange) -> dict[str, Any]:
    review_url = _sanitized_url(change.review_url) if change.review_url else None
    queue_identity = "\0".join((review_url or "", change.review_ref or "", change.published_tip or ""))
    record = {
        "queue_id": hashlib.sha256(queue_identity.encode("utf-8")).hexdigest()[:16],
        "branch": change.branch,
        "checkout_path": change.checkout_path,
        "checkout_identity": _checkout_identity(Path(change.checkout_path)) if change.checkout_path else None,
        "authoritative_branch": change.authoritative_branch,
        "task_class": change.task_class,
        "published_tip": change.published_tip,
        "base_tip": change.base_tip,
        "review_remote": change.review_remote,
        "review_ref": change.review_ref,
        "review_url": review_url,
        "validation_summary": change.validation_summary,
        "checkpoint_generation": change.checkpoint_generation,
        "checkpoint_updated_at": change.checkpoint_updated_at,
        "created_at": change.created_at,
        "start_tip": change.start_tip,
        "submitted_at": _iso_now(),
        "publication_mode": change.publication_mode or "finish",
        "review_acceptance": "not_recorded",
        "lifecycle": "ready_for_integration",
        "checkpoint_mode": "shared" if change.checkpoint_generation is not None else "task_record",
        "disposal_owned": bool(change.review_intent == "new" and change.branch and change.branch.startswith("codex/") and change.review_ref == f"{change.review_remote}/{change.branch}"),
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
                record["disposal_owned"] = latest_review.get("disposal_owned") is True or record.get("disposal_owned") is True
            history = list(latest_review.get("publication_history", []))
            if latest_review.get("published_tip") != published_tip:
                history.append({key: latest_review[key] for key in
                    ("published_tip", "validation_summary", "submitted_at") if key in latest_review})
            elif latest_review.get("submitted_at"):
                record["submitted_at"] = latest_review["submitted_at"]
            if history:
                record["publication_history"] = history
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
            if not {item.get("review_ref"), item.get("queue_id")} & selected_ref_set:
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
        if {item.get("review_ref"), item.get("queue_id")} & selected_ref_set
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
            cwd=state.repo_root,
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
    return json.dumps(_sanitize_review_url_fields(payload), indent=2, sort_keys=True)


def _print_json(payload: Any) -> None:
    print(_json_dump(payload))


def _result_target(payload: dict[str, Any], *, blocked: bool) -> dict[str, Any]:
    target: dict[str, Any] = {"blocked": blocked}
    for key in ("state", "ready_for_worktree", "next_action"):
        if key in payload:
            target[key] = payload[key]
    blockers = [str(item) for item in payload.get("blockers", []) if item]
    if blockers:
        target["blockers"] = blockers
    return target


def _operation_result(
    payload: dict[str, Any],
    *,
    mutation_requested: bool,
) -> tuple[dict[str, Any], int]:
    """Attach the stable semantic result contract and return its process status."""
    original_ok = payload.get("ok", True) is not False
    command_ok = payload.get("command_ok", True) is not False
    blockers = [str(item) for item in payload.get("blockers", []) if item]
    policy_ok = payload.get("policy_ok", original_ok and not blockers) is not False
    target_blocked = bool(blockers) or not policy_ok or not original_ok

    if not command_ok:
        result_status = "internal_error"
        exit_code = 70
    elif mutation_requested and target_blocked:
        result_status = "correctly_blocked"
        exit_code = 1
    else:
        result_status = "completed"
        exit_code = 0

    payload["command_ok"] = result_status in {"completed", "correctly_blocked"}
    payload["policy_ok"] = not target_blocked
    payload["ok"] = exit_code == 0
    payload["operation"] = {
        "kind": "mutation" if mutation_requested else "query",
        "status": result_status,
    }
    payload["target"] = _result_target(payload, blocked=target_blocked)
    return payload, exit_code


_REDACTED_VALUE_FLAGS = {"--message", "--validation", "--title"}
_SANITIZED_URL_FLAGS = {"--review-url"}
_FILE_INPUT_FLAGS = {"--body-file", "--checkpoint-file", "--message-file", "--validation-file", "--integration-validation-file", "--ownership-proof", "--proof-chain"}
_IDENTITY_VALUE_FLAGS = {
    "--checkpoint-generation",
    "--continue-review",
    "--include-review",
    "--base",
    "--checkout-path",
    "--checkout-root",
    "--expected-tip",
    "--expected-plan-digest",
    "--repo",
    "--review-ref",
    "--review-url",
    "--source-ref",
    "--task",
    "--topic",
    "--worktree-path",
    "--worktree-root",
}
_SAFE_ARGV_VALUE_FLAGS = (_FILE_INPUT_FLAGS | _IDENTITY_VALUE_FLAGS | {
    "--depends-on",
    "--goal-id",
    "--mode",
    "--task-class",
    "--thread-id",
}) - _SANITIZED_URL_FLAGS
_BOOLEAN_FLAGS = {
    "--review-only",
    "--integrate",
    "--new-review",
    "-h",
    "--apply",
    "--brief",
    "--dry-run",
    "--from-current",
    "--help",
    "--if-eligible",
    "--json",
    "--plan",
    "--provisional-ordinary",
    "--update-existing",
    "-yes",
}
_SIDE_EFFECT_ID_KEYS = {
    "branch",
    "bundle_path",
    "checkpoint_generation",
    "generation",
    "integrated_tip",
    "parking_ref",
    "published_tip",
    "queue_id",
    "review_ref",
    "review_url",
    "worktree_path",
}


def _sanitized_url(value: str) -> str:
    """Retain provider/path identity without credentials, query values, or fragments."""
    try:
        parsed = urlparse(value)
    except ValueError:
        return "<redacted-url>"
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return "<redacted-url>"
    host = parsed.netloc.rsplit("@", 1)[-1]
    if not host:
        return "<redacted-url>"
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(), netloc=host, params="", query="", fragment=""
    ).geturl()
    try:
        normalized_parsed = urlparse(normalized)
    except ValueError:
        return "<redacted-url>"
    try:
        hostname = normalized_parsed.hostname
        normalized_parsed.port
    except ValueError:
        return "<redacted-url>"
    if (
        normalized_parsed.scheme not in {"http", "https"}
        or not normalized_parsed.netloc
        or not hostname
    ):
        return "<redacted-url>"
    return normalized


def _normalized_review_url(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise GitSafeError("review URL is required")
    normalized = _sanitized_url(candidate)
    parsed = urlparse(normalized)
    if normalized == "<redacted-url>" or parsed.scheme.lower() not in {"http", "https"}:
        raise GitSafeError("review URL must include an HTTP(S) scheme and host")
    return normalized


def _sanitize_review_url_fields(value: Any, *, field_name: str | None = None) -> Any:
    """Strip credentials and transient components before review URLs cross a boundary."""
    if isinstance(value, dict):
        return {
            key: _sanitize_review_url_fields(child, field_name=key)
            for key, child in value.items()
        }
    if isinstance(value, list):
        if field_name in {"review_urls", "dependencies", "selected_refs"}:
            return [_sanitized_identity_value(child) if isinstance(child, str) else child for child in value]
        return [_sanitize_review_url_fields(child) for child in value]
    if field_name == "review_url" and isinstance(value, str):
        return _sanitized_url(value)
    if field_name in {"source_ref", "source_selector", "task_selector"} and isinstance(value, str):
        return _sanitized_identity_value(value)
    return value


def _sanitized_identity_value(value: str) -> str:
    """Sanitize URL-shaped selectors while preserving ordinary refs and IDs verbatim."""
    try:
        parsed = urlparse(value)
    except ValueError:
        return "<redacted-url>" if "://" in value else value
    url_looking = bool(parsed.scheme or parsed.netloc or "://" in value or value.startswith("//"))
    return _sanitized_url(value) if url_looking else value


def _redacted_argv(argv: list[str], *, executable: str) -> list[str]:
    redacted: list[str] = [executable]
    command_seen = False
    pending_value: str | None = None
    for argument in argv:
        if pending_value is not None and not argument.startswith("-"):
            redacted.append(
                _sanitized_url(argument)
                if pending_value == "url"
                else _sanitized_identity_value(argument) if pending_value == "safe" else "<redacted>"
            )
            pending_value = None
            continue
        name, separator, value = argument.partition("=")
        if not command_seen and not argument.startswith("-"):
            redacted.append(argument)
            command_seen = True
            pending_value = None
            continue
        if not argument.startswith("-"):
            redacted.append("<redacted>")
            continue
        if name in _REDACTED_VALUE_FLAGS:
            redacted.append(f"{name}=<redacted>" if separator else name)
            pending_value = None if separator else "redact"
            continue
        if name in _SANITIZED_URL_FLAGS:
            redacted.append(f"{name}={_sanitized_url(value)}" if separator else name)
            pending_value = None if separator else "url"
            continue
        if name in _SAFE_ARGV_VALUE_FLAGS:
            redacted.append(
                f"{name}={_sanitized_identity_value(value)}" if separator else argument
            )
            pending_value = None if separator else "safe"
            continue
        if name in _BOOLEAN_FLAGS:
            redacted.append(argument)
            continue
        redacted.append(f"{name}=<redacted>" if separator else name)
        pending_value = None if separator else "redact"
    return redacted


def _argv_flags(argv: list[str]) -> list[str]:
    flags: list[str] = []
    for argument in argv:
        if not argument.startswith("-"):
            continue
        flags.append(argument.partition("=")[0])
    return flags


def _argv_value_inputs(argv: list[str], *, cwd: Path) -> list[dict[str, Any]]:
    inputs: list[dict[str, Any]] = []
    index = 0
    while index < len(argv):
        argument = argv[index]
        name, separator, inline_value = argument.partition("=")
        if name not in _FILE_INPUT_FLAGS | _IDENTITY_VALUE_FLAGS:
            index += 1
            continue
        if separator:
            value = inline_value
        elif index + 1 < len(argv):
            value = argv[index + 1]
            index += 1
        else:
            index += 1
            continue
        if name in _FILE_INPUT_FLAGS:
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = cwd / path
            path = path.resolve(strict=False)
            item: dict[str, Any] = {"kind": "file", "flag": name, "path": str(path)}
            try:
                stat = path.stat()
            except OSError:
                item["state"] = "unavailable"
            else:
                item["size_bytes"] = stat.st_size
                item["modified_ns"] = stat.st_mtime_ns
            inputs.append(item)
        else:
            inputs.append({
                "kind": "argument",
                "flag": name,
                "value": (
                    _sanitized_url(value)
                    if name in _SANITIZED_URL_FLAGS
                    else _sanitized_identity_value(value)
                ),
            })
        index += 1
    return inputs


def _execution_context(argv: list[str]) -> dict[str, Any]:
    cwd = Path.cwd().resolve()
    supplied_id = os.environ.get("CODEX_GIT_SAFE_EXECUTION_ID", "").strip()
    execution: dict[str, Any] = {
        "schema_version": 1,
        "id": supplied_id or str(uuid.uuid4()),
        "argv": _redacted_argv(argv, executable=sys.argv[0]),
        "flags": _argv_flags(argv),
        "cwd": str(cwd),
        "material_inputs": _argv_value_inputs(argv, cwd=cwd),
    }
    retry_of = os.environ.get("CODEX_GIT_SAFE_RETRY_OF", "").strip()
    execution["retry"] = (
        {"relationship": "retry_of", "execution_id": retry_of}
        if retry_of
        else {"relationship": "initial"}
    )
    process_id = os.environ.get("CODEX_GIT_SAFE_RUNTIME_PROCESS_ID", "").strip()
    if process_id:
        execution["runtime"] = {"process_id": process_id, "owner": "external_runtime"}
    return execution


def _execution_authority(args: argparse.Namespace | None, *, mutation_requested: bool) -> dict[str, str]:
    if mutation_requested:
        declared_by = "--apply"
        if getattr(args, "yes", False):
            declared_by = "-yes"
        elif getattr(args, "command", None) == "start":
            declared_by = "start_without_--dry-run"
        return {"mode": "apply", "declared_by": declared_by}
    if getattr(args, "command", None) in {"adopt-current", "end", "integrate", "park", "repair", "review-import", "review-ready", "reconcile-integration-ownership", "yeet"}:
        return {"mode": "plan", "declared_by": "no_apply_flag"}
    if getattr(args, "command", None) == "start" and getattr(args, "dry_run", False):
        return {"mode": "plan", "declared_by": "--dry-run"}
    return {"mode": "read_only", "declared_by": "command_contract"}


def _side_effect_identifiers(payload: dict[str, Any]) -> list[dict[str, str]]:
    identifiers: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"final_status", "scope", "status"}:
                    continue
                if key == "side_effect_ids" and isinstance(child, list):
                    for item in child:
                        if isinstance(item, str) and item:
                            identity = ("durable_side_effect", item)
                            if identity not in seen:
                                seen.add(identity)
                                identifiers.append({"kind": "durable_side_effect", "id": item})
                elif key in _SIDE_EFFECT_ID_KEYS and isinstance(child, (str, int)) and str(child):
                    identifier = _sanitized_url(str(child)) if key == "review_url" else str(child)
                    identity = (key, identifier)
                    if identity not in seen:
                        seen.add(identity)
                        identifiers.append({"kind": key, "id": identifier})
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return identifiers


def _attach_execution_evidence(
    payload: dict[str, Any],
    *,
    context: dict[str, Any],
    args: argparse.Namespace | None,
    mutation_requested: bool,
    started_ns: int,
) -> dict[str, Any]:
    execution = dict(context)
    execution["duration_ms"] = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
    execution["authority"] = _execution_authority(args, mutation_requested=mutation_requested)
    inputs = list(execution["material_inputs"])
    repo_root = payload.get("repo_root")
    if isinstance(repo_root, str) and repo_root:
        repository: dict[str, Any] = {"kind": "repository", "path": repo_root}
        repo_path = Path(repo_root)
        head = ""
        if repo_path.is_dir():
            head_proc = _run(["git", "rev-parse", "--verify", "HEAD"], cwd=repo_path)
            head = head_proc.stdout.strip() if head_proc.returncode == 0 else ""
        head = head or payload.get("head") or payload.get("published_tip") or payload.get("integrated_tip")
        if isinstance(head, str) and head:
            repository["version"] = head
        inputs.append(repository)
    execution["material_inputs"] = inputs
    execution["side_effects"] = _side_effect_identifiers(payload) if mutation_requested else []
    payload["execution"] = execution
    return payload


def _command_from_argv(argv: list[str]) -> str | None:
    skip_next = False
    for argument in argv:
        if skip_next:
            skip_next = False
            continue
        if argument == "--repo":
            skip_next = True
            continue
        if argument.startswith("--repo=") or argument in {"--json", "-h", "--help"}:
            continue
        if not argument.startswith("-"):
            return argument
    return None


def _mutation_requested(args: argparse.Namespace | None) -> bool:
    if args is None:
        return False
    command = getattr(args, "command", None)
    if command == "start":
        return not bool(getattr(args, "dry_run", False))
    if command == "end":
        return bool(getattr(args, "apply", False) or getattr(args, "yes", False))
    return bool(getattr(args, "apply", False))


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


def _continuation_target(state: RepoState, review_ref: str, expected_tip: str) -> tuple[str, str]:
    if "/" not in review_ref:
        raise GitSafeError("--continue-review requires an exact remote/ref")
    remote, branch = review_ref.split("/", 1)
    if remote not in _git_output(["remote"], cwd=state.repo_root).splitlines() or not branch or branch == _authority_assessment(state).default_branch:
        raise GitSafeError("continuation must name a review branch, not a keeper")
    if _run(["git", "check-ref-format", f"refs/heads/{branch}"], cwd=state.repo_root).returncode:
        raise GitSafeError("invalid continuation review ref")
    _validated_remote_destination(state.repo_root, remote)
    tip = _ref_commit(review_ref, cwd=state.repo_root)
    proc = _run(["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"], cwd=state.repo_root)
    live = proc.stdout.split()[0] if proc.returncode == 0 and proc.stdout.strip() else ""
    if tip != expected_tip or live != expected_tip:
        raise GitSafeError("continuation requires the exact recorded review tip", data={"review_ref": review_ref, "expected_tip": expected_tip, "tracking_tip": tip, "remote_tip": live})
    return remote, review_ref


def _adopt_current_worktree(state: RepoState, **kwargs: Any) -> dict[str, Any]:
    if not kwargs.get("apply"):
        return _adopt_current_worktree_unlocked(state, **kwargs)
    branch = state.branch or _adoption_branch(state, kwargs.get("topic"))
    with _task_mutation(state, branch=branch) as refreshed:
        return _adopt_current_worktree_unlocked(refreshed, **kwargs)


def _adopt_current_worktree_unlocked(
    state: RepoState,
    *,
    topic: str | None,
    task_class: str | None,
    apply: bool,
    if_eligible: bool = False,
    provisional_ordinary: bool = False,
    continue_review: str | None = None,
    new_review: bool = False,
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
    if continue_review and new_review:
        raise GitSafeError("--continue-review and --new-review are mutually exclusive")
    if continue_review:
        _continuation_target(state, continue_review, _ref_commit("HEAD", cwd=state.repo_root))
    if existing is not None:
        if continue_review or new_review:
            if existing.completion or existing.published_tip or existing.lifecycle != "working":
                raise GitSafeError("review intent cannot change after publication or completion begins")
            if continue_review and (state.dirty or _ref_commit("HEAD", cwd=state.repo_root) != existing.start_tip):
                raise GitSafeError("continuation must be bound at the recorded clean baseline")
            if apply:
                _set_active_change(state, branch=existing.branch, authoritative_branch=existing.authoritative_branch,
                    lifecycle=existing.lifecycle, checkout_path=state.repo_root, mode=existing.mode,
                    review_intent="continue" if continue_review else "new",
                    review_ref=continue_review, review_remote=continue_review.split("/", 1)[0] if continue_review else None)
                existing = _managed_active_change(state, assessment) or existing
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
            review_intent="continue" if continue_review else "new",
            review_ref=continue_review,
            review_remote=continue_review.split("/", 1)[0] if continue_review else None,
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
    proc = _run(["git", "config", "--get", "core.hooksPath"], cwd=state.repo_root)
    if proc.returncode not in {0, 1}:
        raise GitSafeError("could not inspect effective core.hooksPath; existing hook configuration was preserved")
    if proc.returncode == 1:
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
    return {"status": "custom", "configured_path": configured, "managed_path": str(managed), "note": "preserved existing effective core.hooksPath"}


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
    usable = bool(authoritative_branch and authoritative_commit)
    blockers: list[str] = []
    if authoritative_branch is None:
        blockers.append("could not infer the authoritative/default branch")
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
            with _integration_lock(state.common_dir):
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


def _push_and_verify_keeper_remotes(
    state: RepoState,
    authoritative_branch: str,
    *,
    canonical_dirty_fingerprint: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
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
    # Validate all destinations before the first keeper is changed.
    for target in targets:
        _validated_remote_destination(state.repo_root, target["remote"])
    actions: list[str] = []
    proofs: list[dict[str, Any]] = []
    side_effect_ids: list[str] = []

    def fail(message: str, *, remote_proof: dict[str, Any] | None = None) -> None:
        data: dict[str, Any] = {
            "completed_actions": actions,
            "remote_proofs": proofs,
            "side_effect_ids": side_effect_ids,
        }
        if remote_proof is not None:
            data["remote_proof"] = remote_proof
        raise GitSafeError(
            message,
            data=data,
            result_status=(
                "side_effect_completed_reconciliation_required"
                if side_effect_ids
                else "correctly_blocked"
            ),
        )

    for target in targets:
        remote = target["remote"]
        branch = target["branch"]
        push_proc = _run(
            ["git", "push", remote, f"refs/heads/{authoritative_branch}:refs/heads/{branch}"],
            cwd=state.repo_root,
        )
        if push_proc.returncode != 0:
            detail = push_proc.stderr.strip() or push_proc.stdout.strip() or f"git push {remote} failed"
            fail(detail)
        actions.append(f"pushed {authoritative_branch} to keeper {remote}/{branch}")
        side_effect_ids.append(f"git_ref:{remote}:{branch}:{local_head}")
        verify_proc = _run(
            ["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"],
            cwd=state.repo_root,
        )
        if verify_proc.returncode != 0:
            detail = verify_proc.stderr.strip() or verify_proc.stdout.strip() or f"git ls-remote {remote} failed"
            fail(detail)
        remote_head = verify_proc.stdout.split()[0] if verify_proc.stdout.strip() else None
        verified = remote_head == local_head
        proof = {**target, "local_head": local_head, "remote_head": remote_head, "verified": verified}
        proofs.append(proof)
        if not verified:
            fail(f"keeper remote head did not match after push: {remote}/{branch}", remote_proof=proof)
        actions.append(f"verified keeper head {remote}/{branch} at {local_head}")
    return proofs, actions, side_effect_ids


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


def _validated_remote_destination(repo_root: Path, remote: str) -> str:
    """Reject implicit Git URL rewriting/fanout before a publication helper runs."""
    raw = _run(["git", "config", "--get-all", f"remote.{remote}.url"], cwd=repo_root)
    fetch = _run(["git", "remote", "get-url", "--all", remote], cwd=repo_root)
    push = _run(["git", "remote", "get-url", "--push", "--all", remote], cwd=repo_root)
    urls = [result.stdout.strip().splitlines() for result in (raw, fetch, push)]
    if (any(result.returncode for result in (raw, fetch, push))
            or any(len(values) != 1 or not values[0] for values in urls)
            or urls[0] != urls[1] or urls[0] != urls[2]):
        raise GitSafeError("publication destination is ambiguous or rewritten",
            blockers=[f"remote {remote} requires one identical configured, fetch, and push URL; no implicit rewrite or fanout"],
            data={"remote": remote})
    return urls[0][0]


def _safe_remote_for_parking(repo_root: Path) -> str | None:
    # Parking remains locally preserved by its ref and verified bundle when no
    # backup role was explicitly configured. Never infer publication authority
    # from pushDefault or alphabetical remote names.
    configured = _run(["git", "config", "--get-all", "codex.privateBackupRemote"], cwd=repo_root)
    remotes = configured.stdout.strip().splitlines()
    if not remotes:
        return None
    if len(remotes) != 1 or not remotes[0]:
        raise GitSafeError("parking requires one explicitly configured private backup remote")
    remote = remotes[0]
    _validated_remote_destination(repo_root, remote)
    return remote


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


def _scratch_residue_entries(
    state: RepoState,
    assessment: AuthorityAssessment,
    *,
    sync_registry: bool = False,
) -> list[dict[str, Any]]:
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

    if sync_registry:
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


def _status_payload(
    state: RepoState,
    *,
    run_semantic_checks: bool = False,
) -> dict[str, Any]:
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
    semantic_checks = (
        _semantic_closeout_results(state.repo_root, task_class)
        if active_change is not None and run_semantic_checks
        else []
    )
    failed_semantic_checks = [item for item in semantic_checks if not item.get("ok")]
    if failed_semantic_checks and lifecycle_state in {"ready_to_finish", "ready_to_push", "complete"}:
        lifecycle_state = "attention_required"
        requires_user_decision = True
        state_note = "repo-declared semantic closeout checks failed"
    ephemeral_worktrees = _ephemeral_worktree_records(state)
    if is_ephemeral_checkout_path(state.repo_root):
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
        "completion_disposition": (_completion_disposition(state, active_change.completion) if active_change and active_change.completion else {"scope": "current_checkout", "state": "no_completion_receipt", "environment_finalness": "not_asserted"}),
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
            "status": "completed" if run_semantic_checks else "not_evaluated",
            **({"ok": not failed_semantic_checks} if run_semantic_checks else {}),
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


def _brief_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    current_change = payload.get("current_change") or {}
    current_task: dict[str, Any] = {"registered": bool(current_change)}
    for key in ("branch", "task_class", "lifecycle", "phase", "checkout_path"):
        value = current_change.get(key)
        if value is not None:
            current_task[key] = value
    if not current_change and payload.get("branch") is not None:
        current_task["branch"] = payload["branch"]

    blockers: list[str] = []
    blockers.extend(str(item) for item in payload.get("cleanup_blockers", []) if item)
    for check in payload.get("semantic_closeout", {}).get("checks", []):
        if check.get("ok"):
            continue
        name = check.get("name") or "unnamed"
        blockers.append(f"semantic closeout check failed: {name}")
    blockers.extend(str(item) for item in payload.get("live_owner_errors", []) if item)
    blockers.extend(
        f"forbidden temporary worktree: {item.get('path', 'unknown')}"
        for item in payload.get("ephemeral_worktrees", [])
        if item.get("path") == payload.get("repo_root")
    )
    blockers.extend(
        f"managed link leak: {item}"
        for item in payload.get("managed_link_leaks", [])
    )
    if payload.get("requires_user_decision"):
        blockers.extend(str(item) for item in payload.get("notes", []) if item)
    blockers = list(dict.fromkeys(blockers))

    keeper_relation: dict[str, Any] = {
        "remotes": [
            {
                "remote": item["remote"],
                "branch": item["branch"],
                "relation": item["relation"],
                "preserved": bool(item["preserved"]),
            }
            for item in payload.get("keeper_remotes", [])
        ]
    }
    if payload.get("authoritative_branch") is not None:
        keeper_relation["authoritative_branch"] = payload["authoritative_branch"]

    residue = payload.get("residue", {})
    return {
        "operation": payload["operation"],
        "execution": payload["execution"],
        "target": payload["target"],
        "current_task": current_task,
        "completion_disposition": payload["completion_disposition"],
        "state": payload["state"],
        "blockers": blockers,
        "next_action": payload["next_action"],
        "keeper_relation": keeper_relation,
        "residue_counts": {
            "total": int(residue.get("total_count", 0)),
            "safe": int(residue.get("safe_count", 0)),
            "auto_park": int(residue.get("auto_park_count", 0)),
            "grace_pending": int(residue.get("grace_pending_count", 0)),
            "decision": int(residue.get("decision_count", 0)),
        },
    }


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
    continue_review: str | None = None,
    new_review: bool = False,
) -> dict[str, Any]:
    if continue_review:
        if new_review or from_current or (base is not None and base != continue_review):
            raise GitSafeError("continuation requires its exact review ref as the base")
        _continuation_target(state, continue_review, _ref_commit(continue_review, cwd=state.repo_root))
        base = continue_review
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
                review_intent="continue" if continue_review else "new",
                review_ref=continue_review,
                review_remote=continue_review.split("/", 1)[0] if continue_review else None,
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
    continue_review: str | None = None,
    new_review: bool = False,
) -> dict[str, Any]:
    """Start is a single control-plane transaction, including registry ownership."""
    with _task_mutation(state, branch=_normalize_branch_name(topic)) as refreshed, _integration_lock(state.common_dir):
        return _start_payload_unlocked(
            refreshed,
            topic=topic,
            base=base,
            from_current=from_current,
            mode=mode,
            worktree_root=worktree_root,
            worktree_path=worktree_path,
            dry_run=dry_run,
            task_class=task_class,
            continue_review=continue_review,
            new_review=new_review,
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
                        result_status="side_effect_completed_reconciliation_required",
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
        _test_stop_after("completion_local_worktree_removed")
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
            with _integration_lock(state.common_dir):
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
        _clear_active_change(state, branch=target_branch)

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
        with _integration_lock(state.common_dir):
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
    residue_entries = _scratch_residue_entries(state, assessment, sync_registry=True)
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
    with _task_mutation(state) as refreshed, _keeper_lock(state.common_dir):
        return _finish_payload_unlocked(refreshed, apply=apply)


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
    checkpoint_generation: int | None = None,
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
    try:
        checkpoint = (
            _update_yeet_checkpoint(control_state, change, submission, checkpoint_file,
                                    expected_generation=checkpoint_generation)
            if update_checkpoint
            else {"state": "task_record", "updated": False}
        )
    except GitSafeError as exc:
        # Publication is already proved, even though the queue/retirement boundary
        # has not been crossed. A checkpoint race is not a zero-effect rejection.
        exc.result_status = "side_effect_completed_reconciliation_required"
        exc.data.update({"review_proof": proof, "resume_checkout": str(state.repo_root),
                         "resume_task": change.branch})
        exc.data["side_effect_ids"] = list(dict.fromkeys([
            *exc.data.get("side_effect_ids", []),
            f"git_ref:{change.review_ref}:{change.published_tip}",
        ]))
        raise
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
    temporary_cleanup = _retire_owned_temporary_artifacts(control_state, change)
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
        raise GitSafeError(
            "task retirement failed after pull-request preservation",
            blockers=list(cleanup["blockers"]),
            data={"cleanup": cleanup},
            result_status="side_effect_completed_reconciliation_required",
        )
    cleanup["temporary_artifacts"] = temporary_cleanup
    cleanup.setdefault("actions", []).extend(temporary_cleanup["actions"])
    return proof, cleanup, submission, checkpoint


def _mark_review_ready_payload_unlocked(
    state: RepoState,
    *,
    review_ref: str,
    review_url: str,
    apply: bool,
) -> dict[str, Any]:
    review_url = _normalized_review_url(review_url)
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
            review_url=review_url,
        )
    return {
        "command": "review-ready",
        "schema_version": STATE_SCHEMA_VERSION,
        "ok": True,
        "apply_requested": apply,
        "branch": active_change.branch,
        "published_tip": published_tip,
        "review_ref": review_ref,
        "review_url": review_url,
        "state": "ready_for_integration" if apply else "plan",
    }


def _mark_review_ready_payload(
    state: RepoState,
    *,
    review_ref: str,
    review_url: str,
    apply: bool,
) -> dict[str, Any]:
    lock = _task_mutation(state) if apply else nullcontext(state)
    with lock as refreshed:
        return _mark_review_ready_payload_unlocked(
            refreshed,
            review_ref=review_ref,
            review_url=review_url,
            apply=apply,
        )


def _recover_import_ownership(
    state: RepoState, payload: dict[str, Any], owner: ManagedChange,
    record: dict[str, Any], proof_path: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Recover lost metadata from explicitly selected, corroborated local evidence.

    This is a trusted operator evidence input, not a signature or a way to adopt
    external branches. Keep the queue and this owner's pre-advancement journal
    consistent in the caller's single state-file transaction.
    """
    path = _resolve_path(proof_path, base=state.repo_root)
    try:
        raw = path.read_bytes()
        proof = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise GitSafeError("cannot read original publication ownership proof") from exc
    if not isinstance(proof, dict):
        raise GitSafeError("ownership proof must be an original successful yeet result")
    original = proof.get("submission", {})
    remote = proof.get("review_proof", {})
    cleanup = proof.get("cleanup", {})
    keys = ("queue_id", "review_ref", "review_remote", "review_url", "published_tip")
    if (proof.get("command") != "yeet" or proof.get("ok") is not True
            or proof.get("state") != "ready_for_integration"
            or not all(isinstance(item, dict) for item in (original, remote, cleanup))
            or original.get("disposal_owned") is not True
            or any(original.get(key) != record[key] for key in keys)
            or remote.get("verified") is not True or cleanup.get("verified") is not True
            or any(remote.get(key) != record[key] for key in ("review_ref", "review_remote", "published_tip"))
            or remote.get("remote_tip") != record["published_tip"]):
        raise GitSafeError("ownership proof lacks exact verified managed publication and retirement")
    checkout = original.get("checkout_identity")
    branch = original.get("branch")
    if (not isinstance(checkout, str) or not Path(checkout).is_absolute()
            or original.get("checkout_path") != checkout
            or branch != record["branch"] or not branch.startswith("codex/")
            or record["review_ref"] != f"{record['review_remote']}/{branch}"
            or not original.get("created_at") or not original.get("start_tip")):
        raise GitSafeError("ownership proof lacks original managed task identity")
    existing = [item for item in payload["submitted_changes"]
                if all(item.get(key) == record[key] for key in keys)]
    if len(existing) != 1:
        raise GitSafeError("ownership recovery requires one exact existing submitted review")
    # A deleted, retained task-temp receipt independently binds the original
    # managed task to this repository. Never synthesize it from the supplied file.
    expected_owner = {"branch": branch, "checkout_identity": checkout,
                      "common_dir": str(state.common_dir), "created_at": original["created_at"],
                      "start_tip": original["start_tip"]}
    temporary = cleanup.get("temporary_artifacts")
    if not isinstance(temporary, dict) or not isinstance(temporary.get("artifacts"), list):
        raise GitSafeError("ownership proof lacks managed temporary retirement evidence")
    saved_artifacts = temporary["artifacts"]
    corroborated = [item for item in payload["temporary_artifacts"]
                   if item.get("owner") == expected_owner and item.get("phase") == "deleted"
                   and item.get("cleanup", {}).get("status") == "deleted"
                   and any(isinstance(saved, dict) and all(saved.get(key) == item.get(key)
                           for key in ("id", "owner", "owner_key", "nonce", "marker_sha256", "cleanup"))
                           for saved in saved_artifacts)]
    if not corroborated:
        raise GitSafeError("ownership proof has no matching retained managed retirement evidence")
    if (Path(checkout).exists() or any(item.get("branch") == branch
            or _payload_checkout_identity(item) == checkout for item in payload["active_changes"])
            or any(item.get("branch") == branch for item in payload["parked_changes"])
            or any(entry.branch == branch or _checkout_identity(entry.path) == checkout for entry in state.worktrees)
            or _run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=state.repo_root).returncode == 0):
        raise GitSafeError("ownership recovery requires the original managed task to remain retired")
    recovered = dict(original)
    # Import annotations may express current preservation obligations.
    for key in ("dependencies", "goal_id", "thread_id"):
        if key in existing[0]:
            recovered[key] = existing[0][key]
    reconciled = False
    for active in payload["active_changes"]:
        receipt = active.get("completion")
        if not receipt:
            continue
        related = [item for item in receipt["selections"]
                   if item.get("review_ref") == record["review_ref"] or item.get("queue_id") == record["queue_id"]]
        if not related:
            continue
        if (_payload_checkout_identity(active) != _checkout_identity(state.repo_root)
                or receipt.get("owner_checkout") != str(state.repo_root)
                or receipt.get("owner_branch") != owner.branch
                or receipt.get("kind") != "standalone_integration"
                or receipt.get("phase") != "integrating" or receipt.get("integrated_tip")
                or active.get("integrated_tip")
                or active.get("phase") in ("integrated_local", "pushed_verified", "checkpoint_updated")
                or len(related) != 1 or any(related[0].get(key) != record[key] for key in keys)
                or _is_ancestor(receipt["integration_head"], owner.authoritative_branch, cwd=state.repo_root)):
            raise GitSafeError("ownership recovery requires this owner's exact pre-advancement standalone selection")
        related[0]["disposal_owned"] = True
        _validate_completion(receipt)
        legacy = payload.get("active_change")
        if legacy and _payload_checkout_identity(legacy) == _payload_checkout_identity(active):
            legacy["completion"] = receipt
        reconciled = True
    evidence = {"sha256": hashlib.sha256(raw).hexdigest(),
                "retirement_artifact_ids": [item["id"] for item in corroborated],
                "completion_reconciled": reconciled}
    recovered["ownership_recovery"] = evidence
    return recovered, evidence


_RECONCILIATION_MAX_PROOF_BYTES = 1024 * 1024


def _reconciliation_state_sha256(state: RepoState) -> str:
    path = _managed_state_path(state.common_dir)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GitSafeError("post-advancement reconciliation cannot read the managed state generation") from exc
    return hashlib.sha256(raw).hexdigest()


def _reconciliation_proof_file(path_value: str, *, base: Path) -> tuple[Path, str, dict[str, Any]]:
    path = _resolve_path(path_value, base=base)
    if path is None or path.is_symlink() or not path.is_file():
        raise GitSafeError(f"ownership proof chain requires a regular, non-symlink file: {path_value}")
    try:
        if path.stat().st_size > _RECONCILIATION_MAX_PROOF_BYTES:
            raise GitSafeError(f"ownership proof chain file is too large: {path}")
        raw = path.read_bytes()
        proof = json.loads(raw)
    except GitSafeError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise GitSafeError(f"cannot read ownership proof chain file: {path}") from exc
    if not isinstance(proof, dict):
        raise GitSafeError(f"ownership proof chain file must contain one JSON result object: {path}")
    return path, hashlib.sha256(raw).hexdigest(), proof


def _reconciliation_proof_chain(
    state: RepoState,
    proof_paths: list[str],
    *,
    review_ref: str,
    review_url: str,
    expected_tip: str,
) -> dict[str, Any]:
    if len(proof_paths) < 2:
        raise GitSafeError(
            "post-advancement reconciliation requires at least two contiguous yeet journal results",
            blockers=["supply the original publication result and every exact continuation result in chronological order"],
        )
    if len(proof_paths) > 32:
        raise GitSafeError("post-advancement reconciliation proof chain is unbounded")
    seen_paths: set[str] = set()
    entries: list[dict[str, Any]] = []
    for raw_path in proof_paths:
        path, digest, proof = _reconciliation_proof_file(raw_path, base=state.repo_root)
        identity = _checkout_identity(path)
        if identity in seen_paths:
            raise GitSafeError("ownership proof chain repeats one journal result")
        seen_paths.add(identity)
        submission = proof.get("submission")
        review = proof.get("review_proof")
        cleanup = proof.get("cleanup")
        execution = proof.get("execution")
        operation = proof.get("operation")
        if (
            proof.get("command") != "yeet"
            or proof.get("ok") is not True
            or proof.get("command_ok") is not True
            or proof.get("policy_ok") is not True
            or proof.get("state") != "ready_for_integration"
            or proof.get("transaction") != "ordinary_pull_request"
            or proof.get("effective_completion") != "review_only"
            or not isinstance(operation, dict)
            or operation.get("status") != "completed"
            or not isinstance(execution, dict)
            or not isinstance(execution.get("id"), str)
            or not execution["id"]
            or execution.get("authority", {}).get("mode") != "apply"
            or not isinstance(execution.get("side_effects"), list)
            or not isinstance(submission, dict)
            or not isinstance(review, dict)
            or not isinstance(cleanup, dict)
        ):
            raise GitSafeError(f"ownership proof chain entry is not an actual successful yeet result: {path}")
        argv = execution.get("argv")
        if not isinstance(argv, list) or "yeet" not in argv or "--apply" not in argv:
            raise GitSafeError(f"ownership proof chain entry lacks its applying yeet invocation: {path}")
        keys = ("queue_id", "review_ref", "review_remote", "review_url", "published_tip")
        if any(not isinstance(submission.get(key), str) or not submission[key] for key in keys):
            raise GitSafeError(f"ownership proof chain entry lacks immutable submission identity: {path}")
        branch = submission.get("branch")
        checkout = submission.get("checkout_identity")
        start_tip = submission.get("start_tip")
        if (
            submission.get("disposal_owned") is not True
            or not isinstance(branch, str)
            or not branch.startswith("codex/")
            or not isinstance(checkout, str)
            or not Path(checkout).is_absolute()
            or submission.get("checkout_path") != checkout
            or not isinstance(start_tip, str)
            or not re.fullmatch(r"[0-9a-f]{40}", start_tip)
            or not re.fullmatch(r"[0-9a-f]{40}", submission["published_tip"])
            or not submission.get("created_at")
            or not submission.get("submitted_at")
        ):
            raise GitSafeError(f"ownership proof chain entry lacks its original managed task identity: {path}")
        if (
            review.get("verified") is not True
            or review.get("review_ref") != submission["review_ref"]
            or review.get("review_remote") != submission["review_remote"]
            or review.get("published_tip") != submission["published_tip"]
            or review.get("remote_tip") != submission["published_tip"]
            or review.get("review_branch") != submission["review_ref"].split("/", 1)[1]
        ):
            raise GitSafeError(f"ownership proof chain entry lacks exact live review-tip proof: {path}")
        if (
            cleanup.get("verified") is not True and cleanup.get("ok") is not True
            or cleanup.get("branch_safe_to_delete") is not True
            or cleanup.get("remote_safe_to_delete") is not True
            or cleanup.get("branch") != branch
            or cleanup.get("target_worktree_path") != checkout
            or not isinstance(cleanup.get("actions"), list)
            or f"deleted branch {branch}" not in cleanup["actions"]
            or f"removed worktree {checkout}" not in cleanup["actions"]
        ):
            raise GitSafeError(f"ownership proof chain entry lacks exact retired branch/worktree proof: {path}")
        temporary = cleanup.get("temporary_artifacts")
        if (
            not isinstance(temporary, dict)
            or temporary.get("verified") is not True
            or temporary.get("artifact_count") != 0
            or temporary.get("receipts") != []
            or ("artifacts" in temporary and temporary.get("artifacts") not in ([], None))
        ):
            raise GitSafeError(
                f"ownership proof chain entry does not prove zero owned temporary allocation: {path}"
            )
        entries.append({
            "path": str(path),
            "sha256": digest,
            "execution_id": execution["id"],
            "queue_id": submission["queue_id"],
            "review_ref": submission["review_ref"],
            "review_remote": submission["review_remote"],
            "review_url": _normalized_review_url(submission["review_url"]),
            "published_tip": submission["published_tip"],
            "branch": branch,
            "checkout": checkout,
            "start_tip": start_tip,
        })
    if len({entry["execution_id"] for entry in entries}) != len(entries):
        raise GitSafeError("ownership proof chain requires distinct recorded yeet executions")
    expected_url = _normalized_review_url(review_url)
    for entry in entries:
        if (
            entry["review_ref"] != review_ref
            or entry["review_url"] != expected_url
            or entry["review_remote"] != review_ref.split("/", 1)[0]
        ):
            raise GitSafeError("ownership proof chain review identity does not match the requested remote/ref/URL")
    if len({entry["queue_id"] for entry in entries}) != 1:
        raise GitSafeError("ownership proof chain is not a contiguous continuation of one queue identity")
    if len({entry["published_tip"] for entry in entries}) != len(entries):
        raise GitSafeError("ownership proof chain repeats one published tip")
    for previous, current in zip(entries, entries[1:]):
        if not _is_ancestor(previous["published_tip"], current["published_tip"], cwd=state.repo_root):
            raise GitSafeError("ownership proof chain has a non-contiguous continuation tip")
    if entries[-1]["published_tip"] != expected_tip:
        raise GitSafeError("ownership proof chain final tip does not match the requested immutable head")
    # A successful cleanup result is only useful here if its task is still absent
    # from the current managed ownership graph. The current integration owner is
    # intentionally allowed; all historical source task identities must be gone.
    managed = _load_managed_state(state.common_dir)
    source_branches = {entry["branch"] for entry in entries}
    source_checkouts = {_checkout_identity(Path(entry["checkout"])) for entry in entries}
    for entry in state.worktrees:
        if entry.branch in source_branches or _checkout_identity(entry.path) in source_checkouts:
            raise GitSafeError("ownership proof chain task still has native worktree metadata")
    for item in [*managed.get("active_changes", []), *managed.get("parked_changes", [])]:
        if item.get("branch") in source_branches or _payload_checkout_identity(item) in source_checkouts:
            raise GitSafeError("ownership proof chain task is still registered to another owner")
    for entry in entries:
        if Path(entry["checkout"]).exists():
            raise GitSafeError("ownership proof chain task checkout still exists")
        if _run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{entry['branch']}"], cwd=state.repo_root).returncode == 0:
            raise GitSafeError("ownership proof chain task branch still exists locally")
    owned_temp = []
    for item in managed.get("temporary_artifacts", []):
        owner = item.get("owner") if isinstance(item, dict) else None
        if not isinstance(owner, dict):
            continue
        owner_checkout = owner.get("checkout_identity")
        checkout_matches = (
            isinstance(owner_checkout, str)
            and _checkout_identity(Path(owner_checkout)) in source_checkouts
        )
        if owner.get("branch") in source_branches or checkout_matches:
            owned_temp.append(item)
    if owned_temp:
        raise GitSafeError("ownership proof chain has a retained owned temporary allocation")
    return {
        "entries": entries,
        "queue_id": entries[0]["queue_id"],
        "review_ref": review_ref,
        "review_remote": review_ref.split("/", 1)[0],
        "review_url": expected_url,
        "published_tip": expected_tip,
        "tips": [entry["published_tip"] for entry in entries],
        "branches": [entry["branch"] for entry in entries],
        "checkouts": [entry["checkout"] for entry in entries],
    }


def _post_advancement_reconciliation_context(
    state: RepoState,
    *,
    review_ref: str,
    review_url: str,
    expected_tip: str,
) -> dict[str, Any]:
    if "/" not in review_ref or not re.fullmatch(r"[0-9a-f]{40}", expected_tip):
        raise GitSafeError("post-advancement reconciliation requires an exact remote/ref and full expected tip")
    review_url = _normalized_review_url(review_url)
    assessment = _authority_assessment(state)
    owner = _managed_active_change(state, assessment)
    if owner is None or not owner.branch or owner.branch != state.branch:
        raise GitSafeError("post-advancement reconciliation requires the exact active integration owner")
    receipt = owner.completion
    if (
        not isinstance(receipt, dict)
        or receipt.get("version") != 2
        or receipt.get("kind") != "standalone_integration"
        or receipt.get("phase") != "disposing"
        or receipt.get("owner_checkout") != str(state.repo_root)
        or receipt.get("owner_branch") != owner.branch
        or not receipt.get("integrated_tip")
        or owner.phase not in {"integrated_local", "pushed_verified", "checkpoint_updated"}
    ):
        raise GitSafeError("post-advancement reconciliation requires the exact disposing integration receipt")
    if state.dirty:
        raise GitSafeError("post-advancement reconciliation refuses a dirty integration checkout")
    if _ref_commit("HEAD", cwd=state.repo_root) != receipt.get("integration_head"):
        raise GitSafeError("post-advancement reconciliation requires the receipt's exact integration HEAD")
    if owner.integrated_tip != receipt.get("integrated_tip"):
        raise GitSafeError("post-advancement reconciliation requires the receipt's exact integrated tip")
    selections = [item for item in receipt.get("selections", []) if item.get("review_ref") == review_ref]
    if len(selections) != 1:
        raise GitSafeError("post-advancement reconciliation requires one exact selected review")
    selection = selections[0]
    if any(selection.get(key) != value for key, value in {
        "review_ref": review_ref,
        "review_url": review_url,
        "published_tip": expected_tip,
        "review_remote": review_ref.split("/", 1)[0],
    }.items()):
        raise GitSafeError("post-advancement reconciliation selection identity changed")
    if not _is_ancestor(expected_tip, receipt["integrated_tip"], cwd=state.repo_root):
        raise GitSafeError("post-advancement reconciliation lacks canonical integration containment")
    control = Path(receipt["control_checkout"])
    if not control.is_dir():
        raise GitSafeError("post-advancement reconciliation requires the persistent control checkout")
    control_state = _repo_state(control)
    if control_state.common_dir != state.common_dir or control_state.branch != owner.authoritative_branch:
        raise GitSafeError("post-advancement reconciliation control checkout identity changed")
    _integration_yeet_preflight(state, owner)
    managed = _load_managed_state(state.common_dir)
    exact_integrated = [item for item in managed.get("integrated_changes", [])
                        if all(item.get(key) == selection.get(key)
                               for key in ("queue_id", "review_ref", "published_tip", "review_url"))]
    if len(exact_integrated) != 1:
        raise GitSafeError("post-advancement reconciliation lacks one exact integrated queue receipt")
    if any(item.get("review_ref") == review_ref for item in managed.get("submitted_changes", [])):
        raise GitSafeError("post-advancement reconciliation found the selected review still queued")
    return {"owner": owner, "receipt": receipt, "selection": selection, "control": control}


def _ownership_reconciliation_plan(
    state: RepoState,
    *,
    review_ref: str,
    review_url: str,
    expected_tip: str,
    proof_paths: list[str],
) -> dict[str, Any]:
    context = _post_advancement_reconciliation_context(
        state, review_ref=review_ref, review_url=review_url, expected_tip=expected_tip,
    )
    chain = _reconciliation_proof_chain(
        state, proof_paths, review_ref=review_ref, review_url=review_url, expected_tip=expected_tip,
    )
    disposal_selection = {**context["selection"], "disposal_owned": True}
    disposal = _validate_completed_review_disposal(state, context["receipt"], disposal_selection)
    state_sha256 = _reconciliation_state_sha256(state)
    identity = {
        "command": "reconcile-integration-ownership",
        "schema_version": 1,
        "review_ref": review_ref,
        "review_remote": chain["review_remote"],
        "review_url": chain["review_url"],
        "published_tip": expected_tip,
        "proof_queue_id": chain["queue_id"],
        "queue_id": context["selection"]["queue_id"],
        "owner_branch": context["owner"].branch,
        "owner_checkout": str(state.repo_root),
        "integration_head": context["receipt"]["integration_head"],
        "proof_chain": [entry["path"] for entry in chain["entries"]],
        "proof_sha256": [entry["sha256"] for entry in chain["entries"]],
        "proof_tips": chain["tips"],
    }
    attestation_id = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:32]
    attestation = {**identity, "attestation_id": attestation_id, "state_sha256": state_sha256, "recorded_at": _iso_now()}
    # The plan token is stable across the plan/apply boundary. The attestation's
    # wall-clock timestamp is evidence metadata, not a concurrency identity.
    plan_digest = hashlib.sha256(json.dumps({
        "state_sha256": state_sha256,
        "attestation_id": attestation_id,
        "attestation_identity": identity,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = context["receipt"].get("ownership_reconciliation", [])
    matching_existing = [item for item in existing if isinstance(item, dict) and item.get("attestation_id") == attestation_id]
    if matching_existing:
        if any(any(item.get(key) != attestation.get(key) for key in identity) for item in matching_existing):
            raise GitSafeError("existing ownership reconciliation attestation conflicts with the proof chain")
        attestation = {**matching_existing[0], "state_sha256": matching_existing[0].get("state_sha256", state_sha256)}
    elif any(isinstance(item, dict) and item.get("review_ref") == review_ref for item in existing):
        raise GitSafeError("existing ownership reconciliation attestation conflicts with this selected review")
    return {
        "context": context,
        "chain": chain,
        "disposal": disposal,
        "state_sha256": state_sha256,
        "attestation": attestation,
        "attestation_present": bool(matching_existing),
        "reconciliation_digest": plan_digest,
    }


def _append_ownership_reconciliation(
    state: RepoState, plan: dict[str, Any], *, expected_state_sha256: str,
) -> None:
    path = _managed_state_path(state.common_dir)
    try:
        current_raw = path.read_bytes()
    except OSError as exc:
        raise GitSafeError("post-advancement reconciliation cannot reread managed state") from exc
    current_sha256 = hashlib.sha256(current_raw).hexdigest()
    if current_sha256 != expected_state_sha256:
        raise GitSafeError(
            "managed state changed after reconciliation planning; no ownership attestation was written",
            blockers=["reread the exact task receipt and rerun the explicit reconciliation plan"],
        )
    context = plan["context"]
    owner = context["owner"]
    receipt = owner.completion
    managed = _load_managed_state(state.common_dir)
    found: list[dict[str, Any]] = []
    for item in managed.get("active_changes", []):
        if item.get("branch") == owner.branch and _payload_checkout_identity(item) == _checkout_identity(state.repo_root):
            found.append(item)
    if len(found) != 1 or found[0].get("completion") is None:
        raise GitSafeError("post-advancement reconciliation lost its exact active owner")
    current_receipt = found[0]["completion"]
    attestations = current_receipt.get("ownership_reconciliation", [])
    existing = [item for item in attestations if isinstance(item, dict) and item.get("attestation_id") == plan["attestation"]["attestation_id"]]
    if existing:
        if any(any(item.get(key) != plan["attestation"].get(key) for key in plan["attestation"] if key != "recorded_at") for item in existing):
            raise GitSafeError("existing ownership reconciliation attestation changed")
        return
    current_receipt["ownership_reconciliation"] = [*attestations, plan["attestation"]]
    # The proof attests the exact selected review identity. Promote that
    # selection and its integrated queue record together with the attestation;
    # the unchanged disposal path must see the recovered ownership bit.
    identity = plan["attestation"]
    matched_selection = [
        item for item in current_receipt.get("selections", [])
        if all(item.get(key) == identity.get(key) for key in
               ("review_ref", "review_url", "published_tip", "queue_id"))
    ]
    if len(matched_selection) != 1:
        raise GitSafeError("post-advancement reconciliation lost its exact selected review")
    matched_selection[0]["disposal_owned"] = True
    matched_queue = [
        item for item in managed.get("integrated_changes", [])
        if all(item.get(key) == identity.get(key) for key in
               ("review_ref", "review_url", "published_tip", "queue_id"))
    ]
    if len(matched_queue) != 1:
        raise GitSafeError("post-advancement reconciliation lost its exact integrated queue record")
    matched_queue[0]["disposal_owned"] = True
    current_receipt["side_effect_ids"] = list(dict.fromkeys([
        *current_receipt.get("side_effect_ids", []),
        f"git_ownership_reconciliation:{owner.branch}:{plan['attestation']['attestation_id']}",
    ]))
    _validate_completion(current_receipt)
    found[0]["completion"] = current_receipt
    legacy = managed.get("active_change")
    if legacy and legacy.get("branch") == owner.branch and _payload_checkout_identity(legacy) == _checkout_identity(state.repo_root):
        legacy["completion"] = current_receipt
    _save_managed_state(state.common_dir, managed)


def _reconcile_integration_ownership(
    state: RepoState,
    *,
    review_ref: str,
    review_url: str,
    expected_tip: str,
    proof_paths: list[str],
    expected_plan_digest: str | None,
    checkpoint_file: str | None,
    checkpoint_generation: int | None,
    apply: bool,
) -> dict[str, Any]:
    if not apply:
        plan = _ownership_reconciliation_plan(
            state, review_ref=review_ref, review_url=review_url, expected_tip=expected_tip,
            proof_paths=proof_paths,
        )
        return {
            "command": "reconcile-integration-ownership",
            "schema_version": STATE_SCHEMA_VERSION,
            "ok": True,
            "state": "plan",
            "transaction": "post_advancement_ownership_reconciliation",
            "apply_required": True,
            "required_flag": "--apply --expected-plan-digest <digest>",
            "repo_root": str(state.repo_root),
            "owner": {"branch": plan["context"]["owner"].branch, "checkout": str(state.repo_root),
                      "phase": plan["context"]["receipt"]["phase"]},
            "selection": plan["context"]["selection"],
            "proof_chain": plan["chain"],
            "provider_disposal": {"state": plan["disposal"]["state"], "review_ref": plan["disposal"]["review_ref"]},
            "state_sha256": plan["state_sha256"],
            "attestation": plan["attestation"],
            "attestation_present": plan["attestation_present"],
            "reconciliation_digest": plan["reconciliation_digest"],
            "actions": [
                "append one immutable ownership reconciliation attestation under the exact integration owner lock",
                "resume the existing standalone integration receipt and its unchanged closure/disposal guards",
            ],
        }
    if not expected_plan_digest:
        raise GitSafeError(
            "post-advancement reconciliation apply requires the read-only plan digest",
            blockers=["run the exact command without --apply, then supply its reconciliation_digest with --apply"],
        )
    task_lock = _task_mutation(state)
    with task_lock as refreshed, _keeper_lock(state.common_dir):
        plan = _ownership_reconciliation_plan(
            refreshed, review_ref=review_ref, review_url=review_url, expected_tip=expected_tip,
            proof_paths=proof_paths,
        )
        if expected_plan_digest != plan["reconciliation_digest"]:
            raise GitSafeError(
                "post-advancement reconciliation plan digest changed; no ownership attestation was written",
                blockers=["reread the plan and retry with its exact digest"],
                data={"reconciliation_digest": plan["reconciliation_digest"], "state_sha256": plan["state_sha256"]},
            )
        if not plan["attestation_present"]:
            _append_ownership_reconciliation(refreshed, plan, expected_state_sha256=plan["state_sha256"])
            refreshed = _repo_state(refreshed.cwd)
        owner = _managed_active_change(refreshed, _authority_assessment(refreshed))
        if owner is None:
            raise GitSafeError("post-advancement reconciliation lost its exact integration owner")
        try:
            result = _complete_standalone_integration_yeet(
                refreshed, owner,
                validation_summary=owner.completion["validation_summary"],
                checkpoint_file=checkpoint_file,
                checkpoint_generation=checkpoint_generation,
                integration_validation_file=None,
            )
        except GitSafeError as exc:
            exc.result_status = "side_effect_completed_reconciliation_required"
            exc.data.setdefault("ownership_reconciliation", plan["attestation"])
            exc.data.setdefault("resume_task", owner.branch)
            exc.data.setdefault("resume_checkout", str(refreshed.repo_root))
            raise
        result["ownership_reconciliation"] = plan["attestation"]
        result["reconciliation_digest"] = plan["reconciliation_digest"]
        return result


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
    ownership_proof: str | None = None,
) -> dict[str, Any]:
    review_url = _normalized_review_url(review_url)
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
        review_url=review_url,
    )
    record = _submitted_change_record(imported)
    if goal_id:
        record["goal_id"] = goal_id
    if thread_id:
        record["thread_id"] = thread_id
    if dependencies:
        record["dependencies"] = list(
            dict.fromkeys(_sanitized_identity_value(item) for item in dependencies)
        )
    recovery = None
    with _integration_lock(state.common_dir) if apply else nullcontext():
        payload = _load_managed_state(state.common_dir)
        existing = payload.get("submitted_changes", [])
        same_immutable_review = [item for item in existing
            if all(item.get(key) == record[key] for key in
                   ("queue_id", "review_ref", "review_remote", "review_url", "published_tip"))]
        if ownership_proof:
            if goal_id or thread_id or dependencies:
                raise GitSafeError("ownership recovery preserves current annotations; import new annotations separately")
            if not expected_tip:
                raise GitSafeError("ownership recovery requires --expected-tip")
            record, recovery = _recover_import_ownership(state, payload, active_change, record, ownership_proof)
        elif any(item.get("disposal_owned") is True for item in same_immutable_review):
            preserved = next(item for item in same_immutable_review if item.get("disposal_owned") is True)
            record = {**preserved, **{key: record[key] for key in ("dependencies", "goal_id", "thread_id") if key in record}}
        if apply:
            payload["submitted_changes"] = [
                item for item in existing
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
        "ownership_recovery": recovery,
        "remote_tip": remote_tip,
        "state": "ready_for_integration" if apply else "plan",
    }


def _import_review_payload(state: RepoState, **kwargs: Any) -> dict[str, Any]:
    lock = _task_mutation(state) if kwargs.get("apply") else nullcontext(state)
    with lock as refreshed:
        return _import_review_payload_unlocked(refreshed, **kwargs)


def _merge_selected_reviews(
    state: RepoState,
    active_branch: str,
    selections: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    actions: list[str] = []
    side_effect_ids: list[str] = []
    for selection in selections:
        source_ref = selection["source_ref"]
        if _is_ancestor(selection["published_tip"], active_branch, cwd=state.repo_root):
            actions.append(f"already included {source_ref}")
            continue
        merge_proc = _run(["git", "merge", "--no-ff", "--no-edit", source_ref], cwd=state.repo_root)
        if merge_proc.returncode != 0:
            merge_head = _ref_commit("MERGE_HEAD", cwd=state.repo_root)
            if merge_head:
                side_effect_ids.append(f"git_merge_state:{active_branch}:{source_ref}:{merge_head}")
            detail = merge_proc.stderr.strip() or merge_proc.stdout.strip() or f"git merge {source_ref} failed"
            raise GitSafeError(
                f"integration stopped while merging {source_ref}: {detail}",
                blockers=["resolve or abort the merge in the integration worktree before continuing"],
                data={
                    "completed_actions": actions,
                    "failed_source_ref": source_ref,
                    "side_effect_ids": side_effect_ids,
                },
                result_status=(
                    "side_effect_completed_reconciliation_required"
                    if side_effect_ids
                    else "correctly_blocked"
                ),
            )
        actions.append(f"merged {source_ref} into {active_branch}")
        merged_tip = _ref_commit(active_branch, cwd=state.repo_root)
        if merged_tip:
            side_effect_ids.append(f"git_merge:{active_branch}:{source_ref}:{merged_tip}")
    return actions, side_effect_ids


def _add_selector_candidate(
    candidates_by_selector: dict[str, list[dict[str, Any]]],
    selector: str,
    candidate: dict[str, Any],
) -> None:
    candidates = candidates_by_selector.setdefault(selector, [])
    if not any(existing is candidate for existing in candidates):
        candidates.append(candidate)


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
    refs = list(dict.fromkeys(_sanitized_identity_value(item) for item in source_refs))
    if not refs:
        raise GitSafeError("integrate requires at least one --source-ref")
    managed = _load_managed_state(state.common_dir)
    submitted_by_selector: dict[str, list[dict[str, Any]]] = {}
    known_by_selector: dict[str, list[dict[str, Any]]] = {}
    for item in managed.get("integrated_changes", []):
        for key in ("review_ref", "review_url", "queue_id"):
            value = item.get(key)
            if isinstance(value, str) and value:
                _add_selector_candidate(known_by_selector, value, item)
    for item in managed.get("submitted_changes", []):
        for key in ("review_ref", "review_url", "queue_id"):
            value = item.get(key)
            if isinstance(value, str) and value:
                _add_selector_candidate(known_by_selector, value, item)
                _add_selector_candidate(submitted_by_selector, value, item)
    selections: list[dict[str, Any]] = []
    blockers: list[str] = []
    selected_review_refs: list[str] = []
    for source_selector in refs:
        candidates = submitted_by_selector.get(source_selector, [])
        if not candidates:
            blockers.append(f"source selector is not a recorded ready pull request: {source_selector}")
            continue
        if len(candidates) != 1:
            blockers.append(f"source selector matches {len(candidates)} recorded ready pull requests")
            continue
        item = candidates[0]
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
    selected_by_selector: dict[str, list[dict[str, Any]]] = {}
    for selection in selections:
        _add_selector_candidate(selected_by_selector, selection["source_ref"], selection)
        for key in ("queue_id", "review_url"):
            value = selection.get(key)
            if isinstance(value, str):
                _add_selector_candidate(selected_by_selector, value, selection)
    dependency_edges: dict[str, set[str]] = {selection["source_ref"]: set() for selection in selections}
    for selection in selections:
        for dependency in selection.get("dependencies", []):
            known_candidates = known_by_selector.get(dependency, [])
            if len(known_candidates) > 1:
                blockers.append(
                    f"selected review has an ambiguous dependency selector: {selection['source_ref']}"
                )
                continue
            selected_candidates = selected_by_selector.get(dependency, [])
            if len(selected_candidates) > 1:
                blockers.append(
                    f"selected review has an ambiguous selected dependency: {selection['source_ref']}"
                )
                continue
            if len(selected_candidates) == 1:
                dependency_edges[selection["source_ref"]].add(selected_candidates[0]["source_ref"])
                continue
            dependency_item = known_candidates[0] if len(known_candidates) == 1 else None
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
    selection_by_ref: dict[str, dict[str, Any]] = {}
    for selection in selections:
        source_ref = selection["source_ref"]
        if source_ref in selection_by_ref:
            raise GitSafeError(
                "project integration selection is not safe",
                blockers=["selected reviews do not have unique immutable refs"],
                data={"selections": selections},
            )
        selection_by_ref[source_ref] = selection
    selections = [selection_by_ref[ref] for ref in ordered_refs]
    actions: list[str] = []
    side_effect_ids: list[str] = []
    if apply:
        actions, side_effect_ids = _merge_selected_reviews(state, active_change.branch, selections)
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
        "side_effect_ids": side_effect_ids,
    }


def _integrate_payload(state: RepoState, *, source_refs: list[str], apply: bool) -> dict[str, Any]:
    task_lock = _task_mutation(state) if apply else nullcontext(state)
    with task_lock as refreshed, _keeper_lock(state.common_dir) if apply else nullcontext():
        return _integrate_payload_unlocked(refreshed, source_refs=source_refs, apply=apply)


def _task_temp_owner(state: RepoState, change: ManagedChange) -> dict[str, str]:
    record = {
        "checkout_identity": _checkout_identity(Path(change.checkout_path)) if change.checkout_path else None,
        "checkout_path": change.checkout_path,
        "branch": change.branch,
        "created_at": change.created_at,
        "start_tip": change.start_tip,
    }
    try:
        return owner_identity(record, common_dir=state.common_dir)
    except TaskTempError as exc:
        raise GitSafeError(str(exc)) from exc


def _task_temp_status(state: RepoState, change: ManagedChange) -> dict[str, Any]:
    if not change.start_tip:
        return {"artifacts": [], "pending_count": 0, "deleted_count": 0}
    try:
        return status_for_owner(_load_managed_state(state.common_dir), _task_temp_owner(state, change))
    except TaskTempError as exc:
        raise GitSafeError(str(exc)) from exc


def _retire_owned_temporary_artifacts(state: RepoState, change: ManagedChange) -> dict[str, Any]:
    if not change.start_tip:
        return {"verified": True, "actions": [], "receipts": [], "artifact_count": 0}
    try:
        return cleanup_owned_roots(
            owner=_task_temp_owner(state, change),
            common_dir=state.common_dir,
            load_state=lambda: _load_managed_state(state.common_dir),
            save_state=lambda payload: _save_managed_state(state.common_dir, payload),
            state_transaction=lambda: _integration_lock(state.common_dir),
        )
    except TaskTempError as exc:
        raise GitSafeError(
            "task-owned temporary scratch cleanup failed",
            blockers=[str(exc)],
            data={"temporary_artifacts": {"verified": False, "error": str(exc)}},
            result_status="side_effect_completed_reconciliation_required",
        ) from exc


def _retire_integrated_change(state: RepoState, change: ManagedChange, authoritative_branch: str, control_checkout: Path, *, canonical_dirty_fingerprint: str | None = None) -> dict[str, Any]:
    temporary_cleanup = _retire_owned_temporary_artifacts(state, change)
    cleanup = _cleanup_payload(
        _repo_state(control_checkout), branch=change.branch, base=authoritative_branch,
        worktree_path=change.checkout_path if change.mode == "worktree" else None,
        cwd_override=str(control_checkout), delete_remote=None, confirm_remote_delete=None,
        preserved_ref=authoritative_branch, apply=True, dry_run=False,
    )
    if cleanup.get("blockers"):
        raise GitSafeError(
            "retirement failed after keeper preservation",
            blockers=list(cleanup["blockers"]),
            data={"cleanup": cleanup},
            result_status="side_effect_completed_reconciliation_required",
        )
    control_state = _repo_state(control_checkout)
    if canonical_dirty_fingerprint is not None:
        after = _dirty_fingerprint(control_state.repo_root)["digest"]
        if after != canonical_dirty_fingerprint:
            raise GitSafeError("canonical dirty fingerprint changed during task retirement")
    _record_retired_change(control_state, change)
    _clear_active_change(control_state, checkout_path=Path(change.checkout_path) if change.checkout_path else None)
    cleanup["temporary_artifacts"] = temporary_cleanup
    cleanup.setdefault("actions", []).extend(temporary_cleanup["actions"])
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
    with _task_mutation(state) as refreshed:
        return _park_payload_unlocked(refreshed, apply=apply)


def _closeout_payload_unlocked(state: RepoState, *, apply: bool, confirmed: bool) -> dict[str, Any]:
    status_payload = _status_payload(state, run_semantic_checks=confirmed)
    lifecycle_state = status_payload["state"]
    payload: dict[str, Any] = {
        "command": "end",
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
        remote_proofs, push_actions, push_side_effect_ids = _push_and_verify_keeper_remotes(
            proof_state,
            authoritative_branch,
            canonical_dirty_fingerprint=dirty_proof,
        )
        payload["actions"].extend(push_actions)
        payload.setdefault("side_effect_ids", []).extend(push_side_effect_ids)
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
            remote_proofs, push_actions, push_side_effect_ids = _push_and_verify_keeper_remotes(
                refreshed,
                authoritative_branch,
            )
            payload["actions"].extend(push_actions)
            payload.setdefault("side_effect_ids", []).extend(push_side_effect_ids)
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
    """Serialize this owner and keeper changes without locking shared metadata across I/O."""
    task_lock = _task_mutation(state) if apply else nullcontext(state)
    with task_lock as refreshed_state, _keeper_lock(state.common_dir) if apply else nullcontext():
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


def _project_checkpoint_resolution(repo_root: Path, *, include_model: bool = False) -> dict[str, Any]:
    proc = _run([_project_checkpoint_helper(), "show", "--repo", str(repo_root), "--json",
                 *(["--model"] if include_model else [])], cwd=repo_root)
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


def _check_checkpoint_generation(
    resolution: dict[str, Any], change: ManagedChange, expected_generation: int | None,
) -> None:
    """Keep an authored snapshot bound to its observed generation, including retries."""
    if expected_generation is None:
        return  # Existing internal callers retain the writer's CAS; authored inputs should bind it explicitly.
    if type(expected_generation) is not int or expected_generation < 1:
        raise GitSafeError("checkpoint generation must be a positive integer")
    generation = resolution.get("generation")
    if not resolution.get("adopted") or type(generation) is not int:
        raise GitSafeError("checkpoint generation requires the adopted checkpoint and its model")
    if change.checkpoint_generation is not None:
        if generation < change.checkpoint_generation:
            raise GitSafeError("the current project checkpoint predates the task's recorded update")
        return  # This task already wrote its handoff; never replay an old model over another writer.
    if generation != expected_generation:
        raise GitSafeError("checkpoint generation changed before the completion write")


def _update_yeet_checkpoint(
    state: RepoState,
    change: ManagedChange,
    submission: dict[str, Any],
    checkpoint_file: str | None,
    *, expected_generation: int | None = None,
    removals: tuple[tuple[str, str, str], ...] = (),
) -> dict[str, Any]:
    resolution = _project_checkpoint_resolution(state.repo_root)
    _check_checkpoint_generation(resolution, change, expected_generation)
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
                *(argument for removal in removals for argument in ("--remove", *removal)),
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
    has_commits = bool(change.start_tip and _ref_commit("HEAD", cwd=state.repo_root) != change.start_tip)
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


def _integration_yeet_preflight(
    state: RepoState,
    change: ManagedChange,
    *,
    permit_ordinary_first_parent: bool = False,
) -> dict[str, Any]:
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
    ordinary_first_parent_commits: list[str] = []
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
                    ordinary_first_parent_commits.append(commit)
                    if not permit_ordinary_first_parent:
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
        "ordinary_first_parent_commits": ordinary_first_parent_commits,
    }


def _recover_legacy_checkpoint_integration_history(
    state: RepoState,
    change: ManagedChange,
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Additively seal one unpublished legacy-checkpoint commit behind a merge."""
    scope = _integration_yeet_preflight(state, change, permit_ordinary_first_parent=True)
    ordinary = scope["ordinary_first_parent_commits"]
    if not ordinary:
        return None

    current_head = _ref_commit("HEAD", cwd=state.repo_root)
    blockers: list[str] = []
    if change.completion is not None:
        blockers.append("integration history recovery cannot rewrite a persisted completion identity")
    if change.published_tip or change.review_ref or change.review_url:
        blockers.append("integration history recovery refuses a published integration owner")
    if len(ordinary) != 1 or ordinary[0] != current_head:
        blockers.append("integration history recovery requires exactly one trailing ordinary commit")

    changed_paths: list[str] = []
    if len(ordinary) == 1:
        changed_paths = [
            line
            for line in _git_output(
                ["diff-tree", "--no-commit-id", "--name-only", "-r", ordinary[0]],
                cwd=state.repo_root,
            ).splitlines()
            if line.strip()
        ]
        if changed_paths != ["CHECKPOINT.md"]:
            blockers.append("integration history recovery permits only a trailing CHECKPOINT.md commit")

    checkpoint = _project_checkpoint_resolution(state.repo_root)
    if checkpoint.get("state") != "not_adopted":
        blockers.append("integration history recovery requires the legacy tracked checkpoint mode")
    tracked_checkpoint = _run(
        ["git", "cat-file", "-e", f"{change.start_tip}:CHECKPOINT.md"],
        cwd=state.repo_root,
    ) if change.start_tip else None
    if tracked_checkpoint is None or tracked_checkpoint.returncode != 0:
        blockers.append("integration history recovery requires CHECKPOINT.md in the recorded baseline")

    authoritative_head = None
    if change.authoritative_branch:
        authoritative_head = _ref_commit(change.authoritative_branch, cwd=state.repo_root)
    if not change.start_tip or authoritative_head != change.start_tip:
        blockers.append("integration history recovery requires unchanged local authority at the recorded baseline")
    for keeper in _keeper_tracking_status(state, change.authoritative_branch):
        if keeper.get("local_head") != change.start_tip or keeper.get("remote_head") != change.start_tip:
            blockers.append(f"integration history recovery requires unchanged keeper baseline: {keeper.get('remote')}")

    if blockers:
        raise GitSafeError(
            "integration yeet preconditions are not satisfied",
            blockers=[
                *(f"integration history contains an ordinary commit: {commit}" for commit in ordinary),
                *blockers,
            ],
            data={"task_class": change.task_class, "selected_refs": list(change.selected_refs)},
        )

    old_head = current_head
    recovery: dict[str, Any] = {
        "kind": "legacy_tracked_checkpoint_merge_seal",
        "old_head": old_head,
        "new_head": None,
        "first_parent": change.start_tip,
        "second_parent": old_head,
        "changed_paths": changed_paths,
        "apply_requested": apply,
    }
    if not apply:
        return {"scope": scope, "recovery": recovery}

    tree = _git_output(["rev-parse", f"{old_head}^{{tree}}"], cwd=state.repo_root)
    commit_proc = _run(
        [
            "git", "commit-tree", tree,
            "-p", change.start_tip,
            "-p", old_head,
            "-m", "Merge prepared integration with legacy tracked checkpoint handoff",
        ],
        cwd=state.repo_root,
    )
    if commit_proc.returncode != 0:
        raise GitSafeError(commit_proc.stderr.strip() or commit_proc.stdout.strip() or "could not create integration recovery merge")
    new_head = commit_proc.stdout.strip()
    update_proc = _run(
        ["git", "update-ref", f"refs/heads/{change.branch}", new_head, old_head],
        cwd=state.repo_root,
    )
    if update_proc.returncode != 0:
        raise GitSafeError(update_proc.stderr.strip() or update_proc.stdout.strip() or "could not advance integration recovery merge")

    refreshed = _repo_state(state.repo_root)
    observed_head = _ref_commit("HEAD", cwd=state.repo_root)
    if observed_head != new_head or refreshed.dirty:
        raise GitSafeError(
            "integration recovery merge did not leave the owner at its clean sealed HEAD",
            data={"old_head": old_head, "new_head": new_head, "observed_head": observed_head},
            result_status="side_effect_completed_reconciliation_required",
        )
    parents = _git_output(["show", "-s", "--format=%P", new_head], cwd=state.repo_root).split()
    recovered_tree = _git_output(["rev-parse", f"{new_head}^{{tree}}"], cwd=state.repo_root)
    if parents != [change.start_tip, old_head] or recovered_tree != tree:
        raise GitSafeError(
            "integration recovery merge failed its parent or tree identity proof",
            data={"old_head": old_head, "new_head": new_head, "parents": parents},
            result_status="side_effect_completed_reconciliation_required",
        )
    recovery["new_head"] = new_head
    return {"scope": scope, "recovery": recovery}


def _finalize_integration_yeet_unlocked(
    state: RepoState,
    change: ManagedChange,
    *,
    checkpoint_file: str | None,
    transaction: str = "selected_integration",
    reconcile_selected: bool = True,
    completion_owner: ManagedChange | None = None,
    checkpoint_generation: int | None = None,
    retire_local: bool = True,
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
    remote_proofs, actions, push_side_effect_ids = _push_and_verify_keeper_remotes(
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
    selected_records = (
        tuple(item["queue_id"] for item in completion_owner.completion["selections"])
        if completion_owner is not None else change.selected_refs
    )
    candidates = (
        _integrated_submission_candidates(proof_state, authoritative_branch, selected_records)
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
    if completion_owner is not None:
        receipt = completion_owner.completion
        checkpoint = _completion_checkpoint(proof_state, completion_owner, receipt, checkpoint_file, final=False, expected_generation=checkpoint_generation)
    else:
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
            selected_records,
        )
        if reconcile_selected
        else []
    )
    dirty_proof = _integrated_dirty_proof(proof_state, change, authoritative_branch)
    if not retire_local:
        cleanup = {"state": "pending", "reason": "selected remote disposal precedes owner retirement"}
    elif completion_owner is not None:
        cleanup = _retire_completion_local(_repo_state(control_checkout), change, control_checkout, integrated_tip)
    else:
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
            "retired the local task state" if retire_local else "retained the owner for selected remote disposal",
        ]
    )
    return {
        "command": "yeet",
        "schema_version": STATE_SCHEMA_VERSION,
        "ok": True,
        "state": "complete" if retire_local else "retirement_pending",
        "transaction": transaction,
        "remote_proofs": remote_proofs,
        "hosted_review_finalization": hosted_review_finalization,
        "integrated_submissions": integrated_submissions,
        "checkpoint": checkpoint,
        "cleanup": cleanup,
        "actions": actions,
        "side_effect_ids": push_side_effect_ids,
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


def _resume_submitted_local(state: RepoState, selector: str) -> None:
    """Resume only an exact queued owner's interrupted local retirement."""
    managed = _load_managed_state(state.common_dir)
    queued = [item for item in managed["submitted_changes"] if item.get("branch") == selector]
    owners = [item for item in managed["active_changes"] if item.get("branch") == selector]
    if not queued or not owners:
        return  # A completed task is re-proved below; no ownership is invented.
    if len(queued) != 1 or len(owners) != 1:
        raise GitSafeError("submitted retirement has ambiguous task ownership")
    record, owner = queued[0], owners[0]
    if owner.get("completion"):
        return  # The integration receipt owns its distinct remaining phases.
    change = _managed_change_from_payload(owner)
    if (change.mode != "worktree" or not change.checkout_path or not change.branch or not change.start_tip or not change.created_at or
        not change.branch.startswith("codex/") or not change.authoritative_branch or
        any(owner.get(key) != record.get(key) for key in
            ("checkout_identity", "published_tip", "review_ref", "review_url", "start_tip", "created_at"))):
        raise GitSafeError("submitted retirement lost its exact original owner identity")
    path = Path(change.checkout_path)
    if state.repo_root == path or is_ephemeral_checkout_path(state.repo_root):
        raise GitSafeError("submitted retirement resume requires a persistent checkout outside the task")
    if path.exists():
        target = _repo_state(path)
        _require_yeet_closeout(target, change)
        _retire_submitted_change(target, change, change.authoritative_branch)
        return
    if _worktree_entry_for_path(state, path) is not None or _branch_checked_out_elsewhere(state, change.branch):
        raise GitSafeError("submitted retirement retains native worktree metadata; inspect its exact owned entry")
    # The queue was recorded only after live remote proof. Re-prove the exact
    # remote before any resumed deletion, including when the local ref is gone.
    remote, review_branch = change.review_ref.split("/", 1)
    remote_proc = _run(["git", "ls-remote", "--heads", remote, f"refs/heads/{review_branch}"], cwd=state.repo_root)
    remote_tip = remote_proc.stdout.split()[0] if remote_proc.returncode == 0 and remote_proc.stdout.strip() else ""
    if remote != change.review_remote or remote_tip != change.published_tip:
        raise GitSafeError("submitted retirement requires the exact live review tip")
    branch_present = _run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{change.branch}"], cwd=state.repo_root).returncode == 0
    if branch_present and _ref_commit(change.branch, cwd=state.repo_root) != change.published_tip:
        raise GitSafeError("submitted local branch changed before retirement")
    _retire_owned_temporary_artifacts(state, change)
    if branch_present:
        deleted = _run(["git", "update-ref", "-d", f"refs/heads/{change.branch}", change.published_tip], cwd=state.repo_root)
        if deleted.returncode:
            raise GitSafeError("submitted local branch compare-and-delete failed")
    with _integration_lock(state.common_dir):
        if is_scratch_path(path):
            _remove_index_registry_paths({path})
            _remove_registry_paths({path})
        _clear_active_change_unlocked(state, checkout_path=path)


def _yeet_submitted_result(state: RepoState, selector: str) -> dict[str, Any]:
    selector = _sanitized_identity_value(selector)
    managed = _load_managed_state(state.common_dir)
    submitted_by_selector: dict[str, list[dict[str, Any]]] = {}
    for item in managed.get("submitted_changes", []):
        for key in ("branch", "queue_id", "review_ref", "review_url"):
            value = item.get(key)
            if isinstance(value, str) and value:
                _add_selector_candidate(submitted_by_selector, value, item)
    matches = submitted_by_selector.get(selector, [])
    if not matches:
        retired_by_selector: dict[str, list[dict[str, Any]]] = {}
        for item in managed.get("retired_changes", []):
            for key in ("branch", "integrated_tip"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    _add_selector_candidate(retired_by_selector, value, item)
        retired_matches = retired_by_selector.get(selector, [])
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
        if local_tip != integrated_tip and not (item.get("completion") and _is_ancestor(integrated_tip, local_tip, cwd=state.repo_root)):
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
        temporary_status = _task_temp_status(state, _managed_change_from_payload(item))
        if temporary_status["pending_count"]:
            raise GitSafeError(
                "the integrated task still has task-owned temporary residue",
                data={"temporary_artifacts": temporary_status},
            )
        checkpoint_resolution = _project_checkpoint_resolution(state.repo_root)
        if checkpoint_resolution.get("adopted") and not isinstance(item.get("checkpoint_generation"), int):
            raise GitSafeError("the retired integration record lacks adopted checkpoint proof")
        if item.get("completion") and checkpoint_resolution.get("adopted") and "checkpoint_final_generation" not in item["completion"]:
            raise GitSafeError("retired completion still needs final handoff reconciliation", data={"completion_phase": item["completion"]["phase"], "resume_task": branch})
        disposition = _completion_disposition(state, item["completion"], verify_remote=True) if item.get("completion") else None
        if disposition and disposition["state"] != "fully_retired":
            raise GitSafeError("retired completion has unresolved owned residue", data={"disposition": disposition})
        selected_integration = _is_integration_task(state.repo_root, item.get("task_class"))
        return {
            "command": "yeet",
            "schema_version": STATE_SCHEMA_VERSION,
            "ok": True,
            "state": "complete",
            "idempotent": True,
            **({"disposition": disposition, "effective_completion": "integrate"} if disposition else {}),
            "transaction": "selected_integration" if selected_integration else "ordinary_integration",
            "integration" if selected_integration else "completion": item,
            "remote_proofs": remote_proofs,
            "cleanup": {"verified": True, "active_registration": False, "local_branch": False,
                        "temporary_artifacts": temporary_status},
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
    temporary_status = _task_temp_status(state, _managed_change_from_payload(item))
    if temporary_status["pending_count"]:
        raise GitSafeError(
            "the submitted task still has task-owned temporary residue",
            data={"temporary_artifacts": temporary_status},
        )
    checkpoint_resolution = (_project_checkpoint_resolution(state.repo_root)
                             if item.get("checkpoint_mode") != "task_record" else {})
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
        "cleanup": {"verified": True, "active_registration": False, "local_branch": False,
                    "temporary_artifacts": temporary_status},
    }


def _save_completion(state: RepoState, owner: ManagedChange, receipt: dict[str, Any]) -> ManagedChange:
    _validate_completion(receipt)
    _set_active_change(state, branch=owner.branch, authoritative_branch=owner.authoritative_branch,
        lifecycle=owner.lifecycle, checkout_path=Path(owner.checkout_path), mode=owner.mode,
        publication_mode="finish", completion=receipt)
    return _managed_active_change(state, _authority_assessment(state)) or owner


def _completion_selection(state: RepoState, selectors: list[str], *, include_integrated: bool = False) -> list[dict[str, Any]]:
    managed = _load_managed_state(state.common_dir)
    records = managed.get("submitted_changes", [])
    selected: list[dict[str, Any]] = []
    for selector in dict.fromkeys(selectors):
        matches = [item for item in records if selector in (item.get("queue_id"), item.get("review_ref"), item.get("review_url"))]
        if not matches and include_integrated:
            matches = [item for item in managed.get("integrated_changes", [])
                       if selector in (item.get("queue_id"), item.get("review_ref"), item.get("review_url"))]
        if len(matches) != 1:
            raise GitSafeError("completion requires one exact queued review per selection", blockers=[f"ambiguous or missing selected review: {selector}"])
        record = matches[0]
        if any(item["review_ref"] == record["review_ref"] for item in selected):
            continue
        selected.append({**{key: record[key] for key in ("review_ref", "review_remote", "review_url", "published_tip", "queue_id")}, "disposal_owned": record.get("disposal_owned") is True})
    return selected


def _completion_disposition(state: RepoState, receipt: dict[str, Any], *, verify_remote: bool = False) -> dict[str, Any]:
    """Selected ownership only; repository query success says nothing about finalness."""
    managed = _load_managed_state(state.common_dir)
    local: list[dict[str, Any]] = []
    scratch_paths = {_checkout_identity(Path(path)) for path in load_registry().get("entries", {})}
    index_paths = {_checkout_identity(path) for path in _index_registry_projects()}
    for prefix in _completion_roles(receipt):
        checkout, branch = receipt[f"{prefix}_checkout"], receipt[f"{prefix}_branch"]
        task_records = [
            item for item in [*managed.get("active_changes", []), *managed.get("retired_changes", [])]
            if item.get("branch") == branch and _payload_checkout_identity(item) == _checkout_identity(Path(checkout))
        ]
        temporary_status = (
            _task_temp_status(state, _managed_change_from_payload(task_records[0]))
            if len(task_records) == 1 and _managed_change_from_payload(task_records[0]) is not None
            else {"artifacts": [], "pending_count": 0, "deleted_count": 0}
        )
        registered = any(_payload_checkout_identity(item) == _checkout_identity(Path(checkout)) for item in managed.get("active_changes", []))
        present = _run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=state.repo_root).returncode == 0
        native_metadata = any(_checkout_identity(entry.path) == _checkout_identity(Path(checkout)) or entry.branch == branch for entry in state.worktrees)
        remaining = [label for label, retained in (("active_registration", registered), ("local_branch", present),
            ("native_worktree_metadata", native_metadata), ("checkout_path", Path(checkout).exists()),
            ("scratch_registration", _checkout_identity(Path(checkout)) in scratch_paths),
            ("index_registration", _checkout_identity(Path(checkout)) in index_paths),
            ("temporary_artifacts", temporary_status["pending_count"] > 0)) if retained]
        local.append({"checkout": checkout, "branch": branch, "retired": not remaining, "remaining": remaining,
                      "temporary_artifacts": temporary_status})
    remote = []
    for item in receipt.get("disposal", []):
        observation = dict(item)
        if verify_remote and item.get("state") == "deleted":
            review_remote, branch = item["review_ref"].split("/", 1)
            proc = _run(["git", "ls-remote", "--heads", review_remote, f"refs/heads/{branch}"], cwd=state.repo_root)
            if proc.returncode or proc.stdout.strip():
                observation["state"] = "unresolved"
        remote.append(observation)
    terminal = (receipt["phase"] == "complete" and all(item["retired"] for item in local)
                and len(remote) == len(receipt["selections"]) and all(item["state"] == "deleted" for item in remote))
    return {"scope": "selected_transaction", "state": "fully_retired" if terminal else "retained",
            "local": local, "remote": remote, "other_owners": "excluded",
            "phase": receipt["phase"], "purpose": receipt.get("hold", "selected work integration and retirement"),
            "handoff": "complete" if "checkpoint_final_generation" in receipt else "pending" if "checkpoint_pending_expected" in receipt else "not_recorded"}


def _completion_submission_duplicates(
    managed: dict[str, Any], selection: dict[str, Any],
) -> list[dict[str, Any]]:
    """Recognize queue aliases without replacing the receipt's integrated identity."""
    identity = ("review_ref", "published_tip", "review_url")
    records = [item for item in managed.get("integrated_changes", [])
               if all(item.get(key) == selection[key] for key in ("queue_id", *identity))]
    if len(records) != 1:
        raise GitSafeError("completion disposal lacks one exact integrated queue receipt")
    duplicates = []
    for item in managed.get("submitted_changes", []):
        if item.get("review_ref") != selection["review_ref"]:
            continue
        if (not all(item.get(key) == selection[key] for key in identity)
                or item.get("lifecycle") != "ready_for_integration"
                or item.get("dependencies") or not item.get("queue_id")):
            raise GitSafeError("completion review ref remains queued with conflicting metadata")
        duplicates.append(item)
    selectors = {selection[key] for key in ("queue_id", "review_ref", "review_url")}
    selectors.update(item["queue_id"] for item in duplicates)
    if any(selectors.intersection(item.get("dependencies", []))
           for item in managed.get("submitted_changes", [])):
        raise GitSafeError("completion review ref remains needed by a queued review")
    return duplicates


def _validate_completed_review_disposal(
    state: RepoState, receipt: dict[str, Any], selection: dict[str, Any],
) -> dict[str, Any]:
    """Run every read-only gate used before an exact selected-ref deletion."""
    remote, branch = selection["review_ref"].split("/", 1)
    if selection.get("disposal_owned") is not True or not branch.startswith("codex/"):
        raise GitSafeError("selected review has no managed disposable-topic ownership proof; retain its remote ref")
    expected = selection["published_tip"]
    authoritative_branch = _authority_assessment(state).default_branch
    if not authoritative_branch or not _is_ancestor(expected, receipt["integrated_tip"], cwd=state.repo_root):
        raise GitSafeError("selected review lacks integration containment proof")
    if any(target["remote"] == remote and target["branch"] == branch for target in _keeper_remote_targets(state, authoritative_branch)):
        raise GitSafeError("completion disposal refuses a keeper ref")
    managed = _load_managed_state(state.common_dir)
    duplicates = _completion_submission_duplicates(managed, selection)
    for item in managed.get("active_changes", []):
        if _payload_checkout_identity(item) in {_checkout_identity(Path(receipt[f"{role}_checkout"])) for role in _completion_roles(receipt)}:
            continue
        checkout = item.get("checkout_path")
        upstream = _repo_state(Path(checkout)).upstream if checkout and Path(checkout).is_dir() else None
        if (item.get("review_ref") == selection["review_ref"] or upstream == selection["review_ref"]
                or item.get("branch") == branch or selection["review_ref"] in item.get("selected_refs", [])):
            raise GitSafeError("completion review ref is retained by another active task")
    if any(item.get("branch") == branch or item.get("review_ref") == selection["review_ref"] for item in managed.get("parked_changes", [])):
        raise GitSafeError("completion review ref is retained by parked work")
    prior = next((item for item in receipt.get("disposal", []) if item.get("review_ref") == selection["review_ref"]), None)
    proc = _run(["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"], cwd=state.repo_root)
    if proc.returncode:
        raise GitSafeError("could not inspect the selected remote review ref")
    live = proc.stdout.split()[0] if proc.stdout.strip() else ""
    if not live and prior and prior.get("expected_tip") == expected and prior.get("state") in ("deleting", "deleted"):
        return {"review_ref": selection["review_ref"], "expected_tip": expected, "state": "deleted",
                "remote": remote, "branch": branch, "provider_proof": None, "queue_duplicates": duplicates}
    if live != expected:
        raise GitSafeError("selected remote review ref changed before disposal", blockers=[selection["review_ref"]])
    remote_url = _git_output(["remote", "get-url", remote], cwd=state.repo_root)
    if not _gitea_review_urls_match_remote(remote_url, [selection["review_url"]]):
        raise GitSafeError("selected hosted review needs provider closure proof before disposal")
    probe = _delegate_helper_process(PR_FINALIZE_HELPER_ENV, "codex-gitea-pr-finalize.sh",
        ["--remote", remote, "--commit", receipt["integrated_tip"], "--json", "--dry-run",
         "--pr-url", selection["review_url"], "--pr-head", expected, "--disposal-branch", branch], capture_output=True, cwd=state.repo_root)
    try:
        proof = json.loads(probe.stdout) if probe.returncode == 0 else {}
    except json.JSONDecodeError:
        proof = {}
    number = selection["review_url"].rstrip("/").split("/")[-1]
    if (not isinstance(proof, dict) or proof.get("pull_requests") != [f"{number}:already-closed"]
            or proof.get("disposal_proof") != {"branch": branch, "open_review_references": "none", "complete": True}):
        raise GitSafeError("selected hosted review is not proved closed at the integrated tip")
    return {"review_ref": selection["review_ref"], "expected_tip": expected, "state": "ready",
            "remote": remote, "branch": branch, "provider_proof": proof, "queue_duplicates": duplicates}


def _dispose_completed_review(state: RepoState, receipt: dict[str, Any], selection: dict[str, Any]) -> dict[str, str]:
    """Delete one closed, integrated, selected managed ref with an exact lease."""
    # Hold shared metadata stable through every gate and the queue-only update.
    # Never route through end: the active owner and completion journal must survive.
    with _integration_lock(state.common_dir):
        checks = _validate_completed_review_disposal(state, receipt, selection)
        duplicates = checks["queue_duplicates"]
        if duplicates:
            managed = _load_managed_state(state.common_dir)
            managed["submitted_changes"] = [item for item in managed["submitted_changes"]
                                            if item not in duplicates]
            _save_managed_state(state.common_dir, managed)
    if checks["state"] == "deleted":
        return {"review_ref": selection["review_ref"], "expected_tip": selection["published_tip"], "state": "deleted"}
    remote, branch, expected = checks["remote"], checks["branch"], checks["expected_tip"]
    # Persist the exact compare-and-delete before the remote effect. A retry may
    # accept absence only for this durable candidate, never from ancestry alone.
    candidate = {"review_ref": selection["review_ref"], "expected_tip": expected, "state": "deleting"}
    receipt["disposal"] = [item for item in receipt.get("disposal", []) if item["review_ref"] != selection["review_ref"]] + [candidate]
    owner_state = _repo_state(Path(receipt["owner_checkout"]))
    owner = _managed_active_change(owner_state, _authority_assessment(owner_state))
    if owner is None:
        raise GitSafeError("completion lost its owner before remote disposal")
    _save_completion(owner_state, owner, receipt)
    delete = _run(["git", "push", f"--force-with-lease=refs/heads/{branch}:{expected}", remote, f":refs/heads/{branch}"], cwd=state.repo_root)
    if delete.returncode:
        raise GitSafeError(delete.stderr.strip() or "selected remote compare-and-delete failed")
    _test_stop_after("review_ref_deleted")
    probe = _run(["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"], cwd=state.repo_root)
    if probe.returncode or probe.stdout.strip():
        raise GitSafeError("selected remote review deletion could not be verified")
    return {**candidate, "state": "deleted"}


def _completion_integration_class(repo_root: Path) -> str:
    classes = _integration_task_classes(repo_root)
    if "integration" in classes:
        return "integration"
    if len(classes) == 1:
        return next(iter(classes))
    raise GitSafeError("completion needs an unambiguous integration task class", blockers=["configure workflow.integration_task_classes to include integration or one unambiguous class"])


def _completion_child_proof(state: RepoState, receipt: dict[str, Any]) -> ManagedChange:
    child = _managed_active_change(state, _authority_assessment(state))
    if child is None or child.branch != receipt["child_branch"]:
        raise GitSafeError("completion child registration changed")
    _integration_yeet_preflight(state, child)
    if set(child.selected_refs) != {item["review_ref"] for item in receipt["selections"]}:
        raise GitSafeError("completion child contains unselected review metadata")
    allowed = [item["published_tip"] for item in receipt["selections"]]
    allowed.append(_ref_commit(child.authoritative_branch, cwd=state.repo_root))
    for commit in _git_output(["rev-list", "--first-parent", f"{child.start_tip}..HEAD"], cwd=state.repo_root).splitlines():
        parents = _git_output(["show", "-s", "--format=%P", commit], cwd=state.repo_root).split()
        if any(not any(_is_ancestor(parent, tip, cwd=state.repo_root) for tip in allowed) for parent in parents[1:]):
            raise GitSafeError("completion child merged an unselected source")
    return child


def _completion_checkpoint(state: RepoState, owner: ManagedChange, receipt: dict[str, Any],
    model_file: str | None, *, final: bool, expected_generation: int | None = None) -> dict[str, Any]:
    resolution = _project_checkpoint_resolution(state.repo_root)
    if not resolution.get("adopted"):
        return {"state": "not_adopted", "updated": False}
    key = "checkpoint_final_generation" if final else "checkpoint_pending_generation"
    if key in receipt:
        return {"state": "current", "updated": True, "generation": receipt[key], "idempotent": True}
    phase_key = "checkpoint_final_expected" if final else "checkpoint_pending_expected"
    transaction_branch = _completion_integration_branch(receipt)
    persisted_model = state.common_dir / "codex-git-safe" / f"{transaction_branch.split('/')[-1]}-checkpoint.json"
    if expected_generation is not None:
        if type(expected_generation) is not int or expected_generation < 1:
            raise GitSafeError("--checkpoint-generation must be a positive integer")
        if model_file is None:
            raise GitSafeError("checkpoint reconciliation requires a fresh model with --checkpoint-generation")
        receipt[phase_key] = expected_generation
    if phase_key not in receipt:
        if final:
            if "checkpoint_pending_generation" not in receipt:
                raise GitSafeError("final handoff lacks its pending generation")
            receipt[phase_key] = receipt["checkpoint_pending_generation"]
        else:
            receipt[phase_key] = resolution["generation"]
    expected = receipt[phase_key]
    if resolution.get("generation") != expected:
        raise GitSafeError("completion checkpoint generation needs reconciliation", blockers=[
            f"expected generation {expected}; observed {resolution.get('generation')}",
            "re-read the current handoff, reconcile a fresh model, and resume with --checkpoint-generation and --checkpoint-file"],
            data={"completion_phase": receipt["phase"], "resume_task": receipt["owner_branch"]})
    if not final or expected_generation is not None:
        path = _resolve_path(model_file, base=state.repo_root) if model_file else None
        if path is None or path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
            raise GitSafeError("completion handoff requires a bounded regular checkpoint model")
        raw = path.read_text(encoding="utf-8")
        try:
            model = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise GitSafeError("invalid completion checkpoint model") from exc
        if not isinstance(model, dict) or not all(isinstance(model.get(section), list) for section in ("in_flight", "just_learned", "references")):
            raise GitSafeError("completion checkpoint model must use the supported project checkpoint schema")
        persisted_model.write_text(raw, encoding="utf-8")
        receipt["checkpoint_model_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    else:
        raw = persisted_model.read_text(encoding="utf-8")
        if hashlib.sha256(raw.encode()).hexdigest() != receipt.get("checkpoint_model_sha256"):
            raise GitSafeError("durable completion checkpoint model changed")
        model = json.loads(raw)
    card_id = f"git-completion-{transaction_branch.split('/')[-1]}"
    pointer = f"{_managed_state_path(state.common_dir)}#{receipt['owner_branch']}"
    stamp = _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    model["in_flight"] = [row for row in model["in_flight"] if not isinstance(row, dict) or row.get("id") != card_id]
    model["just_learned"] = [row for row in model["just_learned"] if not isinstance(row, dict) or row.get("id") != card_id]
    if final:
        model["just_learned"].append({"id": card_id, "finding": f"fully_retired: selected work {receipt['owner_branch']} is integrated and its owned local and remote task state is retired",
            "evidence_status": "verified", "evidence_pointer": pointer, "impact": "selected outcome complete; other owners excluded",
            "last_confirmed_at": stamp, "expires_or_promote_by": (_utc_now() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    else:
        model["in_flight"].append({"id": card_id, "owner_binding": receipt["owner_branch"], "state": "retirement_pending",
            "task_subject": "selected work integrated; local and remote retirement and final handoff remain pending",
            "evidence_status": "integration verified; completion pending", "evidence_pointer": pointer,
            "last_confirmed_at": stamp, "clears_when": f"verify owned disposal and reconcile final handoff from {receipt['control_checkout']} using exact owner {receipt['owner_branch']}"})
    rendered_path = persisted_model.with_name(persisted_model.stem + "-write.json")
    rendered_path.write_text(json.dumps(model, separators=(",", ":")), encoding="utf-8")
    # Persist the CAS expectation before invoking the checkpoint writer. An
    # acknowledgement gap is a named reconciliation need, never latest-wins.
    _persist_completion_receipt(state, receipt)
    cleared = replace(owner, checkpoint_generation=None)
    removals = ()
    if final:
        current = _project_checkpoint_resolution(state.repo_root, include_model=True)
        if current.get("generation") != expected or not isinstance(current.get("model"), dict):
            raise GitSafeError("completion checkpoint generation needs reconciliation")
        pending = [row for row in current["model"]["in_flight"] if row["id"] == card_id]
        if pending:
            if (len(pending) != 1 or pending[0]["owner_binding"] != receipt["owner_branch"]
                    or pending[0]["evidence_pointer"] != pointer):
                raise GitSafeError("completion checkpoint pending card ownership changed")
            # Only this transaction's exact pending card is disposed. Any other
            # missing owner, blocker or boundary remains subject to CLI rejection.
            removals = (("in_flight", card_id, "selected transaction retirement verified; final handoff recorded"),)
    result = _update_yeet_checkpoint(state, cleared, {"branch": receipt["owner_branch"],
        "published_tip": receipt.get("integrated_tip", _ref_commit(owner.authoritative_branch, cwd=state.repo_root)),
        "review_ref": ",".join(item["review_ref"] for item in receipt["selections"])}, str(rendered_path), expected_generation=expected,
        removals=removals)
    _test_stop_after("completion_final_checkpoint_written" if final else "completion_pending_checkpoint_written")
    content = _run([_project_checkpoint_helper(), "show", "--repo", str(state.repo_root)], cwd=state.repo_root)
    if content.returncode or card_id not in content.stdout or ("fully_retired" if final else "retirement_pending") not in content.stdout:
        raise GitSafeError("completion handoff readback did not prove its disposition card")
    if final and f"| {card_id} | {receipt['owner_branch']} | retirement_pending |" in content.stdout:
        raise GitSafeError("final handoff still contains the selected pending card")
    receipt[key] = result["generation"]
    receipt["side_effect_ids"] = list(dict.fromkeys([*receipt["side_effect_ids"], f"project_checkpoint:{receipt['owner_branch']}:generation:{result['generation']}"]))
    _persist_completion_receipt(state, receipt)
    return result


def _persist_completion_receipt(state: RepoState, receipt: dict[str, Any]) -> None:
    with _integration_lock(state.common_dir):
        _validate_completion(receipt)
        managed = _load_managed_state(state.common_dir)
        found = False
        for key in ("active_changes", "retired_changes"):
            for item in managed.get(key, []):
                if item.get("branch") == receipt["owner_branch"] and _payload_checkout_identity(item) == _checkout_identity(Path(receipt["owner_checkout"])):
                    item["completion"] = receipt
                    found = True
        if not found:
            raise GitSafeError("completion receipt lost its exact original owner journal")
        legacy = managed.get("active_change")
        if legacy and legacy.get("branch") == receipt["owner_branch"]:
            legacy["completion"] = receipt
        _save_managed_state(state.common_dir, managed)


def _retire_completion_local(state: RepoState, change: ManagedChange, control: Path, expected_tip: str) -> dict[str, Any]:
    """Journal first, then retire or resume only this exact owned local checkout."""
    path = Path(change.checkout_path)
    authoritative = change.authoritative_branch
    if not authoritative or not change.integrated_tip or not change.branch or not change.branch.startswith("codex/"):
        raise GitSafeError("completion local retirement lacks exact managed ownership and keeper metadata")
    current_keeper = _ref_commit(authoritative, cwd=control)
    if not _is_ancestor(change.integrated_tip, current_keeper, cwd=control):
        raise GitSafeError("completion integration is no longer preserved by the keeper")
    targets = _keeper_remote_targets(state, authoritative)
    if not targets:
        raise GitSafeError("completion local retirement has no keeper remote")
    for target in targets:
        proc = _run(["git", "ls-remote", "--heads", target["remote"], f"refs/heads/{target['branch']}"], cwd=control)
        tip = proc.stdout.split()[0] if proc.returncode == 0 and proc.stdout.strip() else ""
        if tip != current_keeper:
            raise GitSafeError("completion local retirement requires current exact keeper proof")
    branch_present = _run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{change.branch}"], cwd=control).returncode == 0
    if branch_present and _ref_commit(change.branch, cwd=control) != expected_tip:
        raise GitSafeError("completion local branch changed before retirement")
    _record_retired_change(state, change, pending=True)
    native = _worktree_entry_for_path(state, path)
    if path.exists():
        if not branch_present or native is None:
            raise GitSafeError("completion checkout exists without its exact branch/worktree identity")
        _require_yeet_closeout(_repo_state(path), change)
        cleanup = _retire_integrated_change(state, change, authoritative, control)
    else:
        if native is not None or _branch_checked_out_elsewhere(state, change.branch):
            raise GitSafeError("completion retains native worktree metadata; inspect the exact owned entry")
        temporary_cleanup = _retire_owned_temporary_artifacts(state, change)
        cleanup = {"actions": list(temporary_cleanup["actions"]), "temporary_artifacts": temporary_cleanup}
        if branch_present:
            delete = _run(["git", "update-ref", "-d", f"refs/heads/{change.branch}", expected_tip], cwd=control)
            if delete.returncode:
                raise GitSafeError("completion local branch compare-and-delete failed")
            cleanup["actions"].append(f"deleted exact owned branch {change.branch}")
        if is_scratch_path(path):
            with _integration_lock(state.common_dir):
                cleanup["actions"].extend(_remove_index_registry_paths({path}))
                _remove_registry_paths({path})
        _clear_active_change(state, checkout_path=path)
        _record_retired_change(state, change)
    return cleanup


def _completion_provider_preflight(state: RepoState, records: list[dict[str, Any]]) -> None:
    for item in records:
        remote = item["review_remote"]
        remote_url = _git_output(["remote", "get-url", remote], cwd=state.repo_root)
        probe_url = item.get("review_url") or remote_url.removesuffix(".git").rstrip("/") + "/pulls/1"
        if urlparse(remote_url).hostname in ("github.com", "www.github.com") or not _gitea_review_urls_match_remote(remote_url, [probe_url]):
            raise GitSafeError("full completion lacks a supported hosted closure and disposal provider", blockers=[
                "retain review-only scope and use the existing provider integration lane; no keeper advancement was attempted"],
                data={"review_remote": remote})


def _read_integration_validation(repo_root: Path, validation_file: str, head: str) -> str:
    path = _resolve_path(validation_file, base=repo_root)
    if path is None or path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise GitSafeError("integration validation must be a bounded regular JSON file")
    try:
        record = json.loads(path.read_text())
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GitSafeError("invalid integration validation JSON") from exc
    if (not isinstance(record, dict) or record.get("head") != head
            or not isinstance(record.get("summary"), str) or not re.match(r"(?i)^pass(?:ed)?(?:\s|:|-)", record["summary"])):
        raise GitSafeError("integration validation must prove PASS at the exact prepared HEAD")
    return record["summary"]


def _complete_pull_request_yeet(state: RepoState, owner: ManagedChange, *, pr_args: list[str],
    message: str | None, validation_summary: str, checkpoint_file: str | None,
    include_reviews: list[str], integration_validation_file: str | None, apply: bool, checkpoint_generation: int | None = None) -> dict[str, Any]:
    if not apply:
        return {"command": "yeet", "ok": True, "state": "plan", "transaction": "pull_request_completion",
                "authorization_consumed": False, "apply_required": True, "required_flag": "--apply",
                "actions": ["publish the selected task review", "prepare only explicitly selected reviews in one managed integration checkout",
                            "require validation bound to the prepared integration HEAD", "advance and prove keepers", "close selected reviews and retire owned state"]}
    _completion_integration_class(state.repo_root)
    _completion_provider_preflight(state, [{"review_remote": owner.review_remote or "origin", **({"review_url": owner.review_url} if owner.review_url else {})}])
    receipt = owner.completion
    if receipt is None:
        control = _authoritative_control_checkout(state, owner.authoritative_branch, exclude_path=state.repo_root)
        if control is None:
            raise GitSafeError("completion requires the existing authoritative checkout; no activation or bootstrap is inferred")
        identifier = hashlib.sha256(f"{owner.checkout_path}\0{owner.branch}\0{owner.created_at}".encode()).hexdigest()[:16]
        child_branch = f"codex/complete-{identifier}"
        child_checkout = _worktree_root_for_branch(control, child_branch)
        control_state = _repo_state(control)
        if Path(child_checkout).exists() or _run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{child_branch}"], cwd=control).returncode == 0:
            raise GitSafeError("deterministic completion child identity already exists without its owner receipt")
        receipt = {"version": 1, "mode": "integrate", "phase": "preparing", "owner_checkout": str(state.repo_root),
                   "owner_branch": owner.branch, "control_checkout": str(control), "child_checkout": str(child_checkout),
                   "child_branch": child_branch, "include_reviews": list(dict.fromkeys(include_reviews)), "selections": [], "side_effect_ids": []}
        owner = _save_completion(state, owner, receipt)
        _test_stop_after("completion_preparing")
    else:
        _validate_completion(receipt)
        if receipt["owner_checkout"] != str(state.repo_root) or receipt["owner_branch"] != owner.branch:
            raise GitSafeError("completion receipt does not match this registered owner")
        if include_reviews and list(dict.fromkeys(include_reviews)) != receipt["include_reviews"]:
            raise GitSafeError("completion selection cannot change after the transaction begins")
    final_checkpoint_override = checkpoint_generation if "checkpoint_pending_generation" in receipt else None
    if "hold" in receipt:
        receipt.pop("hold")
        owner = _save_completion(state, owner, receipt)
    identifier = hashlib.sha256(f"{owner.checkout_path}\0{owner.branch}\0{owner.created_at}".encode()).hexdigest()[:16]
    if receipt["child_branch"] != f"codex/complete-{identifier}" or Path(receipt["child_checkout"]) != _worktree_root_for_branch(Path(receipt["control_checkout"]), receipt["child_branch"]):
        raise GitSafeError("completion child does not match the deterministic owner identity")
    control = Path(receipt["control_checkout"])
    control_state = _repo_state(control)
    if control_state.common_dir != state.common_dir or control_state.branch != owner.authoritative_branch:
        raise GitSafeError("completion control checkout identity changed")
    child_path = Path(receipt["child_checkout"])
    if receipt["phase"] == "preparing":
        if owner.lifecycle == "working":
            state, owner, actions = _commit_ordinary_yeet(state, owner, message=message, validation_summary=validation_summary)
        submitted = _submit_payload_unlocked(state, pr_args=pr_args, apply=True, retire=False)
        state = _repo_state(state.repo_root)
        owner = _managed_active_change(state, _authority_assessment(state)) or owner
        receipt["selections"] = _completion_selection(state, [submitted["submission"]["queue_id"], *receipt["include_reviews"]])
        _completion_provider_preflight(state, receipt["selections"])
        receipt["phase"] = "published"
        receipt["side_effect_ids"] = [f"git_ref:{item['review_remote']}:{item['review_ref'].split('/', 1)[1]}:{item['published_tip']}" for item in receipt["selections"]]
        owner = _save_completion(state, owner, receipt)
        _test_stop_after("completion_published")
    # Publication is immutable after integration preparation begins.
    if state.dirty or _ref_commit("HEAD", cwd=state.repo_root) != owner.published_tip:
        raise GitSafeError("completion owner changed after publication; retain and reconcile the selected transaction", data={"head": _ref_commit("HEAD", cwd=state.repo_root), "published_tip": owner.published_tip, "dirty": state.dirty, "dirty_paths": _status_lines(state.repo_root)})
    if receipt["phase"] in ("published", "awaiting_validation", "validated"):
        _completion_provider_preflight(state, receipt["selections"])
        if any(item.get("disposal_owned") is not True for item in receipt["selections"]):
            raise GitSafeError("full completion lacks disposable managed-topic ownership for a selected review", blockers=["retain the selected review refs and establish their ownership before authoritative integration"])
    if receipt["phase"] == "published":
        if not child_path.exists():
            with _integration_lock(state.common_dir):
                result = _start_payload_unlocked(_repo_state(control), topic=receipt["child_branch"], base=owner.authoritative_branch,
                    from_current=False, mode="worktree", worktree_root=None, worktree_path=str(child_path), dry_run=False,
                    task_class=_completion_integration_class(control))
            if result.get("blockers"):
                raise GitSafeError("completion integration checkout could not start", blockers=result["blockers"])
        child_state = _repo_state(child_path)
        child = _managed_active_change(child_state, _authority_assessment(child_state))
        if child is None or child.branch != receipt["child_branch"] or child_state.common_dir != state.common_dir:
            raise GitSafeError("completion child registration does not match its durable identity")
        # Re-resolve selected queue identities and compare immutable tips on every retry.
        current = _completion_selection(state, [item["queue_id"] for item in receipt["selections"]])
        if current != receipt["selections"]:
            raise GitSafeError("a selected completion review changed after publication")
        # A known queued ancestor is a dependency even when older intake did
        # not write a depends-on field. Never fold it into a new review silently.
        for pending in _load_managed_state(state.common_dir).get("submitted_changes", []):
            tip = pending.get("published_tip")
            if (pending.get("review_ref") not in {item["review_ref"] for item in receipt["selections"]}
                    and isinstance(tip, str) and not _is_ancestor(tip, _ref_commit("HEAD", cwd=child_path), cwd=state.repo_root)
                    and any(_is_ancestor(tip, item["published_tip"], cwd=state.repo_root) for item in receipt["selections"])):
                raise GitSafeError("completion has an unselected queued dependency", blockers=[str(pending.get("review_ref"))])
        integrated = _integrate_payload_unlocked(child_state, source_refs=[item["queue_id"] for item in receipt["selections"]], apply=True)
        receipt["side_effect_ids"].extend(integrated.get("side_effect_ids", []))
        receipt["integration_head"] = _ref_commit("HEAD", cwd=child_path)
        receipt["phase"] = "awaiting_validation"
        owner = _save_completion(state, owner, receipt)
        _test_stop_after("completion_awaiting_validation")
    if receipt["phase"] in ("awaiting_validation", "validated"):
        child_state = _repo_state(child_path)
        _completion_child_proof(child_state, receipt)
        if _ref_commit("HEAD", cwd=child_path) != receipt["integration_head"]:
            receipt["integration_head"] = _ref_commit("HEAD", cwd=child_path)
            receipt["phase"] = "awaiting_validation"
            receipt.pop("validation_summary", None)
            owner = _save_completion(state, owner, receipt)
    if receipt["phase"] == "awaiting_validation":
        child_state = _repo_state(child_path)
        if not integration_validation_file:
            return {"command": "yeet", "ok": False, "state": "integration_validation_required", "transaction": "pull_request_completion",
                    "blockers": ["validate the exact prepared integration HEAD, then resume this same yeet"],
                    "validation_target": {"checkout": str(child_path), "head": receipt["integration_head"], "file_fields": ["head", "summary"]},
                    "side_effect_ids": receipt["side_effect_ids"], "disposition": _completion_disposition(state, receipt)}
        receipt["validation_summary"] = _read_integration_validation(state.repo_root, integration_validation_file, _ref_commit("HEAD", cwd=child_path))
        receipt["phase"] = "validated"
        owner = _save_completion(state, owner, receipt)
    if receipt["phase"] in ("validated", "integrating"):
        retired = [item for item in _load_managed_state(state.common_dir).get("retired_changes", [])
                   if item.get("branch") == receipt["child_branch"] and item.get("checkout_path") == str(child_path)]
        if retired and not child_path.exists():
            child_record = retired[0]
            retired_child = _managed_change_from_payload(child_record)
            _retire_completion_local(_repo_state(control), retired_child, control, child_record["integrated_tip"])
            result = _yeet_submitted_result(_repo_state(control), receipt["child_branch"])
        else:
            child_state = _repo_state(child_path)
            child = _managed_active_change(child_state, _authority_assessment(child_state))
            if child is None or child.branch != receipt["child_branch"] or _ref_commit("HEAD", cwd=child_path) != receipt["integration_head"]:
                raise GitSafeError("validated completion child identity or HEAD changed")
            _completion_child_proof(child_state, receipt)
            _require_yeet_closeout(child_state, child)
            if child.phase not in ("integrated_local", "pushed_verified", "checkpoint_updated"):
                current = _completion_selection(state, [item["queue_id"] for item in receipt["selections"]])
                if current != receipt["selections"]:
                    raise GitSafeError("selected review identity changed after integration validation")
                _integrate_payload_unlocked(child_state, source_refs=[item["queue_id"] for item in receipt["selections"]], apply=False)
                for pending in _load_managed_state(state.common_dir).get("submitted_changes", []):
                    tip = pending.get("published_tip")
                    if (pending.get("review_ref") not in {item["review_ref"] for item in receipt["selections"]}
                            and isinstance(tip, str) and not _is_ancestor(tip, owner.authoritative_branch, cwd=state.repo_root)
                            and any(_is_ancestor(tip, item["published_tip"], cwd=state.repo_root) for item in receipt["selections"])):
                        raise GitSafeError("completion has an unselected queued dependency", blockers=[str(pending.get("review_ref"))])
            receipt["phase"] = "integrating"
            owner = _save_completion(state, owner, receipt)
            if child.phase not in ("integrated_local", "pushed_verified", "checkpoint_updated"):
                _finish_payload_unlocked(child_state, apply=True, run_semantic_checks=False, validation_summary=receipt["validation_summary"])
                child_state = _repo_state(child_path)
                child = _managed_active_change(child_state, _authority_assessment(child_state)) or child
            result = _finalize_integration_yeet_unlocked(child_state, child, checkpoint_file=checkpoint_file, completion_owner=owner, checkpoint_generation=checkpoint_generation)
            child_record = next(item for item in _load_managed_state(state.common_dir)["retired_changes"] if item.get("branch") == receipt["child_branch"])
        receipt = next(item["completion"] for item in _load_managed_state(state.common_dir)["active_changes"] if item.get("branch") == receipt["owner_branch"])
        receipt["integrated_tip"] = child_record["integrated_tip"]
        if isinstance(child_record.get("checkpoint_generation"), int):
            receipt["checkpoint_generation"] = child_record["checkpoint_generation"]
        receipt["side_effect_ids"].extend(result.get("side_effect_ids", []))
        receipt["phase"] = "child_retired"
        owner = _save_completion(state, owner, receipt)
        _test_stop_after("completion_child_retired")
    if receipt["phase"] == "child_retired":
        for selection in receipt["selections"]:
            disposed = _dispose_completed_review(_repo_state(control), receipt, selection)
            receipt["disposal"] = [item for item in receipt.get("disposal", []) if item["review_ref"] != selection["review_ref"]] + [disposed]
            receipt["side_effect_ids"] = list(dict.fromkeys([*receipt["side_effect_ids"], f"git_ref_deleted:{disposed['review_ref']}:{disposed['expected_tip']}"]))
            owner = _save_completion(state, owner, receipt)
        receipt["phase"] = "complete"
        _set_active_change(state, branch=owner.branch, authoritative_branch=owner.authoritative_branch,
            lifecycle=owner.lifecycle, checkout_path=state.repo_root, mode=owner.mode, completion=receipt,
            integrated_tip=receipt["integrated_tip"], checkpoint_generation=receipt.get("checkpoint_generation"))
        owner = _managed_active_change(state, _authority_assessment(state)) or owner
    # The receipt survives the local cleanup boundary in the retirement journal.
    # It describes intended disposal; terminal proof below still inspects reality.
    cleanup = _retire_completion_local(_repo_state(control), owner, control, owner.published_tip)
    disposition = _completion_disposition(_repo_state(control), receipt, verify_remote=True)
    if disposition["state"] != "fully_retired":
        raise GitSafeError("selected completion still has unresolved owned residue", data={"disposition": disposition})
    final_checkpoint = _completion_checkpoint(_repo_state(control), owner, receipt, checkpoint_file, final=True, expected_generation=final_checkpoint_override)
    disposition = _completion_disposition(_repo_state(control), receipt, verify_remote=True)
    if final_checkpoint.get("updated") and disposition["handoff"] != "complete":
        raise GitSafeError("completion final response lacks its verified handoff", data={"disposition": disposition})
    return {"command": "yeet", "ok": True, "state": "complete", "transaction": "pull_request_completion", "effective_completion": "integrate",
            "disposition": disposition, "cleanup": cleanup, "side_effect_ids": receipt["side_effect_ids"],
            "transaction_record": _terminal_transaction_record(receipt), "checkpoint": final_checkpoint,
            "actions": ["integrated and closed only selected reviews", "verified retirement of the selected local and remote task state"]}


def _complete_standalone_integration_yeet(
    state: RepoState, owner: ManagedChange, *, validation_summary: str,
    checkpoint_file: str | None, checkpoint_generation: int | None,
    integration_validation_file: str | None,
    selections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Use the existing completion journal and guards for a later integration task."""
    prepared_head = _ref_commit("HEAD", cwd=state.repo_root)
    receipt = owner.completion
    if receipt is None:
        control = _authoritative_control_checkout(state, owner.authoritative_branch, exclude_path=state.repo_root)
        if control is None:
            raise GitSafeError("standalone integration requires a persistent authoritative checkout")
        receipt = {
            "version": 2, "kind": "standalone_integration", "mode": "integrate", "phase": "integrating",
            "owner_checkout": str(state.repo_root), "owner_branch": owner.branch, "control_checkout": str(control),
            "selections": selections if selections is not None else _completion_selection(state, list(owner.selected_refs), include_integrated=True),
            "integration_head": prepared_head, "validation_summary": validation_summary, "side_effect_ids": [],
        }
        owner = _save_completion(state, owner, receipt)
        _test_stop_after("standalone_integration_recorded")
    _validate_completion(receipt)
    if (receipt.get("version") != 2 or receipt["owner_checkout"] != str(state.repo_root)
            or receipt["owner_branch"] != owner.branch or state.branch != owner.branch
            or set(owner.selected_refs) != {item["review_ref"] for item in receipt["selections"]}
            or state.dirty):
        raise GitSafeError("standalone integration owner or prepared HEAD changed; retain its receipt")
    control = Path(receipt["control_checkout"])
    control_state = _repo_state(control)
    if control_state.common_dir != state.common_dir or control_state.branch != owner.authoritative_branch:
        raise GitSafeError("standalone integration control checkout identity changed")
    if prepared_head != receipt["integration_head"]:
        authoritative_head = _ref_commit(owner.authoritative_branch, cwd=state.repo_root)
        # Phase alone cannot exclude a keeper update whose acknowledgement was
        # lost. Once the old prepared tree reached authority, its identity is final.
        if (receipt["phase"] != "integrating" or receipt.get("integrated_tip") or owner.integrated_tip
                or owner.phase in ("integrated_local", "pushed_verified", "checkpoint_updated")
                or _is_ancestor(receipt["integration_head"], authoritative_head, cwd=state.repo_root)):
            raise GitSafeError("standalone integration cannot replay after authoritative advancement")
        if (owner.mode != "worktree" or owner.checkout_path != str(state.repo_root)
                or _git_operation_blockers(state.repo_root) or not owner.start_tip
                or any(not _is_ancestor(tip, prepared_head, cwd=state.repo_root)
                       for tip in (owner.start_tip, receipt["integration_head"], authoritative_head))):
            raise GitSafeError("standalone integration replay requires a clean descendant of its prepared HEAD and current authority")
        current = _completion_selection(state, [item["queue_id"] for item in receipt["selections"]], include_integrated=True)
        if current != receipt["selections"]:
            raise GitSafeError("selected standalone integration review identity changed before replay")
        for selected in receipt["selections"]:
            remote, branch = selected["review_ref"].split("/", 1)
            observed = _run(["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"], cwd=state.repo_root)
            tip = observed.stdout.split()[0] if observed.returncode == 0 and observed.stdout.strip() else ""
            if (tip != selected["published_tip"]
                    or not _is_ancestor(selected["published_tip"], prepared_head, cwd=state.repo_root)):
                raise GitSafeError("selected standalone integration review tip changed before replay")
        if not integration_validation_file:
            return {"command": "yeet", "ok": False, "state": "integration_validation_required", "transaction": "selected_integration",
                "blockers": ["validate the replayed integration HEAD, then resume this same yeet; its saved receipt remains unchanged"],
                "validation_target": {"checkout": str(state.repo_root), "head": prepared_head, "file_fields": ["head", "summary"]},
                "side_effect_ids": receipt["side_effect_ids"], "disposition": _completion_disposition(state, receipt)}
        replay_summary = _read_integration_validation(state.repo_root, integration_validation_file, prepared_head)
        receipt["replay_history"] = [*receipt.get("replay_history", []), {
            "previous_head": receipt["integration_head"], "previous_validation_summary": receipt["validation_summary"],
            "head": prepared_head, "authoritative_head": authoritative_head, "validation_summary": replay_summary}]
        receipt["integration_head"] = prepared_head
        receipt["validation_summary"] = replay_summary
        owner = _save_completion(state, owner, receipt)
    final_checkpoint_override = checkpoint_generation if "checkpoint_pending_generation" in receipt else None
    if receipt["phase"] == "integrating":
        # A retry may resume after queue reconciliation or an acknowledgement gap.
        # Identity and containment, including already-contained reviews, remain exact.
        for selected in receipt["selections"]:
            if not _is_ancestor(selected["published_tip"], receipt["integration_head"], cwd=state.repo_root):
                raise GitSafeError("standalone selection is absent from the prepared integration HEAD")
        if owner.phase not in ("integrated_local", "pushed_verified", "checkpoint_updated"):
            _finish_payload_unlocked(state, apply=True, run_semantic_checks=False, validation_summary=receipt["validation_summary"])
            state = _repo_state(state.repo_root)
            owner = _managed_active_change(state, _authority_assessment(state)) or owner
        result = _finalize_integration_yeet_unlocked(
            state, owner, checkpoint_file=checkpoint_file, completion_owner=owner,
            checkpoint_generation=checkpoint_generation, retire_local=False,
        )
        state = _repo_state(state.repo_root)
        owner = _managed_active_change(state, _authority_assessment(state)) or owner
        receipt = owner.completion or receipt
        receipt["integrated_tip"] = owner.integrated_tip
        receipt["side_effect_ids"] = list(dict.fromkeys([*receipt["side_effect_ids"], *result.get("side_effect_ids", []),
            f"git_integration:{owner.branch}:{owner.integrated_tip}"]))
        receipt["phase"] = "disposing"
        owner = _save_completion(state, owner, receipt)
        _test_stop_after("standalone_integration_disposal_pending")
    if receipt["phase"] == "disposing":
        for selection in receipt["selections"]:
            if selection.get("disposal_owned") is not True:
                raise GitSafeError("selected integration retains a remote ref whose disposal ownership is unproven",
                    data={"disposition": {"state": "retained_ownership_unproven", "review_ref": selection["review_ref"],
                        "integration": "verified", "completion": "incomplete"}})
            disposed = _dispose_completed_review(_repo_state(control), receipt, selection)
            receipt["disposal"] = [item for item in receipt.get("disposal", []) if item["review_ref"] != selection["review_ref"]] + [disposed]
            receipt["side_effect_ids"] = list(dict.fromkeys([*receipt["side_effect_ids"], f"git_ref_deleted:{disposed['review_ref']}:{disposed['expected_tip']}"]))
            owner = _save_completion(state, owner, receipt)
        receipt["phase"] = "complete"
        owner = _save_completion(state, owner, receipt)
    cleanup = _retire_completion_local(_repo_state(control), owner, control, receipt["integration_head"])
    disposition = _completion_disposition(_repo_state(control), receipt, verify_remote=True)
    if disposition["state"] != "fully_retired":
        raise GitSafeError("standalone integration retains unresolved owned residue", data={"disposition": disposition})
    final_checkpoint = _completion_checkpoint(_repo_state(control), owner, receipt, checkpoint_file, final=True,
        expected_generation=final_checkpoint_override)
    disposition = _completion_disposition(_repo_state(control), receipt, verify_remote=True)
    if final_checkpoint.get("updated") and disposition["handoff"] != "complete":
        raise GitSafeError("standalone integration lacks its final handoff", data={"disposition": disposition})
    return {"command": "yeet", "schema_version": STATE_SCHEMA_VERSION, "ok": True, "state": "complete",
        "transaction": "selected_integration", "effective_completion": "integrate", "disposition": disposition,
        "cleanup": cleanup, "side_effect_ids": receipt["side_effect_ids"],
        "transaction_record": _terminal_transaction_record(receipt), "checkpoint": final_checkpoint,
        "validation_summary": receipt["validation_summary"],
        "remote_proofs": _yeet_submitted_result(_repo_state(control), owner.branch)["remote_proofs"],
        "actions": ["integrated and closed only selected reviews", "verified selected local and remote retirement and final handoff"]}


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
    review_only: bool = False,
    publish_only: bool = False,
    integrate: bool = False,
    include_reviews: list[str] | None = None,
    integration_validation_file: str | None = None,
    checkpoint_generation: int | None = None,
) -> dict[str, Any]:
    if publish_only and (review_only or integrate or include_reviews or integration_validation_file
                         or task_selector or checkpoint_file or checkpoint_generation is not None):
        raise GitSafeError("--publish-only retains an ordinary task; it cannot select integration, retirement, or a shared checkpoint")
    if task_selector and (integrate or include_reviews or integration_validation_file):
        raise GitSafeError("retired-task proof cannot select a new integration",
            blockers=["start an integration-class task and select the exact queued review with integrate --source-ref; then validate and yeet that task"],
            data={"resume_task": task_selector})
    assessment = _authority_assessment(state)
    active_change = _managed_active_change(state, assessment)
    if active_change is None:
        if task_selector:
            if apply:
                _resume_submitted_local(state, task_selector)
                records = [item for item in _load_managed_state(state.common_dir).get("retired_changes", [])
                           if item.get("branch") == task_selector and item.get("completion")]
                if len(records) == 1:
                    record = records[0]
                    receipt = record["completion"]
                    if receipt["phase"] != "complete" or str(state.repo_root) != receipt["control_checkout"]:
                        raise GitSafeError("--task resume requires the exact persistent control checkout and completed disposal receipt")
                    if any(item.get("state") != "deleted" for item in receipt.get("disposal", [])):
                        raise GitSafeError("--task local resume cannot perform remote disposal")
                    retired_owner = _managed_change_from_payload(record)
                    expected_local_tip = receipt["integration_head"] if receipt.get("version") == 2 else record["published_tip"]
                    _retire_completion_local(state, retired_owner, state.repo_root, expected_local_tip)
                    disposition = _completion_disposition(_repo_state(state.repo_root), receipt, verify_remote=True)
                    if disposition["state"] != "fully_retired":
                        raise GitSafeError("completion local resume retains unresolved disposal", data={"disposition": disposition})
                    _completion_checkpoint(_repo_state(state.repo_root), retired_owner, receipt, checkpoint_file, final=True, expected_generation=checkpoint_generation)
            return _yeet_submitted_result(_repo_state(state.repo_root), task_selector)
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
    if active_change.integrated_tip and not active_change.completion:
        # A started direct integration is a persisted transaction, not a new default decision.
        closeout_mode = "integrate"
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
    if review_only and integrate:
        raise GitSafeError("--integrate and --review-only are mutually exclusive")
    if publish_only and (closeout_mode != "pull_request" or active_change.completion
                         or _is_integration_task(state.repo_root, active_change.task_class)):
        raise GitSafeError("--publish-only requires an ordinary task without a terminal integration receipt")
    if (active_change.publication_mode == "continue" and not publish_only
            and active_change.phase != "published_open"):
        raise GitSafeError("resume interrupted publication with --publish-only before selecting terminal completion")
    effective_completion = ("review_only" if review_only or publish_only else "integrate" if integrate or active_change.completion
                            else _yeet_completion_mode(state.repo_root))
    if review_only and (closeout_mode == "integrate" or _is_integration_task(state.repo_root, active_change.task_class)):
        integrated = bool(active_change.integrated_tip and _is_ancestor(active_change.integrated_tip,
            _ref_commit(active_change.authoritative_branch, cwd=state.repo_root), cwd=state.repo_root))
        return {"command": "yeet", "ok": True, "state": "completion_held" if apply else "plan",
                "effective_completion": "review_only", "validation_summary": validation_summary,
                "integration": {"state": "integrated_locally" if integrated else "not_integrated",
                                "recorded_tip": active_change.integrated_tip},
                "disposition": {"scope": "selected_task", "state": "held", "local": "retained", "remote": "unchanged"},
                "actions": []}
    needs_checkpoint = (closeout_mode == "integrate" or _is_integration_task(state.repo_root, active_change.task_class)
                        or effective_completion == "integrate" or checkpoint_file is not None)
    ordinary_publication = (closeout_mode == "pull_request" and effective_completion == "review_only"
                            and not _is_integration_task(state.repo_root, active_change.task_class)
                            and not active_change.completion)
    if ordinary_publication and active_change.checkpoint_generation is not None and checkpoint_file is None:
        checkpoint_resolution = _project_checkpoint_resolution(state.repo_root)
    else:
        checkpoint_resolution = (_validate_yeet_checkpoint_input(state, checkpoint_file) if needs_checkpoint
                                 else {"state": "task_record", "adopted": False, "updated": False})
    if ordinary_publication:
        # Reject a stale authored snapshot before committing or publishing. The
        # writer checks the same generation again immediately before its CAS.
        _check_checkpoint_generation(checkpoint_resolution, active_change, checkpoint_generation)
    checkpoint_path = (
        str(_resolve_path(checkpoint_file, base=state.repo_root))
        if checkpoint_file is not None
        else None
    )
    if apply:
        _require_yeet_closeout(state, active_change)
    if _is_integration_task(state.repo_root, active_change.task_class):
        history_recovery = None
        if not active_change.completion:
            history_recovery = _recover_legacy_checkpoint_integration_history(state, active_change, apply=apply)
            if apply and history_recovery is not None:
                state = _repo_state(state.repo_root)
                active_change = _managed_active_change(state, _authority_assessment(state)) or active_change
                scope = _integration_yeet_preflight(state, active_change)
            elif history_recovery is not None:
                scope = history_recovery["scope"]
            else:
                scope = _integration_yeet_preflight(state, active_change)
        else:
            scope = {"start_tip": active_change.start_tip, "head": state.head, "selected_refs": list(active_change.selected_refs)}
        if history_recovery is not None:
            scope["history_recovery"] = history_recovery["recovery"]
        # Preserve explicit immutable selectors through standalone completion.
        # Plan and apply must reject the same missing, ambiguous or extra review.
        selectors = include_reviews or (
            [item["queue_id"] for item in active_change.completion["selections"]]
            if active_change.completion else list(active_change.selected_refs)
        )
        selections = _completion_selection(state, selectors, include_integrated=True)
        if {item["review_ref"] for item in selections} != set(active_change.selected_refs):
            raise GitSafeError("completion selectors must match the prepared integration reviews")
        if active_change.completion and selections != active_change.completion["selections"]:
            raise GitSafeError("completion selectors changed from the recorded integration")
        if not apply:
            return {
                "command": "yeet",
                "schema_version": STATE_SCHEMA_VERSION,
                "ok": True,
                "state": "plan",
                "authorization_consumed": False,
                "apply_required": True,
                "required_flag": "--apply",
                "next_action": "rerun the exact prior invocation with --apply",
                "task_class": active_change.task_class,
                "transaction": "selected_integration",
                "scope": scope,
                "actions": [
                    "fast-forward the authoritative line to the selected integration tip",
                    "push and verify each configured keeper remote",
                    "finalize only the selected hosted reviews",
                    "reconcile only the selected integration queue entries",
                    "refresh the adopted project checkpoint when configured",
                    "dispose only selected managed review refs with exact ownership and closure proof",
                    "retire the local integration worktree, branch, and registration",
                    "record the final generation-checked handoff",
                ],
                "checkpoint": {
                    "state": checkpoint_resolution.get("state"),
                    "adopted": bool(checkpoint_resolution.get("adopted")),
                },
            }
        result = _complete_standalone_integration_yeet(state, active_change, validation_summary=validation_summary,
            checkpoint_file=checkpoint_path, checkpoint_generation=checkpoint_generation,
            integration_validation_file=integration_validation_file, selections=selections)
        result["scope"] = scope
        return result
    if active_change.review_intent is None and not active_change.published_tip and state.upstream and state.upstream.split("/", 1)[-1] not in (active_change.branch, active_change.authoritative_branch):
        raise GitSafeError("legacy review intent is ambiguous", blockers=["bind --new-review or exact --continue-review through adopt-current before publication"])
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
                "authorization_consumed": False,
                "apply_required": True,
                "required_flag": "--apply",
                "next_action": "rerun the exact prior invocation with --apply",
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
    _validated_remote_destination(state.repo_root, active_change.review_remote or
        (active_change.review_ref.split("/", 1)[0] if active_change.review_ref else "origin"))
    pr_args: list[str] = ["--title", title or _default_yeet_subject(active_change.branch or "task")]
    if body_file:
        body_path = _resolve_path(body_file, base=state.repo_root)
        if body_path is None or not body_path.is_file() or body_path.is_symlink():
            raise GitSafeError("--body-file must name a regular file")
        pr_args.extend(["--body-file", str(body_path)])
    if update_existing:
        pr_args.append("--update-existing")
    if effective_completion == "review_only" and active_change.completion:
        receipt = dict(active_change.completion)
        if apply:
            receipt["hold"] = "explicit review-only hold"
            _save_completion(state, active_change, receipt)
        result = {"command": "yeet", "ok": True, "state": "completion_held" if apply else "plan",
                  "effective_completion": "review_only", "completion_phase": receipt["phase"],
                  "side_effect_ids": receipt["side_effect_ids"], "disposition": _completion_disposition(state, receipt)}
        if active_change.review_url and active_change.published_tip and receipt["phase"] not in ("integrating", "child_retired", "complete"):
            result["review_proof"] = _review_preservation_proof(state, active_change)
            result["state"] = "held_for_review" if apply else "plan"
        if receipt["phase"] == "preparing" and not active_change.review_url:
            result.update(ok=False, blockers=["publication is incomplete; the selected transaction is held before integration"])
        if receipt["phase"] in ("integrating", "child_retired", "complete"):
            keeper_tip = _ref_commit(active_change.authoritative_branch, cwd=state.repo_root)
            result["integration"] = {"state": "integrated_locally" if active_change.published_tip and _is_ancestor(active_change.published_tip, keeper_tip, cwd=state.repo_root) else "not_integrated", "keeper_head": keeper_tip}
            for item in _load_managed_state(state.common_dir).get("active_changes", []) + _load_managed_state(state.common_dir).get("retired_changes", []):
                if item.get("branch") == receipt["child_branch"] and item.get("integrated_tip"):
                    result["side_effect_ids"] = list(dict.fromkeys([*result["side_effect_ids"], f"git_integration:{item['branch']}:{item['integrated_tip']}"]))
        return result
    if effective_completion == "integrate":
        return _complete_pull_request_yeet(state, active_change, pr_args=pr_args, message=commit_message,
            validation_summary=validation_summary, checkpoint_file=checkpoint_path, include_reviews=include_reviews or [],
            integration_validation_file=integration_validation_file, apply=apply, checkpoint_generation=checkpoint_generation)
    if include_reviews or integration_validation_file:
        raise GitSafeError("review-only does not accept integration selections or validation")
    if not apply:
        return {
            "command": "yeet",
            "schema_version": STATE_SCHEMA_VERSION,
            "ok": True,
            "state": "plan",
            "authorization_consumed": False,
            "apply_required": True,
            "required_flag": "--apply",
            "next_action": "rerun the exact prior invocation with --apply",
            "task_class": active_change.task_class,
            "transaction": "ordinary_pull_request",
            "scope": scope,
            "actions": [
                "stage and commit the proven task delta if needed",
                "push the exact task tip",
                "create or confirm one ready pull request",
                "verify the live remote tip",
                "record the integration queue entry",
                *(["refresh the explicitly supplied shared checkpoint"] if checkpoint_file else []),
                "retain the registered task for review and corrections" if publish_only else "retire the local task worktree, branch, and registration",
            ],
            "publication_mode": "continue" if publish_only else "finish",
            "checkpoint": {
                "state": checkpoint_resolution.get("state"),
                "adopted": bool(checkpoint_resolution.get("adopted")),
            },
        }
    _set_active_change(state, branch=active_change.branch,
        authoritative_branch=active_change.authoritative_branch,
        lifecycle=active_change.lifecycle, checkout_path=Path(active_change.checkout_path),
        mode=active_change.mode, publication_mode="continue" if publish_only else "finish",
        validation_summary=validation_summary)
    actions = []
    # A retry at a published head needs proof, not another commit/push/API write.
    if (state.dirty or _ref_commit("HEAD", cwd=state.repo_root) != active_change.published_tip
            or active_change.lifecycle not in {"review_pending", "ready_for_integration"}):
        state, active_change, actions = _commit_ordinary_yeet(
            state, active_change, message=commit_message, validation_summary=validation_summary)
    else:
        active_change = _managed_active_change(state, _authority_assessment(state)) or active_change
    submitted = _submit_payload_unlocked(
        state,
        pr_args=pr_args,
        apply=True,
        checkpoint_file=checkpoint_path,
        update_checkpoint=checkpoint_file is not None or active_change.checkpoint_generation is not None,
        checkpoint_generation=checkpoint_generation,
        retire=not publish_only,
    )
    if publish_only:
        current = _managed_active_change(state, _authority_assessment(state))
        _set_active_change(state, branch=current.branch, authoritative_branch=current.authoritative_branch,
            lifecycle=current.lifecycle, checkout_path=Path(current.checkout_path), mode=current.mode,
            phase="published_open", publication_mode="continue")
    submitted["command"] = "yeet"
    submitted["transaction"] = "ordinary_pull_request"
    submitted["effective_completion"] = "review_only"
    submitted["publication_mode"] = "continue" if publish_only else "finish"
    submitted["review_acceptance"] = "not_recorded"
    if publish_only:
        submitted["state"] = "published_open"
        submitted["disposition"] = {"scope": "selected_task", "state": "published_open", "local": "active", "remote": "published"}
    else:
        submitted["disposition"] = {"scope": "selected_task", "state": "held_for_review" if review_only else "delivered_for_review", "local": "retired", "remote": "intentionally_retained"}
    submitted["validation_summary"] = validation_summary
    submitted["scope"] = scope
    submitted["actions"] = [*actions, *submitted.get("actions", [])]
    return submitted


def _yeet_payload(state: RepoState, **kwargs: Any) -> dict[str, Any]:
    apply = bool(kwargs.get("apply"))
    change = _managed_active_change(state, _authority_assessment(state))
    branch = kwargs.get("task_selector") or (change.branch if change else state.branch)
    lock_branch = _task_owner_branch(state, branch or str(state.repo_root))
    lock = _task_lock(state.common_dir, lock_branch) if apply else nullcontext()
    with lock:
        try:
            # A duplicate may have waited while the first owner retired its checkout.
            if not state.repo_root.exists() and branch:
                control = _repository_control_checkout(state, exclude_path=state.repo_root)
                if control is None:
                    raise GitSafeError("retired task has no persistent proof checkout")
                return _yeet_submitted_result(_repo_state(control), branch)
            refreshed = _repo_state(state.cwd)
            current = _managed_active_change(refreshed, _authority_assessment(refreshed))
            selected_receipt = any(
                item.get("branch") == kwargs.get("task_selector") and item.get("completion")
                and item["completion"].get("control_checkout") == str(refreshed.repo_root)
                for item in _load_managed_state(refreshed.common_dir).get("retired_changes", [])
            ) if kwargs.get("task_selector") else False
            integrating = selected_receipt or (kwargs.get("integrate") or (current and (current.completion or current.integrated_tip or
                _is_integration_task(refreshed.repo_root, current.task_class))) or
                _thread_closeout_mode(refreshed.repo_root) == "integrate" or
                _yeet_completion_mode(refreshed.repo_root) == "integrate") and not (kwargs.get("review_only") or kwargs.get("publish_only"))
            with _keeper_lock(state.common_dir) if apply and integrating else nullcontext():
                return _yeet_payload_unlocked(refreshed, **kwargs)
        except GitSafeError as exc:
            # Failed later phases must not erase publication/keeper/disposal
            # effects already committed by this same registered transaction.
            if apply:
                try:
                    managed = _load_managed_state(state.common_dir)
                    records = [item for item in [*managed.get("active_changes", []), *managed.get("retired_changes", [])]
                               if item.get("completion") and (
                                   _payload_checkout_identity(item) == _checkout_identity(state.repo_root)
                                   or (kwargs.get("task_selector") == item.get("branch") and item["completion"].get("control_checkout") == str(state.repo_root)))]
                    if records:
                        owner = records[0]
                        receipt = owner["completion"]
                        effects = list(receipt["side_effect_ids"])
                        effects.append(f"git_completion_receipt:{owner['branch']}:{receipt['phase']}")
                        if owner.get("published_tip") and owner.get("review_ref"):
                            effects.append(f"git_ref:{owner['review_ref']}:{owner['published_tip']}")
                        for child in [*managed.get("active_changes", []), *managed.get("retired_changes", [])]:
                            if child.get("branch") == _completion_integration_branch(receipt) and child.get("integrated_tip"):
                                effects.append(f"git_integration:{child['branch']}:{child['integrated_tip']}")
                        exc.data.update({"completion_phase": receipt["phase"], "resume_checkout": receipt["owner_checkout"] if Path(receipt["owner_checkout"]).exists() else receipt["control_checkout"], "resume_task": receipt["owner_branch"],
                                         "side_effect_ids": list(dict.fromkeys([*exc.data.get("side_effect_ids", []), *effects]))})
                        exc.result_status = "side_effect_completed_reconciliation_required"
                    else:
                        active_publication = next((item for item in managed.get("active_changes", [])
                            if item.get("branch") == branch and item.get("publication_mode") == "continue"
                            and item.get("checkout_identity") == _checkout_identity(state.repo_root)), None)
                        if active_publication:
                            exc.data.update(resume_checkout=str(state.repo_root), resume_publication_mode="continue",
                                publication_attempt=active_publication.get("publication_attempt"))
                        submitted = [item for item in managed.get("submitted_changes", [])
                                     if item.get("branch") == branch and item.get("checkout_identity") == _checkout_identity(state.repo_root)]
                        if len(submitted) == 1:
                            record = submitted[0]
                            control = _repository_control_checkout(state, exclude_path=state.repo_root)
                            exc.data.update({"resume_task": branch, "resume_checkout": str(state.repo_root) if active_publication else (str(control) if control else None),
                                "side_effect_ids": [f"git_submission:{record['queue_id']}", f"git_ref:{record['review_ref']}:{record['published_tip']}"]})
                            exc.result_status = "side_effect_completed_reconciliation_required"
                except (GitSafeError, OSError):
                    pass  # Preserve the original actionable failure if state cannot be read.
            raise


def _submit_payload_unlocked(
    state: RepoState,
    *,
    pr_args: list[str],
    apply: bool,
    checkpoint_file: str | None = None,
    update_checkpoint: bool = False,
    retire: bool = True,
    checkpoint_generation: int | None = None,
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
    ignored_delta = _ignored_output_delta(state.repo_root, active_change.ignored_output_baseline)
    if ignored_delta:
        raise GitSafeError("submit cannot discard declared task-relevant ignored outputs",
            blockers=[f"declared ignored task output {item['change']}: {item['path']}" for item in ignored_delta],
            data={"ignored_task_output_delta": ignored_delta})
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
        review_ref = active_change.review_ref if active_change.review_intent == "continue" or active_change.published_tip else None
        push_args: list[str] = []
        if active_change.review_intent is None and not active_change.published_tip:
            upstream = state.upstream
            if upstream and upstream.split("/", 1)[-1] not in (active_change.branch, active_change.authoritative_branch):
                raise GitSafeError("legacy review intent is ambiguous", blockers=["bind --new-review or exact --continue-review through adopt-current before publication"])
        expected = active_change.published_tip or (active_change.start_tip if review_ref else None)
        if not review_ref:
            review_ref = f"origin/{active_change.branch}"
        review_remote, review_branch = review_ref.split("/", 1)
        destination = _validated_remote_destination(state.repo_root, review_remote)
        destination_digest = hashlib.sha256(destination.encode()).hexdigest()
        prepared_tip = _ref_commit(active_change.branch, cwd=state.repo_root)
        attempt = active_change.publication_attempt
        retrying = bool(attempt and attempt.get("head") == prepared_tip
            and attempt.get("review_ref") == review_ref)
        if retrying and attempt.get("destination_sha256") != destination_digest:
            raise GitSafeError("publication destination changed from the recorded attempt")
        live = _run(["git", "ls-remote", "--heads", review_remote, f"refs/heads/{review_branch}"], cwd=state.repo_root)
        if live.returncode:
            raise GitSafeError("cannot prove the publication destination's current head")
        live_tip = live.stdout.split()[0] if live.stdout.strip() else None
        recovered_push = retrying and live_tip == prepared_tip
        if not recovered_push:
            if expected:
                _continuation_target(state, review_ref, expected)
            elif live_tip is not None:
                raise GitSafeError("new review destination already exists without this task's publication attempt")
            _set_active_change(state, branch=active_change.branch,
                authoritative_branch=active_change.authoritative_branch,
                lifecycle="working", checkout_path=Path(active_change.checkout_path), mode=active_change.mode,
                publication_attempt={"head": prepared_tip, "review_ref": review_ref,
                    "destination_sha256": destination_digest, "previous_tip": expected})
            push_args = ["--destination-branch", review_branch, review_remote, active_change.branch]
            push = _delegate_helper_process(PUSH_HELPER_ENV, "codex-gitea-push.sh", push_args, capture_output=True, cwd=state.repo_root)
            if push.returncode != 0:
                raise GitSafeError((push.stderr or push.stdout or "managed task push failed").strip())
            actions.append("pushed task branch through the managed helper")
            _test_stop_after("publication_pushed")
        else:
            # The remote effect can precede the local publication receipt. Repair
            # only its exact tracking ref from this observed immutable attempt.
            tracking = _run(["git", "rev-parse", "--verify", f"refs/remotes/{review_ref}"], cwd=state.repo_root)
            old_tracking = tracking.stdout.strip() if tracking.returncode == 0 else ""
            if old_tracking not in {"", prepared_tip, attempt.get("previous_tip")}:
                raise GitSafeError("publication tracking ref moved outside the recorded attempt")
            update = _run(["git", "update-ref", f"refs/remotes/{review_ref}", prepared_tip, old_tracking], cwd=state.repo_root)
            if update.returncode:
                raise GitSafeError("publication tracking ref changed during recovery")
            actions.append("reconciled the exact already-pushed publication attempt")
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
        pr = _delegate_helper_process(PR_HELPER_ENV, "codex-gitea-pr.sh", helper_args, capture_output=True, cwd=state.repo_root)
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
    if not retire:
        proof = _review_preservation_proof(state, active_change)
        submission = _record_submitted_change(state, active_change)
        return {"command": "submit", "ok": True, "state": "ready_for_integration",
                "review_proof": proof, "submission": submission, "actions": actions}
    proof, cleanup, submission, checkpoint = _retire_submitted_change(
        state,
        active_change,
        authoritative_branch,
        checkpoint_file=checkpoint_file,
        update_checkpoint=update_checkpoint,
        checkpoint_generation=checkpoint_generation,
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


def _terminal_transaction_record(receipt: dict[str, Any]) -> dict[str, Any]:
    """Expose the selected journal facts alongside, not instead of, observed proof."""
    fields = ("version", "kind", "mode", "phase", "owner_branch", "control_checkout",
              "integration_head", "integrated_tip", "validation_summary", "selections",
              "disposal", "checkpoint_generation")
    return {key: receipt[key] for key in fields if key in receipt}


def _brief_yeet_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Omit only the repository-wide inventory; retain every task/proof/error field."""
    return {key: value for key, value in payload.items() if key != "final_status"}


def _validate_review_task_intake(
    state: RepoState, *, task_class: str | None, new_review: bool,
    continue_review: str | None, adopting: bool = False,
) -> None:
    """Reject explicit source-delivery intent on an integration-only CLI intake."""
    if not new_review and not continue_review:
        return
    existing = _managed_active_change(state, _authority_assessment(state)) if adopting else None
    task_class = _normalize_task_class(task_class) if task_class is not None else (existing.task_class if existing else "ordinary")
    if existing is not None and task_class != existing.task_class:
        blockers = _provisional_task_class_promotion_blockers(state, existing, task_class)
        if blockers:
            # Adoption otherwise writes review intent before rejecting the class
            # change. Validate that same existing guard before either mutation.
            raise GitSafeError("review intake cannot change this existing task class", blockers=blockers)
    if _is_integration_task(state.repo_root, _normalize_task_class(task_class)):
        raise GitSafeError(
            "review-producing work cannot use an integration-only task class",
            blockers=["use the ordinary source task class for --new-review or --continue-review; "
                      "later --integrate completion does not change the task class; "
                      "integration-only tasks select existing reviews with integrate --source-ref"],
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = GitSafeArgumentParser(
        prog="codex-git-safe",
        description="Conservative local git helper for Codex change lifecycle.",
    )
    parser.add_argument("--repo", help="Run against this repository or checkout instead of the current directory.")
    parser.add_argument("--json", dest="global_json", action="store_true", help="Emit JSON when the selected command supports it.")
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=GitSafeArgumentParser,
        metavar="{status,preflight,start,adopt-current,integrate,review-ready,review-import,reconcile-integration-ownership,yeet,end,park,repair}",
    )

    status_parser = subparsers.add_parser("status", help="Show a repo change-lifecycle summary.")
    status_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    status_parser.add_argument(
        "--brief",
        action="store_true",
        help="Emit the compact task/state/blocker/keeper/residue JSON schema; requires --json.",
    )

    preflight_parser = subparsers.add_parser("preflight", help="Prove whether this directory is ready for app worktree provisioning.")
    preflight_parser.add_argument("--json", action="store_true", help="Emit JSON.")

    start_parser = subparsers.add_parser("start", help="Start a topic branch or isolated checkout.")
    start_parser.add_argument("--continue-review", help="Continue this exact remote/ref at its verified tip.")
    start_parser.add_argument("--new-review", action="store_true", help="Bind a new review; inherited upstream remains only the base.")
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
    adopt_parser.add_argument("--continue-review", help="Continue this exact remote/ref at its verified tip.")
    adopt_parser.add_argument("--new-review", action="store_true", help="Bind a new review; inherited upstream remains only the base.")
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
    review_import_parser.add_argument("--ownership-proof", help="Explicitly selected original yeet JSON for lost managed ownership; requires --expected-tip and retained retirement evidence.")
    review_import_parser.add_argument(
        "--goal-id",
        help="Optional historical correlation label; never used to select or authorize integration.",
    )
    review_import_parser.add_argument("--thread-id", help="Optional originating thread identifier.")
    review_import_parser.add_argument("--depends-on", action="append", default=[], dest="dependencies", help="Queue ID, PR URL, or ref that must land first. Repeat as needed.")
    review_import_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    review_import_parser.add_argument("--apply", action="store_true", help="Record the pull request as ready for integration.")

    reconcile_parser = subparsers.add_parser(
        "reconcile-integration-ownership",
        help="Reconcile an advanced integration receipt from a contiguous managed yeet proof chain.",
    )
    reconcile_parser.add_argument("--review-ref", required=True, help="Exact remote-tracking ref for the selected integrated review.")
    reconcile_parser.add_argument("--review-url", required=True, help="Exact hosted pull-request URL for the selected review.")
    reconcile_parser.add_argument("--expected-tip", required=True, help="Exact final published review SHA.")
    reconcile_parser.add_argument(
        "--proof-chain", action="append", required=True, dest="proof_paths",
        help="Chronological original successful yeet JSON result; repeat for each continuation.",
    )
    reconcile_parser.add_argument(
        "--expected-plan-digest",
        help="Read-only reconciliation plan digest required with --apply.",
    )
    reconcile_parser.add_argument(
        "--checkpoint-generation", type=int,
        help="Fresh adopted checkpoint generation for the resumed final handoff.",
    )
    reconcile_parser.add_argument(
        "--checkpoint-file",
        help="Authored checkpoint JSON model paired with --checkpoint-generation when required.",
    )
    reconcile_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    reconcile_parser.add_argument("--apply", action="store_true", help="Append the attestation and resume normal integration disposal.")

    yeet_parser = subparsers.add_parser(
        "yeet",
        help="Take the registered task to its configured terminal Git disposition.",
    )
    completion_mode = yeet_parser.add_mutually_exclusive_group()
    completion_mode.add_argument("--publish-only", action="store_true", help="Publish this validated revision and retain the registered task for review and corrections; never integrate.")
    completion_mode.add_argument("--review-only", action="store_true", help="Publish a ready review and intentionally hold integration.")
    completion_mode.add_argument("--integrate", action="store_true", help="Explicitly integrate the selected review transaction.")
    yeet_parser.add_argument("--include-review", action="append", default=[], help="Explicit additional queue ID, review ref, or URL for this completion.")
    yeet_parser.add_argument("--checkpoint-generation", type=int, help="Explicit generation from a fresh read when reconciling a completion handoff.")
    yeet_parser.add_argument("--integration-validation-file", help="JSON with the exact prepared integration head and PASS summary.")
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
        help="Authored checkpoint JSON model; optional for ordinary publication. Pair with --checkpoint-generation.",
    )
    yeet_parser.add_argument("--update-existing", action="store_true", help="Refresh an existing matching pull request.")
    yeet_parser.add_argument(
        "--task",
        dest="task_selector",
        help="Branch, queue ID, review ref, or review URL used only to re-prove an already retired yeet.",
    )
    yeet_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    yeet_parser.add_argument("--brief", action="store_true", help="Omit only the broad final repository inventory; requires --json.")
    yeet_parser.add_argument("--apply", action="store_true", help="Run the resumable yeet transaction.")

    park_parser = subparsers.add_parser("park", help="Keep the active change off the ground-truth line on purpose.")
    park_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    park_parser.add_argument("--apply", action="store_true", help="Apply parking mutations.")

    repair_parser = subparsers.add_parser("repair", help="Audit or reclaim leftover temporary Git state.")
    repair_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    repair_parser.add_argument("--plan", action="store_true", help="Report the repair plan without mutating.")
    repair_parser.add_argument("--apply", action="store_true", help="Apply safe repair and auto-parking mutations.")

    end_parser = subparsers.add_parser(
        "end",
        help="Run the managed closeout state machine after confirmation.",
    )
    end_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    end_parser.add_argument("--apply", action="store_true", help="Apply the closeout state machine.")
    end_parser.add_argument("-yes", dest="yes", action="store_true", help="Confirm and apply closeout.")

    for name, child in subparsers.choices.items():
        child.add_argument(
            "--repo",
            default=argparse.SUPPRESS,
            help="Run against this repository or checkout instead of the current directory.",
        )

    return parser


def _emit_error(
    exc: GitSafeError,
    *,
    json_output: bool,
    command: str | None = None,
    operation_kind: str = "query",
    execution_context: dict[str, Any] | None = None,
    args: argparse.Namespace | None = None,
    started_ns: int | None = None,
) -> None:
    if json_output:
        payload = {
            "command": command,
            "ok": False,
            "command_ok": False,
            "policy_ok": False,
            "operation": {"kind": operation_kind, "status": exc.result_status},
            "target": {"blocked": True, "blockers": exc.blockers},
            "error": str(exc),
            "blockers": exc.blockers,
        }
        payload.update(exc.data)
        if execution_context is not None and started_ns is not None:
            _attach_execution_evidence(
                payload,
                context=execution_context,
                args=args,
                mutation_requested=operation_kind == "mutation",
                started_ns=started_ns,
            )
        _print_json(payload)
    else:
        print(f"codex-git-safe: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    started_ns = time.monotonic_ns()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["--help"]
    json_requested = "--json" in argv
    command = _command_from_argv(argv)
    args: argparse.Namespace | None = None
    execution_context = _execution_context(argv)

    def finish_result(
        payload: dict[str, Any],
        *,
        mutation_requested: bool,
    ) -> tuple[dict[str, Any], int]:
        result, returncode = _operation_result(
            payload,
            mutation_requested=mutation_requested,
        )
        return (
            _attach_execution_evidence(
                result,
                context=execution_context,
                args=args,
                mutation_requested=mutation_requested,
                started_ns=started_ns,
            ),
            returncode,
        )

    try:
        parser = _build_parser()
        args = parser.parse_args(argv)
        args.json = bool(getattr(args, "json", False) or getattr(args, "global_json", False))
        command = args.command
        requested_path = Path(args.repo).expanduser().resolve() if getattr(args, "repo", None) else Path.cwd().resolve()

        if args.command == "preflight":
            payload, _inspection_returncode = _preflight_payload(requested_path)
            payload, semantic_returncode = finish_result(
                payload,
                mutation_requested=False,
            )
            if args.json:
                _print_json(payload)
            else:
                print(f"ready for worktree: {'yes' if payload['ready_for_worktree'] else 'no'}")
                for blocker in payload.get("blockers", []):
                    print(f"- {blocker}")
            return semantic_returncode

        state = _repo_state(requested_path)
        if args.command in {"start", "adopt-current"}:
            _validate_review_task_intake(state, task_class=args.task_class,
                new_review=bool(args.new_review), continue_review=args.continue_review,
                adopting=args.command == "adopt-current")
        if args.command == "status":
            payload = _status_payload(state)
            if args.brief and not args.json:
                raise GitSafeError(
                    "status --brief requires --json",
                    exit_code=2,
                    result_status="invalid_invocation",
                )
            payload, returncode = finish_result(payload, mutation_requested=False)
            if args.json:
                _print_json(_brief_status_payload(payload) if args.brief else payload)
            else:
                _human_status(state)
            return returncode

        if args.command == "repair":
            payload = _repair_payload(state, apply=bool(args.apply))
            payload, returncode = finish_result(payload, mutation_requested=bool(args.apply))
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
            return returncode

        if args.command == "integrate":
            payload = _integrate_payload(state, source_refs=list(args.source_refs), apply=bool(args.apply))
            payload, returncode = finish_result(payload, mutation_requested=bool(args.apply))
            if args.json:
                _print_json(payload)
            else:
                for selection in payload.get("selections", []):
                    print(f"selected: {selection['source_ref']} at {selection['published_tip']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return returncode

        if args.command == "review-ready":
            payload = _mark_review_ready_payload(
                state,
                review_ref=args.review_ref,
                review_url=args.review_url,
                apply=bool(args.apply),
            )
            payload, returncode = finish_result(payload, mutation_requested=bool(args.apply))
            if args.json:
                _print_json(payload)
            else:
                print(f"state: {payload['state']}")
                print(f"review: {payload['review_url']}")
            return returncode

        if args.command == "review-import":
            payload = _import_review_payload(
                state,
                review_ref=args.review_ref,
                review_url=args.review_url,
                expected_tip=args.expected_tip,
                goal_id=args.goal_id,
                thread_id=args.thread_id,
                dependencies=list(args.dependencies),
                ownership_proof=args.ownership_proof,
                apply=bool(args.apply),
            )
            payload, returncode = finish_result(payload, mutation_requested=bool(args.apply))
            if args.json:
                _print_json(payload)
            else:
                print(f"state: {payload['state']}")
                print(f"queue: {payload['submission']['queue_id']}")
            return returncode

        if args.command == "reconcile-integration-ownership":
            payload = _reconcile_integration_ownership(
                state,
                review_ref=args.review_ref,
                review_url=args.review_url,
                expected_tip=args.expected_tip,
                proof_paths=list(args.proof_paths),
                expected_plan_digest=args.expected_plan_digest,
                checkpoint_file=args.checkpoint_file,
                checkpoint_generation=args.checkpoint_generation,
                apply=bool(args.apply),
            )
            payload, returncode = finish_result(payload, mutation_requested=bool(args.apply))
            if args.json:
                _print_json(payload)
            else:
                print(f"state: {payload['state']}")
                print(f"review: {args.review_ref}")
                if payload.get("reconciliation_digest"):
                    print(f"plan digest: {payload['reconciliation_digest']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return returncode

        if args.command == "yeet":
            if args.brief and not args.json:
                raise GitSafeError("yeet --brief requires --json", exit_code=2, result_status="invalid_invocation")
            payload = _yeet_payload(
                state,
                message=args.message,
                message_file=args.message_file,
                validation=args.validation,
                validation_file=args.validation_file,
                title=args.title,
                body_file=args.body_file,
                update_existing=bool(args.update_existing),
                review_only=bool(args.review_only),
                publish_only=bool(args.publish_only),
                integrate=bool(args.integrate),
                include_reviews=list(args.include_review),
                integration_validation_file=args.integration_validation_file,
                checkpoint_generation=args.checkpoint_generation,
                checkpoint_file=args.checkpoint_file,
                task_selector=args.task_selector,
                apply=bool(args.apply),
            )
            payload, returncode = finish_result(payload, mutation_requested=bool(args.apply))
            if args.json:
                _print_json(_brief_yeet_payload(payload) if args.brief else payload)
            else:
                print(f"state: {payload['state']}")
                if payload.get("submission", {}).get("review_url"):
                    print(f"review: {payload['submission']['review_url']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return returncode

        if args.command == "adopt-current":
            payload = _adopt_current_worktree(
                state,
                topic=args.topic,
                task_class=args.task_class,
                apply=bool(args.apply),
                if_eligible=bool(args.if_eligible),
                provisional_ordinary=bool(args.provisional_ordinary),
                continue_review=args.continue_review,
                new_review=bool(args.new_review),
            )
            payload, returncode = finish_result(payload, mutation_requested=bool(args.apply))
            if args.json:
                _print_json(payload)
            else:
                print(f"branch: {payload['branch']}")
                print(f"checkout: {payload['checkout_path']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return returncode

        if args.command == "end":
            stdin_confirmation = ""
            if not sys.stdin.isatty():
                try:
                    stdin_confirmation = sys.stdin.read().strip().lower()
                except OSError:
                    stdin_confirmation = ""
            confirmed = bool(args.apply) or bool(args.yes) or stdin_confirmation in {"y", "yes"}
            payload = _closeout_payload(state, apply=confirmed, confirmed=confirmed)
            payload, returncode = finish_result(payload, mutation_requested=confirmed)
            if args.json:
                _print_json(payload)
            else:
                if payload.get("confirmation_required"):
                    print(payload["prompt"])
                    return returncode
                print(f"state: {payload['state']}")
                print(f"result: {payload['result']}")
                for action in payload.get("actions", []):
                    print(f"- {action}")
            return returncode

        if args.command == "park":
            payload = _park_payload(state, apply=bool(args.apply))
            payload, returncode = finish_result(payload, mutation_requested=bool(args.apply))
            if args.json:
                _print_json(payload)
            else:
                print(f"change: {payload['branch']}")
                print(f"parking ref: {payload['parking_ref']}")
                if payload.get("bundle_path"):
                    print(f"bundle: {payload['bundle_path']}")
            return returncode

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
                continue_review=args.continue_review,
                new_review=bool(args.new_review),
            )
            payload, returncode = finish_result(payload, mutation_requested=not args.dry_run)
            if args.json:
                _print_json(payload)
                return returncode
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
                return returncode

    except PermissionError as exc:
        error = GitSafeError(
            str(exc),
            blockers=["the requested operation requires filesystem authority not available to this process"],
            exit_code=3,
            result_status="authority_required",
        )
        _emit_error(
            error,
            json_output=json_requested or bool(getattr(args, "json", False)),
            command=command,
            operation_kind="mutation" if _mutation_requested(args) else "query",
            execution_context=execution_context,
            args=args,
            started_ns=started_ns,
        )
        return error.exit_code
    except (GitSafeError, RegistryError) as exc:
        if isinstance(exc, RegistryError):
            exc = GitSafeError(str(exc), blockers=["inspect and recover the retained registry before lifecycle mutation"])
        _emit_error(
            exc,
            json_output=json_requested or bool(getattr(args, "json", False)),
            command=command,
            operation_kind="mutation" if _mutation_requested(args) else "query",
            execution_context=execution_context,
            args=args,
            started_ns=started_ns,
        )
        return exc.exit_code
    except OSError as exc:
        error = GitSafeError(
            str(exc),
            exit_code=70,
            result_status="internal_error",
        )
        _emit_error(
            error,
            json_output=json_requested or bool(getattr(args, "json", False)),
            command=command,
            operation_kind="mutation" if _mutation_requested(args) else "query",
            execution_context=execution_context,
            args=args,
            started_ns=started_ns,
        )
        return error.exit_code

    raise GitSafeError(f"unsupported command: {args.command}")
