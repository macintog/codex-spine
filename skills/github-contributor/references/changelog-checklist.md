# Changelog Checklist

Use this when a project has real public releases, external consumers, or a public version history that people will need to reason about later.

The goal is a changelog that helps users and maintainers answer:

- what changed
- whether they need to care
- whether they need to migrate
- whether compatibility or security posture changed

## When It Is Required

Treat `CHANGELOG.md` as required when any of these are true:

- the project has public tagged releases
- users outside the maintainer circle consume versioned updates
- compatibility, migration, or upgrade timing matters
- the project is moving toward a stable public interface and version history will affect trust

Do not create a ceremonial changelog for a private incubator that is not yet shipping meaningful public releases.

## What To Record

Record notable user-visible changes, not every internal edit.

High-signal categories:

- new capabilities
- breaking changes
- migration notes
- security-relevant fixes or hardening
- performance changes that materially affect user experience or cost
- deprecations, removals, or stability milestones

Low-signal items usually do not belong unless they materially affect users:

- internal refactors
- formatting-only changes
- test-only churn
- purely local maintenance
- doc edits with no change to user understanding or behavior

## Entry Shape

Each release entry should make it easy to scan.

Recommended structure:

1. version and date
2. short release summary
3. highlights or notable changes
4. breaking changes or migration notes when applicable
5. security or compatibility notes when applicable

## Style Rules

- Optimize for human readers, not commit mirroring.
- Prefer grouped themes over raw PR lists.
- State breaking changes explicitly and early.
- Name migrations concretely.
- Call out stability milestones when interfaces become supported or frozen.
- Keep entries concise but decision-useful.

## Maintenance Rules

- Update the changelog before or as part of a public release, not weeks later.
- Treat changelog updates as part of release readiness, not optional polish.
- If a release includes a behavior change that would surprise existing users, the changelog is incomplete until that surprise is documented.
- If there is no public release yet, track proposed notable changes elsewhere until the public changelog becomes real.

## Anti-Patterns

- copying commit history into markdown
- burying breaking changes in feature bullets
- recording internal churn instead of user-visible change
- creating a changelog and then letting it go stale
- backfilling history so late that dates and scope are no longer trustworthy
