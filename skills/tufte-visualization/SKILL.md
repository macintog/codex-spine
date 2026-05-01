---
name: tufte-visualization
description: Use when creating, revising, or critiquing charts, dashboards, analytical figures, tables with visual encodings, KPI displays, maps, or evidence-heavy reports. Optimizes for truthful comparison, high information density, direct labeling, documented data, restrained visual design, accessibility, and rendered-output verification. Do not use for general frontend layout, marketing pages, decorative graphics, or non-data visuals unless evidence display is central.
metadata:
  short-description: Evidence-first visualization workflow for truthful, dense, restrained analytical displays
---

# Tufte Visualization

Use this skill to make evidence displays clear, precise, information-rich, and honest. The goal is not fashionable minimalism. The goal is disciplined richness: enough data and context for a capable reader to compare, question, verify, and think.

This is a Tufte-inspired operating guide. Derive principles; do not copy protected book pages, proprietary examples, or another designer's finished visual artifact.

## When To Use This Skill

- The user asks to make, revise, or critique a chart, dashboard, analytical figure, KPI display, visual table, map, slide figure, report figure, or evidence-heavy data display.
- The task calls for "Tufte," "high information density," "clean but rich," "publication-ready," "executive dashboard," "analytical memo," "data story," or "beautiful evidence."
- A visualization is being generated through Python, R, JavaScript, spreadsheet software, slides, PDFs, notebooks, or a frontend app.
- A chart needs diagnosis for misleading scales, missing context, weak comparison, chartjunk, accessibility, or overconfident inference.

## When Not To Use This Skill

- The task is general frontend layout, marketing design, illustration, branding, or decorative graphics and evidence display is not central.
- The user only needs data cleaning, statistical modeling, or spreadsheet manipulation with no visual output or figure critique.
- A narrower medium-specific skill fully owns the task and the data display is incidental.

## Core Doctrine

- Show the data. Preserve measures, units, grain, uncertainty, and source context.
- Support comparison. Most analytical seeing is comparative: before/after, part/whole, observed/expected, group/group, local/global, signal/noise.
- Avoid distortion. Visual change must track data change. Declare filtering, smoothing, transformations, missing values, and selection.
- Increase data resolution. Remove decoration, not evidence. Keep useful detail when it helps the reader think.
- Integrate words, numbers, and graphics. Put labels, units, annotations, captions, and source notes close to the evidence.
- Respect the reader. Do not hide essential meaning in hover states, legends, filters, ornament, or presenter narration.
- Match the promised finish. If the user asks for Tufte, beautiful evidence, publication quality, or an academic-book feeling, the artifact should look like serious editorial evidence, not a product dashboard, generic architecture poster, or UI card layout.

## Visual Genre And Finish Bar

Choose the display's genre before drawing. The genre controls typography, density, spatial grammar, and acceptable ornament.

- **Academic plate / hardback figure**: Default here when the user asks for Tufte, beautiful evidence, a serious printed-book feel, or an expensive academic reference. Use a near-white page, quiet black/gray ink, one restrained accent only when it earns its place, fine rules, direct labels, marginal notes, source notes, and carefully controlled typography. The result should feel at home in an $80 academic hardback.
- **Technical atlas / field guide**: Use when explaining how a system operates. Prefer annotated cutaways, layered maps, visual tables, small multiples, and numbered motion paths. Carry dense source evidence in margins or side notes.
- **Dashboard / operational monitor**: Use only when repeated live scanning or decision support is the real task. Compact modules are allowed, but they still need definitions, priors, benchmarks, and data-quality notes.
- **Slide / executive figure**: Use when the artifact must be read at presentation distance. Keep fewer marks, stronger hierarchy, and one central comparison.
- **Interactive web view**: Use when exploration matters. The default viewport still needs the central comparison, labels, units, caveats, and source without hover.

For academic plates and technical atlas figures:

