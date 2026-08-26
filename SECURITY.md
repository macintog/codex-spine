# Security Policy

## Security Footprint

`codex-spine` is a user-level macOS workstation bootstrap and maintenance tool. Its security-relevant behavior is:

- writing generated Codex config under `~/.codex/config.toml`
- managing symlinks under `~/.codex/` and `~/.local/bin/`
- managing the account-wide `uv` policy at `~/.config/uv/uv.toml`
- editing user shell startup files to source managed fragments
- installing a user LaunchAgent at `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist`
- managing task worktrees and, only after the operator's exact `yeet`
  instruction, performing the registered task's configured commit,
  review/integration, remote-proof, checkpoint, and retirement transaction
- bootstrapping Homebrew when it is missing, which can trigger a one-time macOS password prompt before the rest of the install continues in user space
- installing or updating managed third-party user-space tools such as [@tobi/qmd](https://github.com/tobi/qmd), and wiring the optional jGravelle Munch MCP suite (`jcodemunch-mcp`, `jdocmunch-mcp`, and `jdatamunch-mcp`) through constrained absolute `uv` runner invocations with a stable MCP `PATH`, backed by `exclude-newer = "7 days"` as the default `uv` quarantine plus package-specific suite overrides

Outside the optional first-run Homebrew bootstrap path, `codex-spine` does not require root, install privileged daemons, expose a network service, or act as a sandbox for untrusted code.

## Data And Secrets

- The repo and generated public config are intended to remain secret-free.
- Provider credentials should stay in the user’s normal Codex or operating-system secret mechanisms, not in tracked files.
- The bundled Gitea helpers use a process-scoped `GITEA_TOKEN` when supplied or
  the normal Git credential helper for the configured HTTP(S) remote. They do
  not write credentials into the repository or `codex-spine` state.
- The default [@tobi/qmd](https://github.com/tobi/qmd)-backed memory flow stores local transcript and derived project-memory data under `~/.cache/qmd/codex_chat`. Treat that local index as sensitive if your Codex transcripts contain sensitive content.
- Optional jGravelle Munch MCP suite enablement stores only local enablement state under the repo-local `.state/` directory. It does not store credentials or a copy of the upstream terms text.

## Trust Boundaries

- Tracked repo files and generated local overlays are part of the trusted local installation surface.
- `codex-git-safe` treats task lifecycle records, repository configuration, and
  live remote tips as separate authorities and fails closed when they disagree.
  `yeet` is not authority to run product tests, broad verification, deployment,
  or release work.
- Upstream package artifacts and the fetched terms text shown during optional enablement are external inputs. `codex-spine` reduces risk through explicit opt-in enablement and managed `<2.0` compatibility ceilings for the optional jGravelle Munch MCP suite, not through sandboxing.
- Indexed source trees, Codex transcripts, and project-memory material may contain arbitrary user or project content. `codex-spine` does not claim to sanitize that content for downstream tools.

## Supported Assumptions

- single-user workstation operation
- user-space installation without elevated privileges
- macOS-first automation; Linux and Windows analogs are documented inline but not supported as packaged automation in v1

## Reporting

Report security concerns confidentially to the maintainer rather than opening a public issue with exploit details until a dedicated public reporting channel is published.
