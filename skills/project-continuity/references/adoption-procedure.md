# Unseen Repository Adoption Procedure

Use this procedure when continuity ownership is unknown, stale, or mixed. Start from `undetermined`; location and familiar filenames are not proof of adoption.

## Inputs And Authority

- Repository or workspace root
- Mode: `discovery-only` or `apply-safe-changes`
- Allowed write roots, with the target root as the narrow default
- Named public, exported, external-overlay, and index surfaces

`discovery-only` is read-only. `apply-safe-changes` permits scoped writes only after posture and ownership are proven. External overlays, index creation or refresh, remotes, Git publication, destructive actions, and wider write roots require explicit authority for the exact target.

## Procedure

1. Read the applicable `AGENTS.md` and `AGENTS.override.md` chain for the current working directory plus native contributor, release, packaging, architecture, and operational guidance.
2. Inspect repository shape, Git posture, ownership declarations, existing continuity files, docs, volatile handoffs, generated areas, datasets, runtime assets, public surfaces, and adjacent checkouts.
3. Treat environment-specific declarations as evidence only when the installed environment defines their schema and ownership meaning. Filename overlap alone proves nothing.
4. Classify the smallest truthful posture:
   - `repo-native-only`: preserve native structure and add no continuity overlay.
   - `local-overlay`: keep the repository clean; create or change an external declaration only when that exact write is authorized.
   - `repo-local`: add or repair the smallest in-tree continuity contract because this scope is intentionally managed under it.

Treat `in-tree-adoption` as a deprecated read alias for `repo-local` and `repo-native only` as a deprecated read alias for `repo-native-only`. Never write the deprecated forms back.
5. In `discovery-only`, report the classification and stop. In `apply-safe-changes`, preserve native guidance, merge applicable agent rules, and write only inside allowed roots.
6. Run the lightest declared check that exercises the changed contract. If this skill's `scripts/audit-continuity.py` is available, use it for read-only packet checks. If the target repository or installed environment explicitly provides another adoption auditor, use only that declared command; do not search for or invent `scripts/repo-adoption-audit.py`.
7. Report evidence, chosen posture, files inspected and changed, write roots and isolation used, verification, unresolved conflicts, and reload or restart impact.

## Stop Conditions

Stop without writes when:

- ownership or posture remains ambiguous
- a native or public contract would be overwritten
- the checkout or workspace cannot be safely isolated under its declared policy
- the next action requires an unauthorized external write, index refresh, Git mutation, destructive action, or scope expansion
- current evidence conflicts with a handoff state anchor and cannot be reconciled

Report missing runtime or authority as `not_proven` or `blocked`; do not substitute weaker evidence.
