# Unseen Repo Adoption Prompt

Use this when a repo may be worth keeping aligned over time, but the current layout is partially unknown, stale, dirty, or inconsistent.

The goal is not to make the repo perfect in one pass. The goal is to decide the right adoption posture first, then move locally managed repos toward an explicit, low-fragility operating model without assuming a clean history or a clean working tree.

## Operator Inputs

Fill these in before use:

- Repo root: `<absolute path>`
- Mode: `discovery-only` or `apply-safe-changes`
- Adoption posture: `undetermined`, `repo-native-only`, `local-overlay`, or `in-tree-adoption`
- Constraint: do not touch public/exported surfaces unless explicitly asked
- Constraint: do not use destructive git operations
- Constraint: if the repo is already dirty, prefer an isolated worktree or branch before edits
- Constraint: if safe isolation is not available, stay in discovery-only mode and report the blocker instead of editing in place

## Prompt

```text
You are evaluating an unseen repo for continuity adoption.

Work conservatively. Treat this as a migration decision on a possibly dirty, possibly stale repo that may contain mixed-lifetime docs, ad hoc structure, public release contracts, and local history we should not disturb.

Primary goal:
- choose the right adoption posture, then move locally managed repos toward a small explicit contract that future GPT-based agents can follow reliably

Important framing:
- the continuity packet is one management overlay, not a universal measure of repo health
- a healthy third-party or public upstream repo may need no in-tree continuity files at all
- the primary positive signal that we have taken charge of a repo should be an explicit local marker or manifest when the environment supports one
- do not treat missing README.md, AGENTS.md, PROJECT_CONTINUITY.md, CHECKPOINT.md, or an indexing declaration as defects until you know this repo should carry a continuity layer
- do not treat the presence of a root `AGENTS.md` in a public repo as evidence that it uses your continuity packet; it may be the repo's own native contributor or agent-facing guidance

Possible adoption postures:
- repo-native-only: understand and preserve the repo's existing structure with no continuity overlay
- local-overlay: keep any Codex-specific continuity or indexing metadata outside the repo tree
- in-tree-adoption: add or migrate repo-local continuity files because this repo is locally managed and should carry the overlay itself

Ownership signal:
- if the repo already carries an environment-documented marker or external manifest, that is the primary signal that this repo is already under a continuity contract
- if neither exists, do not infer "we own this" from filename overlap alone

Steady-state target for in-tree-adoption repos:
- root continuity packet: README.md, AGENTS.md, PROJECT_CONTINUITY.md, CHECKPOINT.md
- explicit repo-local ownership marker when the environment uses one
- durable authored docs under docs/ by default
- explicit indexing declarations for code/docs/datasets when supported
- explicit docs index names so docs roots do not collide across projects

Steady-state target for local-overlay repos:
- keep the target repo clean in-tree
- record ownership and posture in the external manifest or local notes the environment documents
- keep index declarations explicit there instead of relying on inference

Migration principles:
- prefer detect-and-report before rewrite
- prefer additive changes before renames or relocations
- do not invent repo-specific special cases unless the repo truly requires them
- separate one-time migration work from the steady-state contract
- if a current layout is stale or odd, do not "perfect" it blindly; capture what should become the future default
- if jcode/jdocs/jdata are available, use them first; otherwise do a careful filesystem audit
- treat missing root packet files and overloaded AGENTS.md files as first-class findings only when the repo should actually carry a continuity layer; otherwise treat them as neutral observations about repo shape
- preserve public doc, packaging, and release contracts before proposing continuity-layer changes
- preserve shipped agent-facing assets such as public `skills/`, plugin metadata, or installable MCP guidance as part of the repo's native surface unless the user explicitly wants a local overlay
- if a public repo already ships `AGENTS.md`, treat it as a native repo surface first; do not assume it implies or partially satisfies your continuity packet

Your workflow:
1. Audit the repo shape first.
2. Classify the repo posture before recommending changes:
   - locally managed project that should probably carry the continuity packet in-tree
   - third-party or public upstream repo that should stay repo-native
   - mixed case such as a local fork, adopted upstream, or repo that needs only a local overlay
3. Classify the current surfaces:
   - whether the repo already carries an environment-documented ownership marker or local manifest
   - whether an external manifest or local notes already claim the repo for `local-overlay`
   - startup docs
   - durable docs
   - volatile handoff docs
   - shipped agent-facing assets such as public skills, plugin manifests, or installation guidance that are part of the repo's native contract
   - root files whose names overlap with a local continuity contract, such as `AGENTS.md`, and whether they are actually native upstream guidance instead of a local overlay
   - runtime assets such as model weights, checkpoints, or other downloaded local artifacts required for execution but not meant for tabular retrieval
   - datasets intended for structured retrieval
   - operational logs, caches, or dumps that live near data but should not automatically be indexed as datasets
   - whether docs-root variants such as `Docs/` and `docs/` are truly distinct in git or only aliases on the local filesystem
   - noisy/generated/build-only areas
   - whether noisy/generated/build-only areas are tracked in git or only present locally
   - whether there are adjacent worktrees, sibling checkouts, or in-progress migration surfaces that affect judgment
4. Identify the minimum steady-state contract this repo should converge to for its chosen posture.
5. Distinguish clearly between:
   - safe changes to apply now
   - migration-only changes that should be deferred or explicitly approved
6. Call out any mismatch between the repo's claimed workflow and its actual on-disk structure.
7. If the repo is dirty or on a shared branch, choose the safest available isolation path before edits:
   - repo-local worktree if the repo already has a pattern for that
   - fresh branch if the working tree is otherwise clean and branch-local edits are acceptable
   - discovery-only with no edits if the checkout is dirty, shared, ambiguous, or not safely isolatable
8. Say explicitly which isolation path you chose and why.
9. In `apply-safe-changes` mode, make only the minimum safe changes that improve future startup and indexing reliability for the chosen posture.
10. Run the lightest obvious verification path you can justify without adding new dependencies or setup churn, and say when no trustworthy verifier exists.
11. Re-index or re-qualify the affected surfaces and report what was actually picked up.
12. End with:
   - findings
   - chosen adoption posture
   - changes made
   - isolation path used
   - deferred migration items
   - verification evidence
   - whether current terminals, new shells, app restarts, or reboots are affected

Rules for safe changes:
- do not add a continuity packet to a third-party or public upstream repo unless the user explicitly wants in-tree adoption
- adding an environment-documented repo-local ownership marker is the explicit act of taking charge; do not add it to third-party or public upstream repos unless the user explicitly wants in-tree adoption
- do not add an in-tree indexing declaration to a public or third-party repo by default when the need is only local retrieval; prefer local overlay or external registration
- for `local-overlay`, prefer updating the environment's external manifest or local notes over adding in-tree continuity files
- adding an explicit indexing declaration is usually safe
- adding docs/README.md as a canonical docs anchor is usually safe
- updating repo-local references from PROJECT_SPINE.md to PROJECT_CONTINUITY.md may be safe if all references are local and obvious
- when a repo already uses PROJECT_SPINE.md, legacy compatibility may need a migration bridge phase instead of an in-place delete
- renaming or relocating existing docs is not automatically safe on a dirty repo; propose it unless the repo is clearly isolated for migration
- do not treat tracked generated output as routine cleanup; if build/noise directories are tracked, report that as a migration decision
- if README.md is missing or still a stock scaffold, say so explicitly when evaluating a locally managed repo; for third-party repos, treat it as a repo-native documentation finding, not evidence they need our packet
- do not declare datasets unless they are actually intended for structured retrieval
- do not auto-declare caches, logs, or refresh byproducts as datasets just because they live under `data/`
- do not treat runtime model or checkpoint assets as datasets or routine cleanup targets; if the repo depends on ignored or downloaded weights, treat that location as part of the runtime contract
- do not treat sibling worktrees or adjacent migration experiments as blessed source without saying so explicitly
- if `Docs/` and `docs/` both appear, check whether they are actually distinct tracked paths before recommending normalization
- if you cannot isolate safely, do not make "just a small change" in place; stop at discovery and report the exact blocker
- do not index the entire repo as docs if that would pull in noisy config or generated files; prefer a real docs root
- if README.md participates in packaging, release, or install flows, treat that behavior as a contract before proposing doc reshaping
- if the repo ships agent-facing assets for public consumption, treat those as part of the native product surface, not as evidence that a private continuity overlay belongs in-tree

Output format:
- Findings
- Chosen adoption posture
- Proposed steady-state contract
- Safe changes applied now
- Deferred migration items
- Verification
- Risks or ambiguities
```

## How To Iterate

Run the prompt in `discovery-only` mode first on a repo you do not fully trust.

When helpful, gather the low-risk facts first with:

```bash
python3 scripts/repo-adoption-audit.py --json <repo-root>
```

If the findings look right:

1. switch to `apply-safe-changes`
2. keep the change set minimal
3. verify the resulting indexes
4. extract any repeated judgment into scripts only after the prompt has stabilized across multiple repos

Prompt-first is the default. Scripts should accelerate a known-good decision path, not substitute for judgment on unseen repos.

The first judgment is whether this repo should carry a continuity overlay at all.
