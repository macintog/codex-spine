---
name: tufte-visualization
description: Use as an evidence-design overlay to create, revise, or critique charts, dashboards, analytical figures, visual tables, maps, KPI displays, evidence-rich diagrams, and decision-grade reports. Governs truthful comparison, uncertainty, documentation, restraint, accessibility, and rendered QA while medium-specific skills own implementation mechanics. Do not use for generic frontend or marketing design, decorative graphics, analysis without visual output, or diagrams without an evidentiary claim.
---

# Tufte Visualization

Design evidence displays that let readers compare, question, and verify. Preserve
resolution and useful context; remove competing decoration. Derive principles,
not a stock Tufte appearance. Do not copy protected book pages, proprietary
examples, or another designer's finished visual artifact.

## Invariants

- **EV-01 Metric contract**: Preserve the material metric definition, unit,
  grain, population, numerator, denominator, and time window.
- **EV-02 Named comparison**: Name the comparator, its validity, and the
  conclusion it can support.
- **EV-03 Magnitude**: When base effects matter, show base values and absolute
  as well as relative change. Distinguish percent from percentage-point change
  and statistical detectability from practical or decision significance.
- **EV-04 Evidence status**: Distinguish observed, estimated, modeled,
  forecast, scenario, imputed, and causally identified quantities.
- **EV-05 Qualification**: Preserve material uncertainty, missingness,
  selection, exclusions, sensitivity, freshness, and partial or provisional periods.
- **EV-06 Default-view integrity**: Keep interpretation-critical evidence out
  of hover-only, narration-only, or export-excluded states.
- **QA-01 Final artifact**: Inspect the exact artifact at delivery size.
- **QA-02 Required states**: Inspect every required viewport, analytical state,
  sibling composition, and export.
- **QA-03 Repair loop**: Re-render and re-inspect after every visible-defect repair.
- **QA-04 Equivalent state**: Verify captions, text equivalents, copied links,
  screenshots, and static exports against the same analytical state.
- **STOP-01 Causality**: Do not imply unsupported causality.
- **STOP-02 Comparability**: Do not encode incompatible definitions,
  populations, periods, denominators, units, or aggregation levels as comparable.
- **STOP-03 Completion grade**: Claim only a grade whose gates were demonstrated.

## Frame And Route

For a non-trivial display, record this compact contract before implementation.
It may stay internal for routine work; include it in decision-grade and
publication-grade handoffs.

```text
Mode: exploratory | explanatory | operational | reference
Reader: audience, distance, conditions, reading time, decision or action
One-sentence claim/question; unit of analysis: what each row, mark, interval, area, or node means
Metric: definition, unit, numerator, denominator, population, grain, time window
Comparison: comparator, validity, supported conclusion; base/absolute/relative magnitude, consequential threshold
Scale: baseline, domain, indexing, normalization, smoothing, aggregation
Evidence: observed | estimated | modeled | forecast | scenario | imputed; uncertainty, exclusions, gaps, sensitivity, missingness
State: filters, vintage, update lag, partial or provisional periods
Delivery: medium, dimensions, viewports, interaction states, static fallback
Verification: data checks, rendered inspections, accessibility, text equivalent
```

Choose mode independently of genre. **Exploratory** work reveals alternatives
with a neutral question or metric title. **Explanatory** work foregrounds one
supported conclusion with a proportional claim title and focused annotation.
**Operational** work supports repeated scanning and action, showing state,
freshness, comparator, target, and data quality. **Reference** work favors
lookup, completeness, stable ordering, and durable documentation.

Inspect the host publication or product; preserve its typography, palette,
and chart grammar unless truth, comparison, legibility, or accessibility
requires a change. Choose genre and finish bar—academic plate, technical
atlas, operational monitor, presentation figure, or interactive analytical
view—from audience, medium, final size, viewing distance, and interaction.
Read `references/principles.md` when selecting a new genre or when host
conventions and these rules do not settle composition, type, color, table,
dashboard, map, or annotation choices. A routine chart within settled host
conventions does not need that deeper reference.

Before drawing, audit sources, column meanings, definitions, units, dates,
denominators, filters, missing values, duplicates, outliers, joins, and
transformations. Distinguish counts, rates, percentages, percentage points,
indexes, ranks, residuals, estimates, predictions, and modeled values.
Do not fabricate production data. If unavailable, specify the needed schema
and comparison architecture; use clearly labeled synthetic data only when
the user explicitly requests a mockup.

Load only the references the task invokes:

| Task condition | Reference and purpose |
| --- | --- |
| Comparing values, groups, periods, rankings, targets, scenarios, or cohorts | `references/comparison-integrity.md`: validity, magnitude, timing, aggregation, freshness, active state, stop conditions |
| Choosing or replacing chart form | `references/chart-selection.md`: architecture and data sufficiency |
| Estimates, samples, models, forecasts, rankings, causal claims, sensitivity, or material measurement error | `references/uncertainty.md`: quantity and qualification |
| Connectors, bounded nodes, causal or system maps, technical atlases, networks, or flows | `references/evidence-diagrams.md`: semantics, geometry, native-resolution proof |
| Reviewing an existing display or final rendered QA | `references/critique-checklist.md`: inspection and finding severity |
| Public, interactive, or durable artifact | `references/accessibility.md`: medium, semantics, interaction, responsive and exported proof |
| Final artifact, caption, documentation note, or text equivalent | `references/captions-alt-text.md`: visible and accessible explanation |
| Public source or provenance map | `references/citations.md`: attribution and further reading |

