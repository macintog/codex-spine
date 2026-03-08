# Architecture

This is the maintainer-level technical map for `codex-spine`.

## Directory Structure

```text
codex-spine/
├── README.md
├── PROJECT_SPINE.md
├── CHECKPOINT.md
├── USER_GUIDE.md
├── ARCHITECTURE.md
├── SECURITY.md
├── CHANGELOG.md
├── COMPONENTS.toml
├── MAINTAINED_COMPONENTS.toml
├── lib/
│   ├── codex_spine.py
│   └── component_manager.py
├── scripts/
│   ├── bootstrap
│   ├── verify
│   ├── render-config
│   ├── update
│   ├── component-status
│   └── component-enable
├── codex/
│   ├── AGENTS.md
│   └── config/
├── bin/
├── shell/
├── launchd/
└── skills/
```

## Core Flows

### Bootstrap

tracked repo state
-> managed symlinks under `~/.codex/skills` and `~/.local/bin`
-> shell source blocks
-> default component install/update
-> rendered `~/.codex/config.toml`
-> rendered launch agent
-> optional `jcode` offer

### Verification

repo state + live machine state
-> registry validation
-> private-reference leak checks
-> symlink and shell-block checks
-> rendered config and launchd drift checks
-> default and enabled-optional component health checks

### Optional Third-Party Component Flow

`jcode` is treated as an optional managed component with a separate upstream license boundary:

1. retrieve terms for the pinned version
2. save a local copy and hash
3. require explicit acknowledgement
4. install/update the pinned upstream artifact
5. render the local overlay that wires the MCP server

## Invariants

- `qmd` and memory are part of the default public core.
- `jcode` is optional but first-class.
- launchd, shell, and config surfaces must remain free of private incubator paths and personal-service assumptions.
- `MAINTAINED_COMPONENTS.toml` owns acquisition/update shape; `COMPONENTS.toml` owns boundary and licensing posture.
