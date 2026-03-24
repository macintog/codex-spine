# codex-spine Tooling Guide

Load this only when the task actually enters one of these stock installed lanes. Routine startup should stay with `README.md` and `codex/AGENTS.md`. Ordinary code-navigation work counts as entering the indexed code-navigation lane.

## Continuity and Closeout

- For non-trivial multi-session repos, keep a compact continuity packet in the repo itself:
  - project `AGENTS.md` for local execution rules
  - `PROJECT_CONTINUITY.md` for durable purpose, topology, and strategy
  - `CHECKPOINT.md` for the volatile plan-of-record and current handoff
  - optional archive references when the active handoff needs to stay compact
- Treat this continuity packet as project-local working state. Create and update these files in the repo you are actively working in.
- Interpret `begin` as: load the default startup packet and resume from the plan-of-record.
- Interpret `end` as the managed closeout command, not as immediate archive or termination.
- On `end`, ask `Confirm end now? (yes/no)` before any closeout mutations.
- After explicit confirmation, run the repo's closeout flow in order: refresh `CHECKPOINT.md` when execution state changed, update archive references only when detailed notes need to move out of the active handoff, rerun required verification, rerun bootstrap or other live refresh only when managed live surfaces changed, preserve validated work through the repo's own snapshot or backup path when one exists and preservation is intended, refresh the current repo's `jcode` coverage with `index_folder` using `path=<repo root>` and `incremental=true` so the next task sees the latest on-disk state, and always report reload, new-shell, restart, or reboot impact.
- Create the continuity packet for repos that are non-trivial, likely to span multiple sessions, or likely to need handoff continuity.
- Refresh `PROJECT_CONTINUITY.md` only when durable strategy, topology, or success criteria change.
- Refresh `CHECKPOINT.md` when execution state changes and again on explicit closeout.
- Keep deep tooling docs on-demand rather than part of routine startup.

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

- Start ordinary code-navigation work in the `jcodemunch` surface rather than filesystem-first exploration. Treat repo shape, definitions, call sites, symbol usage, and adjacent implementations as entering the code-navigation lane by default.
- Use shell or filesystem-first search first only when the actual question is literal text, filename lookup, or other clearly non-symbol content.
- `jcode` means the dedicated `jcodemunch` MCP tools for indexed code navigation and symbol retrieval in the installed Codex environment.
- The managed Codex MCP config invokes the upstream `jcodemunch-mcp<2.0` server through the managed `uv` runner.
- No repo-managed `jcodemunch` clone or local launcher is part of the supported path.
- Call `list_repos` and prefer an entry whose `source_root` matches the current repo root.
- If no exact local repo binding exists, call `index_folder` with `path=<repo root>` and `incremental=true`.
- After binding, use the exact repo id returned by `list_repos` or `index_folder` for the rest of the task; do not keep using a bare display name when multiple local indexes may exist.
- Default flow after binding: `get_repo_outline`, then `search_symbols`, then `get_symbol_source` or related symbol lookups for precise definitions and call sites.
- Re-bind `jcode` on any repo or `cwd` change, branch or `HEAD` change that may invalidate index assumptions, large refactors, or when results suggest stale or missing coverage.
- Use `search_symbols` for identifiers, APIs, and symbol discovery; use `get_file_outline` before loading source when you already know the file.
- Use `get_symbol_source` with `symbol_id` for a single symbol or `symbol_ids` for a batch, and set `verify=true` when source drift matters.
- Use `get_file_content` for imports, constants, config, or line-range reads; use `search_text` for literals, comments, TODOs, or other non-symbol text.
- When touching an older code path or trying to restore prior behavior, extend the understanding surface to include the earlier implementation before editing. Read the current symbols first, then inspect memory plus `git show`, `git log`, or equivalent history for the older path so the original rationale is in hand before you patch.
- Treat `jcode` as API-first for every language: rely on the live tool outputs and observed behavior, not on fork-era assumptions about richer semantics.
- If `jcode` binding fails, the index is missing, or symbol search misses after a reasonable retry, repair with `index_folder` or `invalidate_cache` before broad filesystem scanning.
- Mention `jcode` only when it materially changed repo understanding, found the target faster, or avoided broad file reads.
