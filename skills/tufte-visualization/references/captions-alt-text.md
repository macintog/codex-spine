# Captions And Alt Text

Use captions and alt text to keep evidence interpretable outside the immediate code or notebook context.

## Caption Pattern

```text
[Finding or subject]. [Metric definition and unit], [population/geography], [time range].
Source: [source name/link], [data vintage/access date]. Notes: [filters, exclusions, transformation, uncertainty, or caveat].
```

Example:

```text
Revenue growth slowed after Q3 while churn continued rising. Monthly recurring revenue and logo churn, North America enterprise accounts, Jan 2023-Dec 2025.
Source: Internal billing table v2026-01-15. Notes: Excludes accounts acquired through reseller channel; churn is logo churn, not revenue churn.
```

## Documentation Note Checklist

For decision-grade displays, include a compact note near the figure or in a footnote:

- Data source and URL or citation.
- Date accessed or data vintage.
- Metric definition and denominator.
- Sample size or population.
- Key filters, exclusions, transformations, smoothing, interpolation, and model assumptions.
- Responsible analyst or code/notebook reference when applicable.

## Alt Text Pattern

```text
Chart showing [chart type] of [metric] for [population] over [period]. The main pattern is [primary finding]. Notable exceptions are [exceptions]. Values are [range or key values].
```

Alt text should communicate the conclusion and evidence, not only the visual form.

## Delivery Notes

- If exact values are essential, include them in the caption, adjacent table, or accessible text.
- If uncertainty changes the interpretation, mention it in the caption or notes.
- If missing data or excluded groups affect interpretation, say so plainly.
