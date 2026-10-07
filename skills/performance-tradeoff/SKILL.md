---
name: performance-tradeoff
description: Measure and judge hardware-bound optimization tradeoffs involving latency, throughput, CPU/GPU use, memory, headroom, capacity, fallback, or workload size. Use for benchmark design or execution, performance-claim review, hardware qualification, and optimization acceptance decisions. Do not use for routine cleanup or performance-neutral refactors with no material resource claim.
---

# Performance Tradeoff Evaluation

## Establish the claim

Identify the **baseline** and **candidate** by revision, build and configuration. State:

- the claimed benefit, affected phase and operation frequency;
- target hardware and plausible supported workload;
- correctness, output quality and applicable lifecycle requirements, including cancellation, fallback, cleanup and subsequent jobs;
- the acceptance threshold or tradeoff that would change the decision.

Label material claims **measured**, **estimated**, or **missing**, with evidence pointers. Separate diagnosis and exploratory estimates from qualification. Reuse applicable measurements; commission only the smallest comparison that resolves a consequential unknown. When required evidence is missing, classify the decision as **unproven** and name that comparison. A demonstrated correctness failure or violated requirement can justify rejection without measuring unrelated benefits.

## Make the comparison equivalent

Hold hardware, software, model, driver, inputs, quality, load and relevant power or thermal conditions fixed **except for the intended change**. Record deviations and confounders. Qualify each target machine separately; measurements elsewhere cannot establish its hardware-bound claim. For an intentional hardware comparison, name the hardware difference and hold the workload contract fixed.

Separate cold-start, warm-cache and sustained cases when relevant; do not warm away a claimed startup cost. Use fresh processes when allocator history or retained state matters, and repeated jobs in one process when retention or lifecycle behavior matters. Alternate or randomize arm order; record warmup policy, samples per arm, failures, statistic and spread. If the evidence cannot distinguish the change from measurement variability, treat it as inconclusive.

Recompute every absolute and percentage delta from raw values. Use `(candidate - baseline) / baseline` for relative change, label improvement direction, and flag inconsistent supplied arithmetic. Zero, failed or incomparable baselines have no meaningful percentage; do not calculate successful-run speedup from a timeout or OOM.

## Measure the claimed user cost

For latency, report baseline, candidate, absolute delta and percentage for the affected operation, phase and complete user-visible workload where measured. State timing boundaries. Time asynchronous work through the required completion, including relevant waits and transfers; enqueue duration is not completion latency. Avoid inserting synchronization that changes the production pipeline. Report operation frequency and cumulative repeated cost without multiplying overlapping work as though it were serial.

For throughput, report completed units per time window, offered load, concurrency, batch size, duration, errors and applicable latency statistic or limit. For CPU/GPU or energy claims, define the counter, units, sampling window and normalization; distinguish utilization snapshots from total resource cost for completed work. Select metrics relevant to the claim, not every possible counter.

Interpret absolute end-to-end impact before percentages. Keep microbenchmark, phase and full-workload conclusions separate; do not promote an unmeasured end-to-end improvement from a faster component.

## Measure memory and capacity when relevant

Report available allocated, reserved, process/device-reported and externally sampled memory, naming each metric's scope. Record peak phase and relative timestamp, physical capacity, effective usable budget, headroom calculation, sampling interval and missed-transient risk. Calculate headroom from compatible accounting scopes; do not add overlapping host/device unified-memory counters or subtract one allocator's allocation from physical RAM as though it measured system headroom.

Record OOM, fallback, offload, admission rejection, pressure and workload reduction. Report the largest **tested plausible** workload each arm completes reliably, not an unbounded maximum.

For a demonstrated memory reduction, classify its capacity effect as:

1. **Capacity-enabling** — the baseline fails, falls back or cannot admit a plausible supported case; the candidate completes the identical case reliably.
2. **Boundary-protecting** — the baseline is inside a predeclared unsafe headroom margin; the candidate repeatedly restores the declared safe margin.
3. **Resource-reducing only** — memory falls without a demonstrated capacity or safe-margin change. State any separately measured concurrency, operating-cost or other operational benefit.

Use `unproven` when evidence cannot establish a class, and `not applicable` for non-memory claims or no demonstrated reduction. Declare unsafe margins before inspecting candidate results. When acceptance depends on a capacity boundary, bracket it with identical plausible cases in both arms; reuse existing failures or admission evidence when sufficient. A resource-only or latency decision does not require an unrelated OOM sweep. Stay within the authorized resource budget; an untested boundary remains unproven.

## Judge the result

Decide in this order:

1. correctness and output quality;
2. real workload capability or stability;
3. absolute end-to-end user cost;
4. repeatability in the relevant cold, warm or sustained regime;
5. lifecycle behavior;
6. implementation and maintenance cost;
7. percentages as supporting context.

Capacity-enabling or genuine boundary-protecting results may justify a modest measured latency cost when quality and lifecycle behavior remain sound. Resource-reducing-only results normally do not justify added complexity or regression without another measured operational benefit. Preserve applicable proof for unaffected cases; do not extrapolate a pass to another hardware/workload case. Stop when the selected decision is supported; report remaining untested claims without silently commissioning more work.

## Report one decision per hardware and workload case

Use a compact table or prose covering:

- hardware, workload, baseline/candidate identities and intended difference;
- relevant metrics, units, baseline, candidate, absolute/relative change and end-to-end significance;
- evidence pointers, timing/accounting boundaries, warmup, samples, ordering, statistic/spread, failures and confounders;
- quality and lifecycle results; memory class and tested boundary when applicable;
- **accept**, **reject**, or **unproven**, with rationale and the smallest missing proof if needed.

Use `not measured` or `not applicable` explicitly for material gaps. Distinguish an accepted scoped result from untested proposals and broader performance claims.
