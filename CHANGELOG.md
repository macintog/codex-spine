# Changelog

All notable user-visible changes to `codex-spine` should be tracked here.

## Unreleased

- Initial release-candidate line for `codex-spine`
- Managed bootstrap, verify, update, and component-status commands
- Default QMD and memory integration
- Optional `jCodeMunch MCP` enablement with fetched-term acknowledgement
- Bootstrap now starts from a macOS-shipped shell path, provisions Homebrew Python when the default `python3` is too old, and then hands off to the managed Python implementation
- Bootstrap now runs the first transcript sync and QMD index refresh before its final `verify`, with an explicit notice that first-run memory setup may take a while
- Interactive bootstrap now treats Homebrew as the baseline package manager, warns and skips untested non-zsh shell mutation, and keeps optional component enablement outside first-run install
- Managed updates and verification now fail closed on unhealthy post-update runtime state instead of treating version-only success as enough
