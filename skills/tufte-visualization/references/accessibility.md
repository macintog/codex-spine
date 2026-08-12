# Accessibility For Evidence Displays

Accessibility is precision applied to more readers. Treat it as part of the
evidence contract, not as a tradeoff against elegance.

## Start With The Delivery Medium

Record the final size, viewport, reading distance, display or print medium,
interaction method, and available text equivalent. Apply medium-specific
requirements in addition to this baseline.

## Contrast And Visual Encoding

For digital artifacts targeting WCAG 2.2 AA:

- normal text needs at least 4.5:1 contrast against its background
- large text—at least 18 point, or 14 point and bold, under the WCAG
  definition—needs at least 3:1
- graphical objects and user-interface components needed to understand or
  operate the display need at least 3:1 against adjacent colors

Do not rely on color alone. Pair it with position, direct labels, ordering,
line style, marker shape, texture, or annotation. Test focal, context,
uncertainty, missing, selected, disabled, and focus states—not only the default
palette.

For print, projection, dark mode, or unusual displays, inspect a representative
proof under expected conditions. A mathematically sufficient contrast ratio
does not rescue hairlines, tiny type, glare, poor projection, or low-quality
printing.

## Typography, Magnification, And Density

- Inspect labels at the actual delivered size, not only while zoomed in.
- Keep prose measure and line height readable; avoid dense label clusters that
  become ambiguous under magnification.
- Do not shrink text to preserve a composition. Recompose, shorten labels, use
  small multiples, or move audit detail into an adjacent note.
- Keep direct labels close enough to their marks that magnification does not
  break the relationship.
- Preserve meaningful reading order in the document or DOM rather than relying
  only on two-dimensional placement.

## Semantic And Text Alternatives

Provide an adjacent text equivalent for public or decision-grade displays.
Include:

- chart or display type when it aids orientation
- metric, unit, population, and period
- central comparison or finding
- key values or range
- notable exceptions, missingness, and uncertainty
- source and data vintage

For complex figures, use a short alt text summary plus a longer nearby
description, accessible table, or structured explanation. Do not force the
entire dataset into one alt attribute. For SVG, documents, slides, and PDFs,
use the semantic or accessibility features supported by the delivery format
and verify the exported result rather than only the source authoring surface.

## Interaction And Keyboard Access

- The default view must show the central comparison.
- Hover may add exact values but must not be the only location for labels,
  units, caveats, denominators, or source information.
- Give filters, toggles, legends, tabs, and selectable marks visible state,
  programmatic names, keyboard access, and visible focus.
- Provide an equivalent way to reach pointer-dependent details.
- Announce material state changes where the host platform requires it.
- Do not make incompatible scales appear comparable after filtering.

## Responsive Sibling Compositions

Treat materially different viewports as sibling evidence displays, not one
layout scaled down.

- Preserve the same claim, units, comparison, uncertainty, and documentation.
- Reorder, facet, or convert to a visual table when horizontal compression
  would destroy label or scale legibility.
- Do not silently remove groups, intervals, caveats, or source notes on mobile.
- Test text enlargement, narrow width, landscape when relevant, and the actual
  embedding container—not only full-screen browser presets.

## Motion

- Motion must enhance an already visible and intelligible default.
- Do not gate evidence on an entrance animation, autoplay sequence, or hover.
- Respect reduced-motion preferences.
- Provide pause, stop, or static alternatives for motion that starts
  automatically, repeats, or carries analytical meaning.
- Avoid animation that makes exact comparison depend on memory across frames;
  use small multiples or persistent reference marks when practical.

## Rendered Accessibility Proof

Inspect the final artifact and each required state for:

- contrast and meaning without color
- actual-size label readability
- reading and focus order
- keyboard and pointer equivalence
- text alternative or accessible table
- responsive preservation of evidence
- reduced-motion behavior
- exported PDF, slide, document, SVG, or image semantics where supported

If a required accessibility proof cannot be performed, name the missing check
and do not claim the artifact is fully accessible.
