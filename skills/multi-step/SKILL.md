---
name: multi-step
description: Run long-lived, drift-prone work as a serial, disk-backed program with one narrow pass per fresh thread, explicit authority order, a task-specific checklist, and on-disk handoffs.
metadata:
  short-description: Canonical serial-pass workflow for narrow multi-thread programs
---

# Multi-Step

Use this skill when a problem is too large, ambiguous, or drift-prone for one conversational push, but still benefits from a strict order of operations, a task-specific checklist, and small owned passes.

The goal is not "be more organized." The goal is to turn a fuzzy, recurring problem into a bounded program that survives fresh threads without depending on chat memory.
The exact number of passes does not need to be known up front if the lane has a durable way to discover the next truthful step.

This skill is for workflow and governance. It helps define the packet, pass order, and handoff rules. Repo-local continuity docs, tooling guides, and verifiers still own local file locations, lane routing, and proof commands.

## When To Use This Skill

- The issue will likely span multiple fresh threads.
- Scope drift, repeated re-analysis, or stale chat memory has already slowed progress.
- The work has a real authority stack such as contract, implementation, tests, docs, operations, or release surfaces.
- The problem must be solved in a specific order rather than by broad parallel edits.
- The number of steps is not known yet, but the work can be driven by a task-specific rubric or checklist.
- You need each pass to leave a durable on-disk next step instead of a conversational recap.

## When Not To Use This Skill

- The task is a small one-shot bug, straightforward implementation, or simple review.
- There is no stable authority order, no durable evidence, or no agreement about what counts as truth yet.
- The work can be completed safely in one thread without likely drift.
- The packet overhead would be larger than the actual problem.

If the problem is real but the truth stack is still unclear, resolve that first. This skill can structure ambiguity, but it cannot invent authority where none exists.

## Core Invariants

- One fresh thread owns one narrow pass.
- Every pass has explicit in-scope and out-of-scope boundaries.
- The on-disk queue is the source of truth for what is open, queued, blocked, or closed.
- If chat, memory, or a human recap disagrees with the queue, reconcile the handoff first instead of freelancing the next pass.
- The authority order is chosen up front and does not silently change mid-program.
- Every pass declares its pass type before work starts and does not silently switch types mid-thread.
- The lane carries a task-specific rubric or checklist that classifies seams, findings, or surface lines with evidence.
- The queue may start incomplete; discovering the next needed pass from the rubric is part of the work.
- If the work depends on durable theory, expectations, or target definitions, keep those in named authority docs instead of bloating the active queue.
- A pass writes its reasoning and outcome to disk, not just to chat.
- The live handoff stays small; deep history lives in pass artifacts.
- If work remains, the lane keeps a paste-ready prompt for the next fresh thread on disk.
- The next-thread prompt is a launch instruction, not a second checkpoint.
- The next-thread prompt is derived from the queue and handoff state on disk; it does not create or override scope by itself.
- It should name what to load, which queued pass note owns scope, and which direct evidence anchors to inspect first.
- Do not carry forward old scope fences, historical guardrails, or reopen-if-X conditions unless the queued pass note still marks them as active scope.
- Correction passes are followed by fresh verification passes before the result is treated as closed.
- A line turns green only when the required evidence and fresh verification say it does.
- Closed lines stay closed unless a later pass opens them again on purpose with new evidence and an explicit reopen note.
- If truthful progress requires broader scope, stop and record a scope-expansion note instead of widening the active pass.
- Closeout is not real until startup or handoff surfaces also tell the truth.
- Build, package, release, migration, or rollout proof only counts when it is rerun late enough that the produced result still matches the final on-disk truth.

These invariants matter more than any particular filename or folder layout.

## Recommended Profiles

### Full Program

Use this profile for long cross-surface efforts where the problem needs a durable strategy, a fixed authority order, a lane-specific checklist, and a machine-readable notion of progress.

Typical packet pieces:

- a durable `README` or `SPINE`
- a small volatile `CHECKPOINT`
- named authority docs when the queue depends on durable theory, expectations, or target definitions
- a question bank and pass rubric
- a surface map or authority map
- an optional master ledger
- an optional machine-readable status file
- an optional dedicated prompt surface when the repo wants one
- a pass template
- pass artifacts and queued next-pass notes

This profile is the right fit when the work must move through multiple surface families in order.

### Finite Findings

Use this profile for a bounded follow-on lane where the queue is already mostly known and the job is to retire a fixed set of issues without reopening the larger finished program.

Typical packet pieces:

