# Uncertainty And Inferential Displays

Use this reference whenever the display contains estimates, samples,
measurements with error, model output, forecasts, rankings from incomplete data,
or claims whose conclusion could change under plausible assumptions.

## Classify The Quantity

Before choosing an uncertainty mark, identify what the central value represents:

- a complete-population observation
- a sample statistic
- a measurement with instrument or process error
- a model estimate or fitted value
- a forecast or prediction
- a simulation, posterior distribution, or scenario range
- an imputed value

Do not add generic error bars to a quantity that has no defined uncertainty
model. Do not omit uncertainty merely because the charting tool makes intervals
inconvenient.

## Name The Interval

State what an interval or distribution means. Standard deviation, standard
error, confidence interval, credible interval, prediction interval, quantile
range, tolerance interval, and scenario range are not interchangeable.

- Put the interval type and level in the caption or nearby note.
- State the sample size and denominator where they affect interpretation.
- For asymmetric or bounded quantities, preserve the actual interval shape
  rather than forcing symmetry around a mean.
- For forecasts, distinguish uncertainty about the expected value from the
  wider uncertainty of an individual future outcome.

## Choose An Honest Architecture

- Use dot-and-interval plots for comparable estimates.
- Use bands for uncertainty over a continuous axis when overlap remains
  readable.
- Use raw points, strip plots, histograms, empirical cumulative distributions,
  or quantile displays when distribution shape matters.
- Use small multiples or scenario fans when several plausible trajectories
  must remain distinguishable.
- Use probability or frequency language beside the display when the audience
  may misread an interval as a guaranteed range.
- Avoid ranking estimates when interval overlap or sensitivity makes the rank
  unstable. Group, tier, or show the uncertainty in rank instead.

## Missingness, Imputation, And Sensitivity

- Distinguish missing, zero, not applicable, suppressed, and not yet reported.
- Mark imputed values and name the method or source.
- Do not connect across missing time intervals unless interpolation is explicit
  and visually distinguished.
- Show sensitivity when a reasonable change in assumptions, model, smoothing,
  inclusion criteria, or denominator changes the conclusion.
- If only one sensitivity view can fit, choose the assumption most likely to
  reverse or materially weaken the claim.

## Transformations And Model Output

- Disclose log scales, indexing, normalization, smoothing, aggregation,
  seasonal adjustment, and back-transformation.
- Plot residuals or calibration evidence when a fitted relationship is being
  used to justify inference or prediction.
- Do not present a fitted line as a causal mechanism. Name confounding,
  selection, or design limitations that materially constrain interpretation.
- Keep observed and modeled values visually distinguishable without making the
  model look more authoritative than the observations.

## Annotation Discipline

- Use language proportional to the evidence: "observed," "estimated,"
  "associated," "consistent with," or "projected" rather than causal verbs
  when causality is not established.
- Avoid labeling a noisy maximum or minimum as meaningful without showing the
  distribution or comparison that supports it.
- Do not use opacity, blur, or fading as the sole uncertainty encoding when it
  makes values harder to recover or suggests missingness instead.

## Delivery Note

For decision-grade figures, report:

- quantity type and central estimate
- interval or distribution definition and level
- sample size, population, and denominator
- missingness and imputation
- transformation or model assumptions
- sensitivity that could change the decision
- limits on causal or predictive interpretation
