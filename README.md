# codex-spine

`codex-spine` is a macOS-first public Codex environment spine for shareable retrieval, indexing, workflow, and maintenance tooling. It installs and maintains the core pieces for you instead of turning the setup into a README scavenger hunt.

## What It Includes

- managed bootstrap, verify, update, and component status commands
- generated Codex config for the public core
- shell integration and launchd-backed transcript sync on macOS
- QMD-backed memory and retrieval plumbing by default
- optional `jcode` integration through a managed enablement flow

## Quick Start

1. Clone the repo wherever you want to keep the managed environment.
2. Run `make bootstrap`.
3. Run `make verify`.
4. If you want indexed code navigation, run `./scripts/component-enable jcode`.

## Docs

- `PROJECT_SPINE.md`: durable product scope and strategy
- `CHECKPOINT.md`: current release-candidate focus and next safe step
- `ARCHITECTURE.md`: subsystem map, flows, and invariants
- `USER_GUIDE.md`: install, update, operation, and troubleshooting guidance
- `QA_MATRIX.md`: release-candidate test matrix and pass criteria
- `SECURITY.md`: security posture and reporting expectations

## Third-Party Components And Licensing

`codex-spine` is its own project boundary. Some managed integrations are optional and continue to be governed by their own upstream terms.

`jcode` is one of those optional integrations. `codex-spine` is not the upstream `jcodemunch-mcp` project and does not imply formal affiliation or official distribution. Enabling `jcode` causes `codex-spine` to fetch the exact upstream terms for the pinned version, save a local copy, and require explicit acknowledgement before install or update. If the exact upstream terms cannot be retrieved, `codex-spine` will not enable or update `jcode`.

When `jcode` is not enabled, `codex-spine` remains fully usable without that optional component.
