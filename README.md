# codex-spine

`codex-spine` is a macOS-first public Codex environment spine for shareable retrieval, indexing, workflow, and maintenance tooling. It installs and maintains the core pieces for you instead of turning the setup into a README scavenger hunt.

## Requirements

- macOS with a user-space Codex installation under `~/.codex`
- Homebrew

`make install` uses Homebrew as the baseline package manager for `python`, `ripgrep`, `node`, `pnpm`, `uv`, and `jq`. If Homebrew is missing, install will offer to install it when run from an interactive TTY.
Install starts from macOS-shipped shell tools and will provision Homebrew Python first when the machine's default `python3` is too old for the managed runtime.

## Homebrew Packages

When `make install` installs missing baseline formulas, it installs these Homebrew packages:

- `ripgrep`
- `python`
- `node`
- `pnpm`
- `uv`
- `jq`

## What It Includes

- managed install, verify, update, and component status commands
- generated Codex config for the public core
- shell integration and launchd-backed transcript sync on macOS
- qmd-backed memory and retrieval plumbing by default
- optional `jCodeMunch MCP` integration through a managed enablement flow

## Quick Start

1. Clone the repo wherever you want to keep the managed environment.
2. Run `make install`.
3. Restart Codex app.
4. Open a new shell if install updated your zsh startup files.
5. Run `make verify`.
6. If you want indexed code navigation, run `./scripts/component-enable jcodemunch-mcp`.

`make install` is interactive when run from a TTY. It will explain the Homebrew packages it is about to install and ask for approval before continuing. Use `./scripts/bootstrap --non-interactive` when you need a non-interactive install path.
Install now also runs an initial sync of local Codex transcripts from `~/.codex/sessions` into the local qmd index before the final verification step, so the first run can take noticeably longer than later runs.

`zsh` is the only shell path currently tested. If the detected login shell is not `zsh`, install warns once, skips shell-dotfile mutation, and continues with the core install. In that case, add `~/.local/bin` to your own shell startup manually.

## What Install Changes

`make install` is the install step, not just a validation step. It:

- checks early whether `~/.codex/config.toml` already exists and asks how to handle it before broader managed changes
- checks that Homebrew exists and installs any missing baseline packages needed by the managed runtime
- creates example local overlay files when they do not exist yet
- manages symlinks under `~/.codex/skills/` and `~/.local/bin/`
- updates managed source blocks in `~/.zprofile` and `~/.zshrc` only when the detected login shell is `zsh`
- renders `~/.codex/config.toml`
- installs or reloads `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist`
- installs or updates the default managed components
- runs the first transcript sync and qmd index refresh so memory and transcript retrieval are warm before install finishes

Optional `jCodeMunch MCP` enablement stays separate from first-run install.

Current terminals do not automatically pick up shell changes. Open a new shell after install when you want the refreshed shell environment. If install skipped shell wiring because your login shell is not `zsh`, update your shell startup manually instead.

## Existing Codex Configs

Codex reads one live config file at `~/.codex/config.toml`. `codex-spine` does not patch that file in place table-by-table. Instead, it renders one final managed config from a small set of fragments so the result is predictable and repeatable.

The relevant inputs are:

- `codex/config/00-base.toml` for base `codex-spine` defaults
- `codex/config/20-codex-spine-mcps.toml` for the `codex-spine`-managed `memory` and `qmd_codex` MCP entries
- `codex/config/80-adopted.toml` for settings imported from a pre-existing unmanaged `~/.codex/config.toml`
- `codex/config/90-local.toml` for your own local machine-specific overrides

If `~/.codex/config.toml` already exists and is not already `codex-spine`-managed, install asks about it before broader system changes.

If you accept:

- `codex-spine` imports the non-`codex-spine` parts of the current live config into the local gitignored `codex/config/80-adopted.toml`
- backs up the previous live `~/.codex/config.toml`
- renders a new live config that includes the imported settings plus the `codex-spine`-managed MCP entries

If you decline:

- `~/.codex/config.toml` stays exactly as it was
- `codex/config/80-adopted.toml` is not created
- install stops before `codex-spine` changes Homebrew packages, managed wrappers, shell files, launchd, or the live Codex config

The rationale is to keep `codex-spine` ownership narrow and explicit. It manages the MCP entries it owns, preserves the rest of an existing Codex config when you approve that import, and avoids hand-editing arbitrary live config in place.

## First-Run Success Criteria

After a successful first run:

- `make install` ends with `install: ok`
- `make verify` ends with `verify: ok`
- `./scripts/component-status` reports the default components as healthy
- `make verify` proves both the native components and the Codex-facing wrapper layer (`qmd-codex` and the memory MCP launcher)
- `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist` exists
- `~/.codex/config.toml` exists and starts with `Generated by codex-spine`
- if you enabled `jCodeMunch MCP`, `./scripts/component-enable jcodemunch-mcp` completes and `make verify` still passes

## Daily Commands

- `make update`: refresh default and enabled optional components to the repo's pinned versions
- `make verify`: validate repo state, live-machine state, component health, and wrapper health
- `./scripts/component-status`: inspect managed component health
- `./scripts/component-enable jcodemunch-mcp`: enable the optional upstream `jCodeMunch MCP` integration

## Troubleshooting

- If `make verify` says the live config is stale, run `make install`.
- If transcript sync is missing, check `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist` and re-run `make install`.
- If install warns that your login shell is not `zsh`, add `~/.local/bin` to that shell's startup and source the repo fragments manually if you want shell integration.
- If `launchctl` warnings appear during install, rerun `make install` from a normal macOS GUI login session. The LaunchAgent plist is still written even when load fails.
- If shell changes do not appear in your current terminal, open a new shell session after install.
- If `jCodeMunch MCP` will not enable, inspect the stored upstream terms retrieval error first; the enable flow intentionally hard-fails when it cannot verify the upstream terms for the pinned version.

## Docs

- `ARCHITECTURE.md`: subsystem map, flows, and invariants
- `CHANGELOG.md`: notable user-visible release history
- `SECURITY.md`: security posture and reporting expectations

## Third-Party Components And Licensing

`codex-spine` is licensed under MIT, which permits commercial use. Some managed integrations are optional and continue to be governed by their own upstream terms.

The upstream [`jgravelle/jcodemunch-mcp`](https://github.com/jgravelle/jcodemunch-mcp) project (`jCodeMunch MCP`) is one of those optional integrations. Its current upstream terms permit free non-commercial use and require a separate upstream commercial license for commercial use. `codex-spine` is not the upstream `jCodeMunch MCP` project and does not imply formal affiliation, official distribution, or any re-licensing of upstream artifacts. Enabling `jCodeMunch MCP` causes `codex-spine` to fetch the exact upstream terms for the pinned version, save a local copy, and require explicit acknowledgement before install or update. If the exact upstream terms cannot be retrieved, `codex-spine` will not enable or update `jCodeMunch MCP`.

When `jCodeMunch MCP` is not enabled, `codex-spine` remains fully usable without that optional component.
