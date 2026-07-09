# Pass Artifact: <Pass Title>

## Work Order

- Pass note: `passes/<NNN>-<pass-slug>.md`
- Pass type: `<value from SPINE.md Pass Families>`
- Evidence checked: `<exact anchors and artifacts>`

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

- `<value from SPINE.md State Vocabulary>`

## Residual Risk

- `<value from SPINE.md State Vocabulary>`
- State why that classification is truthful for this lane.

## Unresolved Ambiguities

- ambiguity one
- ambiguity two

## Scope Expansion / Reopen Decision

- State whether this pass stayed inside scope, queued a `scope-expansion` note, or queued a `reopen-decision` note.
- If a historical or green line was challenged, record the exact contradiction and the on-disk note that now owns it.

## Completion Delta

- what made this pass complete
- which rubric and queue fields changed
- what still needs fresh verification, if anything

## Next Recommended Pass

Name the next pass note on disk, or the explicit stop condition.

## Prompt Ownership

- If this artifact updates the canonical next-thread prompt surface, summarize that change here and keep the full prompt only in that owning surface.
- Keep it thin: point at the queued pass note and exact evidence anchors rather than re-encoding the full lane history or old scope guards.
- If another file owns the prompt, link it here and do not duplicate the text.
- If this artifact closes the lane, say `No prompt required; lane historical` or `No prompt required; lane closed`.
