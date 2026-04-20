# Program Spine

## Purpose

- State the user-visible or operator-visible problem this packet exists to resolve.
- Keep the product or workflow goal clear enough that deep local debugging does not redefine it.

## Operator Job

- State how a future fresh thread should execute this program.
- Emphasize that the job is to advance one narrow pass from disk, not to recreate the whole history from chat memory.

## Success Criteria

- List the concrete outcomes that mean the program is closed cleanly.
- Include both truth-alignment goals and replayability goals.

## Non-Goals

- List the tempting side quests this packet must not absorb.
- Say plainly what kinds of fixes, rewrites, or general cleanups stay out of scope.

## Durable Strategy

- Name the frozen authority order.
- Name the required pass order at a family level, for example: contract audit, contract correction, verification, implementation seam audits, CI classification, closeout.
- Say whether the work is expected to move surface by surface, seam by seam, or findings cluster by findings cluster.
- State how the lane-specific rubric discovers the queue when the exact step count is not known yet.
- State which surface owns queue truth and whether the next-thread prompt lives inline in `CHECKPOINT.md` or in another dedicated prompt surface.

## Stable Rules

- During audit passes, do not modify the audited product surface.
- During correction passes, edit only one owning surface family at a time.
- Require a fresh verification pass after any correction pass.
- Only mark a rubric line green when the proof contract and any required fresh verification have both been satisfied.
- Keep the packet checkpoint small; detailed reasoning belongs in pass artifacts.
- Keep queue state canonical on disk: lane mode, active queue note, active pass type, next queue note, prompt surface, and any scope-expansion or reopen note.
- Treat `historical` as a real lane mode, not as shorthand for "nobody updated the checkpoint."
- If a new contradiction reopens a supposedly closed line, record it explicitly on disk before reordering the queue.
- If the lane closes with residual risk, say whether that risk is accepted here, split into a follow-on lane, or grounds immediate reopening.

## Authority Order

List the order of precedence for this program.

1. Current user direction for this packet
2. `<canonical-authority-surface>`
3. `<direct-evidence-surface>`
4. This packet's process rules and lane rubric
5. Current implementation details
6. CI or harness expectations

Replace those placeholders with the actual order that should govern the lane.

## Pass Families

- `audit`: classify one surface or seam without fixing it
- `correction`: repair one owning surface family only
- `verification`: re-check the previous correction from a fresh thread
- `scope-expansion`: stop the active pass, record why truthful progress now needs wider scope, and queue the follow-on decision cleanly
- `reopen-decision`: determine whether a historical or green line must be reopened, split out, or left closed with stronger evidence
- `authority-cleanup`: reconcile stale packet or startup surfaces without reopening closed product lines
- `closeout-gate`: confirm the lane is truthful, replayable, and either closed or explicitly split into a new follow-on lane

## Lane Rubric

- Define the task-specific checklist that governs this program.
- For each line, say what evidence flips it from red or ambiguous to green.
- Say whether new rubric lines may be discovered during audit and verification work, and how they should be recorded without destabilizing already-closed lines.

## Surface Families

- List the surface families this program will touch.
- For each family, say what it owns and what it must not silently redefine.

## Proof Contract

- Name the proof artifacts that matter for this lane.
- State what must be true before a pass can mark a line as settled.
- Record whether proofs are human-read, machine-read, or both.
- If the lane has build, package, release, migration, or rollout proof, name the exact artifact or runtime state that proof must correspond to.
- State how late the proof must run to count as fresh for this lane.
- Define the allowed verification outcomes and what residual-risk levels still count as acceptable for this lane.

## Closeout Gate

- State the exact conditions for treating the packet as closed.
- Require both product-surface truth and packet-surface truth.
- Require the final proof to identify the exact artifact, runtime state, or output now being claimed complete.
- Require that build, package, release, migration, or rollout proof be rerun after the final relevant correction, not merely inherited from earlier passes.
- State what should happen to residual scope: close it here, spin it out into a new lane, or hold it as explicit known residual context.
- If substantive lane work is complete and only repo cleanup remains, say that plainly and treat the remaining work as lifecycle cleanup rather than open product scope.
- If that cleanup is git or other version-control work, say that it is the only remaining step and offer to do it next in the same thread.

## Child-Lane Split Heuristics

- Split a child lane when one residual cluster now has its own stable authority order or proof loop.
- Split a child lane when repeated reopen or correction cycles in one area would bury the parent lane's true status.
- Split a child lane when late-stage build, release, migration, or rollout work needs its own queue and freshness discipline.
- Record the child lane path or queued note that now owns that residual scope.

## Historical / Reopen Rules

- State when this packet should shift from `active` to `historical` or `closed`.
- Define the exact contradictions or new evidence that justify reopening a green line or reviving the lane.
- Say what evidence is strong enough to keep the lane closed even if new discussion appears in chat.
