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
- deeper docs only on demand,
- specialized skills and tooling guides only when the task actually enters their lane.

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

1. direct `memory.bootstrap_context` tool call
2. project `AGENTS.md` if present
3. `PROJECT_SPINE.md`
4. `CHECKPOINT.md`

Use that automatically on the first assistant turn in a new thread.

Do not add repo-local tooling guides such as `TOOLING.md`, architecture references, or skill bodies to the default packet unless the user explicitly asked for that startup profile. Keep those on-demand so routine startup stays cheap.

Treat `memory.bootstrap_context` as the fast bootstrap tool lane. Prefer calling it directly instead of spending startup turns trying to open an equivalent file or generic resource view first.

Within the same thread, when the user shifts to a materially new request, a prior-thread reference, or compaction-drift symptoms, start by re-anchoring with `memory.bootstrap_context` rather than reloading the full startup packet.

Reload that full startup packet when the repo or `cwd` changes, or when the user explicitly asks for a reload or named startup profile.

Across long-running threads, the durable invocation contract is:

- Call `memory.bootstrap_context` on the first assistant turn in every new thread.
- Call `memory.bootstrap_context` at the start of any materially new user request in the same thread.
- When the same thread shifts to a materially new request, a prior-thread reference, or compaction-drift symptoms, start by re-anchoring with `memory.bootstrap_context` rather than reloading the full startup packet.
- Call `memory.bootstrap_context` on any repo or `cwd` change, any resume/prior-thread reference, and any compaction-drift symptoms inside the same task.
- Reload that full startup packet when the repo or `cwd` changes, or when the user explicitly asks for a reload or named startup profile.
- Treat automatic bootstrap as durable local context restoration only. It may restore project frame, durable constraints, historical open loops, and evidence refs, but it must not auto-recap prior task work or choose the next task.
- Treat these as compaction-drift symptoms inside the same task: needing to restate current state or assumptions after a long run, uncertainty about prior constraints or conclusions, or user signals such as "we already covered this" or "you lost context."
- If the same symptom survives two attempted fixes, stop direct retrying, re-anchor with `memory.bootstrap_context`, then use direct `memory` retrieval before proposing another fix.
- The `memory` server also exposes direct retrieval tools: `status`, `deep_search`, `search`, `vector_search`, `get`, and `multi_get`.
- If a client also exposes memory resource reads such as `bootstrap_context` or scoped `qmd://codex-chat/...` URIs, treat them as optional read helpers. The normal startup and re-anchor workflow should still prefer direct memory tool calls.
- If `memory.bootstrap_context` fails (startup timeout, handshake error, or unavailable), immediately fallback to `~/.local/bin/qmd-memory-latest.sh`, which is project-scoped and fail-closed, summarize its output, and continue.
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
  - add a compact topology note when the project includes non-obvious adjacent repos, managed clones, worktrees, or companion source checkouts that materially affect how the project should be understood at startup

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
  - point to specialized skills or on-demand tooling guides instead of inlining their whole playbooks
  - keep it as a routing and local-rules file, not a second skill body

- deep docs such as `Docs/ARCHITECTURE.md`, `Docs/SAFETY.md`, design notes, or references
  - on-demand only

- repo-local tooling guides such as `TOOLING.md`
  - on-demand tool-routing docs for named lanes such as indexed code navigation, authenticated forge flows, or release QA
  - not part of the routine startup packet
  - load only the relevant section when the task clearly needs that tool path

- dated session or tuning notes
  - archive them outside the startup path

## Design Rules

- Give each file one audience and one refresh cadence.
- Do not mix durable product intent, repo-local working rules, volatile execution state, and dated history in one file.
- Do not let a temporary debugging issue rewrite the project purpose.
- Prefer preserving intent over preserving old filenames.
- Keep the startup path compact enough that reloading it is cheaper than drifting away from it.
- On long-running threads, do not make same-thread re-anchor repay the whole startup packet unless the repo changed or the user explicitly asked for a reload.
- Keep specialized tool-routing rules and skill bodies out of routine startup. Mention them from startup docs, then load them just in time when the task actually needs them.
- When the project contains adjacent repos, managed dependency clones, or companion source checkouts that are operationally important, add a durable signpost in the startup path instead of assuming future sessions will infer their role from scripts or Git remotes.
- For any non-obvious adjacent repo that changes how Git or maintenance reasoning works, document four things explicitly: its role, whether it is disposable or preserved state, the live integration path it powers, and the authoritative comparison axes for Git state.
- If Git state has multiple meanings, separate them in words. For example, distinguish backup integrity from upstream intake instead of collapsing both into one ahead/behind judgment.

## On-Demand Tooling And Skills

Startup docs should tell future sessions where deeper operational guidance lives without forcing that guidance into every turn.

- If the repo provides a tool-routing guide such as `TOOLING.md`, keep it outside the default startup packet and load only the relevant section when the task enters one of its named domains.
- If a named skill and a repo-local tooling guide both apply, use the skill for scoping and decision rules, then use the tooling guide for the concrete local route.
- Favor progressive disclosure: startup packet first, then one relevant skill or tooling section, then deeper references only if still needed.
- If the same tool path keeps getting rediscovered ad hoc, that is evidence the startup docs should point to an on-demand tooling guide more clearly.

## Verifiers And Self-Hosting

