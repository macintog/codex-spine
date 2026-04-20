---
name: project-continuity
description: Keep long-lived projects aligned on product purpose while deep technical work moves through narrow local failure modes. Use when standing up a new multi-session project or when restructuring an existing project whose docs mix durable intent with volatile execution state.
metadata:
  short-description: Create a compact continuity contract plus checkpoint structure for multi-session continuity
---

# Project Continuity

Use this skill when a project is large enough, long-lived enough, or drift-prone enough that the agent can lose the product thread while working deep in one subsystem.

The goal is not more documentation. The goal is a tighter startup contract:

- one compact durable project authority,
- one small volatile handoff,
- one small repo-local working-rules file,
- deeper docs only on demand,
- specialized skills and tooling guides only when the task actually enters their lane.

When this pattern is in place, baseline startup should happen automatically on the first turn. The user should not need to remember a startup macro just to recover the project's broad intent.

This skill does not own MCP routing. Concrete continuity/bootstrap tool use belongs to the stock Codex environment docs and tooling guide for the repo.

## When To Use This Skill

- Standing up a new project that is likely to span multiple sessions
- Restructuring an existing project with a mixed-lifetime continuity or handoff file
- Repairing context drift after repeated debugging loops caused the local symptom to crowd out the actual product goal
- Simplifying a startup path that currently requires too many files to reload coherently

Do not force this pattern onto tiny, one-off, or throwaway repos where the overhead is not justified.

## Continuity Worthiness And Location Contract

Continuity-worthiness is a project-management choice, not a universal statement about repo quality. The continuity packet is one management pattern for repos we intend to keep aligned over time; its absence in a healthy third-party or public upstream repo is not a defect.

By default, treat any real multi-session repo we are actively managing as continuity-worthy. Only obvious throwaway or scratch spaces are exempt.

In a managed local workspace, every repo except obvious `scratch` space should be treated as continuity-worthy unless the user explicitly says otherwise. The important step is to choose an explicit posture instead of leaving long-lived ownership or indexing assumptions on inference alone.

The explicit signal can be repo-local or workspace-local depending on the environment. Use the environment's documented local marker or external manifest when one exists, and do not infer ownership from packet-like filenames alone.

For external or upstream repos we do not own, first decide whether the right posture is:

- repo-native understanding only
- local continuity notes or support files outside the repo tree
- an in-tree continuity adoption because the repo is effectively becoming locally managed

Do not skip that posture check and then mistake a local continuity layer for the repo's native contract.

A public or upstream repo may also ship filenames that overlap with a local continuity packet, especially `AGENTS.md`. Treat those as repo-native surfaces until proven otherwise. Filename overlap alone is not evidence that the repo already uses your continuity contract.

Continuity-worthy repos should converge on declared locations so startup, indexing, and maintenance do not depend on guesswork:

- root startup docs live at `README.md`, `AGENTS.md`, `PROJECT_CONTINUITY.md`, and `CHECKPOINT.md`
- durable docs live under `docs/` by default; legacy `Docs/` is acceptable during migration, but converge toward one canonical docs root
- structured data intended for tabular retrieval lives under `data/` or `datasets/`, or is declared explicitly
- an explicit indexing declaration is the preferred contract for code, docs, and dataset targets when the environment supports it
- if your environment uses repo-local ownership markers or workspace-local manifests, keep them explicit and documented

Inference is a migration aid, not the target operating model. Use it to bootstrap coverage, then replace it with an explicit repo-local or workspace-local claim when the repo is worth keeping aligned over time. For blanket safe rollouts, prefer materializing workspace-local claims before attempting broad in-tree edits.

## Core Outcome

After the structure is in place, routine startup context should answer five questions without opening deep history docs:

1. What problem is this project solving?
2. What counts as success?
3. What strategy are we currently using?
4. What exact subproblem are we in right now?
5. Why does that subproblem matter to the actual product goal?

## Startup Contract

For project-continuity repos, the intended default startup packet is:

1. the environment's stock continuity/bootstrap lane
2. project `AGENTS.md` if present
3. `PROJECT_CONTINUITY.md`
4. `CHECKPOINT.md`

Use that automatically on the first assistant turn in a new thread.

Do not add repo-local tooling guides such as `TOOLING.md`, architecture references, or skill bodies to the default packet unless the user explicitly asked for that startup profile. Keep those on-demand so routine startup stays cheap.

Treat the stock continuity/bootstrap lane as the fast re-anchor path. Prefer it over spending startup turns trying to reconstruct equivalent context from ad hoc file reads.

Within the same thread, when the user shifts to a materially new request, keep that latest turn authoritative and add a short task-update restatement rather than reflexively treating bootstrap as the task switch. Reach for the stock lane when durable grounding is actually needed: repo or `cwd` change, prior-thread reference, or compaction-drift symptoms.