- a durable lane `README`
- a small volatile `CHECKPOINT`
- a seed findings file or scoped issue list
- an optional dedicated prompt surface when the repo wants one
- pass notes for each finding and the closeout gate

This profile is the right fit when the problem is already narrowed and the main risk is drift or accidental reopening of closed scope.

## Workflow

### 1. Decide whether the problem deserves a packet

Before creating structure, answer:

- Why is ordinary execution likely to drift here?
- What are the relevant authority surfaces?
- What order must they be handled in?
- What proof will tell you the program is actually done?

If those answers are still fuzzy, do not pretend the packet exists yet.

### 2. Freeze the authority order

Choose the order in which surfaces are allowed to define truth.

Examples:

- contract before implementation before CI
- requirements before migration before rollout
- source before export before downstream verification

Do not let later surfaces quietly redefine earlier ones. Tests, notes, or historical artifacts are evidence only if the chosen authority order says they are.

### 3. Build the lane-specific rubric

Before queueing passes, define the task-specific checklist that will let the lane discover how many truthful steps it actually needs.

That rubric should:

- name the seams, findings, or surface lines that matter for this exact task
- define what red, ambiguous, and green mean for this lane
- point at the evidence needed to flip one line to green
- stay open to new lines when real contradictions are discovered
- avoid generic bookkeeping that does not help the next pass decide what to do

The rubric is what lets the program be open-ended without becoming vague.

### 4. Create a small startup packet

The packet should let a fresh thread start with durable rules, current state, and one owned task without loading the whole history.

Keep the packet cheap to load:

- one durable purpose or rules file
- one volatile current-state handoff
- named authority docs only when the current pass genuinely depends on them
- only the current pass note and directly relevant evidence by default

Do not make every fresh thread reopen the entire pass history unless a contradiction requires it.

### 5. Make queue truth explicit

The queue is not just a convenience list. It is the durable contract for what work exists and what state each line is in.

That means:

- queued pass notes, rubric state, and the live handoff must agree about what is open now
- chat-only intent does not create scope until the queue says it does
- a line is not reopened because someone mentioned it again; it reopens only when the queue records why the prior close no longer holds
- if the handoff, rubric, and queued pass note disagree, stop and run a reconciliation pass before attempting new correction work

When in doubt, fix the queue first and code second.

### 6. Write pass types explicitly

Common pass types:

- `audit`: inspect a surface and record findings without fixing it
- `correction`: change one owning surface family
- `verification`: re-check a narrow corrected scope in a fresh thread
- `scope-expansion`: stop the active pass, record why truthful progress now needs wider scope, and queue the follow-on decision cleanly
- `reopen-decision`: determine whether a historical or green line must be reopened, split out, or left closed with stronger evidence
- `authority-cleanup`: repair queue state, handoff wording, routing truth, or other packet-management surfaces when durable docs disagree about what is actually open, queued, or closed
- `closeout-gate`: prove the lane is actually done and that startup surfaces reflect that fact

Pass-type discipline matters:

- `audit` threads do not fix
- `correction` threads do not broaden into freeform re-audit
- `verification` threads do not silently patch unless the lane explicitly re-queues them as correction work
- `scope-expansion` threads split the queue cleanly; they do not quietly widen the parent
- `reopen-decision` threads decide whether prior closure still holds; they do not smuggle in unrelated new work
- `authority-cleanup` threads fix the lane's durable state before more implementation work proceeds
- `closeout-gate` threads prove closure; they do not smuggle in new feature work

Do not let one pass silently become all seven.

### 7. Keep each pass narrow

A good pass owns one question family, one surface family, or one finding cluster.
A strong pass usually advances one rubric line from red or ambiguous toward green, or proves that the rubric itself needs one new line.

Each pass artifact should say:

- what was in scope
- what evidence was checked
- what was found
- what changed, if anything
- what must not change
- what remains ambiguous
- what the next pass is

If the pass is verification, it should also say whether the target is clearly aligned, aligned with residual risk, still ambiguous, or misaligned.

### 8. End every pass with an on-disk next step

Before the thread ends:

- update the live handoff
- update the relevant rubric or checklist states on disk
- write the next queued pass note or explicit stop condition
- refresh the copy-paste prompt for the next fresh thread if another pass remains
- record any new ambiguity or scope-expansion trigger on disk

