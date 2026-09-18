# Comparison Integrity

Use this reference whenever the display compares values, groups, periods,
rankings, targets, scenarios, or cohorts. A common scale cannot repair an
invalid comparison.

## Contents

- Comparison-validity gate
- Absolute, relative, and decision magnitude
- Temporal comparisons
- Aggregation, weighting, and selection
- Interactive state, freshness, claim language, and stop conditions

## Comparison-Validity Gate

Before encoding a comparison, verify:

- the same metric definition or a disclosed, defensible reconciliation
- the same unit, currency basis, and price basis where relevant
- the same population and inclusion criteria, or an appropriate normalization
- the same denominator or an explicit explanation of denominator change
- aligned time windows, period boundaries, and observation maturity
- compatible aggregation grain and weighting
- no mixture of totals, averages, rates, and row-level observations
- no survivorship, selection, or coverage change presented as performance
- no subgroup reversal or aggregation artifact that changes the conclusion

If these conditions do not hold, reconcile the inputs, facet the populations,
change the claim, or suppress the comparison. Do not rely on a caveat to rescue
a materially incompatible headline comparison.

## Absolute, Relative, And Decision Magnitude

Whenever relative change can exaggerate or conceal practical impact:

- show the base and comparison values
- show the absolute delta and relative delta
- distinguish percent change from percentage-point change
- state the recurrence frequency when a small effect accumulates
- state the threshold, capacity, eligibility, failure, or workload consequence
  when that is the reason the difference matters

For example, prefer “100 to 110, up 10 units or 10%” to “up 10%.” A change from
20% to 15% is a 5-percentage-point decline and a 25% relative decline; choose
the expression the decision needs and label it precisely.

Do not style a difference as important merely because an interval excludes
zero. Distinguish:

- **statistical detectability**: whether the evidence resolves a difference
- **practical magnitude**: whether the difference is substantively meaningful
- **decision significance**: whether it changes an action, threshold, or choice

## Temporal Comparisons

Record and disclose when material:

- timezone and calendar boundary
- calendar versus rolling windows
- complete versus partial periods
- comparable weekdays, business days, holidays, and seasonal periods
- nominal versus inflation-adjusted values
- revised, provisional, backfilled, delayed, or extrapolated observations
- current-period coverage and the basis of any extrapolation
- last-updated time, expected refresh cadence, and update lag

Do not present a partial current period beside a complete prior period without
making the mismatch visible and changing the comparison or claim. Mark missing
intervals; do not connect them as observed continuity.

## Aggregation, Weighting, And Selection

- Name whether values are totals, means, medians, quantiles, rates, indexes, or
  model-derived summaries.
- Disclose weighting changes and verify that group weights have not silently
  shifted the headline result.
- Preserve material subgroup results when aggregation reverses or conceals the
  pattern.
- Declare top-N, post hoc, convenience, survivor, and complete-case selection.
- Show counts with normalized rates when both operational load and population
  risk matter.
- Do not compare ranks without the values and uncertainty needed to judge
  whether the ordering is stable.

## Interactive State And Freshness

Keep the active date range, population, filters, denominator, comparison cohort,
units, scenario, and freshness visible whenever they affect interpretation.

Exports, copied links, screenshots, captions, accessible tables, and text
equivalents must describe the same state as the rendered view. A stale caption,
unfiltered title, or generic alt text attached to a filtered chart is an
integrity failure.

Represent stale, partial, failed, delayed, or degraded data as data-quality
states, not merely as changes in color. When a system cannot establish current
state, say so directly rather than carrying forward the last value as current.

## Claim Language

- Use “observed” for descriptive values and “estimated,” “associated,”
  “projected,” or “modeled” when those qualifications apply.
- Reserve causal verbs for evidence that supports causal identification.
- Use claim titles for explanatory work only when the claim is proportional to
  the evidence.
- Use neutral questions or metric titles for exploration, status or exception
  titles for operations, and descriptive titles for reference displays.

## Stop Conditions

Reject or reframe the comparison when:

- metric definitions, populations, periods, or denominators remain materially
  incompatible
- coverage or missingness could plausibly reverse the claim
- a relative effect lacks the base needed to judge magnitude
- rank is unstable under plausible uncertainty
- filtering changes the claim but the visible documentation does not update
- a partial or stale period is represented as complete or current
