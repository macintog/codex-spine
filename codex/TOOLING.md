# codex-spine Tooling Guide

Load this only when the task actually enters one of these lanes. Routine startup should stay with `README.md` and `codex/AGENTS.md`.

## Continuity and Memory

- This public repo keeps the old continuity skill behavior in shipped docs and the memory lane here rather than in extra exported guidance packages.
- Use the direct `memory.bootstrap_context` tool call on the first assistant turn in a new thread, at the start of any materially new user request, on repo or `cwd` changes, on resume or prior-thread references, and on compaction-drift symptoms. Pass `max_recent_sessions=3`.
- Prefer calling `memory.bootstrap_context` directly instead of trying to open a startup file or generic resource view first.
- Treat automatic bootstrap as durable context restoration only. It must not auto-recap prior task work or choose the next task.
- Use direct memory retrieval, not bootstrap, when exact prior wording or broader historical evidence matters.
- Default retrieval flow: `search` for exact symptom or identifier wording, `deep_search` for analogous prior decisions, `vector_search` for semantic similarity, then `get` or `multi_get` on the best matches before continuing.
- If the same symptom survives two attempted fixes, re-anchor with `memory.bootstrap_context` before another retry.
- If a client also exposes `qmd://codex-chat/...` reads, treat them as optional read helpers rather than the default startup lane.
- If `memory.bootstrap_context` fails, fall back to `qmd-memory-latest.sh`, summarize its output, and continue. `qmd-codex` is the managed adapter behind this memory path.

## Self-Hosting Changes

- Load this section when the task edits startup docs, tooling guides, public docs, config fragments, launchers, or managed links that Codex relies on to understand or operate this repo.
- Treat those as one coordinated surface: update the shipped docs or skills, the relevant verify gates, and the operator guidance together.
- If the semantics materially changed, re-read the changed docs in-thread before continuing. In closeout, say whether the current thread should reload docs, whether a fresh Codex session is recommended, and whether current terminals, new shells, app restarts, or reboots are affected.
- If live managed paths, shell hooks, config, or launchers changed, rerun `make install`. Doc-only self-hosting edits do not require it.

## Code Navigation

- When indexed code navigation would materially reduce broad file scanning, use the optional `jcodemunch` surface rather than filesystem-first exploration.
- Default flow: `search_symbols`, then `get_symbol` or related symbol lookups for precise definitions and call sites.
- Fall back to broad file scans only when the indexed surface is unavailable or clearly misses the target.

## GitHub Work

- Use this lane for GitHub-hosted work such as repo shaping, release discipline, public-doc maintenance, and component-boundary decisions.
- Keep public docs, manifests, verify gates, and implementation aligned when a shipped surface changes.
