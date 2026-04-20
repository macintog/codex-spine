# Project Agent Guide

On the first turn or when the repo or `cwd` changes, routine startup context for this repo is:

1. `PROJECT_CONTINUITY.md`
2. `CHECKPOINT.md`
3. This file

Within one thread, re-anchor by using the environment's stock continuity/bootstrap lane first and reload these docs only on explicit request or repo or `cwd` change.

Open deeper docs only when the task needs them.

## Working Rules

- Repo-specific execution and validation rules only.
- Keep this file short and operational.
- Route to specialized skills or on-demand tooling guides instead of inlining their whole playbooks here.
- If a point needs dated evidence, repeated examples, or deep subsystem nuance, put that detail in a deep doc or archive and keep only the routing rule here.

## Understanding Surfaces

- If this repo self-hosts its own startup docs, tooling guides, skill bodies or templates, generated config, launchers, or managed links, treat them as one coordinated understanding surface.
- Update validation and closeout reload or relaunch guidance when those surfaces change.
- If those changes materially alter startup or tool-routing semantics, say whether the current thread should reload docs or whether a fresh session is recommended.

## Git Safety

- Own Git posture for the user in plain language. Translate desired outcomes into the change-lifecycle plan instead of making the user infer Git mechanics.
- If the repo or environment exposes a preview-first lifecycle helper, say when you are previewing versus mutating and use the helper's real mutation pass only when you intend to change history or cleanup state.
- Define the authoritative base branch and protected refs before branch cleanup.
- In this environment, route routine start, finish, park, and repair through the repo's or environment's documented lifecycle helper instead of embedding ad hoc git sequences here.
- For parallel work or branch-switch-heavy work, prefer an isolated checkout or clone before editing. If the repo has a local isolation pattern, record it here.
- State ancestry results in words; do not report raw exit codes as branch-safety conclusions.
- If preservation intent or base choice is unclear and the answer would change history, ask a short clarifying question before mutating refs or switching a shared branch.
- Treat Git warnings during deletion as blockers.
- When signals disagree, preserve state and escalate instead of cleaning up for tidiness.
- If adjacent repos, managed clones, or companion source checkouts require different Git interpretation than the root repo, record those comparison rules here explicitly.

## Document Roles

- `README.md`: human repo entrypoint
- `PROJECT_CONTINUITY.md`: durable project and strategy authority
- `CHECKPOINT.md`: volatile plan-of-record
- `docs/`: canonical location for durable deep docs and reference material when this repo has more than a couple of root-level docs
- `.codex/indexes.toml`: explicit code or docs or dataset indexing contract when supported by the environment
- Deep docs outside `docs/`: temporary migration state, not the preferred steady shape
- Archive: themed or layered historical notes only, not a rolling history file

## Update Rules

- Durable strategy goes in `PROJECT_CONTINUITY.md`.
- Current blockers and next steps go in `CHECKPOINT.md`.
- Repo-local workflow rules go here.
- Historical detail goes in themed or layered archive surfaces, not in routine startup docs.
- If this repo has a continuity verifier, have it enforce this file's compact routing role as well as the checkpoint contract.
