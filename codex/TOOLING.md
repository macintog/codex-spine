# codex-spine Tooling Guide

Load this only when the task actually enters one of these lanes. Routine startup should stay with `README.md` and `codex/AGENTS.md`.

## Continuity and Memory

- Use `skills/project-spine` for project-focused continuity across threads, branches, and longer runs of work.
- If the installed `project-continuity` skill is available, use it for deeper continuity-file or multi-repo continuity restructuring.
- Use `memory.bootstrap_context` on the first assistant turn in a new thread, at the start of any materially new user request, on repo or `cwd` changes, on resume or prior-thread references, and on compaction-drift symptoms. Pass `max_recent_sessions=3`.
- Treat automatic bootstrap as durable context restoration only. It must not auto-recap prior task work or choose the next task.
- When exact prior wording or broader historical evidence matters, use direct memory retrieval: `search`, then `deep_search`, then `vector_search`, then `get` or `multi_get` against the returned `qmd://codex-chat/projects/` context.
- If `memory.bootstrap_context` fails, fall back to `qmd-memory-latest.sh`, summarize the result, and continue. `qmd-codex` is the managed adapter behind this memory path.

## Code Navigation

- When indexed code navigation is useful, use the optional `jcodemunch` surface rather than broad file scans.
- Default flow: `search_symbols`, then `get_symbol` or related symbol lookups for precise definitions and call sites.

## GitHub and Upstream

- Use `skills/github-contributor` for GitHub-hosted work such as repo shaping, release discipline, and component-boundary decisions.
- If the installed `upstream-contributor` skill applies, use it for upstream-candidate patches, maintainer-facing contribution prep, and upstream delta review.
