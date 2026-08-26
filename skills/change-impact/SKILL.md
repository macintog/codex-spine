---
name: change-impact
description: Map affected consumers and verification obligations before implementing or reviewing a change that crosses interfaces, persistence or schemas, permissions, deployment or release boundaries, or three or more downstream branches. Use for blast-radius and what-could-break questions. Do not use for ordinary local edits, generic code review, or a post-hoc risk narrative with no decision or verification consequence.
---

# Change Impact

Produce an evidence-backed map of what the selected change can affect, the one
or two assumptions carrying most of its safety, and a finite verification list.
Do not broaden the current task, mutate during a read-only review, or turn a
residual finding into successor work.

## Confirm The Gate

Use this skill when the proposed or reviewed change crosses at least one
material boundary:

- a public interface, wire format, shared contract, or independently deployed
  consumer;
- persisted state, a schema, migration, cache, or compatibility contract;
- authorization, permissions, entitlements, secrets, or another trust boundary;
- build, packaging, deployment, rollout, rollback, or release behavior; or
- three or more downstream branches whose failure modes need separate proof.

Skip it when the change is local behind an unchanged interface and focused
tests cover the behavior. Do not activate it merely because a diff is large,
the user requested an ordinary review, or a polished risk section would make a
completed decision look safer.

## Map The Reach

1. Bind the exact change and current evidence: repository, ref or worktree,
   relevant diff, intended behavior, and the authority granted by the user.
2. Start with the repo-declared retrieval lane that matches the evidence: use
   `jcode` for definitions, call sites, callers, and adjacent code; `jdocs` for
   authored contracts, runbooks, and reference trees; and `jdata` for tabular
   or dataset-backed impact. Use only lanes relevant to the crossed boundary.
   A miss clears only the named query and scope; do not sweep all lanes or
   connectors.
3. Trace each crossed boundary to concrete consumers. Go beyond symbol callers
   when behavior also travels through serialized data, configuration, generated
   code, lifecycle ordering, pinned dependencies, operational automation, or a
   different runtime or language.
4. For every plausible consumer, record the interface crossed, reachability,
   failure mode, supporting location or runtime evidence, and status:
   `confirmed risk`, `cleared`, or `unproven`. A search with no matches is useful
   cleared evidence when its scope is named.
5. Keep cleared checks visible. Do not report only alarming possibilities, and
   do not promote a hypothetical failure without a reachable path.

## Prove The Load-Bearing Assumptions

Identify the one or two facts on which most of the safety judgment depends.
Drive each to the strongest proportionate proof available:

1. direct source, contract, or version evidence;
2. a traced good and bad path through the real boundary;
3. a focused test or probe using the shipped implementation;
4. reproduction in the relevant runtime or release environment.

Run code only when the current task authorizes it and the environment is safe.
If direct proof is unavailable or disproportionate, mark the assumption
`unproven`; explanation is not a substitute for execution evidence.

## Close With Finite Obligations

Return:

- **Change:** the behavior difference and crossed boundaries.
- **Consumers:** affected-consumer map with confirmed, cleared, and unproven
  entries.
- **Load-bearing assumptions:** at most two, each with its proof level and exact
  evidence.
- **Confirmed risks:** reachable failure, likelihood, consequence, and the check
  that would detect it.
- **Verification obligations:** the smallest finite list needed for the current
  change, including required environment or authority and any proof that could
  not be run.

Do not create a queue, next prompt, worker reservation, or follow-up task.
Workers and historical packets are evidence only. Do not prescribe models,
worker counts, MCPs, or a delegation scheme; use only the current platform's
native mechanisms within current task authority.

This skill adapts the pstack `blast-radius` pattern. See [LICENSE.txt](LICENSE.txt)
for source and license provenance.