- Prefer serif typography for titles, captions, and explanatory text when the medium supports it. Use a quiet sans or small caps only for compact labels, axes, or file/path metadata. Avoid default system-UI typography when the user asked for a bookish result.
- Build hierarchy through scale, measure, leading, rules, alignment, and annotation density before using color, boxes, or weight.
- Avoid card-heavy or panel-heavy composition. Boxes are not forbidden, but they must be structural evidence containers, not decorative UI cards.
- Favor alignment, brackets, hairline rules, leader lines, callouts, bands, and whitespace over filled rounded rectangles.
- Use arrows sparingly. Too many arrowheads make explanatory figures feel like enterprise architecture. Prefer numbered flowlines, annotated transitions, or before/after spatial ordering unless direction would otherwise be ambiguous.
- Treat connector routing as a first-class layout problem. Curves, arrows, spokes, leader lines, and rules must not cross text, run under labels, enter labeled node interiors, or cross unrelated visual boundaries unless the line is an actual axis, underline, or bracket belonging to that mark. Reserve clear channels and gutters; if a connector competes with text or a boundary, remove the connector, reroute it through whitespace, or replace it with numbering.
- Do not terminate connectors on the visible boundary of a mark. Arrowheads, line caps, and joins occupy real rendered space, so a mathematically exact endpoint on a box edge, circle rim, divider, or node boundary usually reads as overlap. Leave a visible air gap outside every bounded mark unless the connector is intentionally part of that mark's outline or axis.
- Do not let connector elements cross the outline, border, divider, rule, or visible boundary of any non-target mark. A line that merely passes through another box edge or panel rule still creates an accidental relationship and fails the visual dignity check.
- For circular, radial, or icon-like nodes, prove the label fits inside a smaller safe zone, not merely inside the outer shape. Long identifiers and file paths usually belong in external captions or marginal notes. If any line approaches the boundary, wraps awkwardly, or appears clipped by the curve, enlarge the mark, shorten/wrap the text, or move the text out of the shape.
- Do not let a concept mark carry more text than its shape can hold with dignity. A central node can name the concept and one short anchor; dense code identifiers, paths, qualifiers, and evidence belong in nearby labels, side notes, or the source note. If shrinking text is the only way to make it fit, externalize the text instead.
- Keep color almost monochrome by default. Use one muted accent for emphasis, exception, or path tracing. Do not use pastel categorical fills just to make subsystems look different.
- Include enough local evidence that the reader can audit the claim: source files, commit/date, sample size, units, filters, denominators, or uncertainty as appropriate.
- Apply a dignity check before delivery: would a capable reader feel cheated if this figure appeared in a serious printed reference book? If yes, revise the visual language, not just the content.

## Workflow

1. Identify the thinking task.
   - Name the comparison or decision the display should support.
   - Identify the unit of analysis: what one mark, row, point, or line represents.
   - State the assumed audience and use when the user has not specified them.
   - Name the visual genre and finish bar. If the user requests Tufte-like, hardback, publication-quality, or beautiful evidence and no competing medium is specified, choose academic plate / hardback figure.

2. Audit the data before drawing.
   - Check column meanings, units, date ranges, denominators, source, filters, missingness, outliers, duplicates, and category definitions.
   - Distinguish counts, rates, percentages, indexed values, ranks, estimates, residuals, and modeled values.
   - Decide whether uncertainty, sample size, missing data, or sensitivity needs to be visible.

3. Choose a comparison architecture.
   - Prefer position on a common scale, sorted order, direct labels, small multiples, and visual tables over novelty.
   - Read `references/chart-selection.md` when choosing among chart types or converting a weak chart.
   - Use the smallest number of encodings that answer the thinking task.
   - For architecture or system-operation diagrams, prefer annotated cutaways, layered maps, sequence strips, visual tables, small multiples, and evidence-rich marginalia over box-and-arrow posters.

4. Compose from data outward.
   - Build in this order: data marks, scales and units, reference values, direct labels, annotations, documentation note, title, final polish.
   - Make data marks stronger than scaffolding.
   - Prefer white or near-white canvas unless the target medium requires dark mode.
   - Start in grayscale, then add quiet color only to distinguish, encode, or emphasize.
   - For academic plates, start with typography, page margins, rule weights, and annotation structure before adding boxes or color.
   - For diagrams, reserve text and boundary safe zones before drawing connectors. Draw connection paths through whitespace between zones, not through label boxes, node centers, captions, panel borders, table cells, divider rules, or unrelated mark outlines. Z-order, white masks, and "the text is still readable" do not make a connector collision acceptable.
   - Reserve connector endpoint safe zones for every bounded mark before drawing. Offset arrow endpoints away from circles, rectangles, panels, labels, dividers, and table cells by enough distance for the rendered arrowhead or line cap plus visible whitespace.
   - When a flow needs to leave or approach a bounded mark, prefer short detached leaders, external brackets, numbered steps, or spatial ordering over long lines that originate on a boundary and then cross other structure.
   - Remove UI styling that signals software cards, dashboards, marketing pages, or generic architecture posters unless that genre was chosen explicitly.

