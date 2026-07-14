# Project Agent Guide

On the first turn or when the repo or `cwd` changes, routine startup context for this repo is:

1. This file
2. `PROJECT_CONTINUITY.md`
3. `CHECKPOINT.md`

Within one thread, re-anchor by using the environment's stock continuity/bootstrap lane first and reload these docs only on explicit request or repo or `cwd` change.

Open deeper docs only when the task needs them.

## Working Rules

- Repo-specific execution and validation rules only.
- Keep this file short and operational.
- Route to specialized skills, installed environment lanes, or repo-declared on-demand tooling guides instead of inlining their whole playbooks here.
- Do not assume this repo has `codex/TOOLING.md`; use it only if this repo explicitly ships and claims that file.
- If a point needs dated evidence, repeated examples, or deep subsystem nuance, put that detail in a deep doc or archive and keep only the routing rule here.

## Understanding Surfaces

- If this repo self-hosts its own startup docs, tooling guides, skill bodies or templates, generated config, launchers, or managed links, treat them as one coordinated understanding surface.
- Update validation and closeout reload or relaunch guidance when those surfaces change.
- If those changes materially alter startup or tool-routing semantics, say whether the current thread should reload docs or whether a fresh session is recommended.

## Repo Git Contract

- Authoritative base: `<branch or ref>`
- Protected refs or remotes: `<repo-specific list>`
- Isolation pattern for parallel work: `<worktree, clone, or repo-native rule>`
- Thread closeout mode: `<integrate or pull_request>`
- Integration task classes: `<classes allowed to select ready PR refs and advance the authoritative base>`
- Route routine lifecycle mechanics through the installed environment lane or this repo's explicitly owned tooling guide; keep generic Git and approval playbooks out of this file.
- Read-only work may stay in place. Before the first ordinary Git-backed mutation, automatically preflight and enter the exact managed task worktree. Ordinary prompts should concern the work, then conversational `end -yes`, which follows the declared closeout mode. In pull-request mode ordinary tasks publish verified PRs and retire locally; only declared integration task classes select ready refs and advance the authoritative base.

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
