# Checkpoint

This is the volatile handoff for `<lane-name>`.

## Lane State

- State: `active`, `blocked`, `historical`, or `closed`
- Active queue note: `passes/<pass-slug>.md` or `none`
- Active pass type: `audit`, `correction`, `verification`, `scope-expansion`, `reopen-decision`, `authority-cleanup`, or `closeout-gate`
- Canonical prompt surface: `CHECKPOINT.md`, another packet file, or `none`

## Current Focus

- Name the active finding-owning pass, or say plainly that no pass is currently queued.
- State whether this packet is still an active queue or has become historical restart context.

## Why Current Focus Matters

- Connect the current pass back to the seed findings list.
- If the lane is closed, explain why future threads should stop unless a new contradiction is recorded on disk.

## Open Blockers / Decisions

- Record only blockers that affect the current queued finding or closeout state.
- If broader scope is needed, say which new lane or note should be created instead of reopening this packet silently.

## Validation Evidence

- Link the target note, the current finding anchors, and the relevant proof artifacts.

## Residual Risk / Reopen Signals

- If the latest verification left residual risk, classify it as `minor`, `material`, or `unknown`.
- If a green finding might need to reopen, name the exact contradiction and the note that should own that decision.

## Next Safe Step

- Name the next queued pass on disk, or say `Stop here` if all findings are resolved cleanly.
- If all findings are resolved and only git or repo cleanup remains, say that explicitly here and offer that cleanup as the next same-thread action.

## Prompt For Next Fresh Thread

- Keep the actual prompt text here only if `CHECKPOINT.md` is the canonical prompt surface.
- Otherwise, link the owning prompt surface here and do not duplicate the text.
- The prompt should tell the next thread what to load, which queued finding-owning pass to execute first, and which exact evidence anchors it needs before acting.
- Let the queued pass note own detailed scope boundaries and must-not-change rules.
- Do not paste forward historical reopen guards, closed-lane reminders, or old scope-expansion conditions unless the queued pass note still marks them active.
- If no work remains, say `No prompt required; lane historical` or `No prompt required; lane closed`.

## Archive References

- Link the seed note or earlier parent-lane materials that still matter.
