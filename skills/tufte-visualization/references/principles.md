# Tufte Visualization Principles

Use this reference for deeper judgment about taste, composition, typography,
color, tables, dashboards, maps, and explanatory diagrams.

## Overall Character

- Precise, calm, information-rich, and durable.
- More like a scientific figure, atlas, field guide, or well-made analytical
  table than a marketing dashboard or generic infographic.
- Beautiful because proportion, comparison, annotation, and evidence have been
  resolved—not because the artifact performs an aesthetic category.
- Restrained without becoming timid, sparse, or context-poor.

## Reading Situation And House Style

Choose visual language only after naming the reading situation:

- Who is reading, and what decision or comparison are they making?
- Is the artifact printed, projected, embedded, scrolled, monitored, or
  explored?
- What are the final dimensions, viewing distance, ambient light, expected
  reading time, and interaction method?
- Which publication, product, journal, or organizational conventions already
  shape reader expectations?

Preserve the host surface's established typography, palette, and chart grammar
unless they impair truth, comparison, legibility, or accessibility. Tufte is an
evidence-design overlay, not a competing brand identity.

## Anti-Reflex Taste Standard

Run two checks before polishing:

1. **Category reflex**: Could the palette, typography, and layout have been
   predicted from the words "Tufte chart," "executive dashboard," or
   "scientific figure" without seeing the evidence? If yes, the design is being
   generated from category habit.
2. **Second-order reflex**: After rejecting obvious chartjunk, did the artifact
   fall into another stock lane—cream paper, prestige serif, tiny mono labels,
   hairline rules, editorial columns, and a muted red accent? If yes, it is
   performing restraint rather than resolving the evidence.

Do not ban a typeface, color, rule, or layout merely because it is familiar.
Require it to earn its place through medium, house style, or analytical
function. Distinctiveness should emerge from the structure of the evidence.

## Genre Standards

### Academic Plate

- Design for sustained reading and local verification.
- Use controlled measure, quiet scaffolding, direct annotation, source notes,
  and enough local detail to audit the claim.
- Serif typography, off-white stock, marginalia, and monochrome treatment are
  options when the host publication supports them, never automatic signals of
  seriousness.
- Avoid turning every annotation into an editorial ornament. Notes must qualify
  evidence, define a term, or explain a comparison.

### Technical Atlas Or Field Guide

- Prefer cutaways, layered maps, sequence strips, visual tables, small
  multiples, and numbered motion paths over box-and-arrow posters.
- Carry source paths, dates, identifiers, or state transitions in nearby notes
  without forcing them into compact nodes.
- Let adjacency, nesting, order, and alignment encode relationships before
  adding connectors.

### Operational Monitor

- Optimize repeated scanning and action, not dashboard appearance.
- Pair each important current value with an appropriate prior, target,
  benchmark, trend, definition, and data-quality state.
- Make exceptional conditions visible by label and position, not merely color.
- Preserve the detail needed to decide whether an alert is real.

### Presentation Figure

- Make one comparison readable at viewing distance.
- Use a sentence title that states the supported finding without overstating it.
- Retain enough values, units, and source context for the audience to verify the
  claim rather than reducing the slide to assertion plus decoration.

### Interactive Analytical View

- Make the central comparison complete before interaction.
- Use interaction to reveal detail, change a legitimate analytical slice, or
  compare scenarios—not to hide labels, definitions, caveats, or sources.
- Preserve shareable and understandable state where filtering changes the
  claim.

## Canvas And Layout

- Choose the canvas from the reading situation. White or a neutral near-white
  is a strong default for print and analytical work; dark or colored surfaces
  are valid when the medium, host identity, or ambient conditions require them.
- Avoid faux paper, sepia, grain, or warm tint used only to signal scholarship.
- Leave margins for line-end labels, notes, and source context.
- Align related charts on common baselines and scales.
- Give each figure one dominant comparison while retaining dense supporting
  evidence. Density does not mean equal visual weight.
- Use spacing rhythm—tight within a comparison, generous between analytical
  groups—instead of enclosing every group in a card.
- Use boxes only when a boundary is part of the evidence or interaction model.

## Typography

- Follow the host publication or product when it has a coherent type system.
- Otherwise choose one family or a deliberate contrasting pair based on the
  reading situation, not on a generic "editorial" or "technical" association.
