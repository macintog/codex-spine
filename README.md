# codex-spine

`codex-spine` is a macOS-first public Codex environment spine for shareable retrieval, indexing, workflow, and maintenance tooling. It installs and maintains the core pieces for you instead of turning the setup into a README scavenger hunt. When everything is working, your token counts should go down while accuracy goes up.

`codex-spine` v0.5.1 improves Codex in a few focused ways:

- it adapts [@tobi/qmd](https://github.com/tobi/qmd) to the Codex workflow by:
  - converting Codex thread JSON into Markdown for ingestion
  - extracting only user and assistant conversation content for indexing
  - narrowing the practical `qmd` surface down to the retrieval calls that matter for recalling that material
- it can optionally install [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp), which can substantially improve token efficiency when working through code
- it keeps the durable Codex guidance surface in shipped docs instead of exported skills while those skill bodies are still evolving

## Audience

This project is aimed at new macOS Codex users who want a turnkey way around some of Codex's basic limitations. It packages a tested daily-driver environment into a public-safe install path, so people starting from zero can get useful retrieval, indexing, and maintenance tooling without first rebuilding the whole setup themselves. The project is still evolving, but the v0.5.1 release line is intended to be installable today, practical to update, and straightforward to adopt.

## Requirements

- macOS with a user-space Codex installation under `~/.codex`
- stock `/usr/bin/python3` 3.9+ available as the only bootstrap dependency; tested on macOS 15.7.4 and 26.3

`make install` uses Homebrew as the baseline package manager for `python`, `ripgrep`, `node`, `pnpm`, `uv`, and `jq`. If Homebrew is missing, install will offer to install it when run from an interactive TTY.
Interactive install stays in one fullscreen session from the first prompt through completion.

## Homebrew Packages

When `make install` installs missing baseline formulae, it installs these Homebrew packages:

- `ripgrep`
- `python`
- `node`
- `pnpm`
- `uv`
- `jq`

## What It Includes

- managed install, verify, update, and component status commands
- manifest-driven component maintenance in `MAINTAINED_COMPONENTS.toml`, using compatibility ceilings instead of exact version pins
- generated Codex config for the managed core environment
- shell integration and launchd-backed transcript sync on macOS
- [@tobi/qmd](https://github.com/tobi/qmd)-backed memory and retrieval plumbing by default
- optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) integration through a managed enablement flow
- public-safe Codex guidance that stays compatible with the stock GitHub plugin when that plugin is installed

## Quick Start

1. Clone the repo wherever you want to keep the managed environment.
2. Run `make install`.
3. Restart Codex app.
4. Open a new shell if install updated your zsh startup files or installed Homebrew during setup.
5. Run `make verify`.
6. If you skipped the optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) prompt during install and later want indexed code navigation, run `./scripts/component-enable jcodemunch-mcp`.

`make install` is interactive when run from a TTY. On stock macOS, the installer explains the Homebrew packages it is about to install and asks for approval before continuing. Use `./scripts/bootstrap --non-interactive` when you need a non-interactive install path.
If Homebrew installation needs macOS password authentication, `codex-spine` keeps that prompt inside the installer's bottom panel and then continues in the same fullscreen session.
Install now also runs an initial sync of local Codex transcripts from `~/.codex/sessions` into the local [@tobi/qmd](https://github.com/tobi/qmd) index before the final verification step, so the first run can take noticeably longer than later runs.

`zsh` is the only shell path currently tested. If the detected login shell is not `zsh`, install warns once, skips shell-dotfile mutation, and continues with the core install. In that case, add `~/.local/bin` to your own shell startup manually.

## What Install Changes

`make install` is the install step, not just a validation step. It:

- keeps one fullscreen session through the whole interactive install
- checks early whether `~/.codex/config.toml` already exists and asks how to handle it before broader managed changes
- for interactive installs, asks early whether you want to include the optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) integration later in the same install when it is not already enabled; that prompt defaults to yes
- installs Homebrew if needed and then installs any missing baseline runtime packages
- creates example local overlay files when they do not exist yet
- manages symlinks under `~/.codex/` and `~/.local/bin/`
- updates managed source blocks in `~/.zprofile` and `~/.zshrc` only when the detected login shell is `zsh`
- renders `~/.codex/config.toml`
- installs or reloads `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist`
- installs or updates the default managed components
- runs the first transcript sync and [@tobi/qmd](https://github.com/tobi/qmd) index refresh so memory and transcript retrieval are warm before install finishes

Optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) stays out of the default core path, but interactive install can include it when you opt in.

If you choose [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) during interactive install, `codex-spine` remembers that choice early, then later shows the current upstream terms, requires you to type `accept`, and only then enables it. If it is already enabled, install reports that state and continues without re-prompting. The managed overlay then wires Codex to the latest compatible upstream MCP under `<2.0` through the built-in `uv` runner instead of relying on a separate installed launcher path. If you skip it, install continues without the optional component and you can still enable it later with `./scripts/component-enable jcodemunch-mcp`.

Current terminals do not automatically pick up shell changes. Open a new shell after install when you want the refreshed shell environment. If install skipped shell wiring because your login shell is not `zsh`, update your shell startup manually instead.

macOS may also show a one-time `Background Items Added` notification for `sync-codex-chat-qmd.sh` during install. That is expected because `codex-spine` registers the transcript-sync LaunchAgent under Login Items & Extensions.

## Existing Codex Configs

