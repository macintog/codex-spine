# Pass Artifact: <Pass Title>

## Pass Type

- `audit`, `correction`, `verification`, `scope-expansion`, `reopen-decision`, `authority-cleanup`, or `closeout-gate`

## Purpose

State the narrow pass objective in one paragraph.

## Scope

- name the exact surface family
- name the exact files, sections, or artifacts in scope
- name explicit out-of-scope areas

## Inputs

- packet docs consulted
- named authority docs consulted
- exact evidence anchors consulted

## Questions Answered

List the exact questions from `QUESTION_BANK.md` that this pass answered.

## Queue State Updates

- `STATUS.toml` fields changed:
- `CHECKPOINT.md` changes:
- Canonical prompt surface after this pass:

## Rubric State Changes

- `<line-name>`: `<old-state> -> <new-state>` because `<evidence>`

## Findings

- finding one
- finding two

## Exact Corrections Required Or No-Change Decision

- correction one
- correction two

## Verification Outcome

- `not_run`, `aligned`, `aligned_with_residual_risk`, `still_ambiguous`, `misaligned`, `split_required`, or `reopen_required`

## Residual Risk

- `none`, `minor`, `material`, or `unknown`
- State why that classification is truthful for this lane.

## Must Not Change

- invariant one
- invariant two

## Unresolved Ambiguities

- ambiguity one
- ambiguity two

## Scope Expansion / Reopen Decision

- State whether this pass stayed inside scope, queued a `scope-expansion` note, or queued a `reopen-decision` note.
- If a historical or green line was challenged, record the exact contradiction and the on-disk note that now owns it.

## Completion Criteria

- what made this pass complete
- which rubric lines changed state on disk
- what still needs fresh verification, if anything

## Next Recommended Pass

Name the next pass note on disk, or the explicit stop condition.

## Prompt Ownership

- If this artifact updates the canonical next-thread prompt surface, summarize that change here and keep the full prompt only in that owning surface.
- Keep it thin: point at the queued pass note and exact evidence anchors rather than re-encoding the full lane history or old scope guards.
- If another file owns the prompt, link it here and do not duplicate the text.
- If this artifact closes the lane, say `No prompt required; lane historical` or `No prompt required; lane closed`.