Reload that full startup packet when the repo or `cwd` changes, or when the user explicitly asks for a reload or named startup profile.

Across long-running threads, the durable invocation contract is:

- Call the environment's stock continuity/bootstrap lane on the first assistant turn in every new thread.
- When the user makes a materially new request in the same thread, keep that latest turn authoritative and add a short task-update restatement instead of treating bootstrap as the task switch.
- Call that lane on any repo or `cwd` change, any resume/prior-thread reference, and any compaction-drift symptoms inside the same task.
- Reload that full startup packet when the repo or `cwd` changes, or when the user explicitly asks for a reload or named startup profile.
- Treat automatic bootstrap as durable local context restoration only. It may restore project frame, durable constraints, historical open loops, and evidence refs, but it must not auto-recap prior task work or choose the next task.
- Treat these as compaction-drift symptoms inside the same task: needing to restate current state or assumptions after a long run, uncertainty about prior constraints or conclusions, or user signals such as "we already covered this" or "you lost context."
- If compaction or drift removed the live task, use the stock lane, restate the current task before proceeding, and use the repo's stock memory-retrieval lane to fetch the last few user or assistant turns if the task is still unclear.
- When reconstructing recent assistant state from retrieval, preserve whether it was an in-progress working update or a final answer.
- If the same symptom survives two attempted fixes, stop direct retrying, re-anchor with the stock continuity lane, then use the repo's stock memory-retrieval lane before proposing another fix.
- Mention continuity or retrieval use only when it materially changed grounding, retrieved prior decisions, or caused a strategy change.

## Default File Roles

Use these roles unless the repo has a strong reason to differ:

- `README.md`
  - human-facing repo entrypoint
  - keep overview, build or run path, and a short doc map
  - do not let it become the rolling agent continuity file

- `PROJECT_CONTINUITY.md`
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
  - add a compact topology note when the project includes non-obvious adjacent repos, managed clones, isolated checkouts, or companion source checkouts that materially affect how the project should be understood at startup

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
  - keep only the current session-to-session handoff here; move older detail out instead of letting slices accumulate in place
  - when history still matters, archive it by theme or layer such as `docs/checkpoints/archive/ui/`, `docs/checkpoints/archive/updater/`, or `docs/checkpoints/archive/release/` rather than one rolling history file
  - keep the top-level section shape stable; extra top-level sections in `CHECKPOINT.md` usually mean archive material leaked back into the startup path

- project `AGENTS.md`
  - repo-specific working rules and document update rules
  - target size: roughly 150 to 700 words unless repo complexity clearly justifies more
  - keep it short enough to load routinely
  - point to specialized skills or on-demand tooling guides instead of inlining their whole playbooks
  - keep it as a routing and local-rules file, not a second skill body
  - if a rule needs dated evidence, repeated examples, or deep subsystem nuance, move that material into a durable deep doc or archive and leave only the routing summary here

- deep docs such as `Docs/ARCHITECTURE.md`, `Docs/SAFETY.md`, design notes, or references
  - on-demand only
  - prefer `docs/` as the canonical location for these materials in new or actively maintained repos

- repo-local tooling guides such as `TOOLING.md`
  - on-demand tool-routing docs for named lanes such as indexed code navigation, authenticated forge flows, or release QA
  - not part of the routine startup packet
  - load only the relevant section when the task clearly needs that tool path

- dated session or tuning notes
  - archive them outside the startup path

- `.codex/indexes.toml` when the environment supports it
  - explicit indexing contract for code, docs, and datasets
  - keep it aligned with the repo's real location contract instead of relying on inferred fallback

## Design Rules

- Give each file one audience and one refresh cadence.
- Do not mix durable product intent, repo-local working rules, volatile execution state, and dated history in one file.
- Do not let a temporary debugging issue rewrite the project purpose.
- Prefer preserving intent over preserving old filenames.
- Keep the startup path compact enough that reloading it is cheaper than drifting away from it.
- Prefer themed or layered archive surfaces over one monolithic history file. A small live checkpoint plus archive references is easier to search and cheaper to reload than a single running log.
- Prefer canonical locations over heuristics. If a repo keeps forcing agents to rediscover where docs or datasets live, move those materials or declare them explicitly instead of teaching more fallback rules.
- On long-running threads, do not make same-thread re-anchor repay the whole startup packet unless the repo changed or the user explicitly asked for a reload.
- Keep specialized tool-routing rules and skill bodies out of routine startup. Mention them from startup docs, then load them just in time when the task actually needs them.
- When the project contains adjacent repos, managed dependency clones, or companion source checkouts that are operationally important, add a durable signpost in the startup path instead of assuming future sessions will infer their role from scripts or Git remotes.
- For any non-obvious adjacent repo that changes how Git or maintenance reasoning works, document four things explicitly: its role, whether it is disposable or preserved state, the live integration path it powers, and the authoritative comparison axes for Git state.
- If Git state has multiple meanings, separate them in words. For example, distinguish backup integrity from upstream intake instead of collapsing both into one ahead/behind judgment.

