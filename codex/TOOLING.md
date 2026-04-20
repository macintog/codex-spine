# codex-spine Tooling Guide

Load this only when the task actually enters one of these installed lanes. Routine startup should stay with `README.md` and `codex/AGENTS.md`.

## Continuity

- For non-trivial multi-session repos, keep the continuity packet compact and in-repo: `AGENTS.md`, `PROJECT_CONTINUITY.md`, and `CHECKPOINT.md`.
- Use `memory.bootstrap_context` when a new thread or re-anchor needs durable repo continuity: repo or `cwd` changes, prior-thread references, compaction-drift symptoms, or any case where the startup packet and current turn are not enough.
- Treat bootstrap as restoration of durable context, not as permission to resume an old task automatically.
- Keep deeper docs and skill bodies on-demand so routine startup stays cheap.

## Memory

- Use the `memory` MCP tools for durable recall when prior wording, earlier decisions, or older evidence matters.
- Start with `memory.bootstrap_context` for re-anchoring and use `search`, `deep_search`, `vector_search`, `get`, or `multi_get` when you need targeted retrieval.
- Treat built-in Codex memories and app-managed files under `~/.codex/memories/` as complementary client-managed context, not the operator-facing transcript retrieval lane. Keep required rules in `AGENTS.md` or checked-in docs.
- Built-in memories are off by default. In this installed environment, prefer Codex settings, `/memories`, or `codex/config/90-local.toml` when you want to enable or tune them.
- The built-in settings that matter most operationally are `memories.generate_memories`, `memories.use_memories`, and `memories.no_memories_if_mcp_or_web_search`; `memories.extract_model` and `memories.consolidation_model` remain optional tuning overrides.
- Prefer returned identifiers and tool output over guessed URIs, guessed paths, or reconstructed memory targets.
- If the memory lane fails, surface that clearly instead of guessing from recap.

## Code Navigation

- Start ordinary code-navigation work in the `jcodemunch` lane when it is available.
- Prefer targeted retrieval such as `search_symbols`, `get_file_outline`, and `get_symbol_source` over broad file reads.
- Use filesystem-first search for literal text or filename lookup, other small non-symbol checks, or after the indexed lane misses and needs repair.
- If the current repo is not bound yet or the index looks stale, refresh it with `list_repos` and `index_folder` before broad scanning.
