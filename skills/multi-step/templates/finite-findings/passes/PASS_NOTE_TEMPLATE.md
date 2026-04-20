# Pass <NNN>: <Pass Title>

## Queue Metadata

- Pass slug / path: `passes/<NNN>-<pass-slug>.md`
- Pass type: `audit`, `correction`, `verification`, `scope-expansion`, `reopen-decision`, `authority-cleanup`, or `closeout-gate`
- Finding IDs owned by this pass: `F001` or `F001,F002`

## Purpose

State the narrow finding-owning objective in one paragraph.

## Scope

- target note or owning narrow surface only
- in scope: exact files, sections, and artifacts
- out of scope: broader program reopening, unrelated cleanup, or new mechanism design

## Inputs

- `REVIEW_FINDINGS.md`
- exact earlier passes or parent-lane authority docs consulted
- exact current-tree anchors consulted

## Questions Answered

- Which finding does this pass retire?
- What exact finding state change should happen on disk, for example `red -> green` or `ambiguous -> split`?
- Can the target note be repaired truthfully without reopening the broader lane?
- What exact residual, if any, still needs its own queued pass?
- If this is a `correction` pass, what fresh `verification` pass or stronger existing proof will justify closing the finding afterward?

## Queue State Updates To Record

- Which `REVIEW_FINDINGS.md` rows should change?
- What should `CHECKPOINT.md` say about lane state, active note, and prompt ownership after this pass?
- If this pass could create a scope-expansion or reopen note, name the target note path now.

## Exact Corrections Required

- correction one
- correction two

## Must Not Change

- preserved authority line one
- preserved authority line two

## Completion Criteria

- the targeted finding is either resolved truthfully on disk or explicitly split into a new scoped follow-up
- `REVIEW_FINDINGS.md` records the resulting finding state explicitly
- `CHECKPOINT.md` points at the next pass or an explicit stop condition
- if this is a `correction` pass and the finding is meant to close, a fresh `verification` pass or explicitly reused stronger proof is recorded on disk

## If Scope Expands Or Findings Reopen

- State the exact contradiction or trigger that would force this pass to stop and queue a `scope-expansion` or `reopen-decision` note instead of pretending the current lane still fits.
- State whether the lane may remain active, must shift to blocked, or should become historical after that note is written.

## Next Recommended Pass

Name the next pass note on disk, or the explicit stop condition if this pass could close the lane.
