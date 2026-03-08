# User Guide

## Install

1. Clone `codex-spine`.
2. Run `make bootstrap`.
3. Run `make verify`.

This repo is macOS-first. Linux would typically replace launchd with systemd timers or user services. Windows would typically replace shell fragments and launchd with PowerShell profile wiring and Task Scheduler equivalents.

## Daily Commands

- `make update`: refresh default and enabled optional components to the repo's pinned versions
- `make verify`: validate repo and live-machine state
- `./scripts/component-status`: inspect managed component health

## Optional jcode

Enable indexed code navigation with:

```bash
./scripts/component-enable jcode
```

The command retrieves the exact upstream terms for the pinned version, stores a local copy under `.state/licenses/`, and requires explicit acknowledgement before install.

## Troubleshooting

- If `make verify` says the live config is stale, run `make bootstrap`.
- If transcript sync is missing, check `~/Library/LaunchAgents/io.codex.spine.qmd-codex-chat.plist` and re-run `make bootstrap`.
- If `jcode` will not enable, inspect the stored upstream terms retrieval error first; the enable flow intentionally hard-fails when it cannot verify the upstream terms for the pinned version.
