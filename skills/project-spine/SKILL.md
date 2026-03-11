---
name: project-spine
description: Keep long-lived projects aligned on product purpose while deep technical work moves through narrow local failure modes. Use when standing up a new multi-session project or when restructuring an existing project whose docs mix durable intent with volatile execution state.
metadata:
  short-description: Create a compact project spine plus checkpoint structure for multi-session continuity
---

# Project Spine

Use this skill when a project is large enough, long-lived enough, or drift-prone enough that the agent can lose the product thread while working deep in one subsystem.

The goal is not more documentation. The goal is a tighter startup contract:

- one compact durable project authority,
- one small volatile handoff,
- one small repo-local working-rules file,
- deeper docs only on demand.

When this pattern is in place, baseline startup should happen automatically on the first turn. The user should not need to remember a startup macro just to recover the project's broad intent.

## When To Use This Skill

- Standing up a new project that is likely to span multiple sessions
- Restructuring an existing project with a mixed-lifetime continuity or handoff file
- Repairing context drift after repeated debugging loops caused the local symptom to crowd out the actual product goal
- Simplifying a startup path that currently requires too many files to reload coherently

Do not force this pattern onto tiny, one-off, or throwaway repos where the overhead is not justified.

## Core Outcome

After the structure is in place, routine startup context should answer five questions without opening deep history docs:

1. What problem is this project solving?
2. What counts as success?
3. What strategy are we currently using?
4. What exact subproblem are we in right now?
5. Why does that subproblem matter to the actual product goal?

## Startup Contract

For spine-based projects, the intended default startup packet is:

1. `memory.bootstrap_context`
2. project `AGENTS.md` if present
3. `PROJECT_SPINE.md`
4. `CHECKPOINT.md`

Use that automatically on the first assistant turn in a new thread, and reload that startup packet when the same thread shifts to a materially new request or shows compaction drift. If the user explicitly asks for a reload or a named profile, honor that in plain language rather than depending on a dedicated startup macro.

Across long-running threads, the durable invocation contract is:

- Call `memory.bootstrap_context` on the first assistant turn in every new thread.
- Call `memory.bootstrap_context` at the start of any materially new user request in the same thread.
- Call `memory.bootstrap_context` on any repo or `cwd` change, any resume/prior-thread reference, and any compaction-drift symptoms inside the same task.
- Treat automatic bootstrap as durable local context restoration only. It may restore project frame, durable constraints, historical open loops, and evidence refs, but it must not auto-recap prior task work or choose the next task.
- Treat these as compaction-drift symptoms inside the same task: needing to restate current state or assumptions after a long run, uncertainty about prior constraints or conclusions, or user signals such as "we already covered this" or "you lost context."
- If the same symptom survives two attempted fixes, stop direct retrying, re-anchor with `memory.bootstrap_context`, then use direct `memory` retrieval before proposing another fix.
- The `memory` server also exposes direct retrieval tools: `status`, `deep_search`, `search`, `vector_search`, `get`, and `multi_get`.
- If a client reaches for generic MCP resources, `memory` may serve bootstrap or project-memory resources, but the normal workflow should still prefer its tools.
- If `memory.bootstrap_context` fails (startup timeout, handshake error, or unavailable), immediately fallback to `~/.local/bin/qmd-memory-latest.sh`, summarize its output, and continue.
- Use direct memory retrieval, not bootstrap, when you need prior task wording or broader historical evidence.
- Use exact `search` for the same bug, identifiers, or literal symptom wording.
- Use `deep_search` for analogous prior contours or decision patterns.
- Use `vector_search` when semantic similarity is wanted without reranking overhead.
- Use `get` or `multi_get` on the best matches before continuing.
- Mention memory/QMD use only when it materially changed grounding, retrieved prior decisions, or caused a strategy change.

## Default File Roles

Use these roles unless the repo has a strong reason to differ:

- `README.md`
  - human-facing repo entrypoint
  - keep overview, build or run path, and a short doc map
  - do not let it become the rolling agent continuity file

- `PROJECT_SPINE.md`
  - compact durable startup authority
  - target size: roughly 400 to 900 words
  - required sections:
    - `Purpose`
    - `User / Operator Job`
    - `Success Criteria`
    - `Non-Goals`
    - `Current Product Strategy`
    - `Workstream Map`
    - `Stable Constraints / Invariants`
    - `Authority Map`

- `CHECKPOINT.md`
  - volatile plan-of-record
  - target size: roughly 150 to 500 words
  - required sections:
    - `Current Focus`
    - `Why Current Focus Matters`
    - `Open Blockers / Decisions`
    - `Validation Evidence`
    - `Next Safe Step`
    - `Archive References`

- project `AGENTS.md`
  - repo-specific working rules and document update rules
  - keep it short enough to load routinely

- deep docs such as `Docs/ARCHITECTURE.md`, `Docs/SAFETY.md`, design notes, or references
  - on-demand only

- dated session or tuning notes
  - archive them outside the startup path

## Design Rules

- Give each file one audience and one refresh cadence.
- Do not mix durable product intent, repo-local working rules, volatile execution state, and dated history in one file.
- Do not let a temporary debugging issue rewrite the project purpose.
- Prefer preserving intent over preserving old filenames.
- Keep the startup path compact enough that reloading it is cheaper than drifting away from it.

## Migration Workflow

When restructuring an existing repo:

1. Identify the current mixed-lifetime files.
2. Classify each section by lifetime:
   - durable project truth,
   - repo-local operating rule,
   - volatile current state,
   - dated history.
3. Move content by lifetime into `PROJECT_SPINE.md`, `AGENTS.md`, `CHECKPOINT.md`, or an archive.
4. Rewrite `README.md` back to a human-facing entrypoint.
5. Tighten deep docs so they contain only deep technical or safety material.
6. Delete or retire the mixed-lifetime continuity file once its contents are redistributed.

If a current doc is mostly history, archive it instead of trying to save it as an authority.

## Maintenance Loop

Refresh `PROJECT_SPINE.md` only when durable strategy actually changes, such as:

- the project goal sharpens,
- success criteria change,
- non-goals become explicit,
- the main product strategy or workstream map changes.

Refresh `CHECKPOINT.md` whenever execution state changes, especially:

- automatic first-turn startup or session restart,
- explicit closeout or wrap-up requests,
- major workstream shift,
- failure-loop reset after one or two unsuccessful fix attempts,
- new validation evidence,
- a newly blocked decision.

Refresh project `AGENTS.md` only for repo-specific working rules that materially affect how work is performed.

## Failure Modes To Avoid

- turning `PROJECT_SPINE.md` into a second checkpoint
- letting `CHECKPOINT.md` become a mini diary or archive
- storing product strategy only in old session notes
- making startup depend on too many files
- preserving a confused continuity file out of habit
- copying a reference project's exact filenames or machinery when only the role split matters

## Templates

Use the templates in this skill directory as scaffolding, not as a substitute for understanding:

- `templates/PROJECT_SPINE.md`
- `templates/CHECKPOINT.md`
- `templates/AGENTS.md`

Adjust wording to the real project. Do not leave placeholder prose in a live repo.
