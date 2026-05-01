# Tufte Visualization Principles

Use this reference when the active skill needs more depth on style, evidence integrity, dashboards, tables, maps, or slide figures.

## Overall Character

- Classical, calm, precise, and durable.
- More like a scientific figure, atlas, field guide, or well-made book table than a marketing dashboard.
- Beauty should come from proportion, alignment, typography, data richness, and honest comparison.
- Avoid theatrical metaphors such as cockpit, mission control, war room, performance gauge, or traffic light unless the user explicitly requires that domain convention.

## Academic Plate Standard

Use this standard when the user asks for Tufte, beautiful evidence, publication quality, a hardback-book feel, or an artifact that should not feel cheap.

- Design the page as editorial evidence, not as product UI. A clean card layout can still fail if it feels like software documentation rather than a serious printed figure.
- Let the page breathe, but do not make it sparse. Use margins for local notes, source anchors, definitions, caveats, and small comparisons.
- Prefer serif typography for titles, captions, and explanatory paragraphs when the output medium supports it. Pair it with a quiet sans or mono only for compact labels, axes, file paths, or code references.
- Keep most of the page in black, gray, and paper. Add one muted accent for a focal path, exception, or comparison. Avoid pastel subsystem fills unless color carries a measured variable or necessary grouping.
- Use hairline rules, brackets, alignment, labels, and whitespace before boxes. When boxes are necessary, keep them thin, sparse, and structural.
- Prefer annotated cutaways, layered maps, visual tables, sequence strips, and small multiples over generic box-and-arrow architecture diagrams.
- Use arrows only where direction cannot be inferred from order, numbering, or annotation. Repeated arrowheads often make the figure feel bureaucratic instead of analytical.
- Include enough source evidence to audit the figure: file paths, commit/date, sample, unit, denominator, filter, transformation, or uncertainty.
- Before delivery, ask whether the figure would look credible in an expensive academic reference. If not, revise typography, density, and spatial grammar before polishing colors.

## Canvas And Layout

- Use a white or near-white canvas unless the target medium requires dark mode.
- Remove enclosing plot boxes by default. Keep axes and guides that carry meaning.
- Leave margins for direct labels, especially at line ends.
- Choose aspect ratio from the data task: time series often need horizontal room; ranked comparisons often need vertical room.
- Align related charts on common baselines and scales.
- In small multiples, use identical dimensions, axes, and scales by default. If scale differs, label it plainly and do not make cross-panel magnitude claims.
- For diagrams, use layout to encode relationships: layers, adjacency, sequence, nesting, and margins should carry more meaning than decorative containers.

## Typography

- Use one restrained type family or a careful serif/sans-serif pairing.
- Prefer sentence case. Avoid all caps except for short acronyms or tiny labels.
- Use hierarchy through size, weight, and placement, not effects.
- Put units in labels, subtitles, or captions near the evidence.
- Align numeric labels by decimal place. Use thousands separators and meaningful precision.
- For bookish figures, control line length and leading. Long unwrapped labels, default browser fonts, cramped node text, and over-bold headings are signs to rework the composition.

## Color

- Start in grayscale. Add color only to encode, distinguish, or emphasize.
- Prefer one quiet accent for a focal series and muted neutrals for context.
- Use categorical color sparingly. For many categories, prefer small multiples or direct labels.
- Do not rely on color alone. Pair color with position, label, line style, marker shape, ordering, or annotation.
- Avoid rainbow scales, arbitrary red/yellow/green status, saturated palettes, and colors with moral connotations unless the domain convention is necessary and labeled.

## Lines, Marks, Grids, And Axes

- Make data marks visually stronger than scaffolding.
- Use thin, quiet gridlines only when they improve value reading.
- Prefer horizontal gridlines for value comparison and avoid full cages.
- Use reference lines for meaningful thresholds, targets, medians, baselines, and policy changes.
- Directly label series near line ends or relevant points. Legends are a fallback.
- Use zero baselines for bar charts and other length encodings.
- Non-zero y-axes can be acceptable for line charts when the aim is variation, but the range must be clear and not sensationalized.

## Annotation

- Annotate data, not decoration.
- Attach notes to the point, interval, or region they explain.
- Annotate structural context: policy changes, outages, measurement revisions, recessions, product launches, clinical thresholds, confidence bands, or denominator changes.
- If every point needs a label, consider a table or small multiples.
- For architecture or system-operation figures, annotate motion with numbered steps, small verbs, and local evidence. Avoid letting arrows do all explanatory work.

## Integrity

- Visual magnitude should be proportional to data magnitude.
- Treat area and volume encodings with suspicion because readers compare positions and lengths more accurately.
- Use common scales for comparison. Label independent scales and avoid cross-panel magnitude claims.
- Sort categories by a meaningful analytical quantity unless lookup is the task.
- Normalize rates when populations differ. Show counts too when counts matter.
- Show uncertainty for inference, prediction, experimental claims, measurement, or ranking from samples.
- Mark missing intervals and excluded groups. Do not silently connect across gaps.
- State if the figure shows top-N only, selected examples, or post hoc highlights.

## Tables

Tables are often the right answer when exact lookup, many values, or mixed units matter.

- Sort rows by the key analytical variable.
- Group related columns.
- Align numbers by decimal and units.
- Use light horizontal rules and whitespace instead of heavy cell borders.
- Add sparklines or in-cell bars only when they improve pattern recognition without harming exact lookup.
- Put totals, denominators, and definitions where readers need them.

## Dashboards

A Tuftean dashboard is a compact evidence display for recurring decisions, not a dashboard-shaped decoration.

Default KPI module:

- KPI name in plain language.
- Current value with unit.
- Prior comparable value.
- Target or benchmark if meaningful.
- Compact trend over an appropriate historical window.
- Small note for data quality, missingness, or definition changes.
- Exception highlighting by label or subtle emphasis, not only color.

Avoid gauges, dials, traffic lights without context, giant numbers without history, decorative maps used as menus, and executive-summary screens that remove detail needed to judge the claim.

## Slide Figures

- Put the full evidence display on the slide when possible.
- Use sentence titles that state the finding, but keep enough data for the reader to verify it.
- Prefer handouts, appendices, or dense figure pages for serious technical evidence.
- Avoid slide templates that weaken spatial reasoning with oversized titles, low-density bullets, gratuitous icons, and presenter-centric pacing.
