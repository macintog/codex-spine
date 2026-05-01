---
name: multi-step
description: Run long-lived, drift-prone work as a serial, disk-backed program with one narrow pass per fresh thread, explicit authority order, a task-specific checklist, and on-disk handoffs.
metadata:
  short-description: Canonical serial-pass workflow for narrow multi-thread programs
---

# Multi-Step

Use this skill when a problem is too large, ambiguous, or drift-prone for one conversational push, but still benefits from a strict order of operations, a task-specific checklist, and small owned passes.

The goal is not "be more organized." The goal is to turn a fuzzy, recurring problem into a bounded program that survives fresh threads without depending on chat memory. The exact number of passes does not need to be known up front if the lane has a durable way to discover the next truthful step.

This skill owns workflow shape: packet, authority order, queue, pass rules, and handoff. Repo-local continuity docs, tooling guides, and verifiers still own local paths, lane routing, and proof commands.

## Output And Stop Conditions

Every pass must end with one of these on disk:

- a queued next pass with scope, evidence anchors, and pass type
- an explicit blocker with the evidence needed to unblock it
- a scope-expansion note that stops the active pass before wider work begins
- a closeout note proving the queue, handoff, and startup surfaces now agree

If another pass remains, keep one thin paste-ready prompt on disk. It is launch text, not a second checkpoint: name what to load, the queued pass that owns scope, and the direct evidence anchors to inspect first. Point at queue-owned surfaces without overriding them, and do not carry forward old scope fences, historical guardrails, reopen-if-X conditions, or lane history unless the queued pass note still marks them active.

Stop instead of widening the thread when:

- the authority order is unclear or contradicted
- queue, handoff, and evidence disagree
- truthful progress needs broader scope than the current pass owns
- verification contradicts a supposedly closed line
- build, package, release, migration, or rollout proof no longer matches the final on-disk truth

Do not rely on chat-only next steps for multi-step work.

## When To Use This Skill

- The issue will likely span multiple fresh threads.
- Scope drift, repeated re-analysis, or stale chat memory has already slowed progress.
- The work has a real authority stack such as contract, implementation, tests, docs, operations, or release surfaces.
- The problem must be solved in a specific order rather than by broad parallel edits.
- The number of steps is not known yet, but the work can be driven by a task-specific rubric or checklist.
- Each pass needs a durable on-disk next step instead of a conversational recap.

Do not use it for small one-shot fixes, simple reviews, or tasks that can be completed safely in one thread.

If the truth stack is still unclear, resolve that first. This skill can structure ambiguity; it cannot invent authority where none exists.

## Core Invariants

- One fresh thread owns one narrow pass with explicit in-scope and out-of-scope boundaries.
- The on-disk queue is the source of truth for open, queued, blocked, and closed work.
- Authority order is chosen up front and does not silently change mid-program.
- Each pass declares its pass type before work starts and does not silently switch type.
- The lane carries a task-specific rubric that classifies lines with evidence.
- Durable theory, expectations, and target definitions live in named authority docs, not in an ever-growing queue.
- Every pass writes reasoning and outcome to disk; deep history lives in pass artifacts, not the live handoff.
- Closed lines stay closed unless reopened with new evidence and an explicit reopen note.
- Correction passes are followed by fresh verification before closure.
- Closeout is real only when queue, handoff, startup surfaces, and late proof agree.

These invariants matter more than any particular filename or folder layout.

## Profiles

Use **Full Program** for cross-surface efforts that need durable strategy, fixed authority order, a lane-specific rubric, and a machine-readable notion of progress. Typical packet pieces are a durable purpose file, small volatile checkpoint, authority docs when needed, a rubric, queue/pass notes, and optional machine-readable status.

Use **Finite Findings** for a bounded follow-on lane where the queue is already mostly known and the job is to retire a fixed set of issues without reopening the larger finished program. Typical packet pieces are a lane README, small checkpoint, seed findings list, pass notes, and a closeout gate.

## Workflow

### 1. Decide whether the problem deserves a packet

Answer:

- Why is ordinary execution likely to drift here?
- What are the authority surfaces?
- What order must they be handled in?
- What proof shows the program is done?

If those answers are fuzzy, do not pretend the packet exists yet.

### 2. Freeze authority order

Choose the order in which surfaces define truth, such as contract before implementation before CI, or source before export before downstream verification. Later surfaces can provide evidence, but they do not quietly redefine earlier ones.

### 3. Build the rubric

Before queueing passes, define the task-specific checklist that lets the lane discover how many truthful steps it needs. It should name the lines that matter, define red/ambiguous/green, point at evidence needed to flip a line green, and allow new lines only when real contradictions appear.

### 4. Create a small startup packet

A fresh thread should start with durable rules, current state, and one owned task without loading the whole history. Default to one durable purpose/rules file, one volatile handoff, named authority docs only when the current pass needs them, and the current pass note plus direct evidence anchors.

### 5. Keep queue truth explicit

Queued pass notes, rubric state, and live handoff must agree. Chat-only intent does not create scope. If they disagree, run an authority-cleanup or reconciliation pass before more correction work.

### 6. Use pass types

Common pass types:

- `audit`: inspect and record findings without fixing
- `correction`: change one owning surface family
- `verification`: re-check corrected scope in a fresh thread
- `scope-expansion`: stop, record why wider scope is needed, and queue the follow-on decision
- `reopen-decision`: decide whether a historical green line must reopen
- `authority-cleanup`: repair queue, handoff, routing truth, or packet state
- `closeout-gate`: prove the lane is done

Do not let one pass silently become all of them.

### 7. Keep each pass narrow

A good pass owns one question family, one surface family, or one finding cluster. Its artifact should say what was in scope, what evidence was checked, what changed, what must not change, what remains ambiguous, and what comes next.

For verification, also say whether the target is aligned, aligned with residual risk, still ambiguous, or misaligned.

### 8. Reopen only by protocol

Use an explicit reopen note when new evidence invalidates a prior green line, verification contradicts correction, shipped proof differs from the closed result, or startup surfaces no longer match reality.

A good reopen note names what was closed, which evidence changed, whether the reopen is verification, correction, or a child lane, and which old guardrails still apply.

### 9. Close out from disk truth

Before calling the lane done:

- all open lines are green or deliberately out of scope
- required proof was rerun late enough to match the final on-disk result
- the live handoff is small and current
- startup surfaces tell the same truth as the queue
- no next prompt remains unless new work is intentionally queued
