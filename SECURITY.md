# Security Policy

## Security Footprint

`codex-spine` is a user-level macOS workstation bootstrap and maintenance tool. Its security-relevant behavior is:

- writing generated Codex config under `~/.codex/config.toml`
- managing symlinks under `~/.codex/skills/` and `~/.local/bin/`
- editing user shell startup files to source managed fragments
- installing a user LaunchAgent at `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist`
- installing or updating managed third-party user-space tools such as [@tobi/qmd](https://github.com/tobi/qmd), and wiring the optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) integration through a constrained `uvx` invocation

`codex-spine` does not require root, install privileged daemons, expose a network service, or act as a sandbox for untrusted code.

## Data And Secrets

- The repo and generated public config are intended to remain secret-free.
- Provider credentials should stay in the user’s normal Codex or operating-system secret mechanisms, not in tracked files.
- The default [@tobi/qmd](https://github.com/tobi/qmd)-backed memory flow stores local transcript and derived project-memory data under `~/.cache/qmd/codex_chat`. Treat that local index as sensitive if your Codex transcripts contain sensitive content.
- Optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) enablement stores only local enablement state under the repo-local `.state/` directory. It does not store credentials.

## Trust Boundaries

- Tracked repo files and generated local overlays are part of the trusted local installation surface.
- Upstream package artifacts are external inputs. `codex-spine` reduces risk through explicit opt-in enablement and a managed `<2.0` compatibility ceiling for [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp), not through sandboxing.
- Indexed source trees, Codex transcripts, and project-memory material may contain arbitrary user or project content. `codex-spine` does not claim to sanitize that content for downstream tools.

## Supported Assumptions

- single-user workstation operation
- user-space installation without elevated privileges
- macOS-first automation; Linux and Windows analogs are documented inline but not supported as packaged automation in v1

## Reporting

Report security concerns privately to the maintainer rather than opening a public issue with exploit details until a dedicated public reporting channel is published.
