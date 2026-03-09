# codex-spine Codex Policy

- Load `README.md` first for non-trivial work, then pull in `ARCHITECTURE.md`, `SECURITY.md`, or `CHANGELOG.md` as needed for the task.
- Use `skills/github-contributor` for new components, public release discipline, documentation standards, and upstreamability decisions.
- Keep public docs honest about optional third-party licensing and lack of formal affiliation.
- Prefer the managed commands (`make install`, `make verify`, `make update`, `./scripts/component-enable`) over ad hoc local edits.
- On the first assistant turn in every new thread, call `memory.bootstrap_context` with `cwd=<current working directory>`, `refresh_if_stale=true`, and `max_recent_sessions=3`; use that summary as the default project context before solving tasks.
- If the user says "check memory", "use memory", or asks what was previously decided, use the installed `memory` MCP first rather than scanning files by hand.
- If `memory.bootstrap_context` is too shallow or the user wants exact prior wording, switch to direct `qmd_codex` retrieval rather than scanning `~/.codex/sessions` or `.cache/qmd` manually.
