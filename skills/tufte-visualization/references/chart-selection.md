# Chart Selection And Redesign

Choose a comparison architecture, not a fashionable chart type. Prefer designs that let the eye compare positions along common scales.

## Contents

- Selection map and default redesign moves
- Time series, data sufficiency, slopegraphs, small multiples, and sparklines
- Scatterplots, distributions, estimates, and uncertainty
- Maps, network and causal diagrams, and responsive translation

## Selection Map

| Analytical task | Preferred architecture | Avoid by default |
| --- | --- | --- |
| Compare magnitudes across categories | Sorted dot plot, horizontal bar when zero baseline matters, table with in-cell bars; lollipop only when its stem carries useful baseline context | Pie or donut, radial chart, 3D bar, unsorted columns |
| Show change over time | Line chart for genuine continuity, sparkline table, indexed line, small multiples | Area chart when overlap hides values, undisclosed smoothing; horizon chart without dense-series need and reader familiarity |
| Compare two time points | Slopegraph, paired dot plot, before/after table | Grouped bars with heavy legend, arrows without values |
| Compare many groups over time | Small multiples with common scales, sparkline table | Spaghetti chart unless few series; tabs that hide comparisons |
| Show distribution | Dot or strip plot, histogram, box plot plus raw points | Mean-only bar chart, decorative violin without explanation |
| Show relationship | Scatterplot with direct labels for notable points; fitted line only when justified | Bubble chart unless area encoding is necessary and explained |
| Show estimates or uncertainty | Dot-and-interval plot, distribution plot, uncertainty band, quantile display, scenario small multiples | Unnamed error bars, mean-only bars, opacity as the sole uncertainty cue |
| Show composition | Small multiples of parts, simple stacked bars, part-to-whole table | Exploded pie, stacked area with many layers |
| Show geography | Map when geography explains the result; sorted table or dot plot otherwise | Choropleth for non-spatial ranking tasks |
| Monitor KPIs | Dense table with current value, prior value, target, trend, exceptions | Gauges, dials, traffic lights, giant numbers without context |
| Compare actual with target or benchmark | Dot with reference, bullet-like linear display, compact variance table | Gauge, unscaled status icon, target encoded only by color |
| Explain contribution to additive change | Reconciled waterfall, signed contribution bars, variance table | Waterfall when components do not reconcile to the total |
| Compare a cohort or two-dimensional matrix | Ordered heatmap with labels, matrix table, small multiples | Unordered color grid with no value lookup |
| Show ordered stage progression | Stage bars or stage table with explicit denominators | Funnel whose changing geometry obscures stage denominators |
| Show flow between states | Sankey or alluvial only for real direction and conserved quantity; transition table otherwise | Decorative ribbons, implied conservation, unsupported causal arrows |
| Show schedule, spans, or dependencies | Gantt, milestone timeline, or dependency view according to the question | Generic project boxes disconnected from time or dependency evidence |
| Explain causal structure | Annotated diagram with verb-labeled links and evidence notes | Generic arrows implying causality without evidence |

## Default Redesign Moves

- Pie or donut chart -> sorted dot plot, bar chart, or part-to-whole table.
- Gauge or dial -> KPI row with current value, target, prior value, and trend.
- 3D chart -> flat chart using position or length.
- Dual-axis chart -> small multiples, indexed lines, or one shared scale when valid.
- Stacked bars with many categories -> small multiples or grouped dot plots.
- Dense legend -> direct labels.
- Rainbow heat map -> perceptually ordered scale plus labels and thresholds.
- Decorative infographic -> evidence display with sourced data, units, and scale.
- Mean bar with error whiskers -> dot/interval plot or distribution plot.
- Crowded spaghetti plot -> small multiples or highlight/context line chart.

## Time Series

- Use lines for continuous time.
- Use dots or bars for discrete periods when individual observations matter.
- Label lines directly at endpoints when possible.
- Mark regime changes, measurement changes, missing gaps, and meaningful thresholds.
- Use small multiples when overlap, near-coincidence, or decoding burden makes
  the lines ambiguous. Series count alone is not a sufficient threshold.
