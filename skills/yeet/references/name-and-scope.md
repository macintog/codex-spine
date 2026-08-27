# Same name, different contract

`validated registered task → commit → publish or integrate → prove → retire`

`codex-spine` deliberately recycles `yeet`, familiar shorthand for "ship this,"
for an operation built around its managed Git lifecycle. The name is reused;
the public workflow is not.

The local skill grew from a longstanding failure. Finishing a task required the
operator to prompt Codex through an inconsistent sequence of commit, submit,
merge, push, proof, checkpoint, and cleanup steps. The repository already had
most of the guarded machinery, but no single operation owned the whole
transition. `yeet` gives that intent one explicit, resumable entrypoint.

At the versions reviewed during design, the
[OpenAI curated packet](https://github.com/openai/skills/blob/590b49e/skills/.curated/yeet/SKILL.md)
and
[OpenAI GitHub-plugin packet](https://github.com/openai/plugins/blob/1540745/plugins/github/skills/yeet/SKILL.md)
were checkout publishers:

`current checkout → stage → commit → checks → push → draft GitHub PR`

This skill starts with a validated registered task and finishes the repository
lifecycle, including proof and task retirement.

| Public OpenAI packets | `codex-spine` `yeet` |
| --- | --- |
| Act on the current checkout and branch. | Binds one registered managed task with a recorded isolation baseline. |
| May run checks or install missing dependencies while publishing. | Reuses the working task's existing validation and stops when that proof is missing or failed. |
| Push to GitHub and normally open a draft pull request. | Uses the repository's configured remote and task class for a ready review or a preselected integration. |
| Finish after reporting the branch, commit, and pull request. | Proves the exact remote result, reconciles project coordination state, resumes safely after interruption, re-homes the session, and retires only task-owned local state. |

`codex-spine` borrowed the short, useful name for the "take this all the way
through" intent. The behavior, implementation, and safety contract come from
`codex-spine`'s own Git lifecycle.
