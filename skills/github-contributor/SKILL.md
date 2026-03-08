---
name: github-contributor
description: Keep anything that may become public on GitHub professional, actionable, and maintainable by classifying components up front, centralizing public-facing standards, and preserving a clean path to export, release, or upstream contribution.
metadata:
  short-description: Canonical GitHub governance for public readiness, component intake, and upstreamability
---

# GitHub Contributor

Use this skill for work that may become public on GitHub, especially when adding or shaping tools, managed integrations, adapters, workflow assets, or public-facing operational surfaces.

This is the canonical umbrella for GitHub-facing quality in this environment. It centralizes the shared standards for component intake, boundary decisions, licensing posture, release readiness, upstreamability, and maintainer-grade citizenship so those lessons do not drift across separate skills.

## When To Use This Skill

- Adding, adopting, enabling, packaging, or publishing a new tool or component
- Deciding whether something belongs in `public-core`, `private-incubator`, or `local-only`
- Designing install, maintenance, optionality, licensing, or affiliation posture for public-facing integrations
- Reviewing whether a public candidate is ready to export or release
- Preparing a public repo or spin-out to stay professional and unsurprising over time
- Evaluating whether local work belongs upstream and how to separate it from local operational baggage

## Goals

- Classify boundary and maintainability before implementation drifts
- Keep public work professional, factual, and low-friction to inherit
- Separate public design fit from release or export readiness
- Preserve a clean path for optional third-party integrations with separate licensing or affiliation concerns
- Keep local-only and private-incubator work from leaking into public-core
- Centralize reusable GitHub-quality lessons in one canonical skill
- Make architecture legible to outside maintainers when a project is too complex for README-level documentation alone
- Use the right public doc surfaces instead of overloading the README or inventing ceremonial docs

## Phase 1: Classify Repo Role And Publication Target

Determine what kind of repo and publication target you are working in.

- Is this a private incubator, a public repo, a downstream fork, an upstream source repo, or a runtime or data directory?
- Is the relevant target local-only, `private-incubator`, `public-core`, downstream-only, or upstream-candidate?
- If the repo role and publication target are confused, stop and separate them before planning further work.

Do not let a repo's current directory layout substitute for an explicit boundary decision.

## Phase 2: Intake The Component Or Change

Before implementation, answer the component-intake questions explicitly.

- What problem does the tool or component solve?
- Who is the audience?
- Is it default or optional?
- Is it installed from upstream packages, a managed checkout, or a first-party implementation?
- What is the maintenance or update model?
- Does it imply any licensing, attribution, or affiliation posture?
- Is an upstream patch path expected?

If the answers are weak, the component is not ready for `public-core`.

## Phase 3: Decide Boundary Class Up Front

Every new tool or public-facing integration must be classified before it lands.

If you are working in the private source repo or incubator, use the full boundary model:

- `local-only`: personal services, accounts, tokens, trust lists, or machine-specific infrastructure
- `private-incubator`: promising for public use, but still wrong in structure for public inheritance
- `public-core`: generally useful, structurally clean, and appropriate for future public export

Default to `private-incubator` when a component is promising but not yet clean.

Keep this distinction explicit in the private source repo:

- `private-incubator`: not yet public in design
- `public-core` with separate release/export state: public in design, not yet ready to ship

If you are working in a standalone forwarded public repo, do not leak private source classifications into the public surface. Follow that repo's public-only schema instead.

## Phase 4: Leave A Durable Record

Do not rely on chat history for component governance.

- If the repo has a component registry, update it.
- If the repo lacks one and the project is long-lived, create one before more public-facing integration work proceeds.
- Record at minimum:
  - boundary class if the repo models boundary classes
  - the repo's chosen publication or release readiness fields
  - install model
  - maintenance model
  - upstream source
  - license and affiliation posture
  - optionality

Keep strategy in spine docs and per-component facts in the registry.

## Phase 5: Design For Public Inheritance

Shape the implementation so another user can inherit it without inheriting your machine.

