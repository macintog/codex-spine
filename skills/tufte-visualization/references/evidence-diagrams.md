# Evidence Diagram Geometry

Use this reference for network diagrams, causal diagrams, system maps,
technical atlases, flow diagrams, annotated process diagrams, or any display
with connectors and bounded nodes.

## Semantic Contract

Treat every connector as a claim. Establish:

- unambiguous source and target
- direction, sequence, or symmetry
- relationship type, preferably with a verb or named relation
- time, strength, quantity, uncertainty, or evidence quality when material
- whether the line denotes causality, association, flow, dependency, ownership,
  sequence, or mere reference

Do not use an arrow when the evidence supports only adjacency or association.
Do not let spatial proximity, enclosure, or line style imply a stronger
relationship than the documentation supports.

## Connector Geometry

- Reserve whitespace lanes for curves, arrows, spokes, leaders, brackets, and
  rules before placing labels and nodes.
- Anchor connectors to deliberate points on the source and target marks.
- Leave a visible air gap between arrowheads or endpoints and bounded marks;
  marker geometry extends beyond mathematical path endpoints.
- Do not let a connector cross text, unrelated boundaries, panel rules, table
  cells, or non-target marks.
- Apply arrowheads, line styles, and emphasis per relationship. Inherited
  styling can create unintended claims.
- Use detached leaders, brackets, ordered labels, or adjacency when a clean
  connector lane is unavailable.

## Bounded Text

- Prove that the longest label fits inside a conservative safe zone at final
  size.
- SVG and canvas text do not wrap automatically; verify the actual rendering.
- Move dense identifiers, source paths, dates, and audit detail to external
  notes when compact nodes cannot hold them legibly.
- Do not shrink text to preserve a node shape.

## Rendered QA

- Inspect native-resolution crops around connector-label,
  connector-boundary, and connector-crossing relationships.
- One collision, near-miss, or ambiguous attachment triggers inspection of
  every similar connector class.
- Verify that arrowheads touch the intended relationship path without entering
  the target mark or appearing attached to another object.
- Re-render and re-inspect the same close-up after every repair.

Source validity, z-order, white masks, or technical legibility do not override
a visible defect. If the diagram cannot preserve both semantic meaning and
clean attachment, change the geometry or remove the connector.
