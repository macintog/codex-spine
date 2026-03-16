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

## jCode Local Route

- `jcode` means the dedicated `jcodemunch` MCP tools for indexed code navigation and symbol retrieval in the installed Codex environment.
- The managed Codex MCP config invokes the upstream `jcodemunch-mcp<2.0` server through the managed `uv` runner.
- No repo-managed `jcodemunch` clone or local launcher is part of the supported path.
- Call `list_repos` and prefer an entry whose `source_root` matches the current repo root.
- If no exact local repo binding exists, call `index_folder` with `path=<repo root>` and `incremental=true`.
- After binding, use the exact repo id returned by `list_repos` or `index_folder` for the rest of the task; do not keep using a bare display name when multiple local indexes may exist.
- Re-bind `jcode` on any repo or `cwd` change, branch or `HEAD` change that may invalidate index assumptions, large refactors, or when results suggest stale or missing coverage.
- Use `get_repo_outline` first for fast orientation; prefer it to `get_file_tree` unless you need directory detail.
- Use `search_symbols` for identifiers, APIs, and symbol discovery; use `get_file_outline` before loading source when you already know the file.
- Use `get_symbols` to batch related implementations and `get_symbol` with `verify=true` when source drift matters.
- Use `get_file_content` for imports, constants, config, or line-range reads; use `search_text` for literals, comments, TODOs, or other non-symbol text.
- Treat `jcode` as API-first for every language: rely on the live tool outputs and observed behavior, not on fork-era assumptions about richer semantics.
- If `jcode` binding fails, the index is missing, or symbol search misses after a reasonable retry, repair with `index_folder` or `invalidate_cache` before broad filesystem scanning.
- Mention `jcode` only when it materially changed repo understanding, found the target faster, or avoided broad file reads.