- Remove personal hosts, accounts, absolute paths, and service assumptions from public candidates.
- Separate generic reusable logic from private operational glue.
- Prefer install and update flows that are coherent, repeatable, and explainable.
- For optional third-party integrations, make optionality, license posture, and affiliation boundaries explicit.
- Distinguish "fit for public design" from "finished enough to ship now."

README cleanup is not a substitute for a structurally public design.

### Forwarded Public Repos

If the public repo is a forwarded or exported surface from a private source repo:

- decide explicitly which side is canonical
- edit the canonical source first
- materialize the forwarded repo from that source
- verify the forwarded repo matches the canonical source after export

Do not treat the forwarded repo as a second authoring surface and sync back later by hand. That creates avoidable drift, especially in docs, manifests, and maintainer-facing references.

## Phase 6: Sweep The Full Public Surface

Before calling anything publication-ready, release-ready, or upstream-ready, inspect the adjacent surfaces.

Default surfaces to inspect:

- implementation logic
- wrappers and adapters
- config or manifests
- tests or validation
- docs, examples, and README transparency

Assume that GitHub-facing work almost never lives in one file.

## Phase 7: Choose The Right Public Doc Surfaces

Decide which public-facing docs are actually warranted.

Possible surfaces include:

- `README.md` for project entrypoint and doc map
- `USER_GUIDE.md` for practical workflows and operator guidance
- `SPEC.md` for stable interfaces, schemas, and guarantees
- `ARCHITECTURE.md` for subsystem boundaries, flows, and invariants
- `SECURITY.md` for threat model, reporting path, and trust boundaries
- `CHANGELOG.md` for real release history and user-visible change tracking

Create them when they have a real job. Do not create them just to imitate mature projects cosmetically.

Internal startup and maintainer-control docs are different:

- root `AGENTS.md`, `CHECKPOINT.md`, and `PROJECT_SPINE.md` are usually internal workflow surfaces, not public product docs
- QA or release-matrix files are usually internal release-management surfaces, not public product docs
- do not export those files into a public repo by default unless they are intentionally part of the shipped product or contributor workflow
- shipped runtime policy files such as `codex/AGENTS.md` can still belong in a public repo when they are part of the product itself
- when a forwarded public repo has a verifier, make it fail if those internal control files reappear or if public product docs start pointing back at internal source-repo surfaces

Reference checklist:
- `references/public-doc-surface-checklist.md`

## Phase 8: Keep Changelog Discipline For Public Releases

When a project has real public releases or externally consumed version history, maintain a high-signal `CHANGELOG.md`.

The changelog should document notable user-visible changes, especially:

- new capabilities
- breaking changes
- migration notes
- security-relevant fixes or hardening
- performance changes that materially affect user experience or cost
- deprecations, removals, and stability milestones

Do not mirror commit history or fill it with internal churn. Treat changelog upkeep as part of release readiness for public projects, not as optional cleanup later.

Reference checklist:
- `references/changelog-checklist.md`

## Phase 9: Maintain An Architecture Reference When Needed

For non-trivial public projects or shareable components, keep an `ARCHITECTURE.md` or equivalent deep reference doc.

The model to emulate is a concise technical map that explains:

- directory or subsystem structure
- end-to-end data or control flow
- key abstractions, invariants, or stable identifiers
- security or trust boundaries
- storage, caching, or update behavior
- important behavior-defining algorithms or scoring logic
- major external dependencies and why they exist

Use it as an on-demand maintainer document, not as part of the routine startup packet. It should describe the real current architecture, not an aspirational future one.

Reference checklist:
- `references/architecture-doc-checklist.md`

## Phase 10: Review Export And Release Readiness

Separate boundary class from shipping state.

Promotion from `private-incubator` to `public-core` requires:

- generic paths and assumptions
- settled install and maintenance model
- settled licensing and affiliation posture
- no personal-service dependency
- public docs can describe it honestly and clearly

For any repo that tracks publication or release readiness, the ready state requires:

