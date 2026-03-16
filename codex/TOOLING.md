# codex-spine Tooling Guide

Load this only when the task actually enters one of these stock installed lanes. Routine startup should stay with `README.md` and `codex/AGENTS.md`.

## Continuity and Memory

- Use the direct `memory.bootstrap_context` tool call on the first assistant turn in a new thread, at the start of any materially new user request, on repo or `cwd` changes, on resume or prior-thread references, and on compaction-drift symptoms. Pass `max_recent_sessions=3`.
- Prefer calling `memory.bootstrap_context` directly instead of trying to open a startup file or generic resource view first.
- Treat automatic bootstrap as durable context restoration only. It must not auto-recap prior task work or choose the next task.
- Use direct memory retrieval, not bootstrap, when exact prior wording or broader historical evidence matters.
- Default retrieval flow: `search` for exact symptom or identifier wording, `deep_search` for analogous prior decisions, `vector_search` for semantic similarity, then `get` or `multi_get` on the best matches before continuing.
- If the same symptom survives two attempted fixes, re-anchor with `memory.bootstrap_context` before another retry.
- If a client also exposes `qmd://codex-chat/...` reads, treat them as optional read helpers rather than the default startup lane.
- If `memory.bootstrap_context` fails, fall back to `qmd-memory-latest.sh`, summarize its output, and continue. `qmd-codex` is the managed adapter behind this memory path.

## Code Navigation

- When indexed code navigation would materially reduce broad file scanning, use the optional `jcodemunch` surface rather than filesystem-first exploration.
- Default flow: `search_symbols`, then `get_symbol` or related symbol lookups for precise definitions and call sites.
- Fall back to broad file scans only when the indexed surface is unavailable or clearly misses the target.