## Create Or Revise

Choose the comparison architecture after the evidence audit. Use the fewest
encodings that answer the question; prefer position and length to area,
volume, angle, or metaphor. If form is ambiguous or stakes are high, compare
materially different sketches for what each reveals, hides, and makes the
reader decode. Use a table for exact lookup, mixed units, or many values; use
prose or a few numbers when a visual would add no evidence.

Visual magnitude must track data magnitude. Bars and other length encodings
need a zero baseline. Compare magnitudes on common scales; when panels use
independent scales, label them and avoid cross-panel magnitude claims. A
non-zero line-chart range is valid when variation is the question, but disclose
it and avoid sensational framing.

Build data marks, scales and units, references, direct labels or a compact
key, uncertainty, annotation, documentation, title, then polish. Keep marks
stronger than scaffolding. Define color roles—ink, context, focus,
uncertainty, exception, interaction state—before hues; use color to encode,
distinguish, or emphasize, never as the sole carrier of meaning. Use position,
measure, spacing, annotation, and rule weight before ornamental boxes or
shadows. Direct labels are useful when they reduce decoding; a compact legend
is better when direct labels collide.

Avoid styling that could have been chosen from the word “Tufte” before seeing
the evidence: cream paper, prestige serif, hairline rules, marginalia, tiny
mono labels, and muted accents require a medium, house-style, or analytical
reason. Novelty, maximalism, brand theater, card grids, and generic
box-and-arrow posters likewise do not replace precise comparison. Prefer
alignment, grouping, sequence, brackets, small multiples, or direct annotation
when they convey the relationship.

For materially different print, desktop, mobile, or presentation constraints,
recompose sibling displays instead of shrinking one layout; preserve claim,
comparison, units, uncertainty, documentation, and analytical state. An
interactive default must be intelligible before motion or disclosure, with
reduced-motion and static paths. Never gate evidence on animation.

## Disclose And Verify

Keep the default view complete without putting the whole audit trail on marks:

1. **Visible evidence**: claim or question, units and scale, comparator,
   material denominator, active state, and consequential uncertainty or gaps.
2. **Adjacent caption or note**: source and vintage, metric definition,
   consequential filters or exclusions, interval definition, and caveats.
3. **Recoverable audit trail**: lineage, query or notebook, transformations or
   commit, methods, sensitivity, and accessible table or long description.

Layers 1–2 must not be hover-only or disappear from export; layer 3 may be
linked or disclosed if durable and discoverable. Keep captions and text
equivalents synchronized with filters, cohort, denominator, scenario,
freshness, exceptions, and missingness. Interaction, copied links, screenshots,
responsive siblings, and static exports must preserve the interpretation.

Render or export the exact deliverable at final size. Apply the critique
checklist; inspect pixels or pages, required interactive states, every sibling
composition, and each section of long or multi-panel artifacts. Check scale,
units, state, missing intervals, uncertainty, contrast, reading and focus
order, clipping, overflow, label collisions, panel consistency,
documentation placement, and text-equivalent parity. For diagrams, inspect
native-resolution connector crops using `references/evidence-diagrams.md`.
Visible defects block completion: repair, re-render, and re-inspect the same
mark class. If rendering is impossible, state the limitation, do the best
static check, and do not claim reviewed, decision-grade, or publication-grade.

## Authority, Stops, And Grades

Resolve conflicts in this order: (1) truth and non-deception; (2)
accessibility and actual-size legibility; (3) reader task and named comparison;
(4) evidence completeness and auditability; (5) host conventions and brand;
(6) aesthetics and convenience. Medium-specific skills own implementation,
runtime, integration, and format-specific validation; this skill owns
comparison, magnitude, scale meaning, evidence hierarchy, qualification,
visible state, and documentation. Geometry may change; those semantics may not.

Stop or reframe when a common scale would conceal an invalid comparison, or
the display cannot preserve comparison, uncertainty, documentation, state, or
legibility. Do not connect missing intervals or present excluded groups,
selected examples, partial periods, or top-N subsets as the whole. Arrows,
sequence, fitted lines, color, and annotation must not imply unsupported
causality.

Use the highest demonstrated grade:

| Grade | Required evidence |
| --- | --- |
| **Provisional** | Identified source and question; unknowns visibly labeled; no completeness claim. |
| **Reviewed** | Complete metric/comparison contract, checked computation, justified form, final-size rendered inspection. |
| **Decision-grade** | Reviewed plus denominators, material uncertainty or sensitivity, provenance, vintage, visible active state, accessible text equivalent, reproducible query or specification. |
| **Publication-grade** | Decision-grade plus editorial and citation review, every target size and export inspected, format-specific accessibility verified, no unresolved visible defects. |

Polish, source quality, and successful export alone establish no grade.

## Handoff

For creation or revision, return the artifact path or exact changed file,
comparison architecture and rationale, material data or interpretation caveat,
and the sizes, viewports, pages, and states actually inspected. For
decision-grade or publication-grade work, also return the full Evidence
Display Contract, grade evidence, semantic color roles, accessibility proof,
and verification manifest.

For critique, lead with highest-consequence findings: **blocker** for
materially false, misleading, or unsupported claims; **major** for impaired
comparison, interpretation, accessibility, or auditability; **minor** for
craft defects that do not change the conclusion. Do not narrate every
checklist item.