5. Verify the rendered artifact.
   - Render or export at the intended size before finalizing. Source validity, successful export, linting, or XML/HTML syntax checks are not visual QA.
   - Inspect the actual rendered pixels or pages for label collisions, text overflow, clipping, unreadable text, weak contrast, misleading scales, missing units, hidden caveats, broken small multiples, and hover-only essential meaning.
   - For multi-panel figures, inspect every panel or viewport section at final size; a clean overview can still hide local failures.
   - For diagrams, maps, and annotated figures, check that connectors, arrows, callouts, brackets, and leader lines terminate on the intended marks and do not inherit styling or direction where it changes the claim.
   - Inspect close-up crops around every connector-label, connector-boundary, and connector-crossing relationship, especially curved connectors, radial spokes, arrowheads near nodes, arrowheads near panel borders, and text inside circles or compact shapes. A full-page view can miss a line that clips a descender, touches a box edge, crosses a panel rule, crosses another mark's outline, crosses a code identifier, or visually slices a label.
   - If one connector collision is found, broaden the inspection to every similar connector class in the figure. Do not repair only the visible example; check upper, lower, left, right, curved, straight, inbound, outbound, and repeated connector patterns.
   - When text is placed in bounded elements such as cards, nodes, bars, labels, legends, callouts, axes, or table cells, prove the longest rendered text fits. Do not assume SVG, canvas, PDF, or chart libraries will wrap text automatically.
   - If you zoom in, crop, or otherwise notice a rendered defect, that observation is now blocking evidence. Do not hand off the artifact as premium, publication-grade, or complete until the defect is repaired and the same close-up area is re-inspected.
   - Check the genre promise. If the user asked for a Tufte-like or academic-hardback result and the render reads as a dashboard, card UI, generic infographic, or commodity architecture diagram, treat that as a QA failure.
   - If the rendered artifact has visible layout defects, do not present it as complete. Revise, re-render, and inspect again.
   - Revise until the rendered output passes, or state why rendering was not possible and perform the next best static check.

## Rendered QA Gate

Treat rendered QA as a hard gate, not a polish pass.

- Before presenting any created or revised visualization, render the deliverable form and inspect that exact artifact.
- Do not claim validation from build success, parser success, snapshot generation, file existence, or a quick source skim. Those checks can support QA; they cannot replace rendered inspection.
- For static artifacts, open or view the final PNG, PDF, SVG render, slide page, notebook output, spreadsheet chart, or document page at final size. For responsive or interactive views, inspect every required viewport or state.
- Check bounded text aggressively: alignment, wrapping, truncation, overflow, baseline consistency, line height, clipping, and whether labels stay inside their intended marks or containers.
- For bounded text inside compact marks, inspect a crop at native rendered resolution. The crop must show clear breathing room around every label; "technically readable" is not enough when the mark is meant to be polished.
- Check graphical geometry: connector endpoints, arrowheads, leader lines, brackets, axis ticks, legends, annotations, and data marks. They must land on the intended evidence, avoid accidental relationships, and never visually cut through text, node labels, or unrelated boundaries.
- Treat connector-boundary contact or crossing as a rendered QA failure. Arrowheads, line ends, and curved paths must not touch, pierce, cross, or visually sit on top of node outlines, panel borders, label boxes, table cells, dividers, rules, or chart marks unless the line is explicitly part of the mark. Repair by shortening, offsetting, rerouting, using a bracket/leader without an arrowhead, splitting a path into detached leaders, or replacing the connector with ordered labels.
- Treat connector-text contact as a rendered QA failure, even when the underlying SVG/PDF source is syntactically valid and even when the label is technically legible. Repair by rerouting, shortening, resizing, externalizing the label, or removing the connector; do not defend it as a layering artifact.
- Check visual dignity against the selected genre. For academic plates, look for bookish typography, restrained color, high evidence density, direct annotation, and absence of product-card styling.
- When a defect is found after presentation, acknowledge the failed QA plainly, repair the artifact, re-render it, and report the new rendered inspection. Do not defend the earlier artifact with source-level checks.

## Coordination

This skill owns evidence design. Medium-specific skills own mechanics.