- implementation complete enough to publish
- validation appropriate for the component
- README or public docs language ready
- changelog updated when the public release includes notable user-visible change
- no private references in exported config, scripts, or docs
- any optional third-party licensing UX in place

It is acceptable for structurally public work to remain not-yet-ready in either a private source repo or a forwarded public repo.

## Phase 11: Upstream Contribution Mode

When the same work also has an upstream patch path:

- prefer submitting the generic reusable core upstream while keeping local operational layers separate
- match established project patterns unless there is a strong reason not to
- keep tests neutral and domain-agnostic
- remove personal naming, private assumptions, and local automation baggage
- reduce the patch to only the still-unique value if upstream has moved
- prepare a concise submission summary that states the problem, approach, compatibility impact, tests, and follow-up intentionally excluded

## Common Failure Modes

Watch for these anti-patterns:

- adding a tool first and deciding the boundary later
- treating "not polished yet" as the same thing as `private-incubator`
- letting public-core accumulate private paths or personal services
- assuming README cleanup can fix a structurally private design
- treating a forwarded public repo as an independent authoring surface instead of a materialized export
- leaking private-source governance vocabulary into a forwarded public repo whose schema is intentionally narrower
- calling something public-ready while key optional dependencies still have unresolved license or affiliation posture
- relying on chat memory instead of a durable component record
- splitting GitHub-quality guidance across multiple skills until the standards drift
- expecting contributors to reverse-engineer architecture from code when a compact maintainer doc should exist
- treating changelog maintenance as optional after a release already shipped

## Skill Feedback Loop

This skill includes the learning loop for GitHub-facing work. When later evidence shows a meaningful gap between our approach and public maintainer reality, treat extracting reusable lessons as part of completing the task.

### Trigger

Activate the feedback loop when any of these happens:

- upstream lands similar work
- maintainer feedback arrives
- a review or diff shows we missed a required surface
- our patch differs from upstream in a way that exposes a reusable process lesson
- export or release cleanup reveals a repeatable public-readiness failure

### Extraction

Compare:

- what we assumed
- what public maintainers, reviewers, or downstream users actually needed
- which gap is reusable across future GitHub-facing work

Keep only lessons that are generalizable, process-level, and stated at the right level of abstraction.

### Deduplication

Before proposing any update:

- re-read the current global policy and this skill
- do not propose a lesson that is already covered in substance
- reject lessons that fail any of these tests:
  - project-agnostic: can it be stated without project names, language names, or architecture-specific trivia?
  - cross-project usefulness: would it improve many future GitHub-facing efforts rather than only this class of project?
  - decision-changing: would having this rule earlier have materially changed scoping, review, export, or submission behavior?
- classify each new lesson as one of:
  - new rule
  - stronger checklist item
  - new anti-pattern
  - new review gate
  - new maintainer-readiness question

### Automatic Proposal Behavior

When a materially new reusable lesson exists, automatically include a `Skill Improvement Proposal` section in the thread. That proposal should state:

- the new lesson
- why it matters
- where it belongs in the guidance
- whether it should update `AGENTS.md`, this skill, or a narrower compatibility skill

Do this without waiting for the user to ask. Do not silently edit the guidance.

### Guardrails

- Do not propose project trivia or one-off facts.
- Do not propose language-specific minutiae unless they expose a broader process failure.
- Do not add narrow historical anecdotes to the skill just because they can be phrased generically.
- If a lesson is valid only for the current patch or a small class of similar projects, keep it in the task reasoning or PR discussion, not in the permanent skill.
- Do not emit proposal spam. Only propose updates when the lesson would materially improve future public GitHub work.

## Deliverables

When this skill is active, aim to produce:

- repo-role classification
- component-intake summary
- boundary decision
- durable component-registry entry or update
- public-doc-surface decision when the work is user-facing or externally maintained
- changelog update when the project has a real public release history
- architecture reference or architecture-doc update when the project is non-trivial
- export blockers
- README transparency requirements when relevant
- upstreamability decision when relevant
- skill improvement proposal when a new reusable lesson is revealed
