# Visualization Critique Checklist

Use for an existing display or final rendered QA. Apply the skill's invariants,
stop rules, and grade gates; inspect the delivered artifact, not only source.

## Reading Situation

- Is audience, medium, final size, viewing distance, and interaction known?
- Does the design respect host conventions where truthful and accessible?
- Was genre chosen for the evidence and medium rather than the words “Tufte,”
  “dashboard,” or “scientific”?

## Truth And Analytical Use

- Are visual differences proportional to data differences? Disclose scales,
  transformations, filters, smoothing, and justified time window.
- Are definitions, populations, denominators, units, periods, aggregation, and
  weighting comparable? Label percent versus percentage-point change; show
  bases and absolute deltas when relative change distorts magnitude.
- Are intervals, distributions, sample, forecast, or model quantities named?
  Are uncertainty, missing values, discontinuities, complete versus partial
  periods, freshness, timezone, and observation maturity visible when material?
- Declare top-N, examples, selected or excluded groups; can a skeptical reader
  find source and vintage? Are annotations attached to evidence and supported,
  including causal claims?
- Does the display answer a thinking task, with one immediate dominant
  comparison and supporting evidence? Are sorting, alignment, indexing, or
  facets doing useful work? Is the unit of analysis clear, and are exact values
  available where needed?
- Is the default complete without interaction? Do title, caption, text
  equivalent, and exported or responsive siblings match active filters, date
  range, cohort, denominator, scenario, freshness, caveats, and adjacent
  documentation?

## Economy, Taste, And Craft

- Remove any gridline, border, legend, tick, decimal, color, icon, background,
  or label that adds no meaning, but retain necessary context and enough data
  density to reward attention. Keep marks stronger than scaffolding and labels
  near evidence.
- Does color encode meaning rather than mood? Could type, palette, and layout
  have been chosen before inspecting evidence? Cream paper, prestige serif,
  tiny mono, hairlines, marginalia, muted accents, novelty, brand theater,
  cards, and generic arrows require an analytical or house-style reason.
- Check typography, margins, factual titles, label collisions, aligned and
  consistently scaled multiples, and nearby source notes and caveats at final
  size. Inspect each panel or viewport section of long artifacts.
- Recompose materially different print, desktop, mobile, and presentation
  outputs. Choose vector for publication or high-resolution raster when
  needed; do not mechanically shrink away labels, notes, or uncertainty.
- For diagrams, apply `evidence-diagrams.md` to connector semantics,
  attachment, bounded text, and native-resolution crops. Check unintended
  arrowheads, missed targets, and spacing that falsely implies a relationship.

## Accessibility And Failure Patterns

- Is meaning preserved without color, with sufficient contrast and readable
  actual-size labels? Is alt text or a textual summary present when needed?
  Does an adjacent equivalent preserve comparison, key values, exceptions,
  uncertainty, and source?
- Can keyboard users reach interactive controls with visible focus? Does
  pointer-only detail have an equivalent? Is the core evidence visible before
  animation, with static or pause/stop access when practical?
- Watch for erased context masquerading as minimalism; low-information
  dashboards; dense clutter; novelty forms; legends, filters, or hover that
  force readers to assemble the evidence; status colors replacing analysis;
  noisy or cherry-picked annotations; default software settings; faux-book
  styling; and unsupported causal arrows.

## Closeout

Match the claimed completion grade to demonstrated computation, form,
final-size rendering, provenance, vintage, reproducibility, active state,
uncertainty or sensitivity, synchronized text equivalent, and—at publication
grade—editorial/citation, every target/export, and format-specific accessibility
checks. A finished display lets readers recover what was measured, compare
what matters, understand uncertainty and exceptions, find exact values where
needed, and see why the interpretation is credible.
