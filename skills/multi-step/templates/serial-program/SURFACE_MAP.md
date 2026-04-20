# Surface Map

Use this file to make the lane's truth surfaces explicit before the pass queue grows.
Replace the placeholders below with the actual surfaces in the target repo.

## Canonical Contract Surface

- Owner:
  `<team-or-doc-owner>`
- Lives at:
  `<paths-or-docs>`
- Owns:
  the product or operator contract that other surfaces must obey
- Must not silently inherit authority from:
  `<implementation-detail-or-test-suite>`

## Implementation Surface

- Owner:
  `<team-or-runtime-owner>`
- Lives at:
  `<paths>`
- Owns:
  the live behavior and concrete seams being audited
- Must not silently redefine:
  `<canonical-contract-surface>`

## Verification / Harness Surface

- Owner:
  `<ci-or-test-owner>`
- Lives at:
  `<paths>`
- Owns:
  tests, assertions, fixtures, or harness expectations
- Must not silently redefine:
  the contract or the intended product shape

## Evidence Surface

- Owner:
  `<capture-or-observation-owner>`
- Lives at:
  `<paths-or-artifacts>`
- Owns:
  direct field evidence, captures, logs, or proof artifacts
- Role:
  descriptive evidence that can confirm or contradict the claimed model

## Residual / Follow-On Surface

- Owner:
  `<follow-on-owner>`
- Lives at:
  `<queued-follow-on-note-or-lane>`
- Owns:
  residual scope that is intentionally split out instead of being smuggled back into this lane
- Must not silently redefine:
  the closed scope of this packet

## Packet Management Surface

- Owner:
  this packet
- Lives at:
  `SPINE.md`, `CHECKPOINT.md`, `MASTER_LOG.md`, `STATUS.toml`, and `passes/`
- Owns:
  process truth, queueing, and replayability for the lane
- Must not silently redefine:
  product truth or implementation truth

## Historical Restart Surface

- Owner:
  this packet after closeout
- Lives at:
  `SPINE.md`, `CHECKPOINT.md`, `STATUS.toml`, `MASTER_LOG.md`, and any explicitly linked archive references
- Owns:
  truthful restart context for future contradictions or reopen decisions
- Must not silently imply:
  that the lane is still active once the queue is empty

## Startup Discipline

- Normal repo startup comes first.
- Then load the lane's named authority docs.
- Then load this packet in the order defined in `README.md`.
- Do not open the full pass history unless the current pass genuinely requires it.
