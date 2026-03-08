# Project Spine

## Purpose

`codex-spine` is the public, shareable environment spine extracted from the private `codex-env` incubator. Its job is to make a serious Codex workstation easier to install, maintain, and evolve for other Mac users without pulling along personal services or local-only glue.

## User Job

Give advanced Codex users a managed macOS baseline for retrieval, memory, indexing, workflow policy, and ongoing upstream dependency maintenance.

## Success Criteria

- clean bootstrap on supported macOS versions
- deterministic verify and update flows
- QMD and memory work end to end without manual glue
- optional `jcode` enablement is seamless but license-aware
- public docs are clear enough that maintainers do not have to reverse-engineer the repo

## Non-Goals

- cross-platform automation in v1
- bundling personal services or local-only integrations
- pretending optional third-party components are covered by `codex-spine`'s own license boundary

## Strategy

Ship the full managed macOS slice first: bootstrap, verify, rendered config, shell integration, launchd-backed transcript sync, default QMD/memory plumbing, and optional `jcode`. Use private Gitea for pre-GM release-candidate iteration, then push the first public GitHub release only after the matrix and docs are GM quality.

## Stable Constraints

- macOS-first only; Linux and Windows get inline analog notes, not supported automation
- upstream dependency maintenance stays on one shared model even when acquisition backends differ
- optional third-party licensing must stay explicit in docs and runtime
- public repo history starts clean; it is not a long-lived branch of the incubator