Keep that prompt thin.
It should name the packet docs to load, the queued pass note to execute, and the direct evidence anchors needed to start cold.
Treat it as derived output from the current queue and handoff state, not as an independent authority file.
Let the queued pass note own detailed in-scope or out-of-scope boundaries and must-not-change rules.
Do not turn the prompt into a second checkpoint or a dump of old scope fences.
The handoff should say what is true now, not retell the whole program.
If a fresh thread would need deep history, point it at the owning pass artifact instead of bloating the prompt or checkpoint.

Do not rely on chat-only next steps for multi-step work.

### 9. Reopen only by protocol

Reopening is allowed, but only when the lane says why.

Use an explicit reopen note when:

- new evidence invalidates a prior green line
- a later verification contradicts an earlier correction result
- build, package, release, migration, or rollout proof shows the supposedly closed result was not the one that actually shipped or ran
- the lane was closed optimistically and the startup surfaces no longer match reality

A good reopen note names:

- what was previously treated as closed
- which evidence changed
- whether the reopen is a narrow verification replay, a new correction, or a child lane
- which old guardrails still apply and which ones are retired

Do not smuggle reopen logic into a normal correction note and hope the next thread notices.

### 10. Close the loop explicitly

A lane is not done just because the last artifact sounds confident.

Closeout should confirm:

- the pass queue is empty or explicitly stopped
- the lane rubric has no silent red lines left hiding behind optimistic prose
- the relevant startup or handoff docs tell the truth
- residual issues have been moved into a new lane instead of smuggled into a closed one
- the chosen proof for the lane has been rerun fresh enough to trust
- any build, package, release, migration, or rollout proof was produced after the final relevant correction, not before it
- the thing that was verified is the same thing the lane now claims is complete
- if substantive lane work is complete and only repo cleanup remains, say that explicitly instead of implying the lane itself is still unfinished
- when that remaining cleanup is version-control work such as git staging, commit, branch cleanup, push, or PR hygiene, offer to do it next in the same thread

## Scope Expansion And Escalation

Stop the active pass and write a separate note when:

- fixing the issue truthfully would require reopening a closed authority line
- the pass needs to edit more than one owning surface family
- the evidence contradicts the packet's current authority order
- the queue should be reordered for a reason stronger than convenience
- the lane turns out to be a different problem than the one the packet was created to solve

Split a child lane instead of widening the parent when:

- one finding cluster now has its own stable authority order or proof loop
- repeated reopen or correction cycles in one area would bury the parent lane's real status
- build, release, migration, or rollout work needs its own late-stage queue and proof discipline
- the parent lane should stay mostly closed while one residual issue family continues

Escalation here is a success condition, not a failure. The point is to prevent the active pass from becoming an unbounded project again.

## Failure Modes

- Creating a packet for work that should have stayed simple.
- Writing a lot of packet ceremony without a real authority stack.
- Using a generic checklist instead of a lane-specific rubric that actually matches the task.
- Assuming the number of passes up front instead of letting the rubric discover the needed queue.
- Treating the queue as advisory while chat or habit decides what is really next.
- Letting checkpoint or handoff files grow into a second history log.
- Letting a thread drift across pass types because "it was convenient while we were here."
- Treating old tests, notes, or logs as normative truth when they are only evidence.
- Mixing correction of multiple surface families into one pass.
- Calling a correction "done" without a fresh verification pass.
- Reopening a closed line informally without recording why the prior close failed.
- Flipping a line green on confidence or convenience instead of proof.
- Leaving the next step only in chat instead of on disk.
- Leaving the operator to reconstruct the next-thread prompt by hand.
- Closing the lane without propagating the truth back to startup surfaces.
- Closing a build or release flavored lane on pre-final proof, even though later edits may have invalidated the artifact or rollout state.
- Using note repair to avoid admitting that the real work now requires contract or implementation change.

## Relationship To Repo-Local Continuity And Tooling

This skill is not a replacement for repo-local continuity docs, startup packets, or tooling guides.

Use repo-local continuity to decide:

- where the packet lives
- which startup docs are authoritative
- which adjacent repos or export surfaces matter
- which verifier or closeout expectations apply

Use repo-local tooling guidance to decide:

- how to navigate the code or docs efficiently
- how to gather proof for a pass
- how to run local lifecycle or closeout flows

Use this skill to decide:

- whether the work should become a serial program
- what packet profile to use
- how passes are scoped
- how truth moves from one pass to the next
- when to stop, verify, escalate, or close

## Practical Default

If you are unsure whether to use this skill, ask one question:

"Will this work be safer and faster if a fresh thread can pick up one narrow pass tomorrow without reconstructing today's reasoning from memory?"

If the answer is yes, this skill is probably a good fit.
