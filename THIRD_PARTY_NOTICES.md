# Third-Party Notices

The repository's MIT license covers `codex-spine`'s repo-owned code and
documentation. It does not relicense upstream tools that the installer obtains,
or source works that informed repo-owned guidance. This file distinguishes
managed upstream tools, redistributed adaptations, and reference-only sources.

## Managed upstream tools

### @tobi/qmd

- Project: https://github.com/tobi/qmd
- Managed package: `@tobilu/qmd`
- License: https://github.com/tobi/qmd/blob/main/LICENSE
- License classification: MIT
- Copyright: Copyright (c) 2024-2026 Tobi Lutke

`codex-spine` installs and invokes the upstream package. It does not vendor or
fork QMD. The transcript projection, Codex-facing wrappers, bounded memory MCP
adapter, configuration, and operator flow in this repository are repo-owned
integration work.

### Optional jGravelle Munch MCP suite

- jCodeMunch project: https://github.com/jgravelle/jcodemunch-mcp
- jCodeMunch license: https://github.com/jgravelle/jcodemunch-mcp/blob/main/LICENSE
- jDocMunch project: https://github.com/jgravelle/jdocmunch-mcp
- jDocMunch license: https://github.com/jgravelle/jdocmunch-mcp/blob/master/LICENSE
- jDataMunch project: https://github.com/jgravelle/jdatamunch-mcp
- jDataMunch license: https://github.com/jgravelle/jdatamunch-mcp/blob/master/LICENSE
- Copyright holder identified by the licenses: J. Gravelle

These packages use separate dual-use licenses. Their upstream terms permit
non-commercial use without charge and require a paid license for commercial
use. Each upstream `LICENSE` file controls its package.

The suite is optional and is not covered by the repository's MIT license.
`codex-spine` does not vendor, modify, rename, rebrand, or redistribute the
package source. When you opt in, the installer shows the current upstream terms,
requires one explicit `accept`, and configures compatible upstream releases
through `uv`.

## Adapted skill guidance

## Cursor pstack

- Project repository: https://github.com/cursor/plugins
- Pinned pstack project: https://github.com/cursor/plugins/tree/60c641e4fad674784b30abcf9f8915dea39df38d/pstack
- License: https://github.com/cursor/plugins/blob/60c641e4fad674784b30abcf9f8915dea39df38d/pstack/LICENSE
- Copyright: Copyright (c) 2026 Lauren Tan
- Public derivatives:
  - `skills/change-impact`, adapted from `pstack/skills/blast-radius/SKILL.md`
  - `skills/causal-explanation`, adapted from
    `pstack/skills/why/SKILL.md` and `pstack/skills/how/SKILL.md`

The full pstack MIT notice is retained in each listed skill's `LICENSE.txt`.

## Matt Pocock skills

- Project: https://github.com/mattpocock/skills
- Pinned project: https://github.com/mattpocock/skills/tree/885e2ca4d842d139e9aef4e48d366c63cb1b8013
- License: https://github.com/mattpocock/skills/blob/885e2ca4d842d139e9aef4e48d366c63cb1b8013/LICENSE
- Copyright: Copyright (c) 2026 Matt Pocock
- Public derivatives:
  - `skills/skill-authoring-quality`, adapted from
    `skills/productivity/writing-for-agents/SKILL.md` and
    `skills/productivity/writing-for-agents/SKILL-MECHANICS.md`
  - `skills/improve-codebase-architecture`, adapted from
    `skills/engineering/improve-codebase-architecture/SKILL.md`,
    `skills/engineering/domain-modeling/SKILL.md`, and
    `skills/engineering/codebase-design/{SKILL.md,DEEPENING.md,DESIGN-IT-TWICE.md}`

The full Matt Pocock MIT notice is retained in each listed skill's
`LICENSE.txt`.

## Reference-based visualization guidance

### Tufte visualization

`skills/tufte-visualization` is repo-owned synthesis, not a copied or adapted
Tufte packet. Edward Tufte's books and public essays inform its evidence-design
principles; the skill does not reproduce protected book pages, proprietary
examples, or finished visual artifacts. Its complete source map also records
the graphical-perception, accessibility, and statistical references it uses;
see the skill's
[source map](skills/tufte-visualization/references/citations.md).

The name describes the skill's intellectual influence. It does not imply
affiliation with or endorsement by Edward Tufte or Graphics Press.
