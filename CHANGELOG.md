# Changelog

All notable user-visible changes to `codex-spine` should be tracked here.

## 0.5.1

Public release follow-up for `codex-spine`. This patch keeps the exported guidance and verifier aligned with the current jcode vocabulary.

- Ordinary code navigation now routes through `jcodemunch` first in the public startup and tooling guidance
- Release verification now expects `get_symbol_source` instead of the older symbol-read wording

## 0.5

First public release line for `codex-spine`. Additional pre-public edits should continue to accumulate here until the first public publication is cut.

- Initial release-candidate line for `codex-spine`
- Managed install, verify, update, and component-status commands
- Default [@tobi/qmd](https://github.com/tobi/qmd) and memory integration
- Optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) enablement now shows the current upstream terms, requires explicit `accept`, and runs the latest compatible `<2.0` release through the managed `uv` runner
- Install now starts from the macOS-shipped `python3` runtime, uses it for a first-run fullscreen preflight, provisions Homebrew when needed, and then hands off to the managed Python implementation
- Install now runs the first transcript sync and [@tobi/qmd](https://github.com/tobi/qmd) index refresh before its final `verify`, with an explicit notice that first-run memory setup may take a while
- Interactive install now treats Homebrew as the baseline package manager, warns and skips untested non-zsh shell mutation, and keeps unprompted optional components out of the default core path
- Interactive install now asks early whether to include the optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) step in the current run when it is not already enabled
- Managed updates and verification now fail closed on unhealthy post-update runtime state instead of treating version-only success as enough
