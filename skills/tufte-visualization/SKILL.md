---
name: tufte-visualization
description: Use as an evidence-design overlay to create, revise, or critique charts, dashboards, analytical figures, visual tables, maps, KPI displays, evidence-rich diagrams, and decision-grade reports. Governs truthful comparison, uncertainty, documentation, restraint, accessibility, and rendered QA while medium-specific skills own implementation mechanics. Do not use for generic frontend or marketing design, decorative graphics, analysis without visual output, or diagrams without an evidentiary claim.
---

# Tufte Visualization

Design evidence displays that help a capable reader compare, question, verify,
and think. Preserve data resolution and useful context; remove decoration that
competes with them. This is a Tufte-inspired reasoning standard, not a recipe
for imitating a recognizable Tufte aesthetic.

Derive principles. Do not copy protected book pages, proprietary examples, or
another designer's finished visual artifact.

## Evidence Contract

- Show what was measured. Preserve metric definitions, units, grain,
  denominators, time windows, source context, missingness, and transformations.
- Support a named comparison. Use position on common scales, meaningful order,
  direct labels, small multiples, and visual tables before novelty.
- Make uncertainty proportional to the claim. Distinguish observation,
  estimate, model output, forecast, and causal inference.
- Integrate words, numbers, and graphics. Put definitions, annotations, source
  notes, and caveats beside the evidence they qualify.
- Increase information density without flattening hierarchy. Give each figure
  one dominant comparison, then retain the detail needed to audit it.
- Keep the default view complete. Do not hide essential labels, units, caveats,
  denominators, or sources in hover, filters, legends, or presenter narration.
- Prove the rendered result. Source validity and successful export are inputs to
  QA, not substitutes for inspecting the final artifact.

## Workflow

### 1. Frame The Reading Situation

- Name the question, comparison, or decision the display must support.
- Identify the unit of analysis: what one point, row, line, area, or node means.
- Record the audience, medium, final dimensions, viewing distance, ambient
  conditions, interaction model, and expected reading time when they matter.
- Inspect the host publication, product, or report. Preserve its established
  typography, palette, and chart conventions unless they compromise integrity,
  comparison, legibility, or accessibility.
- Select a visual genre and finish bar: academic plate, technical atlas,
  operational monitor, presentation figure, or interactive analytical view.
  The medium and use decide the genre; the word "Tufte" does not.

### 2. Audit The Evidence

- Check source, column meanings, category definitions, units, date range,
  denominators, filters, missing values, duplicates, outliers, joins, and
  transformations before drawing.
- Distinguish counts, rates, percentages, indexed values, ranks, residuals,
  estimates, predictions, and modeled values.
- Decide what sample size, uncertainty, sensitivity, exclusions, or imputation
  must remain visible. Read `references/uncertainty.md` for inferential or
  decision-grade claims.
- Do not fabricate production data. If data is unavailable, provide the needed
  schema and comparison architecture; use clearly labeled synthetic data only
  when the user explicitly asks for a mockup.

### 3. Choose The Comparison Architecture

- Read `references/chart-selection.md` when selecting a chart form or replacing
  a weak one.
- Use the smallest set of encodings that answers the thinking task. Prefer
  position and length over area, volume, angle, or decorative metaphor.
- When the form is ambiguous or the stakes are high, sketch two or three
  materially different comparison architectures before styling. Compare what
  each reveals, hides, and asks the reader to decode.
- Choose a table when exact lookup, mixed units, or many values matter more than
  shape. Choose no visualization when prose or a few numbers answer the task
  more honestly.

### 4. Compose From Evidence Outward

Build in this order: data marks, scales and units, reference values, direct
labels, uncertainty, annotations, documentation note, title, then polish.

- Make data marks stronger than scaffolding.
- Define color roles before choosing hues: ink, context, focus, uncertainty,
  exception, and interaction state. Start with the fewest roles the evidence
  needs; add color only when it encodes, distinguishes, or emphasizes.
- Build hierarchy through position, scale, measure, spacing, annotation, and
  rule weight before boxes, shadows, or ornament.
- Treat compact marks, connector lanes, labels, and boundaries as occupied
  geometry. Reserve safe zones before drawing.
- Design print, desktop, mobile, and presentation outputs as sibling
  compositions when their constraints differ. Preserve the same comparison
  and documentation contract instead of mechanically shrinking one layout.
- For interactive views, make motion and disclosure enhance an already
  intelligible default. Provide a reduced-motion path and never gate evidence
  on animation completion.

### 5. Apply The Anti-Reflex Taste Check

- If typography, palette, or composition could have been chosen from the word
  "Tufte" before inspecting the evidence, restart the styling pass.
