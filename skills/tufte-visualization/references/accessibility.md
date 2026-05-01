# Accessibility For Evidence Displays

Accessibility is precision applied to more readers. Do not treat it as a tradeoff against elegance.

## Visual Encoding

- Do not use color as the only way to convey meaning.
- Pair color with position, text, line style, marker shape, order, or annotation.
- Keep text and essential graphical elements at sufficient contrast for the target medium.
- Avoid tiny labels that look elegant at full resolution but fail at actual display size.
- Prefer direct labels over distant legends when practical.

## Layout And Reading

- Keep labels close to the marks they explain.
- Avoid dense label clusters that cannot be parsed by screen magnification.
- Use meaningful order and grouping so readers do not depend on color scanning.
- Do not hide units, caveats, denominators, or definitions in tooltips only.

## Interaction

- The default view must show the central comparison.
- Hover tooltips may add exact values but must not contain essential labels, units, caveats, or source information exclusively.
- Filters and toggles need visible state.
- Interactive controls should be keyboard accessible and show focus states.
- Do not make incompatible scales look comparable after filtering.
- For animation or motion, provide pause/stop controls and a static equivalent when practical.

## Public Digital Artifacts

- Provide alt text or a text summary.
- Mention chart type, metric, population, period, main pattern, notable exceptions, and key values or range.
- If a chart carries a decision or claim, include source and data-vintage notes in adjacent text.
- Test the rendered output at the size and viewport where readers will see it.
