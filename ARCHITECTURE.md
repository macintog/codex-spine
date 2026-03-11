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
├── COMPONENTS.toml
├── MAINTAINED_COMPONENTS.toml
├── lib/
│   ├── codex_spine.py          # Shared bootstrap/verify/config helpers and registry validation
│   └── component_manager.py    # Pinned acquisition, status, and license-aware component flow
├── scripts/
│   ├── bootstrap               # Powers the managed install command and refreshes live state
│   ├── verify                  # Validates repo shape and live machine drift
│   ├── render-config           # Renders ~/.codex/config.toml from tracked fragments
│   ├── update                  # Installs or refreshes default and enabled optional components
│   ├── component-status        # Reports managed component health
│   └── component-enable        # Enables optional components such as jCodeMunch MCP
├── codex/
│   ├── AGENTS.md               # Shipped Codex runtime policy for installations using codex-spine
│   └── config/                 # Managed config fragments rendered into ~/.codex/config.toml
├── bin/                        # Durable wrappers and managed launcher entrypoints
├── shell/                      # Managed shell fragments sourced into user shells
├── launchd/                    # Managed macOS LaunchAgent definitions
└── skills/                     # Shipped skills installed under ~/.codex/skills
```

## Core Control Flows

### Managed Install

```text
tracked repo policy + config fragments + wrappers
    -> scripts/bootstrap
    -> stock Python preflight under macOS-shipped python3
    -> existing-config review + optional jCodeMunch choice
    -> Homebrew install if needed + baseline package checks
    -> scripts/bootstrap.py under the managed Python runtime
    -> default managed component install/update
    -> managed symlinks under ~/.codex and ~/.local/bin
    -> zsh-only managed shell source blocks
    -> rendered ~/.codex/config.toml
    -> LaunchAgent render + reload
```

`install` is the mechanism that turns tracked repo state into live user-level machine state. A change to config fragments, wrappers, shell hooks, or LaunchAgent behavior is not really installed until `make install` runs successfully.

### Verification

```text
repo state + live machine state
    -> scripts/verify
    -> component registry validation
    -> export-state hash validation against tracked repo files
    -> private-reference and secret scanning
    -> symlink, shell, config, and LaunchAgent drift checks
    -> default and enabled-optional component health checks
```

`verify` is the guardrail against drift, broken managed state, and accidental leakage of private paths into the public surface.

### Memory and Retrieval Flow

```text
Codex transcripts + project-memory material
    -> sync-codex-chat-qmd.sh
    -> projected markdown + refreshed qmd index under ~/.cache/qmd/codex_chat
    -> codex-memory-mcp public MCP surface backed by the internal qmd-codex adapter
    -> Codex startup context and transcript archaeology
```

This subsystem is the default public core. It exists to give Codex better startup context and retrieval without requiring manual transcript spelunking.

### Optional jCodeMunch MCP Flow

```text
user requests optional indexed code navigation
    -> scripts/component-enable jcodemunch-mcp
    -> retrieve exact upstream terms for the pinned version
    -> save local terms copy + hash under repo-local .state/
    -> require explicit acknowledgement
    -> install/update pinned upstream artifact
    -> render local overlay that wires the MCP server
```

The upstream `jgravelle/jcodemunch-mcp` project stays a separate license boundary throughout this flow. Optional enablement fails closed if the pinned upstream terms cannot be retrieved.

## Key Invariants

- `qmd` and memory are part of the default public core.
- `memory` is the only public MCP surface for transcript retrieval; `qmd-codex` remains an internal adapter.
- `jCodeMunch MCP` is optional but first-class.
- `zsh` is the only tested shell integration path. Non-`zsh` shells should receive a warning and a core-only install rather than silent best-effort mutation.
- launchd, shell, and config surfaces must remain free of private paths and personal-service assumptions.
- `MAINTAINED_COMPONENTS.toml` owns acquisition/update shape; `COMPONENTS.toml` owns boundary and licensing posture.
- Managed update paths must fail closed when post-update health is red instead of accepting version-only success.

## Security and Trust Boundaries

- `codex-spine` is a user-space workstation tool. It does not require root, install privileged daemons, or expose a network listener.
- Tracked repo content and generated public config are intended to remain secret-free.
- Transcript sync and project-memory material are stored locally under `~/.cache/qmd/codex_chat`; users should treat that store as sensitive when transcripts contain sensitive material.
- Optional third-party artifacts and retrieved upstream terms are external inputs. The repo reduces risk through pinned versions and explicit license-aware gating, not through sandboxing.

## Storage and Update Model

- Tracked configuration fragments under `codex/config/` are rendered into `~/.codex/config.toml`.
- Live integration points are mostly symlink-based so tracked repo changes can propagate through `bootstrap`.
- LaunchAgent state is managed from tracked plist definitions and reloaded during bootstrap.
- Repo-local `.state/` stores optional component enablement records and retrieved upstream terms provenance.
- `update` refreshes default components and any already-enabled optional components to the repo’s pinned versions and stops with an error if the component remains unhealthy afterward.

## Why This Doc Exists

`README.md` should explain what `codex-spine` is, how to start, and the core operator workflow for this intentionally simple project. `SECURITY.md` should describe the actual security footprint. `ARCHITECTURE.md` exists for the next level down: how the system is shaped, where responsibilities live, and which invariants maintainers should preserve.
