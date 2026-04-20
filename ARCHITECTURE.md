# Architecture

This is the deep technical reference for `codex-spine`. Use it when the work requires subsystem boundaries, data flow, or operational invariants rather than install instructions alone.

## Directory Structure

```text
codex-spine/
├── LICENSE
├── README.md
├── ARCHITECTURE.md
├── SECURITY.md
├── CHANGELOG.md
├── MAINTAINED_COMPONENTS.toml
├── Makefile                    # Thin public dispatcher for install/verify/update/component-status
├── lib/
│   ├── _vendor/tomllib/        # Vendored TOML parser fallback for older stock Python runtimes
│   ├── codex_spine.py          # Shared bootstrap/verify/config helpers, managed-link logic, and path policy
│   ├── component_manager.py    # Managed acquisition, status, and optional-component gating
│   ├── install_tui.py          # Fullscreen install UI shared by preflight and main bootstrap
│   └── toml_compat.py          # TOML loader shim that prefers stdlib and falls back to vendored code
├── scripts/
│   ├── bootstrap               # Shell entrypoint for managed install and live-state refresh
│   ├── bootstrap-preflight.py  # Fullscreen first-run preflight under stock macOS python3
│   ├── bootstrap.py            # Main managed installer after runtime handoff
│   ├── verify                  # Validates repo shape, shipped public contracts, and live machine drift
│   ├── render-config           # Renders ~/.codex/config.toml from tracked fragments
│   ├── update                  # Installs or refreshes default and enabled optional components
│   ├── component-status        # Reports managed component health
│   └── component-enable        # Enables optional third-party code-navigation integrations
├── codex/
│   ├── AGENTS.md               # Compact shipped Codex startup and operating guidance
│   ├── TOOLING.md              # On-demand public continuity, memory, and code-navigation guidance
│   └── config/                 # Managed config fragments rendered into ~/.codex/config.toml
├── skills/
│   ├── project-continuity/     # Reusable continuity skill, starter templates, and adoption reference
│   └── multi-step/             # Reusable serial-pass workflow skill and packet templates
├── bin/                        # Durable wrappers and managed launcher entrypoints
├── shell/
│   ├── zprofile.codex.sh       # Managed zsh login-shell source fragment
│   ├── zshrc.codex.sh          # Managed zsh interactive-shell source fragment
│   ├── bash_profile.codex.sh   # Manual fallback fragment for non-zsh shell wiring
│   └── codex.local.env.example # Starter local shell env overlay copied into a gitignored live file
├── uv/                         # Managed account-wide uv policy rendered to ~/.config/uv/uv.toml
└── launchd/                    # Managed macOS LaunchAgent definitions
```

## Core Control Flows

### Managed Install

```text
tracked repo policy + config fragments + wrappers
    -> Makefile install dispatcher
    -> scripts/bootstrap
    -> stock Python preflight under macOS-shipped python3
    -> existing-config review + Homebrew/package preflight
    -> continue in the same fullscreen installer session
    -> scripts/bootstrap.py under the current Python runtime
    -> managed config adoption + local example files + managed symlinks
    -> managed ~/.config/uv/uv.toml with a seven-day default quarantine and a package-specific jcodemunch override
    -> managed zsh source blocks when supported, with repo-local manual shell fragments otherwise
    -> default managed component install/update
    -> optional jcodemunch acknowledgement + enablement when chosen
    -> rendered ~/.codex/config.toml
    -> LaunchAgent render
    -> first transcript sync + qmd index refresh
    -> launchctl bootstrap for background sync
    -> final verify
```

`install` is the mechanism that turns tracked repo state into live user-level machine state. A change to config fragments, wrappers, shell hooks, or LaunchAgent behavior is not really installed until `make install` runs successfully.

`Makefile` is part of the public operator surface, not build-only scaffolding. It is the thin dispatcher for `install`, `verify`, `update`, and `component-status`, while the shell and Python files under `scripts/` and `lib/` hold the actual implementation.

### Verification

```text
repo state + live machine state
    -> scripts/verify
    -> maintenance manifest validation
    -> public doc, skill, and routing-contract validation
    -> private-reference and secret scanning
    -> symlink, shell, config, and LaunchAgent drift checks
    -> default and enabled-optional component health checks
```

