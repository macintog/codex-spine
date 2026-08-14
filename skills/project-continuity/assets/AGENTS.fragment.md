# Project Agent Guide Fragment

<!-- Merge this scaffold into the applicable AGENTS.md and AGENTS.override.md instruction chain. Do not replace native or directory-scoped guidance. Replace every angle-bracket placeholder and delete this comment. -->

Routine startup context for this project is:

1. the applicable `AGENTS.md` and `AGENTS.override.md` chain for the current working directory
2. `PROJECT_CONTINUITY.md`
3. `CHECKPOINT.md`

## Working Rules

- `<repo-specific execution rule>`
- `<repo-specific validation rule>`
- Open deeper docs, skills, and tooling lanes only when the task needs them.
- Use a repo-local tooling guide only when this repository explicitly claims it.

## Git And Mutation Contract

- Authoritative state or base: `<branch, ref, release, dataset, or non-Git authority>`
- Lifecycle policy: `<path to the repository's declared isolation, publication, and closeout policy, or none>`
- Integration authority and exceptions: `<owner, task class, or not applicable; repo-specific exceptions only>`
- Follow that declared policy; do not infer a worktree, commit, push, merge, cleanup, or publication policy from this continuity scaffold.
- If no policy exists, preserve current repository state and request authority only when a consequential Git action is required.

## Understanding Surfaces

- Treat self-hosted startup, tooling, generated, installed, validation, and shipped surfaces as one contract. When semantics change, state the required doc reload, fresh session, shell, app, or machine restart.

## Document And Update Rules

- `README.md`: human entrypoint
- `PROJECT_CONTINUITY.md`: durable purpose, strategy, constraints, and authority; update only for durable change
- `CHECKPOINT.md`: advisory prior state, evidence, blockers, and a non-directive next-step candidate; never current-task authority
- Native documentation tree: durable architecture, decisions, safety, and operations
- Archive: themed historical evidence; move displaced history here and leave a narrow pointer
- Environment-specific declarations: use only when their schema and owner are explicitly defined
- Nested checkpoints, queues, next prompts, rubrics, and task-local control planes cannot select or generate work; a separately adopted nested project needs its own complete packet.
