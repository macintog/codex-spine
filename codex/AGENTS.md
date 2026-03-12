# codex-spine Codex Policy

- Always describe current work and give regular progress updates with enough reasoning to follow.
- Load `README.md` first for non-trivial work, then pull in `ARCHITECTURE.md`, `SECURITY.md`, or `CHANGELOG.md` as needed.
- Use `skills/github-contributor` for GitHub-hosted work. If the installed `upstream-contributor` skill applies, use it for upstream-candidate or maintainer-facing contribution work.
- Use `skills/project-spine` for project-focused continuity work. If the installed `project-continuity` skill is available, use it for deeper continuity-file or multi-repo continuity restructuring.
- Open `codex/TOOLING.md` only when the task needs on-demand routing for continuity, memory retrieval, indexed code navigation, or GitHub/upstream contribution lanes.
- Keep this file compact. Put detailed playbooks in `codex/TOOLING.md` or the named skills instead of turning `codex/AGENTS.md` into a second skill body.
- Prefer the managed commands (`make install`, `make verify`, `make update`, `./scripts/component-enable`) over ad hoc local edits or one-off environment mutations.
- Prefer durable fixes at the source that actually owns a behavior instead of duplicating the same change across multiple layers.
- Before non-trivial repo-touching work, give a short task-start brief naming repo or branch posture, adjacent surfaces, validation plan, and any destructive-move guard.
- Build a required-surface checklist before non-trivial edits. If a change affects a managed or advertised surface, update implementation, verification, and shipped guidance together.
- If a task changes startup docs, tooling guides, shipped skills or templates, config fragments, launchers, or managed links, treat that as a coordinated understanding surface and say in closeout whether the current thread should reload docs or whether a fresh Codex session would help.
- Treat Git as an explicit operating discipline: reason about repo role, base, current branch or worktree, unique local state, and intended integration path before mutating history or files.
- Do not pile new work onto unrelated dirt. If the checkout already carries unrelated changes, work around untouched files or move the task to a fresh topic branch or worktree.
- If the same symptom survives one or two attempted fixes, stop thrashing, restate the evidence and uncertainty, then switch strategies or ask before retrying again.
- After shell, install, bootstrap, config, launcher, or environment changes, state whether anything changes for current terminals, new shells, app restarts, or reboots.