`verify` is the guardrail against drift, broken managed state, and accidental leakage of private paths or maintainer-only contracts into the public surface. The shipped repo-only path is behavior-first and boundary-first: it validates exported skills, the slim public `codex/AGENTS.md` and `codex/TOOLING.md` routing surface, manifests, and other public interfaces without hard-freezing every sentence.

### Memory and Retrieval Flow

```text
Codex transcripts + project-memory material
    -> sync-codex-chat-qmd.sh
    -> projected markdown + refreshed retrieval index under ~/.cache/qmd/codex_chat
    -> codex-memory-mcp public MCP surface backed by the internal qmd-codex adapter
    -> Codex startup context and transcript archaeology
```

This subsystem is the default public core. It is built around [@tobi/qmd](https://github.com/tobi/qmd) and exists to give Codex better startup context and retrieval without requiring manual transcript spelunking.

Built-in Codex memories and app-managed files under `~/.codex/memories/` are complementary client-managed context in this design, not the operator-facing retrieval lane. The shipped public contract keeps required rules in `codex/AGENTS.md` or checked-in repo docs, uses the `memory` MCP surface for bootstrap and transcript retrieval, and treats `/memories` plus `codex/config/90-local.toml` as the right control points for built-in settings such as `memories.use_memories`, `memories.generate_memories`, and `memories.no_memories_if_mcp_or_web_search`.

When project framing files exist in a target repo, the transcript-sync path prefers `PROJECT_CONTINUITY.md` as the durable product frame before lower-level handoff details so startup context stays anchored on purpose instead of only the latest execution state.

### Optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) Flow

```text
user requests optional indexed code navigation
    -> scripts/component-enable jcodemunch-mcp
    -> retrieve the current upstream terms text
    -> require explicit accept at enable time
    -> validate the latest compatible upstream uv runner invocation under <2.0
    -> render local overlay that wires the MCP server
```

The upstream [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) project stays a separate license boundary throughout this flow. Optional enablement fails closed if the managed `<2.0` compatibility contract cannot be satisfied.

## Public Understanding Surface

`codex-spine` deliberately ships a smaller public operating surface than the private source repo it is derived from.

- `README.md` and `Makefile` are the public operator entrypoints; common commands dispatch into `scripts/`.
- `codex/AGENTS.md` is the compact startup and operating policy for installed public use.
- `codex/TOOLING.md` is the public on-demand guide for continuity, memory retrieval, and code navigation only.
- `skills/project-continuity/` and `skills/multi-step/` are reusable workflow scaffolds, not maintainer control-plane docs.
- Repo-specific Git lifecycle helpers, maintainer closeout choreography, export QA authority, and private release-lane governance stay outside the shipped public tree.

That split is intentional. The public repo should explain installed product behavior and reusable workflow patterns without publishing the maintainer control plane that produces the repo.

## Public Runtime Payload

Some shipped runtime pieces are easy to miss if you only look at the top-level wrappers.

- `lib/install_tui.py` is shared by `scripts/bootstrap-preflight.py` and `scripts/bootstrap.py` so the interactive install stays in one fullscreen UI model across the handoff from stock macOS Python to the selected runtime.
- `lib/toml_compat.py` and `lib/_vendor/tomllib/` are part of the public runtime contract because `codex-spine` still needs TOML parsing to work on stock macOS Python versions that do not ship stdlib `tomllib`.
- `shell/zprofile.codex.sh` and `shell/zshrc.codex.sh` are the managed zsh integration fragments; `shell/bash_profile.codex.sh` and `shell/codex.local.env.example` are shipped manual fallback surfaces for users who want shell integration without the managed zsh path.
- The repo-local `shell/codex.local.env` and `codex/config/90-local.toml` files are intentionally local-only live overlays copied from shipped examples when missing; they are not part of the tracked public payload.

## Public Skill Payload

The shipped `skills/` tree is part of the public product surface, not incidental example content.

### `skills/project-continuity/`

This tree ships a reusable continuity workflow for long-lived repos:

- `SKILL.md` defines the continuity model itself: durable project authority, volatile handoff, startup packet shape, and self-hosting rules.
- `templates/PROJECT_CONTINUITY.md`, `templates/CHECKPOINT.md`, and `templates/AGENTS.md` provide starter files for repos that adopt that continuity structure.
- `references/unseen-repo-adoption-prompt.md` is a reusable audit/adoption prompt for deciding whether a repo should stay repo-native, use a local overlay, or adopt the packet in-tree.

This skill is reusable scaffolding. It does not mean `codex-spine` itself owns the downstream repo's continuity files.

### `skills/multi-step/`

This tree ships a reusable serial-pass workflow for larger, drift-prone efforts:

- `SKILL.md` defines the pass model, queue truth, pass types, and authority-order discipline.
- `templates/serial-program/` is the fuller packet for open-ended or multi-surface programs, including `SPINE.md`, `CHECKPOINT.md`, `STATUS.toml`, `QUESTION_BANK.md`, `SURFACE_MAP.md`, and pass templates.
- `templates/finite-findings/` is the lighter packet for bounded issue-retirement work such as scoped findings sweeps or narrow follow-on cleanup.
- `templates/README.md` is the index for choosing between the two packet styles.

Like `project-continuity`, this skill is meant to be copied into the repo being worked in as needed. The shipped tree in `codex-spine` is the reusable source payload, not active state for every downstream project.

## Key Invariants

- [@tobi/qmd](https://github.com/tobi/qmd) and memory are part of the default public core.
- Public workflow skills ship under `skills/` as reusable scaffolding; the actual continuity packet files still live in the repo being worked in.
- The public skill payload is intentionally narrow: `project-continuity` and `multi-step` only, plus their shipped templates and the single public adoption reference.
- `memory` is the only public MCP surface for transcript retrieval; `qmd-codex` remains an internal adapter.
- Built-in Codex memories remain an optional complementary surface, not a replacement for the `memory` MCP lane; required rules stay in shipped docs, and durable built-in-memory defaults belong in `codex/config/90-local.toml` rather than generated state under `~/.codex/memories/`.
- [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) is optional but first-class.
- The shipped `codex/TOOLING.md` surface is intentionally limited to continuity, memory, and code navigation; maintainer-only Git and release governance are out of scope for the public repo.
- Managed shell-dotfile mutation is only tested for `zsh`. Non-`zsh` shells should receive a warning and a core-only install rather than silent best-effort mutation, with the shipped shell fragments kept available for explicit manual wiring.
- launchd, shell, and config surfaces must remain free of private paths and personal-service assumptions.
- `MAINTAINED_COMPONENTS.toml` owns shipped acquisition and update shape; public runtime behavior should not depend on export-control metadata.
- Managed update paths must fail closed when post-update health is red instead of accepting version-only success.

## Security and Trust Boundaries

- `codex-spine` is a user-space workstation tool. It does not require root, install privileged daemons, or expose a network listener.
- Tracked repo content and generated public config are intended to remain secret-free.
- Transcript sync and project-memory material are stored locally under the [@tobi/qmd](https://github.com/tobi/qmd)-backed cache at `~/.cache/qmd/codex_chat`; users should treat that store as sensitive when transcripts contain sensitive material.
- Optional third-party artifacts and retrieved upstream terms text are external inputs. The repo reduces risk through compatibility constraints and explicit opt-in gating, not through sandboxing.

## Storage and Update Model

- Tracked configuration fragments under `codex/config/` are rendered into `~/.codex/config.toml`.
- Existing unmanaged Codex settings can be adopted into `codex/config/80-adopted.toml`, while machine-specific local overrides live in `codex/config/90-local.toml`.
- `bootstrap` also copies `shell/codex.local.env.example` into a gitignored `shell/codex.local.env` when the local env overlay is missing.
- Live integration points are mostly symlink-based so tracked repo changes can propagate through `bootstrap`.
- LaunchAgent state is managed from tracked plist definitions and reloaded during bootstrap.
- Repo-local `.state/` stores optional component enablement records.
- `update` refreshes default components and any already-enabled optional components to the repo’s managed versions or compatibility constraints and stops with an error if the component remains unhealthy afterward.
- Exported skills, docs, and verifier gates are expected to agree as one shipped understanding surface. When they drift, `scripts/verify.py --repo-only` is supposed to catch it before release.

## Why This Doc Exists

`README.md` should explain what `codex-spine` is, how to start, and the core operator workflow for this intentionally simple project. `SECURITY.md` should describe the actual security footprint. `ARCHITECTURE.md` exists for the next level down: how the system is shaped, where responsibilities live, and which invariants maintainers should preserve.