## On-Demand Tooling And Skills

Startup docs should tell future sessions where deeper operational guidance lives without forcing that guidance into every turn.

- If the repo provides a tool-routing guide such as `TOOLING.md`, keep it outside the default startup packet and load only the relevant section when the task enters one of its named domains.
- If a named skill and a repo-local tooling guide both apply, use the skill for scoping and decision rules, then use the tooling guide for MCP and other concrete local routes.
- Favor progressive disclosure: startup packet first, then one relevant skill or tooling section, then deeper references only if still needed.
- If the same tool path keeps getting rediscovered ad hoc, that is evidence the startup docs should point to an on-demand tooling guide more clearly.

## Verifiers And Self-Hosting

- If the repo has a verifier, use it to enforce file roles, shipped interfaces, stable routing anchors, scope or boundary checks, and concrete behavior contracts.
- Do not let a verifier fail hard on exact sentence-level copies of docs or skills. Phrase drift belongs in review or advisory output unless it breaks a real interface, boundary, or routing anchor.
- When a repo verifier owns continuity hygiene, make it fail on clear checkpoint-archive drift such as extra top-level sections beyond the canonical checkpoint headings. Keep exact word budgets configurable, but enforce some compactness boundary so `CHECKPOINT.md` cannot silently become a history file.
- Apply the same hygiene to `AGENTS.md` when the repo self-hosts a continuity contract there. Guard against obvious routing drift such as unexpected heading ladders, runaway word count, or embedded subsystem playbooks that belong in deep docs.
- If the intended operator contract is "latest compatible", encode that as compatibility ranges or ceilings rather than exact third-party version pins. Exact pins need explicit user direction or concrete breakage evidence.
- If QA or fixture automation needs a consent, acknowledgement, or destructive-confirmation shortcut, keep that shortcut out of shipped production CLIs, docs, config, and exported surfaces. Treat any leaked bypass flag or hidden escape hatch as a verify failure.
- When a repo mutates its own startup docs, tooling guides, skill bodies or templates, generated config, launchers, or managed links, treat that as a self-hosting change.
- Distinguish canonical source from installed copies. If the repo originated the source, edit the canonical source and resync managed copies; if the source is third-party or plugin-provided, treat the installed copy or cache as immutable and adapt in repo-owned docs, verifiers, or wrappers instead of patching another maintainer's surface.
- For self-hosting changes, update the coordinated surfaces together and close out with explicit reload expectations: whether the current thread should reload docs, whether a fresh Codex session or relaunch is recommended, and whether new shells, app restarts, or reboots are affected.
- If a self-hosting change materially alters startup or tool-routing semantics, re-read the changed understanding surfaces before continuing in the same thread.
- For source/export/downstream stacks, keep the downstream public repo as a pure materialization of the canonical source rather than a second authoring lane. Keep the canonical public-safe tree inside the source repo free of local noise such as `.DS_Store`, `__pycache__`, and other generated residue; prefer export-lane pruning plus verify enforcement over ad hoc manual cleanup.

## Topology Signposts

Continuity is not only about files in the root repo. It is also about making project shape legible enough that future sessions do not have to reverse-engineer it.

When a project includes managed clones, sibling isolated checkouts, nested source checkouts, generated-but-preserved state, or other adjacent repos that materially change decisions, surface them in routine startup context.

- For source/export/downstream stacks, classify the adjacent surfaces explicitly before planning or implementation: canonical source repo, any private export control layer, public-safe source tree, and downstream or materialized QA checkout.
- For source/export/downstream stacks, document whether the downstream checkout is a blessable materialization only or an actual authoring surface. If it is materialization-only, say plainly that functional changes belong in the canonical source and flow downstream through export.
- If a public repo is intentionally published as a rewritten current snapshot, document both surfaces explicitly: the local authoring branch or checkout that keeps real history, and the public snapshot branch that is safe to rewrite.

The signpost does not need to be large. It should be just enough to prevent re-discovery:

- what the adjacent repo or checkout is
- why it exists
- whether it is a disposable cache, a live companion source checkout, a downstream fork, an upstream mirror, or preserved local state
- which branch or remote comparisons answer which question
- where destructive cleanup rules for that surface live

When long-lived side branches materially affect reasoning, record their role explicitly instead of letting names or age stand in for meaning. Useful branch-role labels include:

- shared base
- active topic branch
- preserved selective-salvage source
- preserved major workstream

If a branch is preserved only as an idea source, say so plainly and state that it is not a wholesale merge target.

Prefer the split by audience:

- `PROJECT_CONTINUITY.md`: durable explanation of role and why it matters to the product or operator job
- project `AGENTS.md`: operational Git and cleanup interpretation rules
- `README.md`: short human-facing map when operators are likely to touch the surface directly

If the same adjacent repo or path has to be re-explained in multiple sessions, that is evidence the startup contract is missing a topology signpost.

## Cleanup Gate

- Own Git posture for the user in plain language. Translate outcome-shaped Git requests into the recommended change-lifecycle plan instead of asking the user to pick mechanics by label.
- When work includes branch pruning, ref deletion, archive removal, or other destructive cleanup, define the shared base and preserved state before cleanup begins.
- Treat Git warnings during deletion as blockers.
- If the proof disagrees, or the repo's branch roles are unclear, stop cleanup, checkpoint the discrepancy, and preserve state until clarified.
- When a repo has long-lived side branches or non-obvious branch roles, record the cleanup rules in project `AGENTS.md` instead of improvising them mid-task.
- Make Git posture legible for the operator: record the shared base, any preferred isolated-checkout pattern for parallel Codex work, and whether ambiguous preservation or ownership choices require a short clarifying question before history moves.

## Migration Workflow

When restructuring an existing repo:

1. Identify the current mixed-lifetime files.
2. Classify each section by lifetime:
   - durable project truth,
   - repo-local operating rule,
   - volatile current state,
   - dated history.
3. Move content by lifetime into `PROJECT_CONTINUITY.md`, `AGENTS.md`, `CHECKPOINT.md`, or an archive.
4. Rewrite `README.md` back to a human-facing entrypoint.
5. Move durable docs toward a canonical `docs/` location and declare indexing targets explicitly when supported, or use an external manifest when keeping the repo clean in-tree is the safer posture.
6. Tighten deep docs so they contain only deep technical or safety material.
7. Delete or retire the mixed-lifetime continuity file once its contents are redistributed.

If a current doc is mostly history, archive it instead of trying to save it as an authority.

For unseen or dirty repos, treat prompt-first adoption as the default path before building scripts. Start with a careful audit and a conservative proposed steady-state contract, then automate only the pieces that repeat cleanly. When a user explicitly wants a blanket safe sweep across many repos, prefer explicit local notes or manifests first and reserve repo-local promotion for the repos that truly benefit from in-tree continuity files. A reusable reference prompt lives at `references/unseen-repo-adoption-prompt.md`.

## Maintenance Loop

Refresh `PROJECT_CONTINUITY.md` only when durable strategy actually changes, such as:

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
This includes changes to shared-branch roles, Git interpretation rules, or cleanup gates for adjacent repos and managed clones.
If a repo self-hosts its own understanding surfaces, refresh `AGENTS.md` or the relevant tooling guide when reload or relaunch handling changes.

## Failure Modes To Avoid

- turning `PROJECT_CONTINUITY.md` into a second checkpoint
- letting `CHECKPOINT.md` become a mini diary or archive
- letting `AGENTS.md` become a second safety manual, architecture note, or skill body
- storing product strategy only in old session notes
- making startup depend on too many files
- stuffing startup docs with detailed tool-routing playbooks that should live in an on-demand tooling guide instead
- loading specialized skill bodies or tooling guides by default instead of only when the task needs them
- letting a verifier become a hidden co-author of docs by freezing exact prose instead of enforcing real contracts
- letting hidden QA-only consent or confirmation bypasses leak into shipped user-facing surfaces
- pinning exact third-party versions when the real product contract is "latest compatible"
- preserving a confused continuity file out of habit
- copying a reference project's exact filenames or machinery when only the role split matters
- letting hygiene work outrank preservation of unmerged work
- leaving non-obvious adjacent repos or managed clones undocumented so every session has to rediscover their role
- leaving long-lived side branches unclassified so future sessions have to infer whether they are merge targets, idea sources, or preserved workstreams from Git history alone
- collapsing multi-axis Git state into one vague ahead/behind statement when different comparisons answer different operational questions
- treating raw exit codes as self-explanatory branch-safety conclusions
- deleting refs after Git warns they are not merged
- performing destructive cleanup before writing down the shared base and recovery path
- failing to consult the repo's named skill or tooling guide when the task clearly enters that domain, and then reinventing a weaker path from scratch
- changing self-hosted startup, tooling, or skill surfaces without stating whether the current thread should reload docs or whether a fresh session is advisable
- treating a real long-lived repo like a scratchpad and then expecting indexing or startup to stay accurate through heuristics alone

## Templates

Use the templates in this skill directory as scaffolding, not as a substitute for understanding:

- `templates/PROJECT_CONTINUITY.md`
- `templates/CHECKPOINT.md`
- `templates/AGENTS.md`
- `references/unseen-repo-adoption-prompt.md`

Adjust wording to the real project. Do not leave placeholder prose in a live repo.
