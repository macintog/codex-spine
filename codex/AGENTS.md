# codex-spine Codex Policy

- Load `README.md` first for non-trivial work, then pull in `ARCHITECTURE.md`, `SECURITY.md`, or `CHANGELOG.md` as needed for the task.
- Use `skills/github-contributor` for public maintenance work such as release discipline, documentation quality, component boundaries, and upstreamability decisions.
- Use `skills/project-spine` when a long-running task needs continuity help across sessions while keeping the public repo's purpose and boundaries intact.
- Prefer the managed commands (`make install`, `make verify`, `make update`, `./scripts/component-enable`) over ad hoc local edits or one-off environment mutations.
- Keep public docs honest about optional third-party components, their licenses, and the lack of formal affiliation with upstream projects.
- Treat this repository as a shipped public product tree. Do not add private continuity notes, export provenance, workstation-specific paths, internal URLs, or maintainer-only runbooks here.
- `codex-spine` is a downstream export surface, not the canonical source for shared implementation. If a defect visible here originates in the paired private source repo for this export, fix it there first and propagate it through the export path. Patch this repo directly only when the issue is truly downstream-only.
- Keep user-facing guidance runnable from a `codex-spine` checkout or an identical clone, and prefer instructions that validate the exact tree the user is looking at.
- When using the shipped memory surface, call `memory.bootstrap_context` on the first assistant turn in a new thread with `max_recent_sessions=3`, then call it again on a materially new user request, on repo or `cwd` changes, on resume, and on compaction-drift symptoms.
- Treat automatic bootstrap as durable context restoration only. It should restore project frame and durable constraints, but it must not auto-recap prior task work or choose the next task from memory alone.
- If the user needs exact prior wording or broader historical evidence, use direct memory retrieval instead of another bootstrap pass. Default flow: `search`, then `deep_search`, then `vector_search`, then `get` or `multi_get` against the returned `qmd://codex-chat/projects/` context.
- If `memory.bootstrap_context` fails, fall back to `qmd-memory-latest.sh`, summarize the result, and continue. `qmd-codex` is the managed adapter behind this memory path, not a second public MCP to document separately.
- When indexed code navigation is useful, use the optional `jcodemunch` surface rather than broad file scans. Default flow: `search_symbols`, then `get_symbol` or related symbol lookups for precise definitions and call sites.