- If the repo has a verifier, use it to enforce file roles, shipped interfaces, stable routing anchors, scope or boundary checks, and concrete behavior contracts.
- Do not let a verifier fail hard on exact sentence-level copies of docs or skills. Phrase drift belongs in review or advisory output unless it breaks a real interface, boundary, or routing anchor.
- When a repo mutates its own startup docs, tooling guides, skill bodies or templates, generated config, launchers, or managed links, treat that as a self-hosting change.
- For self-hosting changes, update the coordinated surfaces together and close out with explicit reload expectations: whether the current thread should reload docs, whether a fresh Codex session or relaunch is recommended, and whether new shells, app restarts, or reboots are affected.
- If a self-hosting change materially alters startup or tool-routing semantics, re-read the changed understanding surfaces before continuing in the same thread.

## Topology Signposts

Continuity is not only about files in the root repo. It is also about making project shape legible enough that future sessions do not have to reverse-engineer it.

When a project includes managed clones, sibling worktrees, nested source checkouts, generated-but-preserved state, or other adjacent repos that materially change decisions, surface them in routine startup context.

- For source/export/downstream stacks, classify the adjacent surfaces explicitly before planning or implementation: canonical source repo, private export or maintainer control plane, public-safe source tree, and downstream or materialized QA checkout.

The signpost does not need to be large. It should be just enough to prevent re-discovery:

- what the adjacent repo or checkout is
- why it exists
- whether it is a disposable cache, a live companion source checkout, a downstream fork, an upstream mirror, or preserved local state
- which branch or remote comparisons answer which question
- where destructive cleanup rules for that surface live

When long-lived side branches materially affect reasoning, record their role explicitly instead of letting names or age stand in for meaning. Useful branch-role labels include:

- shared or authoritative base
- active topic branch
- preserved selective-salvage source
- preserved major workstream

If a branch is preserved only as an idea source, say so plainly and state that it is not a wholesale merge target.

Prefer the split by audience:

- `PROJECT_SPINE.md`: durable explanation of role and why it matters to the product or operator job
- project `AGENTS.md`: operational Git and cleanup interpretation rules
- `README.md`: short human-facing map when operators are likely to touch the surface directly

If the same adjacent repo or path has to be re-explained in multiple sessions, that is evidence the startup contract is missing a topology signpost.

## Destructive Cleanup Gate

- When work includes branch pruning, ref deletion, archive removal, or other destructive cleanup, define the authoritative base and preserved state before cleanup begins.
- For Git cleanup, require a read-only proof packet before deletion:
  - a `unique-commit audit` against the authoritative base (`git log <base>..<branch>` or equivalent) that is empty
  - an ancestry or containment check whose result is stated in words, not raw exit codes
- Treat Git warnings during deletion as blockers.
- If the proof disagrees, or the repo's branch roles are unclear, stop cleanup, checkpoint the discrepancy, and preserve state until clarified.
- When a repo has long-lived side branches or non-obvious branch roles, record the cleanup rules in project `AGENTS.md` instead of improvising them mid-task.

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
- the main product strategy or workstream map changes,
- the set of adjacent repos or companion source checkouts that materially affect startup understanding changes.

Refresh `CHECKPOINT.md` whenever execution state changes, especially:

- automatic first-turn startup or session restart,
- explicit closeout or wrap-up requests,
- major workstream shift,
- failure-loop reset after one or two unsuccessful fix attempts,
- new validation evidence,
- a newly blocked decision.

Refresh project `AGENTS.md` only for repo-specific working rules that materially affect how work is performed.
This includes changes to authoritative branch roles, Git interpretation rules, or cleanup gates for adjacent repos and managed clones.
If a repo self-hosts its own understanding surfaces, refresh `AGENTS.md` or the relevant tooling guide when reload or relaunch handling changes.

## Failure Modes To Avoid

- turning `PROJECT_SPINE.md` into a second checkpoint
- letting `CHECKPOINT.md` become a mini diary or archive
- storing product strategy only in old session notes
- making startup depend on too many files
- stuffing startup docs with detailed tool-routing playbooks that should live in an on-demand tooling guide instead
- loading specialized skill bodies or tooling guides by default instead of only when the task needs them
- letting a verifier become a hidden co-author of docs by freezing exact prose instead of enforcing real contracts
- preserving a confused continuity file out of habit
- copying a reference project's exact filenames or machinery when only the role split matters
- letting hygiene work outrank preservation of unmerged work
- leaving non-obvious adjacent repos or managed clones undocumented so every session has to rediscover their role
- leaving long-lived side branches unclassified so future sessions have to infer whether they are merge targets, idea sources, or preserved workstreams from Git history alone
- collapsing multi-axis Git state into one vague ahead/behind statement when different comparisons answer different operational questions
- treating raw exit codes as self-explanatory branch-safety conclusions
- deleting refs after Git warns they are not merged
- performing destructive cleanup before writing down the authoritative base and recovery path
- failing to consult the repo's named skill or tooling guide when the task clearly enters that domain, and then reinventing a weaker path from scratch
- changing self-hosted startup, tooling, or skill surfaces without stating whether the current thread should reload docs or whether a fresh session is advisable

## Templates

Use the templates in this skill directory as scaffolding, not as a substitute for understanding:

- `templates/PROJECT_SPINE.md`
- `templates/CHECKPOINT.md`
- `templates/AGENTS.md`

Adjust wording to the real project. Do not leave placeholder prose in a live repo.
