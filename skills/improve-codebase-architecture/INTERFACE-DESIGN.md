# Interface Design

Use this guide when the user has chosen a deepening candidate and wants to explore alternative interface shapes.

## Process

### 1. Frame The Problem

Before proposing designs, summarize:

- The product concept the module should own.
- The callers that will cross the interface.
- The dependencies behind the seam and their category from [DEEPENING.md](DEEPENING.md).
- The invariants, ordering constraints, error modes, and performance expectations callers must understand.
- A small illustrative sketch, clearly marked as a sketch rather than a proposal.

### 2. Generate Alternatives

Produce at least three meaningfully different interface designs:

- Minimal interface: 1 to 3 entry points with high depth per entry point.
- Flexible interface: more extension points where real variation exists.
- Common-case interface: make the normal caller path trivial.
- Ports-and-adapters interface when remote owned dependencies or true externals dominate the seam.

Use subagents for these alternatives only when the user explicitly asked for workers or parallel agent work.

Each design should include:

1. Interface: types, methods, parameters, invariants, ordering, and error modes.
2. Usage example.
3. What the implementation hides behind the seam.
4. Dependency and adapter strategy.
5. Tradeoffs in depth, locality, and seam placement.

### 3. Recommend

Compare the designs in prose. Give an opinionated recommendation, including any hybrid that keeps the strongest parts of multiple designs.
