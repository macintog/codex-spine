# codex-spine Tooling Guide

Load this only when the task actually enters one of these lanes. Routine startup should stay with `README.md` and `codex/AGENTS.md`.

## Continuity and Memory

- Use `skills/project-spine` for project-focused continuity across threads, branches, and longer runs of work.
- If the installed `project-continuity` skill is available, use it for deeper continuity-file or multi-repo continuity restructuring.
- Use the direct `memory.bootstrap_context` tool call on the first assistant turn in a new thread, at the start of any materially new user request, on repo or `cwd` changes, on resume or prior-thread references, and on compaction-drift symptoms. Pass `max_recent_sessions=3`.
- Prefer calling `memory.bootstrap_context` directly instead of trying to open a startup file or generic resource view first.
- Treat automatic bootstrap as durable context restoration only. It must not auto-recap prior task work or choose the next task.
- When exact prior wording or broader historical evidence matters, use direct memory retrieval: `search`, then `deep_search`, then `vector_search`, then `get` or `multi_get`. If a client also exposes `qmd://codex-chat/...` reads, treat them as optional read helpers rather than the default startup lane.
- If `memory.bootstrap_context` fails, fall back to `qmd-memory-latest.sh`, summarize the result, and continue. `qmd-codex` is the managed adapter behind this memory path.

## Self-Hosting Changes

- Load this section when the task edits startup docs, tooling guides, shipped skills or templates, config fragments, launchers, or managed links that Codex relies on to understand or operate this repo.
- Treat those as one coordinated surface: update the shipped docs or skills, the relevant verify gates, and the operator guidance together.
- If the semantics materially changed, re-read the changed docs in-thread before continuing. In closeout, say whether the current thread should reload docs, whether a fresh Codex session is recommended, and whether current terminals, new shells, app restarts, or reboots are affected.
- If live managed paths, shell hooks, config, or launchers changed, rerun `make install`. Doc-only self-hosting edits do not require it.

## Code Navigation

- When indexed code navigation is useful, use the optional `jcodemunch` surface rather than broad file scans.
- Default flow: `search_symbols`, then `get_symbol` or related symbol lookups for precise definitions and call sites.

## GitHub and Upstream

- Use `skills/github-contributor` for GitHub-hosted work such as repo shaping, release discipline, and component-boundary decisions.
- If the installed `upstream-contributor` skill applies, use it for upstream-candidate patches, maintainer-facing contribution prep, and upstream delta review.