- For web apps, use frontend or web testing skills for layout and interaction, while this skill keeps charts evidence-first, legible, directly labeled, and complete in the default view.
- For spreadsheets, use spreadsheet-native formulas, tables, charts, and provenance while preserving exact lookup and recalculation.
- For presentations, keep the figure self-sufficient on the slide; do not reduce serious evidence to bullets.
- For PDFs and documents, verify the rendered page, not only the source file.
- For dashboards, prefer compact evidence modules: current value, prior comparable value, target or benchmark, trend, definition, and data quality note.

## Reference Map

- Read `CITATIONS.md` for the public sources consulted for the original draft.
- Read `references/principles.md` for deeper visual style, integrity, and dashboard guidance.
- Read `references/chart-selection.md` when selecting chart architecture or redesigning a weak chart.
- Read `references/critique-checklist.md` when reviewing an existing display or doing final QA.
- Read `references/accessibility.md` for digital, public, or interactive artifacts.
- Read `references/captions-alt-text.md` before delivering public-facing captions, notes, or alt text.

## Stop Rules

- Do not fabricate production data. If no data is available, provide the needed schema, chart architecture, and reproducible template unless the user explicitly asks for a mockup.
- Do not ask for clarification unless missing information would change the chart fundamentally. State assumptions when you can proceed safely.
- Do not imply causality with arrows, trend lines, sequencing, color, or annotation unless causal evidence is part of the data or user-provided context.
- Do not silently connect across missing time intervals or hide excluded groups.
- Do not call an artifact Tufte-like or publication-grade merely because it is clean, muted, or source-grounded. If it looks like product documentation rather than serious evidence design, say so and revise.

## Implementation Defaults

- Create a reproducible figure pipeline: load data, validate data, compute derived measures explicitly, plot data marks first, style with restraint, add direct labels and documentation, export, inspect.
- Prefer one excellent chart over many mediocre charts. Use a coherent figure set only when the task needs overview, comparison, detail, and documentation.
- Prefer vector output such as SVG or PDF for publication and web. Use high-resolution raster output only when the target medium requires it.
- When hand-authoring vector diagrams, prefer explicit anchors and per-element styling for connectors, markers, and callouts; grouped defaults are acceptable only after rendered inspection confirms they do not add unintended arrows, emphasis, relationships, connector-boundary collisions, or connector-text collisions.
- Account for marker geometry when setting vector endpoints. SVG markers, PDF arrowheads, line caps, and stroke joins can extend past the path endpoint; set path endpoints in whitespace rather than on the target boundary, or draw a separate non-overlapping arrowhead when exact geometry matters.
- Treat connector lanes as occupied space, not decoration. Before drawing long curves or arrows, sketch the clear channel they will occupy and prove that channel does not cross any panel edge, node boundary, table cell, label box, divider, title rule, or unrelated evidence mark.
- When hand-authoring SVG or canvas text, either measure/wrap text explicitly or keep copy short enough to fit with generous margin. SVG `<text>` is not a layout engine. For circular nodes, use a conservative inner text box such as about 60-70% of the diameter, or place dense labels outside the circle.
- Treat circular, radial, badge, and icon-like nodes as labels of last resort, not containers for audit trails. Before rendering, set a text budget for each compact mark. After rendering, crop the mark and replace any cramped identifier with a short human label plus an external file/path note.
- Keep titles factual and specific: subject, metric, population or geography, and time period when space allows.
- Include source, data vintage or access date, metric definition, denominator, filters, transformations, smoothing, interpolation, and model assumptions when the display informs decisions.
- For interactive charts, the default view must show the central comparison. Hover may add exact values, but must not be the only place for labels, units, caveats, or source.
- For architecture or codebase-operation illustrations, ground the figure in inspected source evidence, then design it as an editorial explanatory plate: fewer boxes, more precise spatial grouping, direct annotations, file-path marginalia, and restrained motion cues.

## Output Contract

When creating or revising a visualization, return:

- the artifact path or exact changed file
- the key assumptions about data, units, filters, scale, and audience
- the selected visual genre and finish bar
- the comparison architecture chosen and why
- the validation performed, including the rendered artifact inspected and any viewport/page size used; if rendered inspection was impossible, say that clearly before presenting caveats
- any remaining caveat about source data, uncertainty, or interpretation

When critiquing a visualization, lead with the highest-risk integrity or comprehension issues, then give focused redesign moves.