Codex reads one live config file at `~/.codex/config.toml`. `codex-spine` does not patch that file in place table-by-table. Instead, it renders one final managed config from a small set of fragments so the result is predictable and repeatable.

The relevant inputs are:

- `codex/config/00-base.toml` for base `codex-spine` defaults
- `codex/config/20-codex-spine-mcps.toml` for the `codex-spine`-managed `memory` MCP entry
- `codex/config/80-adopted.toml` for settings imported from a pre-existing unmanaged `~/.codex/config.toml`
- `codex/config/90-local.toml` for your own local machine-specific overrides

If `~/.codex/config.toml` already exists and is not already `codex-spine`-managed, install asks about it before broader system changes.

If you accept:

- `codex-spine` imports the non-`codex-spine` parts of the current live config into the local gitignored `codex/config/80-adopted.toml`
- backs up the previous live `~/.codex/config.toml` as `~/.codex/config.toml.bak.<timestamp>` before writing the managed replacement
- renders a new live config that includes the imported settings plus the `codex-spine`-managed memory entry and wrapper support

If you decline:

- `~/.codex/config.toml` stays exactly as it was
- `codex/config/80-adopted.toml` is not created
- install stops before `codex-spine` changes Homebrew packages, managed wrappers, shell files, launchd, or the live Codex config

The rationale is to keep `codex-spine` ownership narrow and explicit. It manages the memory entry and supporting wrapper layer it owns, preserves the rest of an existing Codex config when you approve that import, and avoids hand-editing arbitrary live config in place.

## First-Run Success Criteria

After a successful first run:

- `make install` ends with `install: ok`
- `make verify` ends with `verify: ok`
- `./scripts/component-status` reports the default components as healthy
- `make verify` proves both the native components and the Codex-facing wrapper layer (`qmd-codex` and the memory MCP launcher)
- `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist` exists
- `~/.codex/config.toml` exists and starts with `Generated by codex-spine`
- if you enabled [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp), `./scripts/component-enable jcodemunch-mcp` completes and `make verify` still passes

## Daily Commands

- `make update`: refresh default and enabled optional components to the repo's managed compatibility ceilings
- `make verify`: validate repo state, live-machine state, component health, and wrapper health
- `./scripts/component-status`: inspect managed component health
- `./scripts/component-enable jcodemunch-mcp`: enable the optional upstream [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) integration

## Testing Branches

When testing a branch or release candidate, start from a fresh or freshly updated clone of the exact remote branch, print the exact commit with `git rev-parse --short HEAD`, then run `make install` and `make verify`.

## Project Continuity

`codex-spine` teaches a continuity packet for adopting repos: project `AGENTS.md` for local rules, `PROJECT_CONTINUITY.md` for durable intent, `CHECKPOINT.md` for volatile handoff, and optional archive references when the active handoff needs to stay compact.

Those files are project-local working state. The environment ships the guidance in `codex/AGENTS.md` and `codex/TOOLING.md`; create or update the actual continuity files in the repo you are actively working in.

The public repo does not ship GitHub plugin skills or maintainer-only governance docs. Its job is compatibility with the stock Codex GitHub plugin when installed, not bundling a second hosted-GitHub workflow layer of its own.

## Troubleshooting

- If `make verify` says the live config is stale, run `make install`.
- If transcript sync is missing, check `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist` and re-run `make install`.
- If install warns that your login shell is not `zsh`, add `~/.local/bin` to that shell's startup and source the repo fragments manually if you want shell integration.
- If `launchctl` warnings appear during install, rerun `make install` from a normal macOS GUI login session. The LaunchAgent plist is still written even when load fails.
- If macOS shows `Background Items Added` for `sync-codex-chat-qmd.sh`, that is the expected one-time notice for the managed transcript-sync LaunchAgent.
- If shell changes do not appear in your current terminal, open a new shell session after install.
- If [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) will not enable, rerun `./scripts/component-enable jcodemunch-mcp` from an interactive TTY and check the reported terms-fetch, `uv`, or version-compatibility error.

## Docs

- `ARCHITECTURE.md`: subsystem map, flows, and invariants
- `CHANGELOG.md`: notable user-visible release history
- `SECURITY.md`: security posture and reporting expectations
- `codex/AGENTS.md`: compact Codex startup guidance plus the `begin` and `end` session shortcut contract
- `codex/TOOLING.md`: on-demand guidance for the continuity packet, closeout flow, memory retrieval, and code navigation lanes

This repo ships the docs needed to install, operate, and maintain `codex-spine`.
The shipped maintenance manifest lives in `MAINTAINED_COMPONENTS.toml`.

## Third-Party Components And Licensing

`codex-spine` is licensed under MIT, which permits commercial use. Some managed integrations are optional and continue to be governed by their own upstream terms.

The default retrieval foundation is built around [@tobi/qmd](https://github.com/tobi/qmd). `codex-spine` adds the public Codex-facing wrappers, transcript sync, config rendering, and operator flow around that upstream project while keeping the upstream package boundary explicit.

The upstream [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) project is one of the optional integrations. It remains governed by its own upstream terms, including any commercial-use restrictions the upstream project applies. `codex-spine` is not the upstream [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) project and does not imply formal affiliation, official distribution, or any re-licensing of upstream artifacts. Enabling [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) shows the current upstream terms when you opt in, requires an explicit `accept`, and then runs the latest compatible upstream release under `<2.0` through `uv`.

When [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) is not enabled, `codex-spine` remains fully usable without that optional component.
