# Question Bank And Lane Rubric

Every audit and verification pass in this packet should answer the relevant questions below with evidence.
If a pass cannot answer one of them cleanly, record that as an ambiguity instead of hand-waving past it.

This file is also the task-specific checklist for the lane.
It is allowed to start incomplete if the lane is still discovering the real seams, but every new seam should be added here before it becomes "just one more thing" in chat.

## Rubric Status Model

- `red`: known misaligned or still missing required proof
- `ambiguous`: not yet classifiable truthfully
- `green`: aligned and verified strongly enough for this lane
- `split`: no longer belongs in this lane and now needs a separate queued note or follow-on packet

Only move a line to `green` when the required evidence and any required fresh verification both exist on disk.
If a green line later contradicts new evidence, record the contradiction explicitly, downgrade the line truthfully, and queue a `reopen-decision` or `scope-expansion` pass instead of editing history silently.

## Verification Outcome Model

- `not_run`: no fresh verification has happened yet
- `aligned`: the owning surface matches the stated authority with no meaningful residual risk
- `aligned_with_residual_risk`: the owning surface is aligned, but the pass must name the remaining risk explicitly
- `still_ambiguous`: evidence is still too weak or contradictory to settle the line
- `misaligned`: the owning surface still fails the authority check
- `split_required`: the line cannot close inside this lane and must move into follow-on scope
- `reopen_required`: a historical or green line needs an explicit reopen decision

## Residual Risk Model

- `none`: no meaningful residual concern remains for this lane
- `minor`: acceptable to close here if the packet says why
- `material`: too large to hide inside a green line; split or reopen it
- `unknown`: the pass could not classify risk truthfully

## Checklist

| Line | Authority owner | Evidence needed to turn green | Current status | Residual risk | Reopen only if | Last owning pass |
| --- | --- | --- | --- | --- | --- | --- |
| `<seam-or-question-one>` | `<authority-surface>` | `<required-proof>` | `red` | `unknown` | `<contradiction-threshold>` | `<pass-slug>` |
| `<seam-or-question-two>` | `<authority-surface>` | `<required-proof>` | `ambiguous` | `unknown` | `<contradiction-threshold>` | `<pass-slug>` |

Add lines as the real queue becomes clearer.
Do not delete an awkward line just because it makes closeout harder.

## Core Pass Questions

1. What exact surface or seam is this pass classifying or repairing?
2. What does a healthy state for that surface look like before implementation detail is considered?
3. Which evidence anchors are descriptive, and which surfaces are normative?
4. What must remain unchanged while this pass runs?
5. What exact contradiction, if any, would justify reopening a previously closed line?

## Authority Questions

1. Which source is authoritative for this pass?
2. Which source is informative but non-authoritative?
3. Is any implementation detail silently redefining the intended contract?
4. Is any test or harness expectation freezing mechanism rather than durable behavior?
5. Does the packet itself still tell the truth about the current lane?

## Correction Questions

1. What is the smallest owning surface that can be corrected truthfully?
2. What adjacent surfaces are affected but must not be edited in this pass?
3. What proof will be required from a fresh verification thread?
4. What exact residual should be split out instead of widening this pass?

## Scope Expansion / Reopen Questions

1. Did this pass discover a contradiction that the existing lane cannot absorb cleanly?
2. Does truthful progress now require a wider authority line, another owning surface family, or a reopened green line?
3. Should the result be a new follow-on note, a reopened line, or an explicit stop condition?
4. What evidence is strong enough that the current lane should remain closed anyway?

## Verification Questions

1. Did the previous correction actually align the owning surface with the stated authority?
2. Did that correction accidentally change a preserved invariant?
3. Is the remaining risk minor, material, or still ambiguous?
4. Can the lane advance, or does it need a narrower follow-up note first?

## Required Outputs

Every completed pass artifact should end with:

- findings
- exact corrections required or an explicit no-change decision
- must not change
- unresolved ambiguities
- verification outcome and residual risk, if applicable
- completion criteria
- next recommended pass

Every completed pass artifact should also say which checklist lines changed state and why.
It should also say whether the next-thread prompt text was updated in that artifact's owning surface or intentionally left owned elsewhere.

Verification artifacts should also classify the audited surface as one of:

- `aligned`
- `aligned_with_residual_risk`
- `still_ambiguous`
- `misaligned`
- `split_required`
- `reopen_required`
