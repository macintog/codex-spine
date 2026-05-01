# codex-spine Tooling Guide

Load this only when the task actually enters one of these installed lanes. Routine startup should stay with `README.md` and `codex/AGENTS.md`.

## Continuity

- For non-trivial multi-session repos, keep the continuity packet compact and in-repo: `AGENTS.md`, `PROJECT_CONTINUITY.md`, and `CHECKPOINT.md`.
- Use `memory.bootstrap_context` when a new thread or re-anchor needs durable repo continuity: repo or `cwd` changes, prior-thread references, compaction-drift symptoms, or any case where the startup packet and current turn are not enough.
- Treat bootstrap as restoration of durable context, not as permission to resume an old task automatically.
- Keep deeper docs and skill bodies on-demand so routine startup stays cheap.

## Memory

- Use the `memory` MCP tools for durable recall when prior wording, earlier decisions, or older evidence matters.
- Start with `memory.bootstrap_context` for re-anchoring. For targeted retrieval, choose the smallest memory tool that answers the question: use `deep_search` as the default broad-recall path, `search` for exact terms, identifiers, filenames, or quoted phrases, and `vector_search` for same-idea/different-wording recall. If exact `search` returns nothing, broaden the wording or switch to `deep_search` or `vector_search` before concluding there is no evidence.
- Follow retrieval hits with `get` or `multi_get` on returned identifiers before relying on the result.
- Treat built-in Codex memories and app-managed files under `~/.codex/memories/` as complementary client-managed context, not the operator-facing transcript retrieval lane. Keep required rules in `AGENTS.md` or checked-in docs.
- Built-in memories are off by default. In this installed environment, prefer Codex settings, `/memories`, or `codex/config/90-local.toml` when you want to enable or tune them.
- The built-in settings that matter most operationally are `memories.generate_memories`, `memories.use_memories`, and `memories.disable_on_external_context`; `memories.no_memories_if_mcp_or_web_search` is a legacy alias, while `memories.extract_model` and `memories.consolidation_model` remain optional tuning overrides.
- Prefer returned identifiers and tool output over guessed URIs, guessed paths, or reconstructed memory targets.
- If the memory lane fails, surface that clearly instead of guessing from recap.

## Code Navigation

- Start ordinary code-navigation work in the `jcodemunch` lane when it is available.
- Prefer targeted retrieval such as `search_symbols`, `get_file_outline`, and `get_symbol_source` over broad file reads.
- For broad symbol discovery, leave `detail_level` implicit unless you need a specific shape; newer upstream builds can return a cheaper compact default when `max_results >= 5`.
- When you need bundled context instead of discovery, pass a real `token_budget` so the upstream server can keep the response inside that budget.
- Use filesystem-first search for literal text or filename lookup, other small non-symbol checks, or after the indexed lane misses and needs repair.
- If the current repo is not bound yet or the index looks stale, refresh it with `list_repos` and `index_folder` before broad scanning.

## Git Lifecycle

- Treat `do git magic` as a full local lifecycle request: commit the intended work, finish or merge it back to the authoritative line, clean up the current topic branch and safe residue, push keeper changes to the configured forge or local-host remote, and end with clean top-of-tree proof for every participating checkout.
- Before mutating Git state, establish the authoritative base, current branch, unique commits, uncommitted changes, remote targets, participating repos or generated checkouts, and whether unrelated dirt or residue is present.
- Run required generation, formatting, materialization, and validation before the first commit so generated files are included in the intended change set when they belong there.
- Keep commit, merge, finish, repair, and push actions single-writer. Re-check status after each mutation because hooks, merge drivers, validation, index refreshes, generated files, submodules, or adjacent checkouts can make a tree dirty.
- Push the authoritative line to the configured keeper remotes before residue repair. If a helper refuses only because the just-finished authoritative branch is ahead of its remote, use the repo's documented direct push path and then re-run lifecycle status.
- Prune all remote aliases that may have seen the topic branch, then re-check that merged topic tracking refs are gone.
- Re-home the terminal before reclaiming a worktree. If the current terminal is still inside a cleanup target, stop cleanup or move to a preserved checkout first.
- If a full validation gate is blocked by unrelated live machine state, record the exact blocker, run the strongest scoped proof for the intended change, and stop retrying the same failing gate until the blocker changes.
- If lifecycle status still reports residue after preservation and push, inspect whether it is actionable. Clean Codex-created helper worktrees and preserved scratch state should be reclaimed; dirty, locked, live-owned, or current-terminal cleanup targets should block or be reported instead.
- If new dirt appears after a mutation, classify it before continuing. Commit keeper dirt, repair only safe residue, and stop if preservation intent, base choice, or publish target is ambiguous.
- The final proof is a clean status on the authoritative top-of-tree line after the push, remote-head proof, status for every participating checkout, no task-owned actionable residue, proof that topic refs were retired only after ancestry or patch-equivalence preservation, and any remote prune or cleanup the repo documents.

## Documentation Navigation

- Use the `jdocmunch` lane when the task is about authored docs, manuals, or reference trees rather than source code.
- Prefer `search_sections`, `get_section`, and `get_section_context` over opening whole files.
- Start by indexing the docs source and inspecting structure with `list_repos`, `get_toc_tree`, or `get_document_outline`.

## Tabular Data Navigation

- Use the `jdatamunch` lane when the task is about CSVs, spreadsheets, parquet tables, or dataset shape rather than source code or authored docs.
- Call `describe_dataset` before pulling rows so the schema and likely filter columns are grounded first.
- Prefer `search_data`, `get_rows`, and `aggregate` over loading whole datasets into context.
