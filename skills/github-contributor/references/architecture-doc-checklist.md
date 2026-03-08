# Public Architecture Doc Checklist

Use this when a public project or shareable component is non-trivial enough that maintainers, contributors, or adopters would otherwise need to reverse-engineer the shape from source.

The goal is not exhaustive design prose. The goal is a compact technical map that makes the system legible.

## When To Create One

Create `ARCHITECTURE.md` or an equivalent deep reference doc when any of these are true:

- the project has multiple subsystems or packages
- the data flow is not obvious from the README
- security or trust boundaries matter
- stable identifiers, schemas, or response envelopes exist
- non-obvious algorithms or ranking logic materially affect behavior
- contributors would need to understand storage, caching, indexing, or background maintenance behavior

Do not promote it into the startup packet by default. Keep it as an on-demand deep reference.

## What Good Looks Like

The strongest examples explain the system by following the work through it. They do not just list files.

Recommended sections:

1. Purpose and scope
- What this document explains
- What it intentionally leaves to README, PROJECT_SPINE, or API-specific docs

2. Directory or subsystem structure
- Top-level layout
- Ownership or responsibility of each important package or directory
- Brief annotations for non-obvious modules

3. End-to-end data or control flow
- Input sources
- major processing stages
- post-processing or validation passes
- storage or output surfaces
- user-facing or API-facing entry points

4. Key abstractions and invariants
- registries, identifiers, schemas, envelopes, or contracts that must stay stable
- what must remain true across refactors

5. Security and trust boundaries
- secret handling
- path or file safety constraints
- sandbox, network, auth, or machine-boundary assumptions

6. Storage, caching, and update model
- what is persisted
- where it lives
- how change detection or incremental work happens
- what writes must be atomic or deterministic

7. Important behavior-defining algorithms
- scoring or ranking rules
- matching or selection logic
- fallback order
- retry or degradation behavior

8. External dependencies and why they exist
- important third-party packages, services, or runtimes
- what responsibility each one carries

## Style Rules

- Keep it factual, current, and implementation-oriented.
- Prefer concrete terminology over aspiration.
- Show relationships, not just inventory.
- If a diagram helps, keep it simple and consistent with the text.
- Link out to narrower specs instead of bloating the file.
- Update it when architectural reality changes, not just when features ship.

## Anti-Patterns

- repeating the README at greater length
- documenting planned architecture instead of actual architecture
- listing every file without explaining boundaries or flow
- omitting invariants, trust boundaries, or storage behavior when those drive maintenance risk
- letting the document drift until contributors stop trusting it
