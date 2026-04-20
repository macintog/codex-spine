# <Program Name> Packet

This packet is the dedicated working area for `<program-name>`.
It exists so fresh threads can run one narrow pass at a time without reloading the full history of the failure.

Use this profile when the work is a multi-pass program with a frozen authority order, multiple surface families, a custom lane checklist, and explicit correction or verification sequencing.
Do not use it for a one-shot fix or for a bounded note-repair lane that already has a finite findings list.

## Startup Order

Fresh threads should load this packet only after the normal repo startup packet and any named authority docs for this lane such as `<authority-doc>`, `<contract-doc>`, or an adjacent doctrine or target-definition doc.

1. `SPINE.md`
2. `CHECKPOINT.md`
3. `STATUS.toml`
4. `QUESTION_BANK.md`
5. `SURFACE_MAP.md`
6. Only the current pass note and any exact evidence anchors named by the checkpoint or status file

Do not open every pass note by default.
The packet is designed so a fresh thread can stay cold on old details and still know exactly what to do next.

## Packet Files

- `SPINE.md`: durable purpose, strategy, authority order, pass families, and closeout gate
- `CHECKPOINT.md`: volatile handoff for the active pass or the explicit stop condition
- `STATUS.toml`: compact machine-readable lane state and queue ownership
- `QUESTION_BANK.md`: shared interrogation script and red-to-green rubric for audit and verification passes
- `SURFACE_MAP.md`: where the authority surfaces, implementation surfaces, evidence anchors, and packet-management surfaces live
- `MASTER_LOG.md`: terse pass ledger for navigation only
- `passes/PASS_NOTE_TEMPLATE.md`: template for queued work-order notes
- `passes/PASS_ARTIFACT_TEMPLATE.md`: template for completed pass artifacts

## Working Rules

- During audit passes, the only substantive write is the pass artifact itself plus the packet handoff files.
- During correction passes, edit only one owning surface family plus the packet handoff files.
- One fresh thread should own one narrow pass.
- Keep `QUESTION_BANK.md` task-specific; it is the lane rubric, not generic ceremony.
- Keep the canonical queue fields in `STATUS.toml` current: lane mode, active note, active pass type, next note, prompt surface, and any scope-expansion or reopen note.
- Derive the pass queue from the remaining red or ambiguous rubric lines instead of assuming the full step count up front.
- Use helpers or workers only for bounded read-only subtasks; keep one thread responsible for the pass result.
- After one correction pass, require one fresh verification pass before treating the line as settled.
- A pass may add one new rubric line when evidence exposes a missing seam, but it must record that discovery on disk before ending.
- If the same seam remains ambiguous after one correction pass and one fresh verification pass, stop and record the ambiguity instead of broadening the patch.
- If another pass remains after the current one, write the next queued pass note to disk and point `CHECKPOINT.md` and `STATUS.toml` at it before ending the thread.
- If the lane uses a paste-ready prompt, keep it in one canonical surface only. `CHECKPOINT.md` may own it inline, or the packet may point at another prompt surface instead.
- Treat that prompt as a launch stub, not a second pass note.
- Treat it as derived output from `STATUS.toml`, `CHECKPOINT.md`, and the queued pass note. If those disagree, fix the queue-owned surfaces first and then refresh the prompt.
- Let the queued pass note own detailed scope and must-not-change language.
- When the queue is empty, convert the packet to `historical` or `closed` state explicitly instead of leaving it looking merely idle.
- Reopen a historical lane only through an explicit contradiction or scope-expansion note recorded on disk.
