# Multi-Step Templates

These templates scaffold disk-backed serial work packets for problems that are too drift-prone for ordinary one-thread debugging.
They are designed for lanes where the exact number of steps may be unknown at the start, but a task-specific checklist can reveal and retire the work one line at a time.

Choose one profile before instantiating anything:

- `serial-program/`: use for a long-running, cross-surface program that needs a durable spine, a shared question bank, a surface map, machine-readable state, and explicit verification gates between correction passes.
- `finite-findings/`: use for a bounded follow-on lane seeded by a finite findings list after the broader program is already closed or intentionally out of scope.

If the lane depends on durable theory, expectations, or target definitions, keep those in adjacent authority docs rather than stuffing them into the active queue packet.

Both profiles share the same core vocabulary:

- lane states: `active`, `blocked`, `historical`, `closed`
- pass types: `audit`, `correction`, `verification`, `scope-expansion`, `reopen-decision`, `authority-cleanup`, `closeout-gate`
- finding or rubric states: `red`, `ambiguous`, `green`, `split`
- verification outcomes: `not_run`, `aligned`, `aligned_with_residual_risk`, `still_ambiguous`, `misaligned`, `split_required`, `reopen_required`
- residual risk levels: `none`, `minor`, `material`, `unknown`

## Instantiation Rules

1. Copy exactly one profile into the target repo's chosen packet directory.
2. Replace placeholders like `<program-name>`, `<authority-doc>`, and `<first-pass-slug>` before handing the packet to another thread.
3. Queue the first pass on disk before ending setup.
4. Pick one canonical prompt surface if the lane needs a paste-ready next-thread prompt. Keep that prompt in exactly one place, and let other files point to it.
5. Treat that prompt as derived output from the queue and handoff state on disk, not as an independent authority surface.
6. Keep detailed reasoning in pass notes, not in the packet checkpoint.
7. Load only the packet docs and the current queued pass by default; do not open the whole pass history on routine startup.

## Shared Method Invariants

- One fresh thread owns one narrow pass.
- Authority order must be explicit.
- Each lane needs a task-specific rubric or checklist that can move exact lines from red to green with evidence.
- Scope and out-of-scope must be written down for every pass.
- Queue truth should be explicit on disk: active note, active pass type, next note, lane state, and any scope-expansion or reopen note.
- After a correction pass, use a fresh verification pass before treating the correction as settled.
- Let the rubric discover the required queue; do not fake certainty about the step count on day one.
- If truthful progress would require wider scope, record a new scoped note instead of widening the active pass.
- If a supposedly closed line needs attention again, record the contradiction and route it through an explicit `reopen-decision` or `scope-expansion` pass instead of silently editing history.
- Every pass must end with the next on-disk pass note or an explicit stop condition.
- If work remains, the packet may maintain a minimal paste-ready launch prompt for the next fresh thread.
- That prompt should point at the queued pass note instead of re-encoding lane history or old scope fences.
- If the prompt disagrees with queue-owned surfaces, fix the queue first and then refresh the prompt.
- If substantive lane work is complete and only repo cleanup remains, say so explicitly in the handoff instead of sounding like product work is still open.
- Closed lanes should stay readable as historical restart context. Do not turn them back into active queues without an explicit on-disk reason.
