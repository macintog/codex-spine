---
name: yeet
description: Commit, publish or integrate, prove, and retire a completed registered Git task when the operator explicitly says yeet. Use only for that exact terminal instruction after working-thread validation exists. Do not use for ordinary commits, tests, deployments, read-only or no-diff work, or selecting integration refs.
---

# Yeet

`validated registered task → commit → publish or integrate → prove → retire`

Treat the operator's exact `yeet` instruction as authorization to attempt the
registered task's configured terminal Git transaction now. It is not authority
to run product tests, verification suites, bootstrap, hosting, deployment,
release work, or to select additional integration refs.

1. Read the repository's Git lane and bind the current checkout to exactly one
   active managed task. Refuse an unregistered, detached, dirty-adopted, or
   wrong-task-class checkout.
2. Use the compact passing validation result already produced by the working
   thread, recorded as `PASS: <checks and result>`. If it is missing or failed,
   stop before mutation; do not manufacture it or run tests.
3. Prepare the task's commit message, review title/body when ordinary, and the
   generation-checked checkpoint JSON model when the repository is adopted.
4. Run `codex-git-safe yeet --apply` once with those inputs. Let the transaction
   stage the proven task delta, commit if needed, publish or integrate according
   to task class, prove the live remote state, update the checkpoint, re-home,
   and retire only the task-owned local state. When the task was isolated from
   an existing non-authoritative tracked review head, the transaction may
   update that same head only if both its tracking and live remote tips still
   equal the recorded isolation baseline; never create a replacement review.
5. On a blocker, report the exact failed precondition and retained phase. A
   retry uses the same command and inputs. After retirement, use `--task` only
   to re-prove the recorded terminal result.

Success requires the task-class-specific remote proof, checkpoint disposition,
and absence of its local worktree, branch, and active registration. Completion
is terminal; do not ask for or emit a second closeout phrase.

This packet deliberately recycles a familiar name for a materially different
Git contract. When comparing it with public skills named `yeet`, read
[Same name, different contract](references/name-and-scope.md).
