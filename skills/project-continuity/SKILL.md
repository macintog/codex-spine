---
name: project-continuity
description: Keep long-lived projects aligned on product purpose while deep technical work moves through narrow local failure modes. Use when standing up a new multi-session project or when restructuring an existing project whose docs mix durable intent with volatile execution state.
metadata:
  short-description: Create a compact continuity contract plus checkpoint structure for multi-session continuity
---

# Project Continuity

Use this skill when a project is large enough, long-lived enough, or drift-prone enough that an agent can lose the product thread while working deep in one subsystem.

The goal is not more documentation. The goal is a compact continuity design that answers, at startup, what the project is for, what success means, what strategy is active, what subproblem is current, and why that subproblem matters.

This skill designs the continuity packet and file roles. Concrete bootstrap tools, memory retrieval, Git lifecycle, indexing, and local proof commands belong to the repo's environment docs and tooling guide.

## Core Output

Produce or repair a continuity contract with:

- a compact durable project authority
- a small volatile handoff
- a short repo-local working-rules surface
- archive references for older detail
- clear on-demand pointers to deeper docs, skills, and tooling lanes
- explicit topology signposts when adjacent repos or generated checkouts affect reasoning

Routine startup should be cheap. Deeper history, subsystem notes, release playbooks, and tooling manuals should load only when the current task enters that lane.

## Templates And References

Use shipped scaffolds when creating or repairing a continuity packet:

- `templates/PROJECT_CONTINUITY.md`: durable project authority scaffold
- `templates/CHECKPOINT.md`: volatile handoff scaffold
- `templates/AGENTS.md`: repo-local working-rules scaffold
- `references/unseen-repo-adoption-prompt.md`: adoption prompt for first-pass continuity setup in an unfamiliar repo

## When To Use This Skill

- Standing up a new project likely to span multiple sessions.
- Restructuring continuity files that mix durable intent, volatile state, and history.
- Repairing context drift after local debugging crowded out the product goal.
- Simplifying a startup path that needs too many files to reload coherently.
- Adding or correcting topology signposts for adjacent repos, managed clones, exports, or downstream checkouts.

Do not force this pattern onto tiny, one-off, or throwaway repos.

## Continuity Worthiness And Location Contract

Continuity-worthiness is a local management choice, not a universal repo-quality claim. A healthy third-party or upstream repo may have no continuity packet.

For repos we actively manage over time, make ownership explicit instead of relying on filename inference:

- `repo-local`: in-tree continuity and indexing declarations, usually including `.codex/codex-spine.toml`
- `local-overlay`: external workspace overlay for repos that should stay clean in-tree
- `repo-native only`: no Codex continuity adoption; use the repo's own docs and conventions

Filename overlap, especially `AGENTS.md`, is not proof that a repo uses this continuity contract. Decide the posture before treating local overlay rules as native repo rules.

In a managed local workspace, every repo except obvious `scratch` space should be treated as continuity-worthy unless the user explicitly says otherwise. The steady state is not inferred coverage; a kept repo should be explicitly claimed as either `repo-local` or `local-overlay`.

Continuity-worthy repos should converge on declared locations: durable docs live under `docs/` by default, `.codex/indexes.toml` is the preferred declaration for code, docs, and dataset indexing targets, and `.codex/codex-spine.toml` is the in-tree ownership cookie when we have taken charge. Inference is a migration aid, not the target operating model.

## Startup Contract

For a project-continuity repo, the intended default startup packet is:

1. the environment's stock continuity/bootstrap lane when durable re-anchor is needed
2. project `AGENTS.md` if present
3. `PROJECT_CONTINUITY.md`
4. `CHECKPOINT.md`

Keep repo-local tooling guides, architecture references, and skill bodies out of routine startup. Load them just in time.

Inside the same thread, when the user shifts to a materially new request, keep the latest turn authoritative and add a short task restatement. Re-anchor only when durable grounding is needed: repo or `cwd` change, prior-thread reference, compaction drift, or an explicit reload request.

## File Roles

