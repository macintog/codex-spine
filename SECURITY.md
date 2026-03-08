# Security Policy

## Scope

`codex-spine` manages local environment state, generated config, shell hooks, and background transcript-sync behavior. Treat it as workstation infrastructure.

## Secret Handling

- Tracked files must remain secret-free.
- `codex-spine` does not bundle plaintext secrets.
- Users should continue to manage provider tokens through their normal Codex or OS secret mechanisms.
- Optional components with separate licensing, such as `jcode`, store acknowledgement provenance only; they do not store secret credentials.

## Reporting

Until `codex-spine` is public on GitHub, report security concerns privately to the maintainer rather than opening a public issue with exploit details.

## Review Priorities

- accidental private-path or personal-service leakage into the public repo
- secret material in tracked config, shell fragments, or docs
- unsafe machine-state mutation during bootstrap or update
- unbounded trust in downloaded or fetched third-party artifacts
