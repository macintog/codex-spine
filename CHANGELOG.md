# Changelog

All notable user-visible changes to `codex-spine` should be tracked here.

## Unreleased

- Initial release-candidate line for `codex-spine`
- Managed install, verify, update, and component-status commands
- Default [@tobi/qmd](https://github.com/tobi/qmd) and memory integration
- Optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) enablement with fetched-term acknowledgement
- Install now starts from the macOS-shipped `python3` runtime, uses it for a first-run fullscreen preflight, provisions Homebrew when needed, and then hands off to the managed Python implementation
- Install now runs the first transcript sync and [@tobi/qmd](https://github.com/tobi/qmd) index refresh before its final `verify`, with an explicit notice that first-run memory setup may take a while
- Interactive install now treats Homebrew as the baseline package manager, warns and skips untested non-zsh shell mutation, and keeps optional component enablement outside first-run install
- Interactive install again asks early whether to keep the optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) step in the current run, even when local state already has it enabled
- Managed updates and verification now fail closed on unhealthy post-update runtime state instead of treating version-only success as enough
