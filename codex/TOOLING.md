# codex-spine Tooling Guide

Load this only when the task actually enters one of these installed lanes. Routine startup should stay with `README.md` and `codex/AGENTS.md`.

## Continuity

- For non-trivial multi-session repos, keep the continuity packet compact and in-repo: `AGENTS.md`, `PROJECT_CONTINUITY.md`, and `CHECKPOINT.md`.
- Use `memory.bootstrap_context` only for durable re-anchor after a repo or `cwd` change (`reason=repo_cwd_change`), prior-thread recovery (`reason=prior_thread_recovery`), or demonstrated compaction drift (`reason=demonstrated_drift`). The adapter bounds and deduplicates same-project calls by reason and recent-session limit; use direct retrieval plus `get` or `multi_get` for historical wording and evidence.
- Treat bootstrap as restoration of durable context, not as permission to resume an old task automatically.
- Keep deeper docs and skill bodies on-demand so routine startup stays cheap.

## Memory

- Use the `memory` MCP tools for durable recall when prior wording, earlier decisions, or older evidence matters.
- For one of the three durable re-anchor cases, call `memory.bootstrap_context` with the matching reason. For targeted retrieval, choose the smallest memory tool that answers the question: use `deep_search` as the default broad-recall path, `search` for exact terms, identifiers, filenames, or quoted phrases, and `vector_search` for same-idea/different-wording recall. If exact `search` returns nothing, broaden the wording or switch to `deep_search` or `vector_search` before concluding there is no evidence.
- Follow retrieval hits with `get` or `multi_get` on returned identifiers before relying on the result.
- Treat built-in Codex memories and app-managed files under `~/.codex/memories/` as complementary client-managed context, not the operator-facing transcript retrieval lane. Keep required rules in `AGENTS.md` or checked-in docs.
- Built-in memories are enabled by the base config so new projects and projectless Codex conversations inherit memory without project-local setup. Prefer Codex settings, `/memories`, or `codex/config/90-local.toml` only when you want to inspect or intentionally narrow that default.
- The built-in settings that matter most operationally are `features.memories`, `memories.generate_memories`, `memories.use_memories`, and `memories.disable_on_external_context`; `memories.no_memories_if_mcp_or_web_search` is a legacy alias, while `memories.extract_model` and `memories.consolidation_model` remain optional tuning overrides.
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

- Before app worktree creation, the parent preflights Git from the canonical checkout and performs separately authorized Git bootstrap. An app-created checkout is adopted by exact path as `mode=worktree`. Successful adoption installs the repo-local managed commit guard only when no custom `hooksPath` exists; existing project hooks are preserved and exact lifecycle adoption remains authoritative. Ordinary prompts need only describe the work, then conversational `end -yes`.
- Treat confirmed `end` as task-scoped completion: under one repository control-plane lock, commit, integrate through the canonical target checkout, run proof, push and verify keepers, then re-home and retire only current-task state in that same closeout turn. Preserve ordinary non-overlapping canonical dirt only after replay to latest authority and content-level pre/post fingerprint proof; overlaps, special Git/index states, nested/submodule/unsafe files, or proof mismatch fail closed without a model-visible bypass. Task idleness is not success.
- Before mutating Git state, establish the authoritative base, current branch, unique commits, uncommitted changes, remote targets, participating repos or generated checkouts, and whether unrelated dirt or residue is present.
- Run required generation, formatting, materialization, and validation before the first commit so generated files are included in the intended change set when they belong there.
- Keep lifecycle-state changes plus commit, integration, and push actions under one repository control-plane lock. The parent must inspect final disposition and repository proof after closeout; re-check status after each mutation because hooks, merge drivers, validation, index refreshes, generated files, submodules, or adjacent checkouts can make a tree dirty.
- Push the authoritative line to the configured keeper remotes before residue repair. The lifecycle helper must verify each exact remote head with `git ls-remote`; a local tracking ref alone isn't completion proof.
- Prune stale local remote-tracking refs after preservation. Keep backend topic refs as historical authority unless the operator explicitly names the exact remote and ref for deletion.
- Re-home the terminal before reclaiming a worktree. If the current terminal is still inside a cleanup target, stop cleanup or move to a preserved checkout first.
- If a full validation gate is blocked by unrelated live machine state, record the exact blocker, run the strongest scoped proof for the intended change, and stop retrying the same failing gate until the blocker changes.
- If lifecycle status still reports residue after preservation and push, inspect whether it is actionable. Clean Codex-created helper worktrees and preserved scratch state should be reclaimed; dirty, locked, live-owned, or current-terminal cleanup targets should block or be reported instead.
- If new dirt appears after a mutation, classify it before continuing. Commit keeper dirt, repair only safe residue, and stop if preservation intent, base choice, or publish target is ambiguous.
- The final proof is a clean status on the authoritative top-of-tree line after the push, exact remote-head proof, status for every participating checkout, no task-owned actionable residue, and proof that local topic refs were retired only after ancestry or patch-equivalence preservation.

## Documentation Navigation

- Use the `jdocmunch` lane when the task is about authored docs, manuals, or reference trees rather than source code.
- Prefer `search_sections`, `get_section`, and `get_section_context` over opening whole files.
- Start by indexing the docs source and inspecting structure with `list_repos`, `get_toc_tree`, or `get_document_outline`.

## Tabular Data Navigation

- Use the `jdatamunch` lane when the task is about CSVs, spreadsheets, parquet tables, or dataset shape rather than source code or authored docs.
- Call `describe_dataset` before pulling rows so the schema and likely filter columns are grounded first.
- Prefer `search_data`, `get_rows`, and `aggregate` over loading whole datasets into context.
