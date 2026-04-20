# Review Findings

These are the recorded findings that define this lane's queue.
Treat them as the seed authority for the queued passes until the target note is corrected or an explicit on-disk contradiction replaces them.
Treat this file as the lane checklist: each finding should have an explicit state, and the lane only closes when every line is green or explicitly split elsewhere.

## Target

- `<target-note-or-surface>`

## Finding Status Model

- `red`: known mismatch or missing required proof
- `ambiguous`: not yet classifiable truthfully
- `green`: aligned and verified strongly enough for this lane
- `split`: no longer belongs in this lane and now needs a separate note or follow-on packet

## Verification Outcome Model

- `not_run`
- `aligned`
- `aligned_with_residual_risk`
- `still_ambiguous`
- `misaligned`
- `split_required`
- `reopen_required`

## Findings Ledger

| ID | Title | Severity | Status | Outcome | Residual risk | Target lines or sections | Current-tree anchors | Owning pass | Reopen only if | Split target | Summary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `F001` | `<finding-title>` | `<P1|P2|P3>` | `red` | `not_run` | `unknown` | `<line-range-or-section>` | `<paths-or-artifacts>` | `passes/001-<finding-slug>.md` | `<contradiction-threshold>` | `<follow-on-note-or-lane>` | `State the mismatch plainly.` |
| `F002` | `<finding-title>` | `<P1|P2|P3>` | `ambiguous` | `not_run` | `unknown` | `<line-range-or-section>` | `<paths-or-artifacts>` | `passes/002-<finding-slug>.md` | `<contradiction-threshold>` | `<follow-on-note-or-lane>` | `State the mismatch plainly.` |

Add or remove rows to match the real queue.
If two findings must move together, say that explicitly and assign one owning pass.
Do not flip a finding to `green` until the owning pass artifact says why the evidence is strong enough.
Do not treat a `correction` pass alone as enough to turn a finding `green` unless a fresh verification result or explicitly reused stronger proof is named on disk.
If a green finding later contradicts stronger evidence, record that by changing the row truthfully and queueing a `reopen-decision` note instead of silently rewriting history.
