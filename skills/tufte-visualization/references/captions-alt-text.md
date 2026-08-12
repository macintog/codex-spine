# Captions, Documentation Notes, And Text Equivalents

Use captions and text alternatives to keep evidence interpretable outside the
immediate chart, notebook, slide, or application context.

## Caption Pattern

```text
[Finding or subject]. [Metric definition and unit], [population/geography], [time range].
Source: [source/link], [data vintage/access date]. Notes: [filters, exclusions, transformation, missingness, interval/model definition, or caveat].
```

Keep the finding proportional to the evidence. Use "observed," "estimated,"
"associated," or "projected" when a causal verb would overstate the design.

Example:

```text
Revenue growth slowed after Q3 while observed logo churn continued rising. Monthly recurring revenue and logo churn, North America enterprise accounts, Jan 2023-Dec 2025.
Source: Internal billing table v2026-01-15. Notes: Excludes reseller-acquired accounts; churn is logo churn, not revenue churn; values are descriptive, not a causal estimate.
```

## Documentation Note Checklist

For decision-grade displays, keep these items near the figure or in a linked
note:

- data source and stable URL, citation, file, or dataset identifier
- data vintage or access date
- metric definition, unit, population, and denominator
- sample size when it changes interpretation
- filters, exclusions, top-N selection, suppression, and missingness
- transformation, normalization, smoothing, interpolation, or imputation
- interval, model, forecast, or sensitivity definition
- responsible analysis code, notebook, query, or commit when appropriate

## Short Alt Text Pattern

```text
[Display type] comparing [metric and unit] for [population] over [period]. [Central comparison]. [Most important exception or uncertainty].
```

Alt text should communicate the evidence, not merely inventory shapes and
colors. Avoid phrases such as "image of a chart" when the platform already
announces the image role.

## Complex Figure Pattern

Use two layers when the figure carries more detail than concise alt text can
hold:

1. A short alt text summary naming the comparison and conclusion.
2. A nearby long description, accessible table, or structured explanation that
   preserves key values, exceptions, uncertainty, and source context.

Do not paste an entire dataset into one alt attribute. Do not make a downloadable
CSV the only explanation of the visual claim.

## Text Equivalent Checklist

- Name the metric, unit, population, and period.
- State the central comparison before secondary observations.
- Include the key values or range needed to verify it.
- Name missing data, exclusions, and unstable or uncertain conclusions.
- Preserve reading order for multi-panel figures.
- Explain encodings only when the reader needs them to interpret the evidence.
- Link or identify the source and data vintage.

## Delivery Rules

- If exact values are essential, include them in the caption, adjacent table,
  or accessible text.
- If uncertainty changes the conclusion, include it in both the visible note
  and text equivalent.
- Keep captions and alternatives synchronized with the final filtered or
  exported state.
- Verify the delivered SVG, HTML, PDF, slide, document, or image accessibility
  surface rather than assuming authoring metadata survived export.