- Consider indexing to a common baseline for relative change.

## Data Sufficiency And Continuity

- For two meaningful periods, prefer a paired dot plot, slopegraph, or table.
- For a handful of discrete periods, prefer dots, bars, or a table unless
  continuity is genuinely the question.
- If there are too few observations to reveal scatterplot structure, use a
  labeled dot plot, table, or prose.
- For sparse distributions, show raw points rather than a smooth density.
- If denominator, coverage, or observation maturity is inadequate, suppress or
  qualify the visual claim rather than inventing precision.
- A line is a continuity claim. Do not connect categories, incomplete periods,
  or isolated observations merely because the software defaults to a line.

## Slopegraphs

Use slopegraphs for two-point or few-point comparisons where the gradient is the message.

- Label endpoints with values.
- Use thin connecting lines that do not collide with labels.
- Sort by starting value, ending value, or change, depending on the question.
- Use a common scale. If log scale is appropriate, label it.
- Highlight only the focal few lines; keep the rest quiet.

## Small Multiples

- Use same size, same axes, and same scale by default.
- Order panels by a meaningful variable: geography, baseline level, recent value, change, or domain sequence.
- Put panel labels in consistent locations.
- Remove repeated clutter while retaining enough scale cues to compare.
- Use one shared legend only if direct labels are impossible.

## Sparklines

- Use sparklines when a trend belongs inside a sentence, table, headline, or KPI row.
- Add start/end markers, latest value, high/low, or benchmark only when useful.
- Use consistent scales across rows when comparing rows. Disclose varying scales.
- Do not use sparklines as decorative squiggles.

## Scatterplots

- Use scatterplots for relationships, outliers, clusters, and residuals.
- Label notable points directly.
- Use transparency, binning, hexbin, or density contours for overplotting.
- Add a fitted line only when it answers a stated question. Provide uncertainty and model notes when inferential.
- Consider marginal distributions when they clarify structure.

## Distributions

- Do not summarize distributions with a mean bar unless distribution shape is irrelevant.
- Show raw points when sample size permits.
- Use histograms or density plots only with sensible binning or bandwidth.
- Use box plots for compact comparisons, preferably with points or sample sizes.
- Show important thresholds and practical ranges.

## Estimates And Uncertainty

- Name the central quantity and interval before selecting the mark.
- Prefer dot-and-interval plots for comparable estimates on a common scale.
- Use bands for continuous uncertainty only when overlap remains readable.
- Show raw observations or distribution shape when a summary interval would
  conceal skew, multimodality, sparse samples, or important outliers.
- Do not rank estimates when plausible uncertainty makes the ordering unstable.
- Read `uncertainty.md` before presenting model, forecast, sample, or causal
  claims.

## Maps

- Use maps when spatial arrangement is part of the argument.
- For ranking places, consider a sorted dot plot plus a small locator map.
- Normalize by population or relevant denominator for choropleths.
- Avoid choropleths for raw counts across unequal regions unless area or population itself is the message.
- Use restrained, ordered color scales with clear labels.

## Network And Causal Diagrams

- Treat every line and arrow as a claim.
- Label links with verbs or relationship types when possible.
- Encode strength, direction, time, uncertainty, or evidence quality when they matter.
- Include citations or notes for contested links.
- Do not let crisp nodes and generic arrows imply more knowledge than exists.
- Apply `evidence-diagrams.md` for connector semantics, attachment geometry,
  bounded text, and native-resolution rendered QA.

## Responsive Translation

- Preserve the analytical relationship rather than the desktop geometry.
- Convert crowded line-end labels to small multiples or a visual table instead
  of hiding series on narrow screens.
- Reorder panels and annotations to keep the reading path explicit.
- Keep units, uncertainty, caveats, and source notes in every required sibling
  composition.
