# Project Continuity

<!-- Replace every angle-bracket instruction, remove unused optional rows or sections, and delete this comment when instantiating. -->

## Purpose

<What the project exists to do, which real problem it solves, and why that matters.>

## User / Operator Job

<Who uses or operates the project, what they need to accomplish, and what trust or control they expect.>

## Success Criteria

- <Concrete product or operator-visible outcome.>

## Non-Goals

- <Tempting side quest or optimization that must not redefine the project.>

## Current Product Strategy

<The durable strategy that should stay visible during narrow implementation work.>

### Strategy Assumptions

- <Assumption the strategy currently depends on.>

### Revisit When

- <Evidence or condition that requires reconsidering the strategy.>

## Workstream Map

- `<workstream>`: <durable area of work, not a one-session task>

## Repository Topology / Adjacent Managed Repos

<!-- Optional. Keep only when adjacent surfaces materially affect project reasoning. -->

- `<surface>`: <role, reason it exists, whether it is disposable or preserved, and which comparison matters>

## Stable Constraints / Invariants

- <Durable architecture, environment, data, safety, source-of-truth, or publication boundary.>

## Authority Map

| Question | Authority | Conflict Rule |
| --- | --- | --- |
| Product purpose and success | This file | Change only after a deliberate product decision. |
| Active task | Current user instruction | Supersedes prior handoff scope subject to durable safety constraints. |
| Current implementation state | Repository and current validation evidence | A checkpoint is a pointer, not proof. |
| Repo working rules | Applicable `AGENTS.md` and `AGENTS.override.md` chain | Preserve directory-scoped precedence for the current working directory. |
| Current focus and next step | `CHECKPOINT.md` | Reconcile its state anchor before acting. |
| Architecture, release, or production procedure | `<specific accepted reference>` | Do not reconstruct current procedure from archived history. |