Use these roles unless the repo has a strong reason to differ.

### `README.md`

Human-facing entrypoint: overview, build/run path, and a short doc map. Do not let it become the rolling agent handoff.

### `PROJECT_CONTINUITY.md`

Compact durable startup authority, roughly 400 to 900 words. It should cover:

- `Purpose`
- `User / Operator Job`
- `Success Criteria`
- `Non-Goals`
- `Current Product Strategy`
- `Workstream Map`
- `Stable Constraints / Invariants`
- `Authority Map`

Add a short topology note when adjacent repos, isolated checkouts, companion source trees, or generated-but-preserved state materially affect project understanding.

### `CHECKPOINT.md`

Volatile plan of record, roughly 150 to 500 words. It should cover:

- `Current Focus`
- `Why Current Focus Matters`
- `Open Blockers / Decisions`
- `Validation Evidence`
- `Next Safe Step`
- `Archive References`

Keep only the current handoff here. Move older detail into themed or layered archive notes instead of adding live top-level sections.

When history still matters, archive it by theme or layer rather than keeping one rolling history file. Avoid extra top-level sections in `CHECKPOINT.md`; they usually mean archive material leaked back into the startup path.

### Project `AGENTS.md`

Repo-specific working rules and document update rules, short enough for routine load. Point to skills and on-demand tooling guides; do not inline their playbooks.

### Deep Docs And Tooling Guides

Architecture notes, safety docs, release playbooks, `TOOLING.md`, and subsystem references are on-demand. Startup docs may point to them, but should not force-load them.

### Index And Overlay Declarations

When supported, `.codex/indexes.toml` declares code, docs, and dataset indexing targets. For clean upstream repos managed by local overlay, use the external overlay registry expected by the local environment.

## Design Rules

- Give each file one audience and one refresh cadence.
- Keep durable product intent, repo-local working rules, volatile state, and dated history separate.
- Preserve intent over preserving old filenames.
- Keep startup cheap enough that reloading beats drifting.
- Prefer canonical declared locations over heuristics.
- Archive by theme or layer, not by growing one running log.
- Point to specialized skills and tooling only when the task actually enters their lane.
- If adjacent repos affect Git, maintenance, release, or export reasoning, signpost their role, whether they are preserved state or disposable, and which comparisons answer which question.

## Topology Signposts

When a project has managed clones, sibling checkouts, nested source trees, published trees, downstream QA checkouts, or long-lived side branches, add a brief signpost to the startup path.

Record:

- what the adjacent surface is
- why it exists
- whether it is disposable cache, companion source, downstream fork, public export, or preserved local state
- which branch or remote comparisons matter
- where destructive cleanup rules live

For release or publication stacks, name the surfaces explicitly: authoring source, release coordination notes, published tree, and QA checkout. If functional changes belong only in the authoring source, say that plainly.

## Verifiers And Self-Hosting

If a repo verifies continuity hygiene, make it fail on real contract breaks: missing required sections, runaway live handoff shape, boundary leaks, shipped interface drift, or leaked QA/destructive shortcuts. Keep exact prose drift advisory unless it breaks a real interface or routing anchor.

When startup docs, tooling guides, skill bodies, templates, generated config, launchers, or managed links change, treat that as a self-hosting change:

- update coordinated surfaces together
- verify the authoring source and any published surface that users inherit
- re-read changed startup or routing surfaces in-thread if semantics changed
- close out with reload expectations for current threads, new shells, app restarts, or reboots

Distinguish canonical source from installed copies. If the source lives elsewhere, treat the installed copy or cache as immutable instead of patching another maintainer's surface. Adapt in repo-owned docs, verifiers, wrappers, or overlays instead.

## Git Posture Signposts

Continuity docs do not own Git mechanics, but they should prevent Git-state ambiguity from becoming continuity drift. Own Git posture for the user in plain language, route routine local lifecycle through the local Git control plane in `codex/TOOLING.md`, and signpost the isolated-checkout pattern when parallel work or scratch state affects the project.
