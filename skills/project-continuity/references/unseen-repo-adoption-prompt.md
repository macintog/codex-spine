# Unseen Repo Adoption Prompt

Use this for a repo whose continuity ownership is unknown, stale, or mixed. Start from `undetermined`; do not treat location or familiar filenames as proof of adoption.

## Inputs And Authority

- Repo root: `<absolute path>`
- Mode: `discovery-only` or `apply-safe-changes`
- Initial posture: `undetermined`, `repo-native-only`, `local-overlay`, or `in-tree-adoption`
- Allowed write roots: `<repo root only by default>`
- Allowed index targets: `<none unless named>`
- Public/exported surfaces: read-only unless explicitly authorized

`discovery-only` is read-only. `apply-safe-changes` permits scoped writes only inside the named repo by default. Writing external overlays under `~/.codex`, refreshing or creating indexes, changing remotes, destructive actions, or widening scope requires explicit authority naming the target.

## Prompt

```text
Evaluate this repo for continuity adoption.

Goal:
- choose the smallest truthful posture: repo-native-only, local-overlay, or in-tree-adoption
- preserve the repo's existing public, contributor, release, packaging, and agent-facing contracts
- make only the changes authorized by the supplied mode and write roots

Evidence first:
1. Inspect repo shape, native guidance, Git posture, existing ownership markers, indexes, docs, volatile handoffs, generated areas, datasets, runtime assets, and adjacent checkouts.
2. Treat `.codex/codex-spine.toml` as evidence of in-tree adoption and a matching external overlay entry as evidence of local-overlay adoption. Filename overlap alone proves nothing.
3. Classify the posture before proposing or applying changes.

Postures:
- repo-native-only: preserve native structure; add no continuity overlay
- local-overlay: keep the repo clean and place continuity/index declarations only in an explicitly authorized external overlay
- in-tree-adoption: add the smallest repo-local continuity contract because the repo is intentionally managed under it

Apply mode:
- In discovery-only mode, report findings and stop without writes or refreshes.
- In apply-safe-changes mode, write only inside the allowed roots and only after the posture is established.
- If an external overlay or index refresh is needed but not authorized, report the exact target and stop.
- If the checkout is dirty, shared, or unsafe to isolate, remain read-only unless the supplied authority explicitly covers that state.

Verification:
- run the lightest existing check that exercises the changed contract
- refresh only explicitly authorized index targets
- report missing runtime or authority as not_proven or blocked instead of substituting weaker evidence

Stop when:
- ownership or posture remains ambiguous
- a public/native contract would be overwritten
- the next action requires an unapproved external write, index refresh, Git mutation, destructive action, or scope expansion

Return:
- findings and evidence
- chosen posture
- changes made, if any
- write roots and isolation path used
- verification result
- deferred or blocked actions with the authority needed
- reload or restart impact
```

## Low-Risk Discovery

When available, gather the initial repo facts with:

```bash
python3 scripts/repo-adoption-audit.py --json <repo-root>
```

Use the result as evidence, not as permission to adopt or write. For unfamiliar or externally owned repos, run `discovery-only` first.
