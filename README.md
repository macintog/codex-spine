# codex-spine

`codex-spine` is a macOS-first public Codex environment spine for shareable retrieval, indexing, workflow, and maintenance tooling. It installs and maintains the core pieces for you instead of turning the setup into a README scavenger hunt. When everything is working, your token counts should go down while accuracy goes up.

The current `codex-spine` tree improves Codex in a few focused ways:

- it adapts [@tobi/qmd](https://github.com/tobi/qmd) to the Codex workflow by:
  - converting Codex thread JSON into Markdown for ingestion
  - extracting only user and assistant conversation content for indexing
  - narrowing the practical `qmd` surface down to the retrieval calls that matter for recalling that material
- it can optionally install the [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp), [@jgravelle/jdocmunch-mcp](https://github.com/jgravelle/jdocmunch-mcp), and [@jgravelle/jdatamunch-mcp](https://github.com/jgravelle/jdatamunch-mcp) suite, which can substantially improve token efficiency when working through code, docs, and data
- it ships a focused public skill set for continuity, terminal closeout, change reasoning, architecture, skill authoring, and evidence-first visualization

## Audience

This project is aimed at new macOS Codex users who want a turnkey way around some of Codex's basic limitations. It packages a tested daily-driver environment into a public install path, so people starting from zero can get useful retrieval, indexing, and maintenance tooling without first rebuilding the whole setup themselves. The project is still evolving, but the v0.5.4 release line is intended to be installable today, practical to update, and straightforward to adopt.

## What It Includes

- managed install, verify, update, and component status commands
- manifest-driven component maintenance in `MAINTAINED_COMPONENTS.toml`, using compatibility ceilings instead of exact version pins
- reusable `project-continuity`, `yeet`, `change-impact`, `causal-explanation`, `improve-codebase-architecture`, `skill-authoring-quality`, and `tufte-visualization` trees under `skills/`
- generated Codex config for the managed core environment
- shell integration and launchd-backed transcript sync on macOS
- a managed system-wide `uv` policy at `~/.config/uv/uv.toml` with `exclude-newer = "7 days"` as the default quarantine plus package-specific overrides for the optional jGravelle Munch MCP suite so the optional runners remain installable
- a `memory` MCP lane backed by [@tobi/qmd](https://github.com/tobi/qmd): bounded bootstrap for durable re-anchors, `recent_session` for explicit topicless last-conversation recall, and one unified typed `query` followed by bounded source retrieval for named history
- optional jGravelle Munch MCP suite integration through a managed enablement flow

The memory lane is intentionally selective. Codex should use the current thread and checkout for current facts, reach for `recent_session` when you explicitly ask what the last conversation was about, and query indexed history when a named past decision or method is missing from the current thread. Exact names and identifiers start with fast lexical retrieval and only broaden to semantic search when needed. This keeps ordinary repository work local while avoiding broad scans of an unrelated checkout or live historical paths during lookback. QMD retrieval is bounded; the model's later synthesis may still be the larger time and token cost for complex questions.

## Skills

`codex-spine` ships seven public skill trees and installs them under `~/.codex/skills/` during `make install`. Skills are reusable guidance and scaffolding for Codex sessions; they are not background services or MCP servers.

### `project-continuity`

Use this skill when a repo is long-lived enough that Codex needs durable product intent and a small current handoff instead of relying on chat memory alone. It defines project `AGENTS.md` for local rules, `PROJECT_CONTINUITY.md` for durable intent, and `codex-project-checkpoint` for worktree-independent handoff state. Adopted repositories keep tracked `CHECKPOINT.md` only as a discovery stub; `not_adopted` retains the legacy tracked handoff.

The artifacts under `skills/project-continuity/assets/` scaffold those files without replacing an existing instruction chain. The direct adoption procedure and read-only auditor live beside them under `references/` and `scripts/`. The shipped skill is the reusable pattern; actual continuity files remain project-local working state.

Built-in Codex memories are disabled by the base config. Retained app-managed files under `~/.codex/memories/` are historical generated state and must not be read or routed into work unless the current user explicitly asks about those files. Keep required rules in `AGENTS.md` or checked-in docs, use the QMD-backed `memory` MCP lane documented in `codex/TOOLING.md` for historical retrieval, and use `/memories` or `codex/config/90-local.toml` only for an intentional user-owned opt-in.

### `yeet`

Use this explicit-only skill when the operator says `yeet` after a registered task's validation has passed. The bundled `codex-git-safe` runtime attempts the configured terminal commit/review or integration transaction, proves the remote result, reconciles an adopted checkpoint, and retires only task-owned state. It deliberately does not run product tests, broad verification, bootstrap, deployment, or release gates.

### `change-impact`

Use this skill before a change crosses interfaces, persisted schemas, permissions, deployment or release boundaries, or three or more downstream consumers. It produces an evidence-backed consumer map, the load-bearing assumptions, and a finite verification obligation list.

### `causal-explanation`

Use this skill to explain why or how an established consequential behavior, design choice, regression, threshold, or tradeoff exists. It keeps direct observations, causal inference, alternatives, and gaps distinct.

### `improve-codebase-architecture`

Use this skill to find architecture deepening, terminology, and semantic-symmetry opportunities, or to implement an architecture direction the user has already selected.

### `skill-authoring-quality`

Use this skill with the platform's skill-creation guidance to audit routing, placement, prompt economy, validation, distribution, provenance, and collision safety for skill packets.

### `tufte-visualization`

Use this skill as an evidence-design overlay when creating, revising, or critiquing charts, dashboards, analytical figures, visual tables, maps, KPI displays, evidence-rich diagrams, and decision-grade reports. It combines comparison-first reasoning with explicit uncertainty, anti-reflex taste checks, host-style preservation, responsive sibling compositions, accessibility, source documentation, and rendered QA. Medium-specific skills still own implementation mechanics; it does not install a charting runtime or bring its own data source.

## What Install Changes

`make install` is the install step, not just a validation step. It:

- keeps one fullscreen session through the whole interactive install
- checks early whether `~/.codex/config.toml` already exists and asks how to handle it before broader managed changes
- for interactive installs, asks early whether you want to include the optional jGravelle Munch MCP suite later in the same install when it is not already fully enabled; that prompt defaults to yes
- installs Homebrew if needed and then installs any missing baseline runtime packages
- creates example local overlay files when they do not exist yet
- manages symlinks under `~/.codex/` and `~/.local/bin/`, including all shipped skill trees and the `codex-git-safe` terminal-closeout runtime
- manages `~/.config/uv/uv.toml` from the tracked `uv/uv.toml` policy file
- updates managed source blocks in `~/.zprofile` and `~/.zshrc` only when the detected login shell is `zsh`
- renders `~/.codex/config.toml`
- installs or reloads `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist`
- installs or updates the default managed components
- runs the first transcript sync and [@tobi/qmd](https://github.com/tobi/qmd) lexical index refresh so memory and transcript retrieval are warm before install finishes

The optional jGravelle Munch MCP suite stays out of the default core path, but interactive install can include it when you opt in.

If you choose that suite during interactive install, `codex-spine` remembers that choice early, then later shows the current upstream terms once, requires you to type `accept` once, and only then enables all three integrations together. If the whole suite is already enabled, install reports that state and continues without re-prompting. The managed overlay then wires Codex to the latest compatible upstream MCP runners for `jcodemunch`, `jdocmunch`, and `jdatamunch` through the built-in `uv` runner, rendered as an absolute runtime path with a stable Munch MCP `PATH`. The `jcodemunch` path also writes `~/.code-index/config.jsonc` from the tracked `codex/config/jcodemunch.config.jsonc` default, keeping upstream `tool_profile: "core"`, `compact_schemas: true`, and `meta_fields: []`; a repo-local `.jcodemunch.jsonc` can widen that later when a project genuinely needs richer tools. The managed overlay also keeps `JDOCMUNCH_SHARE_SAVINGS=0`, `JDOCMUNCH_META_FIELDS=[]`, `JDATAMUNCH_SHARE_SAVINGS=0`, and `JDATAMUNCH_META_FIELDS=[]` in the rendered MCP entries so docs/data retrieval stay on the public token-saving posture. Those runners use the managed `~/.config/uv/uv.toml` policy with `exclude-newer = "7 days"` as the default quarantine plus package-specific cutoffs for the optional suite so the compatible runners stay installable on a clean system. If you skip it, install continues without the optional suite and you can still enable it later with `./scripts/component-enable jcodemunch-mcp`.

Current terminals do not automatically pick up shell changes. Open a new shell after install when you want the refreshed shell environment. If install skipped shell wiring because your login shell is not `zsh`, update your shell startup manually instead.

macOS may also show a one-time `Background Items Added` notification for `sync-codex-chat-qmd.sh` during install. That is expected because `codex-spine` registers the transcript-sync LaunchAgent under Login Items & Extensions. The scheduled agent sets `QMD_SYNC_EMBED=1`, so it refreshes transcript projection, bootstrap state, the lexical QMD index, contexts, and vector embeddings in the background. The default cadence is 15 minutes, which keeps backpressure below measured full-sync runtime while the pipeline records per-stage timing for incremental improvements.

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

## Quick Start

1. Clone the repo wherever you want to keep the managed environment.
2. Run `make install`.
3. Restart Codex app.
4. Open a new shell if install updated your zsh startup files or installed Homebrew during setup.
5. Run `make verify`.
6. If you skipped the optional jGravelle Munch MCP suite prompt during install and later want indexed code, docs, and data navigation, run `./scripts/component-enable jcodemunch-mcp`.

`make install` is interactive when run from a TTY. On stock macOS, the installer explains the Homebrew packages it is about to install and asks for approval before continuing. Use `./scripts/bootstrap --non-interactive` when you need a non-interactive install path.
If Homebrew installation needs macOS password authentication, `codex-spine` keeps that prompt inside the installer's bottom panel and then continues in the same fullscreen session.
Install now also runs an initial sync of local Codex transcripts from `~/.codex/sessions` into the local [@tobi/qmd](https://github.com/tobi/qmd) lexical and vector indexes before the final verification step, so the first run can take noticeably longer than later runs. Failed embed attempts record a cooldown marker under the QMD state directory instead of retrying on every scheduled run; after fixing QMD, run `QMD_EMBED_RETRY=1 sync-codex-chat-qmd.sh` to force a retry.

`zsh` is the only shell path currently tested. If the detected login shell is not `zsh`, install warns once, skips shell-dotfile mutation, and continues with the core install. In that case, add `~/.local/bin` to your own shell startup manually.

## Existing Codex Configs

Codex reads one live config file at `~/.codex/config.toml`. `codex-spine` does not patch that file in place table-by-table. Instead, it renders one final managed config from a small set of fragments so the result is predictable and repeatable.

The relevant inputs are:

- `codex/config/00-base.toml` for base `codex-spine` defaults
- `codex/config/20-codex-spine-mcps.toml` for the `codex-spine`-managed `memory` MCP entry
- `codex/config/80-adopted.toml` for settings imported from a pre-existing unmanaged `~/.codex/config.toml`
- `codex/config/90-local.toml` for your own local machine-specific overrides
- temporary live `model_reasoning_effort` changes are treated as operator-tunable and do not count as config drift in `make verify`
- avoid top-level `sandbox_mode` and `approval_policy` in `codex/config/90-local.toml` for Codex desktop use; explicit values make the desktop app treat the config as `custom (config.toml)` instead of persisting the UI mode cleanly

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
- if you enabled the optional jGravelle Munch MCP suite, `./scripts/component-enable jcodemunch-mcp` completes and `make verify` still passes

## Daily Commands

- `make update`: refresh default and enabled optional components to the repo's managed compatibility ceilings
- `make upgrade`: move a clean checkout to the newest `vX.Y.Z` release tag from `origin`, then run install, update, and verify
- `make verify`: validate repo state, live-machine state, component health, and wrapper health
- `./scripts/component-status`: inspect managed component health
- `./scripts/component-enable jcodemunch-mcp`: enable the optional jGravelle Munch MCP suite for code, docs, and data

`make update` does not move your repo checkout between `codex-spine` releases. Use `make upgrade` when you want to move from an older release tag to the newest release tag published on your configured `origin` remote. `make upgrade` refuses to run when the checkout has local changes, then fetches tags, checks out the newest release, runs `make install`, refreshes managed components, and finishes with `make verify`.

## Troubleshooting

- If `make verify` says the live config is stale for non-tunable settings, run `make install`.
- If transcript sync is missing, check `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist` and re-run `make install`.
- If install warns that your login shell is not `zsh`, add `~/.local/bin` to that shell's startup and source the repo fragments manually if you want shell integration.
- If `launchctl` warnings appear during install, rerun `make install` from a normal macOS GUI login session. The LaunchAgent plist is still written even when load fails.
- If macOS shows `Background Items Added` for `sync-codex-chat-qmd.sh`, that is the expected one-time notice for the managed transcript-sync LaunchAgent.
- If shell changes do not appear in your current terminal, open a new shell session after install.
- If the optional jGravelle Munch MCP suite will not enable, rerun `./scripts/component-enable jcodemunch-mcp` from an interactive TTY and check the reported terms-fetch, `uv`, or version-compatibility error.

## Docs

- `ARCHITECTURE.md`: subsystem map, flows, and invariants
- `CHANGELOG.md`: notable user-visible release history
- `SECURITY.md`: security posture and reporting expectations
- `codex/AGENTS.md`: compact Codex startup and operating guidance for this installed environment
- `codex/TOOLING.md`: on-demand guidance for continuity, memory retrieval, indexed navigation, and managed Git lifecycle
- `THIRD_PARTY_NOTICES.md`: upstream project, pinned-source, license, and derivative-work attribution
- `skills/project-continuity/`: reusable continuity contract plus starter templates
- `skills/yeet/`: explicit terminal Git transaction contract backed by `codex-git-safe`
- `skills/change-impact/`: affected-consumer and verification-obligation mapping
- `skills/causal-explanation/`: evidence-calibrated why/how explanations
- `skills/improve-codebase-architecture/`: architecture deepening and interface review
- `skills/skill-authoring-quality/`: portable skill governance and audit workflow
- `skills/tufte-visualization/`: evidence-first visualization workflow plus chart, accessibility, critique, and caption references

This repo ships the docs needed to install, operate, and maintain `codex-spine`.
The shipped maintenance manifest lives in `MAINTAINED_COMPONENTS.toml`.

## Third-Party Components And Licensing

`codex-spine` is licensed under MIT, which permits commercial use. Some managed integrations are optional and continue to be governed by their own upstream terms.

Adapted public skill packets retain their upstream MIT notices and pinned
project links in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and in each
derivative skill's `LICENSE.txt`.

The default retrieval foundation is built around [@tobi/qmd](https://github.com/tobi/qmd). `codex-spine` adds the public Codex-facing wrappers, transcript sync, config rendering, and operator flow around that upstream project while keeping the upstream package boundary explicit.

The upstream [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp), [@jgravelle/jdocmunch-mcp](https://github.com/jgravelle/jdocmunch-mcp), and [@jgravelle/jdatamunch-mcp](https://github.com/jgravelle/jdatamunch-mcp) projects are optional integrations. They remain governed by their own upstream terms, including any commercial-use restrictions those upstream projects apply. `codex-spine` is not those upstream projects and does not imply formal affiliation, official distribution, or any re-licensing of upstream artifacts. Enabling the optional jGravelle Munch MCP suite shows the current upstream terms once when you opt in, requires one explicit `accept`, and then runs the latest compatible upstream releases under `<2.0` through `uv`.

When the optional jGravelle Munch MCP suite is not enabled, `codex-spine` remains fully usable without those optional components.
