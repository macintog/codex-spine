# Technical prose

Use these rules for documentation, READMEs, RFCs, procedures, technical
explanations, reports, PR descriptions, and commit messages. The goal is a
tired engineer understanding the text on the first read.

## Pick the document job

For a substantial document, choose its primary job before editing its form:

- **Tutorial:** help a learner succeed through a sequence with visible results.
- **How-to:** help a competent reader accomplish a concrete task.
- **Reference:** provide complete, navigable facts for lookup.
- **Explanation:** answer a bounded why question with context and tradeoffs.

Split and link when a document tries to do incompatible jobs. Do not impose
this taxonomy on a short message, PR description, commit message, or UI string.

## Write for the reader's action

- Lead with the result, decision, or task. Put background after the reader
  knows why it matters.
- Address the reader as "you" when appropriate and use present tense for
  current behavior.
- Write instructions as commands. Put the condition before the instruction it
  governs and the common case before exceptions.
- In a tutorial, state what the reader will build and what they should observe
  after each meaningful step.
- In a how-to, omit teaching digressions. Link to explanation or reference when
  that material is necessary.
- In reference, mirror the structure of the described interface. State facts,
  options, limits, and errors without persuasion.
- In explanation, name the actual why question, constraints, alternatives, and
  supported judgment.

## Make sentences parse once

- Give one instruction per sentence and one main thought per sentence.
- Name the actor when it matters. Use passive voice when the actor is unknown
  or beside the point.
- Keep `only`, `not`, and other modifiers beside the words they change.
- Make every pronoun point to one obvious noun. Repeat the noun when needed.
- Break up long noun strings. Prefer "the script that checks the import budget"
  over "the proto import budget check script".
- Give every clause a verb. Retain articles and connecting words when they
  prevent a second reading.
- Use one term for one concept across the document. Use the repository's real
  symbol, path, flag, or command instead of a fresh synonym.
- Use numbered lists for sequences and bullets for unordered sets. Introduce a
  list with a complete sentence and keep items parallel.
- Use descriptive link text. Do not use "click here".
- Keep headings in sentence case and make them carry the point or task.

## Keep claims reproducible

- Verify symbols, paths, commands, counts, links, and measurements against the
  current artifact before delivery.
- State whether a claim is observed, inferred, estimated, or not proven when
  the distinction matters.
- Preserve denominators, units, comparison arms, and qualification boundaries.
- Do not turn a cleaner sentence into a stronger claim.

PR descriptions and commit messages use the sentence and evidence rules, but
they do not need document-mode classification. Product UI strings follow the
product's copy and accessibility rules first.
