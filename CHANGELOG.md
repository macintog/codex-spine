# Changelog

All notable user-visible changes to `codex-spine` should be tracked here.

## 0.5.4

This release widens the optional indexed-retrieval lane from code-only enablement to a shared three-tool suite.

- The public skill payload now includes `tufte-visualization` and installs it under `~/.codex/skills/` with the other shipped skills
- Interactive install and `./scripts/component-enable jcodemunch-mcp` now treat `jcodemunch-mcp`, `jdocmunch-mcp`, and `jdatamunch-mcp` as one optional suite with one terms readthrough and one `accept`
- The managed optional overlay now wires `jcodemunch`, `jdocmunch`, and `jdatamunch` together while keeping the existing jCodeMunch global profile sync for `~/.code-index/config.jsonc`
- Public docs and package policy now describe the optional jGravelle Munch MCP suite instead of a jCodeMunch-only add-on
- `make upgrade` is available as an explicit repo self-update path for clean checkouts; it fetches release tags, checks out the newest release, then runs install, update, and verify

## 0.5.3

This release tightens the public Codex operating surface for `codex-spine`, bringing the memory model, architecture guide, and shipped workflow surface back into sync.

- The public release line now adds the reusable `project-continuity` and `multi-step` skills as part of the installable workflow surface
- Shipped public guidance now treats built-in Codex memories as complementary client-managed context while keeping the `memory` MCP lane as the operator-facing bootstrap and transcript-retrieval path
- Public config examples and verifier coverage now call out the built-in memory controls that matter operationally, including `/memories`, `memories.use_memories`, `memories.generate_memories`, and `memories.disable_on_external_context`
- `ARCHITECTURE.md` now reflects that split explicitly so the deep technical reference matches the shipped README and Codex operating docs

## 0.5.2

Public release follow-up for `codex-spine`.

- Updated the installer and optional enable flow to handle the current upstream jCodeMunch EULA page
- The fullscreen installer terms viewer now preserves quoted heading, paragraph, and bullet formatting for the current upstream jCodeMunch terms text
- The shipped public guidance now stays compatible with the stock Codex GitHub plugin without exporting repo-local GitHub skills

## 0.5.1

Current installable public release line for `codex-spine`. This patch keeps the shipped public docs, verifier, and package policy aligned with the published product surface.

- Ordinary code navigation now routes through `jcodemunch` first in the public startup and tooling guidance
- Public repo verification now expects `get_symbol_source` instead of the older symbol-read wording
- Public closeout guidance and verification no longer require repo-local Git helpers
- Install now manages `~/.config/uv/uv.toml` with a seven-day default quarantine and a package-specific `jcodemunch-mcp` override so the optional runner stays installable on clean systems

## 0.5

Initial public release line for `codex-spine`.

- Initial public release line for `codex-spine`
- Managed install, verify, update, and component-status commands
- Default [@tobi/qmd](https://github.com/tobi/qmd) and memory integration
- Optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) enablement now shows the current upstream terms, requires explicit `accept`, and runs the latest compatible `<2.0` release through the managed `uv` runner
- Install now starts from the macOS-shipped `python3` runtime, uses it for a first-run fullscreen preflight, provisions Homebrew when needed, and then hands off to the managed Python implementation
- Install now runs the first transcript sync and [@tobi/qmd](https://github.com/tobi/qmd) index refresh before its final `verify`, with an explicit notice that first-run memory setup may take a while
- Interactive install now treats Homebrew as the baseline package manager, warns and skips untested non-zsh shell mutation, and keeps unprompted optional components out of the default core path
- Interactive install now asks early whether to include the optional [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) step in the current run when it is not already enabled
- Managed updates and verification now fail closed on unhealthy post-update runtime state instead of treating version-only success as enough
