# Unseen Repository Adoption Procedure

Use this procedure when continuity ownership is unknown, stale, or mixed. Start from `undetermined`; location and familiar filenames are not proof of adoption.

## Inputs And Authority

- Repository or workspace root
- Mode: `discovery-only` or `apply-safe-changes`
- Allowed write roots, with the target root as the narrow default
- Named public, exported, external-overlay, and index surfaces

`discovery-only` is read-only. `apply-safe-changes` permits scoped writes only after posture and ownership are proven. External overlays, index creation or refresh, remotes, Git publication, destructive actions, and wider write roots require explicit authority for the exact target.

## Procedure

1. Read the applicable `AGENTS.md` and `AGENTS.override.md` chain for the current working directory and the native project entrypoint. Follow contributor, release, packaging, architecture, or operational references only when they establish ownership, an affected contract, or a claim needed for this adoption.
2. Inspect repository shape, Git posture, ownership declarations, and existing continuity. Follow generated, runtime, dataset, publication, or adjacent-checkout surfaces when they affect the selected scope; do not turn adoption into an unrelated repository audit.
3. Treat environment-specific declarations as evidence only when the installed environment defines their schema and ownership meaning. Filename overlap alone proves nothing.
4. Classify the smallest truthful posture:
   - `repo-native-only`: preserve native structure and add no continuity overlay.
   - `local-overlay`: keep the repository clean; create or change an external declaration only when that exact write is authorized.
   - `repo-local`: add or repair the smallest in-tree continuity contract because this scope is intentionally managed under it.

Treat `in-tree-adoption` as a deprecated read alias for `repo-local` and `repo-native only` as a deprecated read alias for `repo-native-only`. Never write the deprecated forms back.
5. In `discovery-only`, report the classification and stop. In `apply-safe-changes`, preserve native guidance, merge applicable agent rules, and write only inside allowed roots.
6. Run the lightest declared check that exercises the changed contract. Use the installed `codex-continuity inspect --repo <root> --json` front door when available; otherwise use this skill's `scripts/audit-continuity.py --root <root> --json` for structural packet checks or another explicitly declared adoption auditor. Do not search for or invent `scripts/repo-adoption-audit.py`. Report absent resolver or project-contract coverage separately from a structural pass; neither the auditor's inferred posture nor matching filenames proves intentional ownership.
7. Report evidence, chosen posture, files inspected and changed, write roots and isolation used, verification, unresolved conflicts, and reload or restart impact.

## External Checkpoint Adoption

External checkpoint adoption is a separate selected migration, not an automatic consequence of creating a repo-local packet. Do it only after the installed resolver, coordinator writer, QMD/bootstrap integration, index exclusion, auditor, and adversarial fixtures pass together. Reuse applicable proof for the installed version; exercise changed consumers and target-specific cutover rather than rerunning unrelated runtime qualification. Do not invent a remote or registration when the target lacks a supported identity.

1. Freeze legacy checkpoint writers and identify every reader, renderer, release generator, and retrieval projection.
2. Move durable facts to their owning authority. Seed the strict JSON board model with only verified live coordination.
3. Run `codex-project-checkpoint adopt --repo <root> --remote <private-remote> --file <model.json> --json`. The command writes and fsyncs the external board first, atomically installs the Git-common-dir registration second, then replaces the tracked root file with the permanent discovery stub.
4. Treat registration installation as cutover. Registration wins on every linked worktree and on branches predating the stub; old tracked checkpoint prose is ignored. A stub without registration is an identity error.
5. Update board state only through `codex-project-checkpoint update --repo <root> --expected-generation <n> --file <model.json>`. Read the latest board before composing the model, preserve other active owners' entries, and reconcile a generation conflict against that new read. The shipped model is a seed for adoption, not a replacement for an existing board. A stale generation fails without overwriting. Ordinary workers never write; the designated yeet worker may coordinate its selected delivery through this CLI.
6. Never fall back from an adopted `missing`, `unreadable`, `identity_mismatch`, or `corrupt` state to tracked prose, recovery files, QMD projections, or another clone. Recovery is explicit repair evidence only.
7. Rollback reverses consumers and the tracked stub first and removes the common-dir registration last. Never auto-rollback because current state is unavailable.

## Stop Conditions

Pause affected writes when:

- ownership or posture remains ambiguous
- a native or public contract would be overwritten
- the checkout or workspace cannot be safely isolated under its declared policy
- the next action requires an unauthorized external write, index refresh, Git mutation, destructive action, or scope expansion
- a write depends on a handoff claim that current evidence cannot reconcile

Preserve unreconciled claims as attributed uncertainty. Continue independent authorized repairs that do not assume the missing decision. Report missing runtime or authority as `not_proven` or `blocked`; do not substitute weaker evidence.
