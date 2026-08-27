# codex-spine

`codex-spine` is a macOS-first Codex environment built around two recurring failures: useful context disappears between conversations, and a general-purpose agent improvises exactly where long-running work needs consistent judgment.

A new chat does not know what you decided last week, why you rejected an alternative, or where the work stopped. Feeding it every old conversation creates the opposite problem: irrelevant history consumes context, and stale summaries can start acting like current authority. The [@tobi/qmd](https://github.com/tobi/qmd)-backed memory lane retrieves prior evidence only when the answer depends on it, returns a bounded source window, and leaves the current thread and checkout authoritative for current facts.

Memory handles the past. The shipped skills handle the decision boundaries that repeatedly produce expensive mistakes:

- preserving durable project intent without letting an old handoff choose today's task, then completing Git work without losing ownership or proof
- finding affected consumers before a cross-boundary change, explaining causes without outrunning the evidence, and catching terminology or architectural drift before it spreads
- keeping skill guidance concise enough to route reliably, and making visual evidence clarify comparisons instead of decorating them

These are narrow, triggered judgment tools—not a second agent framework, a background autonomy loop, or a catalog you must remember by name. Concise hooks stay visible; detailed guidance loads only when the current task matches.

## Quick start

Requirements:

- macOS with a user-space Codex installation under `~/.codex`
- stock `/usr/bin/python3` 3.9+; tested on macOS 15.7.4 and 26.3
- `zsh` for the tested shell-integration path

Then:

1. Clone this repository wherever you want to keep the managed environment.
2. Run `make install`.
3. Restart the Codex app.
4. Open a new shell if install changed your zsh startup files or installed Homebrew.
5. Run `make verify`.

`make install` is interactive when run from a TTY. It explains any Homebrew changes, asks before importing an existing Codex config, and offers the optional jGravelle Munch MCP suite. For unattended setup, run `./scripts/bootstrap --non-interactive`.

The first install can take longer because it projects local Codex transcripts from `~/.codex/sessions` into QMD and builds the initial lexical and vector indexes. If Homebrew needs your macOS password, the prompt stays inside the installer's fullscreen interface.

## What you get

### Selective conversation memory

`codex-spine` converts Codex thread JSON into Markdown, indexes only user and assistant conversation content, and exposes a bounded `memory` MCP lane:

- `bootstrap_context` restores durable project context after a repository change, prior-thread recovery, or demonstrated context drift.
- `recent_session` answers an explicit question about the last conversation.
- `query`, followed by bounded source retrieval, finds a named past decision or method that is missing from the current thread and checkout.

The lane is deliberately selective. Current facts stay grounded in the current thread and checkout; historical retrieval runs only when the question needs it. Exact names and identifiers start with fast lexical retrieval, broadening to semantic search only when needed, without scanning unrelated checkouts or live historical paths. QMD bounds retrieval, though the model's synthesis can still dominate time and token use for complex questions.

Built-in Codex memories are disabled by the base config. Files retained under `~/.codex/memories/` are historical app-managed state and are not routed into work unless the current user explicitly asks about them. Use `/memories` or `codex/config/90-local.toml` if you want to opt back in.

### Optional indexed navigation

The optional jGravelle Munch MCP suite adds:

- `jcodemunch` for code
- `jdocmunch` for documentation
- `jdatamunch` for tabular data

Interactive install offers the suite early and defaults to yes. If you opt in, the installer shows the current upstream terms once and requires you to type `accept` before enabling all three integrations. You can skip it and enable it later:

```sh
./scripts/component-enable jcodemunch-mcp
```

The managed overlay runs compatible upstream releases under `<2.0` through `uv`. It also writes the default jCodeMunch profile to `~/.code-index/config.jsonc` and keeps anonymous docs/data savings sharing disabled. A repo-local `.jcodemunch.jsonc` can widen the default core profile when a project needs more tools.

The suite is optional. `codex-spine` remains fully usable without it, and the upstream projects retain their own terms, including any commercial-use restrictions.

### Public workflow skills

`make install` places seven reusable skill trees under `~/.codex/skills/`:

| Skill | Use it when |
| --- | --- |
| `project-continuity` | A long-lived repository needs durable product intent, local rules, and a small worktree-independent handoff. |
| `yeet` | Validated task → commit → publish or integrate → prove → retire. |
| `change-impact` | A change crosses interfaces, schemas, permissions, release boundaries, or several downstream consumers. |
| `causal-explanation` | You need an evidence-calibrated explanation of an established behavior, regression, threshold, or tradeoff. |
| `improve-codebase-architecture` | You want architecture, terminology, interface, or testability improvements. |
| `skill-authoring-quality` | You are creating or auditing a portable Codex skill. |
| `tufte-visualization` | You are creating or critiquing an evidence-rich chart, dashboard, map, or report. |

Skills are session guidance and scaffolding, not background services or MCP servers. See each tree under `skills/` for its full contract, references, and assets.


## What the installer changes

`make install` performs real machine setup. It:

- checks `~/.codex/config.toml` before broader changes and asks how to handle an existing unmanaged config
- installs Homebrew when needed, then installs missing baseline packages: `ripgrep`, `python`, `node`, `pnpm`, `uv`, and `jq`
- creates missing local overlay examples
- manages symlinks under `~/.codex/` and `~/.local/bin/`, including the shipped skills and `codex-git-safe`
- manages `~/.config/uv/uv.toml` with `exclude-newer = "7 days"` as the default package quarantine and compatibility overrides for the optional Munch suite
- updates managed blocks in `~/.zprofile` and `~/.zshrc` when the detected login shell is `zsh`
- renders the final managed `~/.codex/config.toml`
- installs or reloads `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist`
- installs or updates default components
- runs the first transcript sync and QMD index refresh

Current terminals do not inherit shell changes. Open a new shell after install. If your login shell is not `zsh`, install skips shell-dotfile changes; add `~/.local/bin` to that shell yourself if you want command-line integration.

macOS may show a one-time `Background Items Added` notification for `sync-codex-chat-qmd.sh`. This is expected. The LaunchAgent refreshes transcript projection, bootstrap state, lexical indexes, contexts, and vector embeddings every 15 minutes.

## Existing Codex configs

Codex reads one live config file at `~/.codex/config.toml`. `codex-spine` renders that file from explicit fragments instead of patching arbitrary TOML tables in place:

- `codex/config/00-base.toml` contains base defaults.
- `codex/config/20-codex-spine-mcps.toml` defines the managed `memory` MCP entry.
- `codex/config/80-adopted.toml` receives settings imported from an existing unmanaged config.
- `codex/config/90-local.toml` contains your machine-specific overrides.

If an unmanaged `~/.codex/config.toml` already exists, install asks before changing anything else. If you accept, it imports the non-`codex-spine` settings into the gitignored `codex/config/80-adopted.toml`, backs up the live file as `~/.codex/config.toml.bak.<timestamp>`, and renders the managed replacement. If you decline, install leaves the live config untouched and stops before changing Homebrew packages, wrappers, shell files, launchd, or Codex configuration.

Temporary `model_reasoning_effort` changes do not count as config drift. Avoid top-level `sandbox_mode` and `approval_policy` in `codex/config/90-local.toml`; those values make Codex desktop treat the config as `custom (config.toml)` instead of persisting the UI mode cleanly.

## Operate and update

| Command | Purpose |
| --- | --- |
| `make install` | Install or reconcile the managed environment. |
| `make verify` | Check repository state, live-machine state, component health, and Codex-facing wrappers. |
| `make update` | Refresh default and enabled optional components within the managed compatibility ceilings. |
| `make upgrade` | Move a clean checkout to the newest `vX.Y.Z` release tag from `origin`, then install, update, and verify. |
| `./scripts/component-status` | Report managed component health. |
| `./scripts/component-enable jcodemunch-mcp` | Enable the optional indexed-navigation suite. |

`make update` updates components but does not move the repository to a newer `codex-spine` release. `make upgrade` performs that release change and refuses to run from a dirty checkout.

## Verify the first install

A healthy first run has all of these outcomes:

- `make install` ends with `install: ok`.
- `make verify` ends with `verify: ok`.
- `./scripts/component-status` reports the default components as healthy.
- `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist` exists.
- `~/.codex/config.toml` begins with `Generated by codex-spine`.
- If you enabled the optional Munch suite, `./scripts/component-enable jcodemunch-mcp` completes and `make verify` still passes.

## Troubleshooting

- **Live config is stale:** Run `make install` when `make verify` reports drift in non-tunable settings.
- **Transcript sync is missing:** Check `~/Library/LaunchAgents/codex-spine.qmd-codex-chat.plist`, then rerun `make install`.
- **QMD embeddings keep failing:** Fix QMD, then run `QMD_EMBED_RETRY=1 sync-codex-chat-qmd.sh` to bypass the recorded retry cooldown once.
- **Shell changes are missing:** Open a new shell. For a non-`zsh` login shell, add `~/.local/bin` to that shell's startup manually.
- **LaunchAgent loading warns or fails:** Rerun `make install` from a normal macOS GUI login session. The plist is still written when loading fails.
- **The Munch suite will not enable:** Rerun `./scripts/component-enable jcodemunch-mcp` from an interactive TTY and follow the reported terms-fetch, `uv`, or compatibility error.

## Documentation map

| Document | What it answers |
| --- | --- |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | How install, verification, memory, optional retrieval, and the public skill payload fit together. |
| [`CHANGELOG.md`](CHANGELOG.md) | What changed in each release. |
| [`SECURITY.md`](SECURITY.md) | What the project touches, its trust boundaries, and how to report a vulnerability. |
| [`codex/AGENTS.md`](codex/AGENTS.md) | Which compact operating rules Codex loads in this environment. |
| [`codex/TOOLING.md`](codex/TOOLING.md) | How continuity, memory, indexed navigation, and managed Git lifecycle work on demand. |
| [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) | Which upstream projects and adapted skill packets are included, with licenses and attribution. |
| [`MAINTAINED_COMPONENTS.toml`](MAINTAINED_COMPONENTS.toml) | Which external components `codex-spine` manages and within what compatibility bounds. |

## License and third-party terms

`codex-spine` is licensed under MIT, including commercial use. Adapted public skill packets retain their upstream MIT notices, pinned project links, and derivative `LICENSE.txt` files; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

The default retrieval layer builds on [@tobi/qmd](https://github.com/tobi/qmd). `codex-spine` provides the Codex-facing wrappers, transcript sync, config rendering, and operator flow while keeping the upstream package boundary explicit.

The optional [jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp), [jdocmunch-mcp](https://github.com/jgravelle/jdocmunch-mcp), and [jdatamunch-mcp](https://github.com/jgravelle/jdatamunch-mcp) integrations remain governed by their upstream terms. `codex-spine` does not claim affiliation, official distribution, or the right to relicense those projects.
