# Project Agent Guide

On the first turn or when the repo or `cwd` changes, routine startup context for this repo is:

1. `PROJECT_SPINE.md`
2. `CHECKPOINT.md`
3. This file

Within one thread, re-anchor by calling `memory.bootstrap_context` first and reload these docs only on explicit request or repo or `cwd` change.

Open deeper docs only when the task needs them.

## Working Rules

- Repo-specific execution and validation rules only.
- Keep this file short and operational.
- Route to specialized skills or on-demand tooling guides instead of inlining their whole playbooks here.

## Understanding Surfaces

- If this repo self-hosts its own startup docs, tooling guides, skill bodies or templates, generated config, launchers, or managed links, treat them as one coordinated understanding surface.
- Update validation and closeout reload or relaunch guidance when those surfaces change.
- If those changes materially alter startup or tool-routing semantics, say whether the current thread should reload docs or whether a fresh session is recommended.

## Git Safety

- Define the authoritative base branch and protected refs before branch cleanup.
- Require a `unique-commit audit` against that base before deleting or pruning a branch.
- State ancestry results in words; do not report raw exit codes as branch-safety conclusions.
- Treat Git warnings during deletion as blockers.
- When signals disagree, preserve state and escalate instead of cleaning up for tidiness.
- If adjacent repos, managed clones, or companion source checkouts require different Git interpretation than the root repo, record those comparison rules here explicitly.

## Document Roles

- `README.md`: human repo entrypoint
- `PROJECT_SPINE.md`: durable project and strategy authority
- `CHECKPOINT.md`: volatile plan-of-record
- Deep docs: on-demand reference
- Archive: dated historical notes only

## Update Rules

- Durable strategy goes in `PROJECT_SPINE.md`.
- Current blockers and next steps go in `CHECKPOINT.md`.
- Repo-local workflow rules go here.
- Historical detail goes in the archive, not in routine startup docs.
