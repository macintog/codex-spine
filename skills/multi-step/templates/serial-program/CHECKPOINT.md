# Checkpoint

This is the volatile handoff for `<program-name>`.
Use it after `SPINE.md`, not instead of it.

## Lane State

- State: `active`, `blocked`, `historical`, or `closed`
- Active queue note: `passes/<pass-slug>.md` or `none`
- Active pass type: `audit`, `correction`, `verification`, `scope-expansion`, `reopen-decision`, `authority-cleanup`, or `closeout-gate`
- Canonical prompt surface: `CHECKPOINT.md`, another packet file, or `none`

## Current Focus

- Name the active pass, or say plainly that no pass is currently queued.
- State the one sentence version of what the active pass is trying to prove or repair.

## Why Current Focus Matters

- Connect the current pass back to the broader program goal.
- If the packet is closed, explain why future threads should treat it as historical restart context rather than an active queue.

## Open Blockers / Decisions

- Record only active blockers or decisions that still affect the current queued pass.
- If the packet is closed, say what kind of contradiction would justify reopening it.

## Validation Evidence

- Link the proof artifacts, captures, tests, or source anchors that matter right now.
- Favor exact evidence over recap.

## Residual Risk / Reopen Signals

- If the latest verification left residual risk, classify it as `minor`, `material`, or `unknown`.
- If a formerly green or historical line might need attention again, name the exact contradiction and the note that should own the reopen decision.

## Next Safe Step

- Name the next queued pass on disk, or say `Stop here` if no pass remains queued.
- If a new lane should be created for residual scope, name the exact child lane or note path and why instead of silently reopening this packet.
- If substantive lane work is complete and only git or repo cleanup remains, say that explicitly here and name the cleanup step as the next same-thread action.

## Prompt For Next Fresh Thread

- Keep the actual prompt text here only if `CHECKPOINT.md` is the canonical prompt surface.
- Otherwise, link the owning prompt surface here and do not duplicate the text.
- The prompt should tell the next thread what to load, which queued pass note to run first, and which exact evidence anchors it needs before acting.
- Let the queued pass note own detailed scope boundaries and must-not-change rules.
- Do not paste forward historical reopen guards, closed-lane reminders, or old scope-expansion conditions unless the queued pass note still marks them active.
- If no work remains, say `No prompt required; lane historical` or `No prompt required; lane closed`.

## Archive References

- Link older notes that still matter but should not be loaded by default.
