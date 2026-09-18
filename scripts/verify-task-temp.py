#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

import codex_git_safe as git_safe
import codex_task_temp as task_temp


class StateStore:
    def __init__(self) -> None:
        self.payload: dict[str, object] = {"temporary_artifacts": []}

    def load(self) -> dict[str, object]:
        return copy.deepcopy(self.payload)

    def save(self, payload: dict[str, object]) -> None:
        self.payload = copy.deepcopy(payload)


def owner(common_dir: Path, name: str = "task") -> dict[str, str]:
    checkout = common_dir.parent / name
    return {
        "common_dir": str(common_dir.resolve()),
        "checkout_identity": str(checkout.resolve(strict=False)),
        "branch": f"codex/{name}",
        "created_at": "2026-09-05T12:00:00Z",
        "start_tip": "a" * 40,
    }


def allocate(store: StateStore, root: Path, task_owner: dict[str, str], label: str = "build") -> dict[str, object]:
    return task_temp.allocate_root(
        owner=task_owner,
        common_dir=Path(task_owner["common_dir"]),
        label=label,
        load_state=store.load,
        save_state=store.save,
        base_root=root.resolve(),
    )


def cleanup(store: StateStore, task_owner: dict[str, str], **kwargs: object) -> dict[str, object]:
    return task_temp.cleanup_owned_roots(
        owner=task_owner,
        common_dir=Path(task_owner["common_dir"]),
        load_state=store.load,
        save_state=store.save,
        live_check=kwargs.get("live_check", lambda path: None),
        base_root=kwargs.get("base_root"),
    )


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def init_remote_repo(base: Path, name: str) -> tuple[Path, Path]:
    repo = base / name
    remote = base / f"{name}.git"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    (repo / "README").write_text("fixture\n", encoding="utf-8")
    git(repo, "add", "README")
    git(repo, "commit", "-m", "fixture")
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-u", "origin", "main")
    return repo, remote


def allocate_for_managed_task(state: git_safe.RepoState, change: git_safe.ManagedChange, label: str, storage: str = "temporary") -> Path:
    with git_safe._integration_lock(state.common_dir):
        entry = task_temp.allocate_root(
            owner=git_safe._task_temp_owner(state, change),
            common_dir=state.common_dir,
            label=label,
            storage=storage,
            load_state=lambda: git_safe._load_managed_state(state.common_dir),
            save_state=lambda payload: git_safe._save_managed_state(state.common_dir, payload),
        )
    return Path(str(entry["path"]))


