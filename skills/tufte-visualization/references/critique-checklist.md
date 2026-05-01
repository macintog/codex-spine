# Visualization Critique Checklist

Use this checklist when reviewing an existing visualization or doing final QA before delivery.

## Truth And Integrity

- Are visual differences proportional to data differences?
- Are scales, transformations, filters, and smoothing disclosed?
- Is uncertainty shown or explained when inference is involved?
- Are missing values or discontinuities visible?
- Are denominators and units explicit?
- Would a skeptical reader know where the data came from?
- Is the time window analytically justified rather than cherry-picked?
- Are selected examples, top-N filters, and excluded groups declared?

## Analytical Usefulness

- Does the chart answer a real thinking task?
- Is the key comparison immediate?
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

## Craft

- Is typography consistent and calm?
- Are labels collision-free at final size?
- Do arrows, connectors, callouts, brackets, and leader lines attach to the intended evidence without overlaps, near-misses, or inherited styles that change meaning?
- Are margins adequate?
- Are small multiples aligned and scaled consistently?
- For multi-panel or long-scrolling artifacts, has each panel or viewport section been inspected at final size?
- Is the output format appropriate: vector for publication, high-resolution raster only when needed?
- Are titles specific and factual?
- Are source notes and caveats close enough to the figure?

## Accessibility

- Is meaning preserved without color?
- Is contrast sufficient?
- Is there alt text or a textual summary when needed?
- Are labels readable at actual display size?
- Are interactive controls keyboard-accessible with visible focus states?
- Does motion have a static equivalent or pause/stop control when practical?

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

## Final Standard

A finished evidence display should let a thoughtful reader see what was measured, compare what matters, understand why the comparison is credible, notice exceptions, recover exact values where needed, and trust that the design has not exaggerated or concealed the evidence.
