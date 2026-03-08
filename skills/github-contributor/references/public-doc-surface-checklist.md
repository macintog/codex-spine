# Public Doc Surface Checklist

Use this to decide which public-facing docs a project or shareable component should carry. The goal is not to maximize document count. The goal is to give maintainers and users the right information at the right layer.

## Core Principle

Different docs should answer different questions. Do not collapse everything into `README.md`, and do not create placeholder docs that have no real job yet.

## Document Roles

### `README.md`

Use for:

- what the project is
- why it exists
- who it is for
- quick start or installation
- doc map to deeper references

Create or strengthen this when the project needs a clear public entrypoint.

### `USER_GUIDE.md`

Use for:

- operator workflows
- tool selection strategy
- common tasks
- troubleshooting and practical usage advice

Create this when day-to-day usage guidance would otherwise bloat the README or remain trapped in maintainer heads.

### `SPEC.md`

Use for:

- stable interfaces
- schemas, envelopes, identifiers, or contracts
- behavior guarantees and edge-case semantics
- compatibility expectations

Create this when external users, clients, tools, or maintainers need a precise contract beyond narrative docs.

Do not create it just to restate implementation details or architecture.

### `ARCHITECTURE.md`

Use for:

- subsystem boundaries
- end-to-end data or control flow
- invariants
- storage, caching, or indexing behavior
- trust boundaries

Create this when the internal shape is no longer obvious from the README and source layout.

### `SECURITY.md`

Use for:

- the project's actual security footprint and attack surface
- threat model and security posture
- vulnerability reporting path
- data handling and storage locations that matter for security
- secret-handling rules
- trust or sandbox boundaries
- privileged versus user-space behavior
- external artifact or dependency trust assumptions
- supported deployment assumptions that affect security

Create this when the project handles secrets, credentials, code execution, external content, storage/indexing of user data, or any workflow where responsible disclosure and security expectations should be explicit.

Do not use it for maintainer process notes or repo-development hygiene unless those details materially affect the shipped product's security behavior.

### `CHANGELOG.md`

Use for:

- release-to-release user-visible changes
- compatibility or migration notes
- fixed regressions
- deprecations and removals

Create this when the project has a real release cadence or externally consumed version history. Do not backfill a ceremonial changelog for a repo that is not yet shipping meaningful public releases.

Reference checklist:
- `changelog-checklist.md`

## Decision Heuristics

Ask these questions:

- Would a new user need more than a quick start and overview?
  - if yes, consider `USER_GUIDE.md`
- Would an integrator or maintainer need exact contracts, schemas, or guarantees?
  - if yes, consider `SPEC.md`
- Would a contributor need to reconstruct architecture from source?
  - if yes, create `ARCHITECTURE.md`
- Does the project handle secrets, code execution, local files, indexing, auth, or user data?
  - if yes, create `SECURITY.md`
- Are releases and user-visible changes starting to matter over time?
  - if yes, create `CHANGELOG.md`
- Are you reaching for root `AGENTS.md`, `CHECKPOINT.md`, `PROJECT_SPINE.md`, or a QA/release matrix in a public repo?
  - if yes, stop and ask whether it is an internal maintainer or release-management doc that should stay out of the public export
- Is this a forwarded public repo with a verifier?
  - if yes, make the verifier reject reintroduction of internal control docs and obvious references back to the private source repo in shipped public product docs

## Anti-Patterns

- duplicating the same content across README, guide, spec, and architecture docs
- writing aspirational specs for unstable interfaces
- writing security theater instead of concrete posture and reporting guidance
- shipping internal maintainer or release-management docs as if they were public product documentation
- creating a changelog before the project has real public release history
- hiding important contracts in prose docs when they should be explicit in a spec