- Prefer sentence case. Reserve capitals and monospace for short labels,
  identifiers, code, or established domain notation.
- Control line length, line height, numeric alignment, precision, and label
  measure at the final size.
- Align comparable numbers by decimal place and units. Use thousands separators
  and only meaningful precision.
- Do not shrink text to rescue an overfull mark. Shorten the label, enlarge the
  mark, recompose the figure, or move detail to an external note.

## Semantic Color Roles

Name roles before choosing hues:

- **Ink**: primary text, axes, and marks needed to read the comparison.
- **Context**: historical, baseline, or non-focal evidence.
- **Focus**: the series, interval, or exception currently under discussion.
- **Uncertainty**: interval, distribution, sensitivity, or confidence state.
- **Exception**: missing, invalid, out-of-policy, or otherwise qualitatively
  different data.
- **Interaction state**: selected, filtered, disabled, or focused controls.

Start in grayscale when practical, then add the fewest roles the evidence
requires. A single accent is a useful default, not a law. Multiple hues are
appropriate when they encode distinct categories or states that cannot be
compared clearly by position, line style, shape, or faceting alone.

Do not use color only for meaning. Avoid rainbow scales, arbitrary traffic-light
status, and moralized hues unless the domain convention is necessary and
labeled. Use perceptually ordered scales for ordered values.

## Lines, Marks, Scales, And Grids

- Make data marks stronger than scaffolding.
- Use grids only when they improve value reading; avoid full cages by reflex.
- Use reference lines for meaningful thresholds, targets, medians, baselines,
  or regime changes.
- Use zero baselines for bars and other length encodings.
- A non-zero line-chart axis can be valid when variation is the question, but
  disclose the range and avoid sensational framing.
- Treat area, volume, perspective, and animation with suspicion because they
  are harder to compare precisely.
- Directly label series near the relevant marks. Use legends when direct labels
  would collide or create more decoding burden.

## Annotation And Documentation

- Annotate evidence, not empty space.
- Attach notes to the point, interval, region, or transition they explain.
- Document structural context: policy changes, outages, measurement revisions,
  denominator changes, thresholds, experimental conditions, and model changes.
- Include source, data vintage, metric definition, denominator, filters,
  transformations, and uncertainty when the figure informs a decision.
- If every point needs a label, consider a table, small multiples, or a
  different aggregation.

## Tables

Use a table when exact lookup, many values, or mixed units matter.

- Sort rows by the analytical variable unless stable lookup order is the task.
- Group related columns and align comparable numbers.
- Use light rules and whitespace instead of heavy cell borders.
- Add sparklines or in-cell bars only when they improve pattern recognition
  without weakening exact lookup.
- Place totals, denominators, definitions, and missingness where readers need
  them.

## Maps And Explanatory Diagrams

- Use a map only when spatial arrangement contributes to the explanation.
- Pair a map with a ranked table or dot plot when ranking places is the real
  task.
- Treat every connector and arrow as a claim. Label relationship type,
  direction, time, strength, or uncertainty when it matters.
- Reserve connector lanes and endpoint air gaps. Do not let a line touch text,
  enter an unrelated boundary, or imply attachment through a near-miss.
- Prefer external notes for paths, identifiers, and audit detail that compact
  shapes cannot hold with dignity.

## Responsive And Motion Principles

- Recompose for materially different output sizes. Do not shrink a desktop
  figure until labels, context, and caveats become unreadable.
- Preserve the same analytical claim, comparison, units, uncertainty, and
  documentation across sibling compositions.
- If small screens cannot hold the full figure, use ordered sections, small
  multiples, a visual table, or a paired text equivalent rather than deleting
  evidence silently.
- Motion must clarify change, sequence, or causally supported flow. It must
  enhance an already intelligible default and have a reduced-motion or static
  equivalent.

## Integrity Standard

- Visual magnitude must track data magnitude.
- Normalize rates when populations differ; show counts too when they matter.
- Use common scales for comparison. Label independent scales and avoid
  cross-panel magnitude claims when scales differ.
- Show or explain uncertainty for estimation, prediction, measurement,
  experimental, or model-based claims.
- Mark missing intervals, imputed values, excluded groups, selected examples,
  top-N filters, and post hoc highlights.
- Never let polish imply more precision, causality, completeness, or confidence
  than the evidence supports.
