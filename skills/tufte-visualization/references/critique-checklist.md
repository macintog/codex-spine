# Visualization Critique Checklist

Use this checklist when reviewing an existing visualization or doing final QA before delivery.

## Reading Situation And House Style

- Is the audience, medium, final size, viewing distance, and interaction model
  known well enough to judge the artifact?
- Does the design preserve the host publication or product's established visual
  system where it remains truthful and accessible?
- Was the genre selected from the use and medium, or inferred mechanically from
  words such as "Tufte," "dashboard," or "scientific"?

## Truth And Integrity

- Are visual differences proportional to data differences?
- Are scales, transformations, filters, and smoothing disclosed?
- Is uncertainty shown or explained when inference is involved?
- Is the interval, distribution, sample, forecast, or model quantity named
  rather than represented by generic error bars?
- Are missing values or discontinuities visible?
- Are denominators and units explicit?
- Would a skeptical reader know where the data came from?
- Is the time window analytically justified rather than cherry-picked?
- Are selected examples, top-N filters, and excluded groups declared?

## Analytical Usefulness

- Does the chart answer a real thinking task?
- Is the key comparison immediate?
- Is there one dominant comparison with supporting evidence, rather than many
  equally weighted claims?
- Is the chart sorted, aligned, indexed, or faceted to reveal the comparison?
- Are exact values available where needed?
- Are annotations attached to evidence rather than floating as decoration?
- Is the unit of analysis clear?
- Is the default view complete enough without interaction?

## Visual Economy

- Can any gridline, border, legend, tick, decimal, color, icon, background, or label be removed without loss?
- Has necessary context been over-erased?
- Are data marks stronger than scaffolding?
- Are labels direct and close to the data?
- Does the display have enough data density to reward attention?
- Does color encode meaning rather than mood?

## Anti-Reflex Taste

- Could the typography, palette, and layout have been selected before the
  evidence was inspected?
- Does the artifact perform a stock "Tufte" or editorial lane through cream
  paper, prestige serif, tiny mono labels, hairline rules, marginalia, or a
  muted accent without an analytical or house-style reason?
- Is distinctiveness coming from evidence structure and comparison rather than
  novelty, brand theater, or decorative strangeness?
- Are boxes, cards, arrows, and panel boundaries carrying information, or merely
  making the artifact look designed?

## Craft

- Is typography consistent and calm?
- Are labels collision-free at final size?
- Do arrows, connectors, callouts, brackets, and leader lines attach to the intended evidence without overlaps, near-misses, or inherited styles that change meaning?
- Are margins adequate?
- Are small multiples aligned and scaled consistently?
- Were materially different print, desktop, mobile, or presentation outputs
  recomposed and inspected as sibling evidence displays?
- For multi-panel or long-scrolling artifacts, has each panel or viewport section been inspected at final size?
- Is the output format appropriate: vector for publication, high-resolution raster only when needed?
- Are titles specific and factual?
- Are source notes and caveats close enough to the figure?

### Connector And Bounded-Text Geometry

- Reserve whitespace channels for curves, arrows, spokes, leaders, brackets, and rules. They must not cross text, labels, unrelated boundaries, panel rules, table cells, or non-target marks.
- Leave a visible air gap between connector endpoints or arrowheads and bounded marks. Marker geometry extends past mathematical path endpoints.
- Inspect native-resolution crops around connector-label, connector-boundary, and connector-crossing relationships. One collision triggers inspection of every similar connector class.
- Prove the longest bounded label fits inside a conservative safe zone. SVG and canvas text do not wrap automatically; move dense identifiers or file paths to external notes when needed.
- Repair contact by shortening, offsetting, rerouting, using detached leaders or brackets, externalizing labels, replacing arrows with ordered labels, or removing the connector.
- Re-render and re-inspect the same close-up after every repair. Source validity, z-order, white masks, or technical legibility do not override a visible defect.

## Accessibility

- Is meaning preserved without color?
- Is contrast sufficient?
- Is there alt text or a textual summary when needed?
- Are labels readable at actual display size?
- Are interactive controls keyboard-accessible with visible focus states?
- Does motion have a static equivalent or pause/stop control when practical?
- Is the core evidence visible before animation or interaction?
- Does an adjacent text equivalent preserve the central comparison, key values,
  exceptions, uncertainty, and source?

## Common Failure Modes

- Minimalist charts that erase units, context, uncertainty, and comparison.
- Beautiful dashboards that are low-information status theater.
- Dense charts that are cluttered rather than rich.
- Fancy chart types chosen for novelty.
- Legends, filters, and hover states that make the reader assemble the evidence manually.
- Causal arrows without causal evidence.
- Diagram connectors that miss their targets, inherit unintended arrowheads or emphasis, or make spacing imply a relationship the evidence does not support.
- Red/yellow/green indicators that replace analysis with mood.
- Overconfident annotations on noisy or cherry-picked data.
- Default software settings accepted without editing.
- Faux-book styling used as a substitute for evidence design.
- Desktop figures mechanically shrunk until labels, notes, or uncertainty
  disappear on smaller outputs.

## Final Standard

A finished evidence display should let a thoughtful reader see what was
measured, compare what matters, understand uncertainty and why the comparison
is credible, notice exceptions, recover exact values where needed, and trust
that neither the styling nor the interaction has exaggerated or concealed the
evidence.
