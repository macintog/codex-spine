# <Lane Name> Packet

This packet is the dedicated working area for `<lane-name>`.
It exists so fresh threads can retire a finite findings list one narrow pass at a time without reopening a broader closed program by accident.

Use this profile when the remaining work is bounded by an explicit findings list, a target note, or a narrow cleanup lane.
Do not use it when the real work still needs a durable strategy document, a shared question bank, and a cross-surface pass family sequence.
Do not use it when closeout depends on build, package, release, migration, or rollout proof that must be rerun late enough to match the final claimed result; split that work into a `serial-program/` lane instead.

## Startup Order

Fresh threads should load this packet only after the normal repo startup packet and any named authority docs for the parent lane.

1. `README.md`
2. `CHECKPOINT.md`
3. `REVIEW_FINDINGS.md`
4. Only the current pass note and the exact evidence named by that pass

Do not load every pass note by default.
The packet is designed so a fresh thread can stay cold on completed steps and still know exactly what to do next.

## Packet Files

- `README.md`: durable scope, process rules, and closeout state for this lane
- `CHECKPOINT.md`: volatile handoff for the current pass or the explicit stop condition after closeout
- `REVIEW_FINDINGS.md`: the finite seed list and lightweight queue ledger for this lane
- `passes/PASS_NOTE_TEMPLATE.md`: template for one-note pass work orders

This profile is intentionally thinner than `serial-program/`.
Queue truth lives in `REVIEW_FINDINGS.md` plus `CHECKPOINT.md`; do not add a second machine-readable control plane unless the lane has clearly outgrown this profile.

## Working Rules

- One fresh thread owns one pass.
- Each pass should retire one finding or one tightly coupled findings cluster only.
- Treat `REVIEW_FINDINGS.md` as the red-to-green checklist for the lane, not just as static prose.
- Use the shared pass-type vocabulary, but most lanes here should only need `audit`, `correction`, `verification`, `scope-expansion`, `reopen-decision`, `authority-cleanup`, or `closeout-gate`.
- Edit only the target note or owning narrow surface plus this packet's handoff files.
- After a `correction` pass, queue a fresh `verification` pass before treating a finding as green unless the lane explicitly records why stronger existing evidence already satisfies that proof need.
- If truthful repair would require reopening the broader closed program, stop and queue a separate scope-expansion note instead of widening the active pass.
- End every pass by updating `CHECKPOINT.md` and by pointing it at the next on-disk pass note or the explicit stop condition.
- If the lane uses a paste-ready prompt, keep it in one canonical surface only.
- Treat that prompt as a launch stub, not a second pass note.
- Treat it as derived output from `REVIEW_FINDINGS.md`, `CHECKPOINT.md`, and the queued pass note. If those disagree, fix those queue-owning surfaces first and then refresh the prompt.
- Let the queued pass note own detailed scope and must-not-change language.
- If the packet truth drifts from the actual lane state, run a narrow `authority-cleanup` pass before more finding repair.
- When the findings are all green or split elsewhere, shift the lane to `historical` or `closed` explicitly instead of leaving an ambiguous idle checkpoint.
- If the findings work is complete and only git or repo cleanup remains, say that explicitly instead of implying another finding pass is still required.

## Pass Order

- Seed the queue directly from `REVIEW_FINDINGS.md`.
- Move findings toward green one by one; if a pass reveals a hidden finding, add it explicitly instead of smuggling it into another line.
- Keep the order stable unless a new explicit contradiction is recorded on disk.
- If the lane closes cleanly, leave this packet as historical restart context rather than an active queue.
- If a green finding later contradicts stronger evidence, route it through a `reopen-decision` note instead of silently resetting the lane.

## Common Evidence

- Name the parent authority docs.
- Name the seed note or target note.
- Name the specific proof artifacts or earlier passes that future threads should treat as the stable evidence floor for this lane.
