# Same name, different contract

`validated task → ready review → remote-tip and task evidence → local retirement`

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
| May run checks or install missing dependencies while publishing. | Reuses working-task validation; the root performs necessary integration checks when the exact integration tree changes. |
| Push to GitHub and normally open a draft pull request. | Uses the selected completion intent: tested ready PR delivery and local retirement by default; integration only when selected or deliberately configured. |
| Finish after reporting the branch, commit, and pull request. | Proves the exact remote result, persists durable task/queue evidence, resumes safely after interruption, re-homes the session, and retires the transaction's disposable local state and, for selected integration, eligible closed remote review refs. |

`codex-spine` borrowed the short, useful name for the "take this all the way
through" intent. The behavior, implementation, and safety contract come from
`codex-spine`'s own Git lifecycle.
