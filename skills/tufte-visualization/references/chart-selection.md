# Chart Selection And Redesign

Choose a comparison architecture, not a fashionable chart type. Prefer designs that let the eye compare positions along common scales.

## Selection Map

| Analytical task | Preferred architecture | Avoid by default |
| --- | --- | --- |
| Compare magnitudes across categories | Sorted dot plot, lollipop, horizontal bar when zero baseline matters, table with in-cell bars | Pie or donut, radial chart, 3D bar, unsorted columns |
| Show change over time | Line chart, horizon or sparkline table, indexed line, small multiples | Area chart when overlap hides values, undisclosed smoothing |
| Compare two time points | Slopegraph, paired dot plot, before/after table | Grouped bars with heavy legend, arrows without values |
| Compare many groups over time | Small multiples with common scales, sparkline table | Spaghetti chart unless few series; tabs that hide comparisons |
| Show distribution | Dot or strip plot, histogram, box plot plus raw points | Mean-only bar chart, decorative violin without explanation |
| Show relationship | Scatterplot with direct labels for notable points; fitted line only when justified | Bubble chart unless area encoding is necessary and explained |
| Show composition | Small multiples of parts, simple stacked bars, part-to-whole table | Exploded pie, stacked area with many layers |
| Show geography | Map when geography explains the result; sorted table or dot plot otherwise | Choropleth for non-spatial ranking tasks |
| Monitor KPIs | Dense table with current value, prior value, target, trend, exceptions | Gauges, dials, traffic lights, giant numbers without context |
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
- Use small multiples when more than five to seven series compete.
- Consider indexing to a common baseline for relative change.

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
- Anchor connectors to deliberate points on the source and target marks; avoid floating endpoints, near-misses, and arrowheads that appear to attach to the wrong object.
- Apply arrowheads, line styles, and emphasis per relationship when direction or meaning differs; inherited styling can create unintended claims.
- Include citations or notes for contested links.
- Do not let crisp nodes and generic arrows imply more knowledge than exists.