class TaskTempTests(unittest.TestCase):
    def fixture(self):
        return tempfile.TemporaryDirectory(prefix="codex-task-temp-fixture-")

    def test_durable_storage_rejects_real_os_temporary_common_directory(self):
        with self.fixture() as directory:
            # The process temporary directory is ephemeral even when it is not /tmp.
            common = Path(directory).resolve() / "repo.git"
            common.mkdir()
            store = StateStore()
            with self.assertRaisesRegex(task_temp.TaskTempError, "outside OS temporary roots"):
                task_temp.allocate_root(owner=owner(common), common_dir=common, label="fixture",
                                        storage="durable", load_state=store.load, save_state=store.save)
            self.assertEqual(store.payload["temporary_artifacts"], [])

    def test_mixed_legacy_and_durable_roots_share_exact_owner_cleanup(self):
        with self.fixture() as directory, mock.patch.object(task_temp, "is_ephemeral_checkout_path", return_value=False):
            # Only fixture placement is substituted; ownership and deletion remain real.
            base = Path(directory).resolve()
            common = base / "repo.git"
            common.mkdir()
            temp_root = base / "os-temp"
            temp_root.mkdir()
            store = StateStore()
            task_owner = owner(common)
            legacy = allocate(store, temp_root, task_owner)
            self.assertEqual(legacy["schema_version"], 1)
            self.assertNotIn("storage", legacy)
            durable = task_temp.allocate_root(owner=task_owner, common_dir=common, label="fixtures",
                                             storage="durable", load_state=store.load, save_state=store.save)
            root = Path(durable["path"])
            self.assertEqual(root.parent, common / "codex-git-safe/temporary-artifacts")
            marker = json.loads((root / task_temp.MARKER_NAME).read_text())
            self.assertEqual(marker["schema_version"], 2)
            self.assertEqual(marker["storage"], "durable")
            self.assertEqual(marker["storage_root"], str(root.parent))
            (root / "nested-fixture").mkdir()
            (root / "nested-fixture/result").write_text("fixture")
            unrelated = task_temp.allocate_root(owner=owner(common, "other"), common_dir=common,
                                               label="other", storage="durable",
                                               load_state=store.load, save_state=store.save)
            self.assertEqual(task_temp.status_for_owner(store.load(), task_owner, base_root=temp_root)["pending_count"], 2)
            self.assertEqual(cleanup(store, task_owner, base_root=temp_root)["artifact_count"], 2)
            self.assertFalse(root.exists())
            self.assertFalse(Path(legacy["path"]).exists())
            self.assertTrue(Path(unrelated["path"]).exists())
            self.assertEqual(task_temp.status_for_owner(store.load(), task_owner, base_root=temp_root)["pending_count"], 0)
            self.assertEqual(cleanup(store, task_owner, base_root=temp_root)["artifact_count"], 2)

    def test_durable_storage_rejects_forgery_replacement_symlink_and_live_use(self):
        with self.fixture() as directory, mock.patch.object(task_temp, "is_ephemeral_checkout_path", return_value=False):
            common = Path(directory).resolve() / "repo.git"
            common.mkdir()
            store = StateStore()
            task_owner = owner(common)
            entry = task_temp.allocate_root(owner=task_owner, common_dir=common, label="fixtures",
                                           storage="durable", load_state=store.load, save_state=store.save)
            root = Path(entry["path"])
            original = store.load()
            store.payload["temporary_artifacts"][0]["storage_root"] = str(common)
            with self.assertRaisesRegex(task_temp.TaskTempError, "noncanonical storage parent"):
                cleanup(store, task_owner)
            store.payload = copy.deepcopy(original)
            store.payload["temporary_artifacts"][0]["schema_version"] = 1
            with self.assertRaisesRegex(task_temp.TaskTempError, "legacy temporary artifact"):
                cleanup(store, task_owner)
            store.payload = copy.deepcopy(original)
            # Downgrading both journal fields still cannot reinterpret durable storage as legacy temp.
            store.payload["temporary_artifacts"][0]["schema_version"] = 1
            del store.payload["temporary_artifacts"][0]["storage"]
            with self.assertRaisesRegex(task_temp.TaskTempError, "noncanonical storage parent"):
                cleanup(store, task_owner)
            store.payload = copy.deepcopy(original)
            with self.assertRaisesRegex(task_temp.TaskTempError, "live"):
                cleanup(store, task_owner, live_check=lambda path: (_ for _ in ()).throw(task_temp.TaskTempError("live")))
            saved_root = root.with_name("saved-root")
            root.rename(saved_root)
            root.symlink_to(saved_root, target_is_directory=True)
            with self.assertRaisesRegex(task_temp.TaskTempError, "became a symlink"):
                cleanup(store, task_owner)
            root.unlink()
            root.mkdir(mode=0o700)
            shutil.copy2(saved_root / task_temp.MARKER_NAME, root / task_temp.MARKER_NAME)
            with self.assertRaisesRegex(task_temp.TaskTempError, "identity changed"):
                cleanup(store, task_owner)
            shutil.rmtree(root)
            saved_root.rename(root)
            parent = root.parent
            moved_parent = parent.with_name("saved-parent")
            parent.rename(moved_parent)
            parent.symlink_to(moved_parent, target_is_directory=True)
            with self.assertRaisesRegex(task_temp.TaskTempError, "must not be a symlink"):
                cleanup(store, task_owner)
            with self.assertRaisesRegex(task_temp.TaskTempError, "must not be a symlink"):
                task_temp.allocate_root(owner=task_owner, common_dir=common, label="blocked",
                                        storage="durable", load_state=store.load, save_state=store.save)
            parent.unlink()
            moved_parent.rename(parent)
            self.assertEqual(cleanup(store, task_owner)["artifact_count"], 1)

    def test_allocate_owns_all_descendants_and_cleanup_excludes_siblings(self):
        with self.fixture() as directory:
            base = Path(directory)
            common = base / "repo.git"
            common.mkdir()
            temp_root = base / "tmp"
            temp_root.mkdir()
            store = StateStore()
            task_owner = owner(common)
            entry = allocate(store, temp_root, task_owner)
            root = Path(str(entry["path"]))
            (root / "baseline/subdir").mkdir(parents=True)
            (root / "baseline/subdir/data").write_text("generated", encoding="utf-8")
            (root / "result.xcresult").mkdir()
            (root / "link").symlink_to(root / "baseline")
            sibling = temp_root / "unowned"
            sibling.mkdir()
            result = cleanup(store, task_owner, base_root=temp_root.resolve())
            self.assertFalse(root.exists())
            self.assertTrue(sibling.exists())
            self.assertEqual(result["artifact_count"], 1)
            self.assertEqual(store.payload["temporary_artifacts"][0]["phase"], "deleted")
            self.assertEqual(cleanup(store, task_owner, base_root=temp_root.resolve())["artifact_count"], 1)

    def test_foreign_owner_and_arbitrary_journal_path_are_excluded(self):
        with self.fixture() as directory:
            base = Path(directory)
            common = base / "repo.git"
            common.mkdir()
            temp_root = base / "tmp"
            temp_root.mkdir()
            store = StateStore()
            first = owner(common, "first")
            second = owner(common, "second")
            entry = allocate(store, temp_root, first)
            root = Path(str(entry["path"]))
            self.assertEqual(cleanup(store, second, base_root=temp_root.resolve())["artifact_count"], 0)
            self.assertTrue(root.exists())
            forged = copy.deepcopy(store.payload)
            forged["temporary_artifacts"][0]["path"] = str(temp_root / "unrelated")
            (temp_root / "unrelated").mkdir()
            store.payload = forged
            with self.assertRaisesRegex(task_temp.TaskTempError, "escaped its canonical parent"):
                cleanup(store, first, base_root=temp_root.resolve())

            store = StateStore()
            allocate(store, temp_root, first)
            store.payload["temporary_artifacts"][0]["storage_root"] = str(common)
            with self.assertRaisesRegex(task_temp.TaskTempError, "noncanonical storage parent"):
                cleanup(store, first, base_root=temp_root.resolve())
            alias = base / "tmp-alias"
            alias.symlink_to(temp_root, target_is_directory=True)
            with self.assertRaisesRegex(task_temp.TaskTempError, "must not be a symlink"):
                task_temp.status_for_owner(store.load(), first, base_root=alias)

    def test_root_replacement_and_live_use_fail_closed(self):
        with self.fixture() as directory:
            base = Path(directory)
            common = base / "repo.git"
            common.mkdir()
            temp_root = base / "tmp"
            temp_root.mkdir()
            store = StateStore()
            task_owner = owner(common)
            entry = allocate(store, temp_root, task_owner)
            root = Path(str(entry["path"]))
            with self.assertRaisesRegex(task_temp.TaskTempError, "live"):
                cleanup(store, task_owner, live_check=lambda path: (_ for _ in ()).throw(task_temp.TaskTempError("live")), base_root=temp_root.resolve())
            self.assertTrue(root.exists())
            marker = (root / task_temp.MARKER_NAME).read_bytes()
            shutil.rmtree(root)
            root.mkdir(mode=0o700)
            (root / task_temp.MARKER_NAME).write_bytes(marker)
            with self.assertRaisesRegex(task_temp.TaskTempError, "identity changed"):
                cleanup(store, task_owner, base_root=temp_root.resolve())

    def test_special_file_and_protected_disposition_block_cleanup(self):
        with self.fixture() as directory:
            base = Path(directory)
            common = base / "repo.git"
            common.mkdir()
            temp_root = base / "tmp"
            temp_root.mkdir()
            store = StateStore()
            task_owner = owner(common)
            entry = allocate(store, temp_root, task_owner)
            root = Path(str(entry["path"]))
            fifo = root / "pipe"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(task_temp.TaskTempError, "unsupported special file"):
                cleanup(store, task_owner, base_root=temp_root.resolve())
            fifo.unlink()
            store.payload["temporary_artifacts"][0]["disposition"] = "protected"
            with self.assertRaisesRegex(task_temp.TaskTempError, "protected"):
                cleanup(store, task_owner, base_root=temp_root.resolve())

    def test_preexisting_sidecar_collision_is_never_unlinked(self):
        with self.fixture() as directory:
            base = Path(directory)
            common = base / "repo.git"
            common.mkdir()
            temp_root = base / "tmp"
            temp_root.mkdir()
            store = StateStore()
            task_owner = owner(common)
            entry = allocate(store, temp_root, task_owner)
            root = Path(str(entry["path"]))
            sidecar = temp_root.resolve() / f".codex-task-temp-{entry['id']}.owner"
            sidecar.write_text("unrelated\n", encoding="utf-8")
            with self.assertRaisesRegex(task_temp.TaskTempError, "unexpectedly exists"):
                cleanup(store, task_owner, base_root=temp_root.resolve())
            self.assertTrue(root.exists())
            self.assertEqual(sidecar.read_text(encoding="utf-8"), "unrelated\n")

    def test_partial_delete_and_absent_root_crash_are_resumable(self):
        with self.fixture() as directory:
            base = Path(directory)
            common = base / "repo.git"
            common.mkdir()
            temp_root = base / "tmp"
            temp_root.mkdir()
            task_owner = owner(common)

            partial_store = StateStore()
            partial_entry = allocate(partial_store, temp_root, task_owner, "partial")
            partial_root = Path(str(partial_entry["path"]))
            (partial_root / "one").write_text("one", encoding="utf-8")
            (partial_root / "two").write_text("two", encoding="utf-8")

            def partial_delete(path: Path) -> None:
                (path / "one").unlink()
                raise OSError("interrupted")

            with mock.patch.object(task_temp.shutil, "rmtree", side_effect=partial_delete):
                with self.assertRaisesRegex(task_temp.TaskTempError, "receipt retained"):
                    cleanup(partial_store, task_owner, base_root=temp_root.resolve())
            self.assertEqual(partial_store.payload["temporary_artifacts"][0]["phase"], "cleanup_failed")
            cleanup(partial_store, task_owner, base_root=temp_root.resolve())
            self.assertFalse(partial_root.exists())

            absent_store = StateStore()
            absent_entry = allocate(absent_store, temp_root, task_owner, "absent")
            absent_root = Path(str(absent_entry["path"]))
            real_rmtree = shutil.rmtree

            def delete_then_interrupt(path: Path) -> None:
                real_rmtree(path)
                raise OSError("crash after root deletion")

            with mock.patch.object(task_temp.shutil, "rmtree", side_effect=delete_then_interrupt):
                with self.assertRaisesRegex(task_temp.TaskTempError, "receipt retained"):
                    cleanup(absent_store, task_owner, base_root=temp_root.resolve())
            self.assertFalse(absent_root.exists())
            cleanup(absent_store, task_owner, base_root=temp_root.resolve())
            self.assertEqual(absent_store.payload["temporary_artifacts"][0]["phase"], "deleted")
            absent_status = task_temp.status_for_owner(absent_store.load(), task_owner, base_root=temp_root.resolve())
            self.assertEqual(absent_status["pending_count"], 0)
            self.assertFalse(any(temp_root.glob(".codex-task-temp-*.owner")))

    def test_content_change_between_plan_and_delete_fails_closed(self):
        with self.fixture() as directory:
            base = Path(directory)
            common = base / "repo.git"
            common.mkdir()
            temp_root = base / "tmp"
            temp_root.mkdir()
            store = StateStore()
            task_owner = owner(common)
            entry = allocate(store, temp_root, task_owner)
            root = Path(str(entry["path"]))
            generated = root / "generated"
            generated.write_text("before", encoding="utf-8")
            calls = 0

            def mutate_before_final_fingerprint(path: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    generated.write_text("after", encoding="utf-8")

            with self.assertRaisesRegex(task_temp.TaskTempError, "contents changed"):
                cleanup(
                    store,
                    task_owner,
                    live_check=mutate_before_final_fingerprint,
                    base_root=temp_root.resolve(),
                )
            self.assertTrue(root.exists())

    def test_allocation_failure_is_journaled_and_absent_intent_reconciles(self):
        with self.fixture() as directory:
            base = Path(directory)
            common = base / "repo.git"
            common.mkdir()
            temp_root = base / "tmp"
            temp_root.mkdir()
            store = StateStore()
            task_owner = owner(common)
            with mock.patch.object(Path, "mkdir", side_effect=OSError("allocation crash")):
                with self.assertRaisesRegex(task_temp.TaskTempError, "journal retained"):
                    allocate(store, temp_root, task_owner)
            self.assertEqual(store.payload["temporary_artifacts"][0]["phase"], "allocation_failed")
            cleanup(store, task_owner, base_root=temp_root.resolve())
            self.assertEqual(store.payload["temporary_artifacts"][0]["phase"], "deleted")

            marker_store = StateStore()
            real_open = os.open

            def fail_marker(path: object, flags: int, mode: int = 0o777) -> int:
                if str(path).endswith(task_temp.MARKER_NAME):
                    raise OSError("marker crash")
                return real_open(path, flags, mode)

            with mock.patch.object(task_temp.os, "open", side_effect=fail_marker):
                with self.assertRaisesRegex(task_temp.TaskTempError, "journal retained"):
                    allocate(marker_store, temp_root, task_owner, "marker")
            incomplete = Path(str(marker_store.payload["temporary_artifacts"][0]["path"]))
            self.assertTrue(incomplete.is_dir())
            cleanup(marker_store, task_owner, base_root=temp_root.resolve())
            self.assertFalse(incomplete.exists())

    def test_launcher_requires_exact_live_attached_registered_worktree(self):
        with self.fixture() as directory:
            base = Path(directory)
            repo = base / "repo"
            subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
            git(repo, "config", "user.name", "Fixture")
            git(repo, "config", "user.email", "fixture@example.invalid")
            (repo / "README").write_text("fixture\n", encoding="utf-8")
            git(repo, "add", "README")
            git(repo, "commit", "-m", "fixture")
            task = base / "task"
            git(repo, "worktree", "add", "-b", "codex/temp-fixture", str(task), "main")
            state = git_safe._repo_state(task)
            git_safe._set_active_change(
                state,
                branch="codex/temp-fixture",
                authoritative_branch="main",
                lifecycle="working",
                checkout_path=task,
                mode="worktree",
                start_tip=git(task, "rev-parse", "HEAD"),
            )
            command = [sys.executable, str(REPO_ROOT / "bin/codex-task-temp"), "create", "--repo", str(task), "--label", "fixture", "--json"]
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            created_root = Path(payload["root"])
            try:
                status = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "bin/codex-task-temp"), "status", "--repo", str(task), "--json"],
                    check=False, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
                self.assertEqual(json.loads(status.stdout)["pending_count"], 1)
                canonical = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "bin/codex-task-temp"), "create", "--repo", str(repo), "--label", "forbidden", "--json"],
                    check=False, capture_output=True, text=True, timeout=30,
                )
                self.assertNotEqual(canonical.returncode, 0)
                self.assertIn("one exact active managed task", canonical.stdout)
            finally:
                task_state = git_safe._repo_state(task)
                active = git_safe._managed_active_change(task_state, git_safe._authority_assessment(task_state))
                if active is not None:
                    git_safe._retire_owned_temporary_artifacts(task_state, active)
                if created_root.exists():
                    shutil.rmtree(created_root)

    @mock.patch.object(task_temp, "is_ephemeral_checkout_path", return_value=False)
    def test_review_only_retirement_cleans_nonempty_owned_root(self, _fixture_placement):
        with self.fixture() as directory:
            base = Path(directory)
            repo, _ = init_remote_repo(base, "review-only")
            task = base / "review-task"
            branch = "codex/review-temp"
            start_tip = git(repo, "rev-parse", "HEAD")
            git(repo, "worktree", "add", "-b", branch, str(task), "main")
            (task / "delta").write_text("change\n", encoding="utf-8")
            git(task, "add", "delta")
            git(task, "commit", "-m", "change")
            tip = git(task, "rev-parse", "HEAD")
            git(task, "push", "-u", "origin", branch)
            task_state = git_safe._repo_state(task)
            git_safe._set_active_change(
                task_state,
                branch=branch,
                authoritative_branch="main",
                lifecycle="ready_for_integration",
                checkout_path=task,
                mode="worktree",
                phase="ready_for_integration",
                published_tip=tip,
                base_tip=start_tip,
                review_remote="origin",
                review_ref=f"origin/{branch}",
                review_url="https://example.invalid/review/1",
                start_tip=start_tip,
                validation_summary="PASS: fixture",
                review_intent="new",
            )
            task_state = git_safe._repo_state(task)
            change = git_safe._managed_active_change(task_state, git_safe._authority_assessment(task_state))
            self.assertIsNotNone(change)
            assert change is not None
            owned_root = allocate_for_managed_task(task_state, change, "review")
            durable_root = allocate_for_managed_task(task_state, change, "review-fixture", "durable")
            (durable_root / "fixture-output").write_text("generated")
            (owned_root / "result.xcresult").mkdir()
            try:
                with mock.patch.object(git_safe, "is_ephemeral_checkout_path", return_value=False):
                    _, cleanup_result, _, _ = git_safe._retire_submitted_change(
                        task_state,
                        change,
                        "main",
                        update_checkpoint=False,
                    )
                self.assertFalse(owned_root.exists())
                self.assertFalse(durable_root.exists())
                self.assertFalse(task.exists())
                self.assertEqual(cleanup_result["temporary_artifacts"]["artifact_count"], 2)
                reproved = git_safe._yeet_submitted_result(git_safe._repo_state(repo), branch)
                self.assertEqual(reproved["cleanup"]["temporary_artifacts"]["pending_count"], 0)
            finally:
                if owned_root.exists():
                    shutil.rmtree(owned_root)

    @mock.patch.object(task_temp, "is_ephemeral_checkout_path", return_value=False)
    def test_integrated_retirement_cleans_nonempty_owned_root(self, _fixture_placement):
        with self.fixture() as directory:
            base = Path(directory)
            repo, _ = init_remote_repo(base, "integrated")
            task = base / "integration-task"
            branch = "codex/integrated-temp"
            start_tip = git(repo, "rev-parse", "HEAD")
            git(repo, "worktree", "add", "-b", branch, str(task), "main")
            (task / "delta").write_text("change\n", encoding="utf-8")
            git(task, "add", "delta")
            git(task, "commit", "-m", "change")
            tip = git(task, "rev-parse", "HEAD")
            git(repo, "merge", "--ff-only", branch)
            git(repo, "push", "origin", "main")
            task_state = git_safe._repo_state(task)
            git_safe._set_active_change(
                task_state,
                branch=branch,
                authoritative_branch="main",
                lifecycle="integrated_local",
                checkout_path=task,
                mode="worktree",
                phase="integrated_local",
                integrated_tip=tip,
                start_tip=start_tip,
                validation_summary="PASS: fixture",
            )
            task_state = git_safe._repo_state(task)
            change = git_safe._managed_active_change(task_state, git_safe._authority_assessment(task_state))
            self.assertIsNotNone(change)
            assert change is not None
            owned_root = allocate_for_managed_task(task_state, change, "integrated")
            durable_root = allocate_for_managed_task(task_state, change, "integrated-fixture", "durable")
            (durable_root / "fixture-output").write_text("generated")
            (owned_root / "DerivedData").mkdir()
            try:
                cleanup_result = git_safe._retire_integrated_change(
                    git_safe._repo_state(repo), change, "main", repo
                )
                self.assertFalse(owned_root.exists())
                self.assertFalse(durable_root.exists())
                self.assertFalse(task.exists())
                self.assertEqual(cleanup_result["temporary_artifacts"]["artifact_count"], 2)
                retired = [
                    item for item in git_safe._load_managed_state(git_safe._repo_state(repo).common_dir)["retired_changes"]
                    if item.get("branch") == branch
                ]
                self.assertEqual(retired[0]["start_tip"], start_tip)
                reproved = git_safe._yeet_submitted_result(git_safe._repo_state(repo), branch)
                self.assertEqual(reproved["cleanup"]["temporary_artifacts"]["pending_count"], 0)
            finally:
                if owned_root.exists():
                    shutil.rmtree(owned_root)


if __name__ == "__main__":
    unittest.main()
