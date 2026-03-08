# codex-spine Repo Rules

- Treat this repo as the public-facing product surface, not the private incubator.
- Use `skills/github-contributor` for any new managed component, public-facing integration, release prep, or upstreamability question.
- Classify new components up front in `COMPONENTS.toml` as `public-core`, `private-incubator`, or `local-only`; do not defer the boundary decision until release time.
- Keep `public-core` and `export_ready` separate. Structural public fitness does not imply that a change is ready to ship.
- Keep optional third-party components explicit in docs and runtime. Separate upstream terms, optionality, and non-affiliation should be obvious without reading the source.
- For non-trivial public surfaces, keep README, user guide, architecture, security, and changelog quality aligned with maintainer needs rather than only first-time install needs.
