# Project Continuity

This is the compact durable startup authority for this project. Use it to keep purpose, success, strategy, and stable constraints visible when local work gets narrow.

Read it after the project `AGENTS.md` and before `CHECKPOINT.md` on first turn or repo or `cwd` change. Keep re-anchor mechanics, deep-doc routing, and reload or relaunch handling in `AGENTS.md` and `CHECKPOINT.md`. If the repo self-hosts the startup docs, tooling guides, skills, generated config, or launchers that agents rely on, record the durable relationship in `Stable Constraints / Invariants`.

## Purpose

- What the project exists to do.
- The real user or product problem being solved.
- Why this project matters when deep technical work gets narrow.

## User / Operator Job

- Who is using or operating the system.
- What they need the project to help them do.
- What kind of trust, control, or visibility they expect.

## Success Criteria

- The concrete outcomes that mean the project is working.
- Product-level or operator-visible wins that should steer prioritization.

## Non-Goals

- What the project is not trying to optimize for.
- What kinds of tempting side quests should not redefine the effort.

## Current Product Strategy

- The current strategy for achieving the project goal.
- The framing that should remain visible even during local debugging.

## Workstream Map

- The main lanes of work in the project.
- Each line should describe a durable area, not a one-session task.

## Repository Topology / Adjacent Managed Repos

- Optional section. Use when sibling repos, managed clones, worktrees, generated-but-preserved state, or companion source checkouts materially affect startup understanding.
- For each important adjacent surface, state its role, why it exists, whether it is disposable or preserved state, and what live path or runtime surface it powers.
- If parallel Codex work should use a preferred worktree pattern, record it here and keep the stricter cleanup rules in `AGENTS.md`.
- If Git interpretation differs by comparison target, name those axes explicitly here and put the stricter cleanup rules in `AGENTS.md`.

## Stable Constraints / Invariants

- Durable environment, data, architecture, or operating facts.
- Stable paths, source-of-truth files, or boundaries that should survive across sessions.
- Location contract for continuity-critical material. Record where durable docs live, where structured datasets live, and whether `.codex/indexes.toml` is the explicit indexing contract.
- If the repo self-hosts its own understanding surfaces, state which ones they are and whether verification is behavior-first, anchor-based, or only advisory for wording drift.

## Authority Map

- `README.md`: human entrypoint
- `AGENTS.md`: repo-specific working rules
- `CHECKPOINT.md`: current focus and next safe step
- Tooling guides and specialized skills: on-demand only
- Deep reference docs: on-demand only
- Archive: dated history only
