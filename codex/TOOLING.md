# codex-spine Tooling Guide

Load this only when the task actually enters one of these installed lanes. Routine startup should stay with `README.md` and `codex/AGENTS.md`.

## Current Task Subject Binding

- The latest explicit user request selects the task. Before planning, goal creation, resumption, delegation, or mutation, bind its objective and scope to the canonical repository or system, exact worktree/ref/HEAD or runtime/artifact identity, and current authority/evidence.
- Goals, queues, checkpoints, prompts, packets, index results, workers, and automations are evidence only. A consequential mismatch requires a read-only stop instead of blended or resumed work.
- Completion may report residual findings as non-directive candidate scope, but it cannot create, revive, queue, authorize, or begin a successor. Every successor requires a fresh explicit user request and subject binding.

## Intervention Before Workaround

- At the first consequential missing user choice, authority conflict, material ambiguity, or strategy-changing failure, stop consequential tools, mutation, retries, delegation, and alternate-design work. Ask one targeted question that names the decision.
- Do not choose a feasible workaround merely to keep an active task or goal moving. A substitute artifact, weaker proof, changed implementation strategy, revived historical task, or locally authored approval cannot stand in for the user's answer.
- Cheap read-only inspection may continue only when it can objectively resolve the uncertainty without selecting an outcome. An exact retry through the correct authority lane remains evidence gathering.
- An automatic goal continuation while the question is unanswered is a no-op. Preserve the same pause and mark the task formally blocked at the earliest turn the runtime permits.

## Continuity

- For non-trivial multi-session repos, keep `AGENTS.md` and `PROJECT_CONTINUITY.md` in-repo and resolve handoff state through `codex-project-checkpoint`. Adopted repos keep root `CHECKPOINT.md` tracked only as a discovery stub; `not_adopted` retains the legacy tracked handoff.
- After final remote-tip or keeper proof and before reporting completion for `yeet`, the coordinator re-reads the resolver-selected adopted handoff, reconciles the final disposition, and writes it with `codex-project-checkpoint update --expected-generation ...`. Re-read and reconcile a stale generation; never overwrite it, directly edit the external board, or let a worker write it.
- Keep only one root handoff. Nested queues, checkpoints, next prompts, rubrics, and equivalent continuation controls are invalid unless they belong to a separately adopted complete nested project or are plainly historical and non-authoritative.
- Use `memory.bootstrap_context` only for durable re-anchor after a repo or `cwd` change (`reason=repo_cwd_change`), prior-thread recovery (`reason=prior_thread_recovery`), or demonstrated compaction drift (`reason=demonstrated_drift`). The adapter bounds and deduplicates same-project calls by reason and recent-session limit; use direct retrieval plus `get` or `multi_get` for historical wording and evidence.
- Treat bootstrap as restoration of durable context, not as permission to resume an old task automatically.
- Keep deeper docs and skill bodies on-demand so routine startup stays cheap.

## Memory

- Use the `memory` MCP tools for durable recall when prior wording, earlier decisions, or older evidence matters.
- For one of the three durable re-anchor cases, call `memory.bootstrap_context` with the matching reason. For an explicit topicless last-conversation question, call `memory.recent_session`; do not infer recency from startup or checkout context. For a named historical subject, call `memory.query` only when the current thread and current checkout do not already answer it. For current Git landing, containment, or ref-existence questions, inspect current refs first; memory may resolve an approximate historical label but current Git is authority for current state. Supply a concise `intent` and one to three typed searches: `lex` for a few discriminative exact terms, one exact phrase, identifiers, filenames, or exclusions; `vec` for same-idea/different-wording recall; and `hyde` only for a nuanced concept that benefits from a hypothetical answer. Do not overconstrain one `lex` search with terms that may not co-occur. Normally make one query and one bounded `get` or `multi_get`, starting transcript retrieval near the hit's returned line instead of line 1. Stop when that source answers the question; do not search for redundant corroboration. Broaden once only when it does not answer, then retrieve a bounded source from the broadened pass before answering. For a final-decision lookup, do not treat a window ending in a proposal, question, or confirmation request as final; follow its `nextFromLine` continuation.
- After the one allowed broadened query, batch multiple selected sources in one `multi_get` rather than serial `get` calls. Follow one same-source continuation only when `nextFromLine` is needed to finish the decision.
- Follow retrieval hits with `get` or `multi_get` on returned identifiers before relying on the result.
- Built-in Codex memories are disabled by the base config. Do not read or route through retained app-managed files under `~/.codex/memories/` unless the current user explicitly asks about those files; keep required rules in `AGENTS.md` or checked-in docs and use the QMD-backed `memory` MCP lane for historical retrieval.
- Codex settings, `/memories`, or `codex/config/90-local.toml` may explicitly opt a workstation back in. That opt-in is user/client-owned and must not be inferred from the retained generated corpus or an older project pointer.
- The built-in settings that matter most operationally are `features.memories`, `memories.generate_memories`, `memories.use_memories`, and `memories.disable_on_external_context`; the shipped default keeps the first three false.
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

- Before app worktree creation, the parent preflights Git from the canonical checkout and performs separately authorized Git bootstrap. An app-created checkout is adopted by exact path as `mode=worktree`. Every task worktree, including one for a nested repository, uses durable `~/.codex/worktrees` storage. Never create one under `/tmp`, `/private/tmp`, `/var/tmp`, or another OS temporary directory, and never bypass the control plane with raw `git worktree add`. Preflight and status fail closed on any such registered worktree, even when only stale metadata remains; OS temp directories remain limited to disposable artifacts. Successful adoption installs the repo-local managed commit guard only when no custom `hooksPath` exists; existing project hooks are preserved and exact lifecycle adoption remains authoritative. The exact current-turn `yeet` instruction authorizes one attempt at the active registered task's configured terminal Git transaction; it does not authorize product tests, broad verification, bootstrap, deployment, or release gates.
- Use the explicit-only `yeet` skill and `codex-git-safe yeet --apply`; reuse validation already produced by the working thread, and stop before mutation if validation, task identity, remote, checkpoint, or residue proof is missing. In integrate mode the transaction commits, integrates on the authoritative ref, pushes and verifies keepers, then re-homes and retires only current-task state. In pull-request mode an ordinary task publishes or confirms its PR, verifies the exact remote topic tip, records it for later integration, and retires only its local task state; only configured integration-task classes may select recorded PR refs and advance the authoritative line. GitHub review creation may be performed through the installed GitHub connector and recorded with `codex-git-safe review-import`; the bundled helper scripts provide the direct Gitea path. If the primary checkout belongs to another in-flight task, do not switch or advance that sibling; use it only as the outside location for current-task retirement. Preserve ordinary non-overlapping canonical dirt only after replay to latest authority and content-level pre/post fingerprint proof; overlaps, special Git/index states, nested/submodule/unsafe files, or proof mismatch fail closed without a model-visible bypass. Task idleness is not success.
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