- Do not simulate seriousness with cream paper, prestige serif typography,
  hairline rules, marginalia, tiny mono labels, or a muted red accent by reflex.
  Use any of them only when the reading situation, host identity, and evidence
  structure earn them.
- Do not substitute novelty, strangeness, maximalism, or brand theater for
  analytical distinctiveness. A figure should be memorable because the
  evidence became unusually clear.
- Avoid card grids and generic box-and-arrow posters when alignment, grouping,
  sequence, brackets, small multiples, or direct annotation carry the
  relationship more precisely.
- Check the promised genre. A publication figure should not read as product UI;
  an operational monitor should not be forced into faux-book styling.

Read `references/principles.md` for the full taste and composition standard.

### 6. Verify The Rendered Artifact

Treat rendered QA as a hard gate.

- Render or export the exact deliverable at its intended size. Inspect pixels,
  pages, or required interactive states rather than only source or build output.
- Apply `references/critique-checklist.md` at final size. Inspect every panel,
  viewport, and repeated mark class, including native-resolution crops for
  compact labels, connectors, and boundaries.
- Check scales, units, missing intervals, uncertainty, contrast, reading order,
  clipping, overflow, label collisions, connector contact, small-multiple
  consistency, hover-only meaning, and source-note placement.
- A visible defect blocks completion. Repair it, re-render, and re-inspect the
  same mark class. Do not defend a defect with z-order, masks, source validity,
  or technical legibility.
- If rendered inspection is impossible, state that before presenting the
  artifact, perform the best available static check, and do not call the result
  publication-grade or complete.

## Genre Guidance

- **Academic plate**: Editorial evidence at reading distance. Use controlled
  typography, local annotation, quiet scaffolding, and enough detail to audit
  the claim. Serif type and off-white paper are options, not requirements.
- **Technical atlas**: Explain operation or structure with layered maps,
  cutaways, sequence strips, visual tables, and evidence-rich marginalia.
- **Operational monitor**: Optimize repeated scanning and decisions. Show
  current value, comparable prior, target or benchmark, trend, definition, and
  data-quality state without status theater.
- **Presentation figure**: Preserve one central comparison at viewing distance,
  with enough evidence to verify the statement title.
- **Interactive analytical view**: Support exploration while keeping the core
  comparison, labels, units, caveats, and source available without interaction.

## Coordination And Authority

This skill owns evidence design. Medium-specific skills own implementation
mechanics, runtime behavior, and format-specific validation.

- For web interfaces, frontend skills own layout, controls, responsive UI, and
  interaction polish. This skill retains authority over truthful encoding,
  default-view completeness, uncertainty, and evidence documentation.
- For analytical work, data skills own computation, statistical methods, and
  source retrieval. This skill must not invent or silently reinterpret their
  outputs.
- For spreadsheets, slides, documents, and PDFs, use the medium-native skill and
  inspect the rendered sheet, slide, or page.
- When brand guidance conflicts with evidence integrity or accessibility,
  integrity and accessibility win. Otherwise preserve the host identity rather
  than imposing a separate Tufte house style.

## Reference Map

- Read `references/principles.md` for taste, genre, composition, color, tables,
  dashboards, and anti-reflex guidance.
- Read `references/chart-selection.md` when choosing or redesigning the visual
  architecture.
- Read `references/uncertainty.md` for estimates, intervals, forecasts,
  sensitivity, missingness, and inferential claims.
- Read `references/critique-checklist.md` when reviewing an existing display or
  performing final rendered QA.
- Read `references/accessibility.md` for digital, interactive, responsive,
  print, and semantic-access requirements.
- Read `references/captions-alt-text.md` before delivering captions,
  documentation notes, alt text, or text equivalents.
- Read `references/citations.md` for the public source and provenance map.

## Stop Rules

- Do not imply causality with arrows, sequencing, fitted lines, color, or
  annotation unless the evidence supports a causal claim.
- Do not silently connect across missing intervals, hide excluded groups, or
  present selected examples or top-N subsets as the whole population.
- Do not call a display Tufte-like, accessible, decision-grade, or
  publication-grade because it is clean, muted, or source-grounded. The
  evidence, rendering, and medium-specific checks must support the claim.
- Stop and change the form when the chosen visual cannot preserve the required
  comparison, uncertainty, documentation, or legibility.

## Output Contract

When creating or revising a visualization, return:

- the artifact path or exact changed file
- the reading situation, audience, medium, and selected genre
- the data assumptions, units, filters, scale, and uncertainty treatment
- the comparison architecture and semantic color roles
- the rendered artifact, pages, dimensions, viewports, or states inspected
- any remaining caveat about source data, accessibility, or interpretation

When critiquing a visualization, lead with integrity and comprehension risks,
then give focused redesign moves in descending order of consequence.
