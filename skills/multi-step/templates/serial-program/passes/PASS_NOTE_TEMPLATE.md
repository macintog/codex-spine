# Pass <NNN>: <Pass Title>

## Queue Metadata

- Pass slug / path: `passes/<NNN>-<pass-slug>.md`
- Pass type: `audit`, `correction`, `verification`, `scope-expansion`, `reopen-decision`, `authority-cleanup`, or `closeout-gate`
- Queue owner: exact rubric line or line cluster this note owns
- Expected lane state on entry: `active`, `blocked`, or `historical`

## Purpose

State the narrow pass objective in one paragraph.

## Scope

- Name the exact surface family in scope.
- Name the exact files, sections, or artifacts in scope.
- Name the explicit out-of-scope areas that must not be widened into this pass.

## Inputs

- packet docs consulted
- named authority docs consulted
- exact evidence anchors consulted

## Questions To Answer

List the exact questions from `QUESTION_BANK.md` that this pass must answer.

## Rubric Lines To Advance

- Name the exact checklist lines this pass owns.
- State the intended transition, for example `red -> green` or `ambiguous -> split`.

## Queue State Updates To Record

- Name the `STATUS.toml` queue fields this pass should change.
- Say whether `CHECKPOINT.md` stays the canonical prompt surface or should point at another prompt-owning file.
- If this pass could create a scope-expansion or reopen note, name the target note path now.

## Allowed Writes

- Name the owning surface that may be edited in this pass.
- If this is an audit or verification pass, say plainly that only packet handoff files may change.

## Must Not Change

- preserved invariant one
- preserved invariant two

## Completion Criteria

- what must be true for this pass to count as complete
- which rubric lines must change state on disk before the pass can close
- what proof must exist on disk before the pass can close

## If Scope Expands Or Closed Lines Reopen

- State the exact contradiction or trigger that would force this pass to stop and queue a `scope-expansion` or `reopen-decision` note instead of pretending the original scope still holds.
- State whether the lane may remain active, must shift to blocked, or should become historical after that note is written.

## Next Recommended Pass

Name the next pass note to queue, or the explicit stop condition if this pass could close the lane.
