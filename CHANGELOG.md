# Changelog

All notable user-visible changes to `codex-spine` should be tracked here.

## Unreleased

- Initial release-candidate line for `codex-spine`
- Managed bootstrap, verify, update, and component-status commands
- Default QMD and memory integration
- Optional `jCodeMunch MCP` enablement with fetched-term acknowledgement
- Interactive bootstrap now treats Homebrew as the baseline package manager, warns and skips untested non-zsh shell mutation, and keeps optional component enablement outside first-run install
- Managed updates and verification now fail closed on unhealthy post-update runtime state instead of treating version-only success as enough
