# Pre-registration

Committed before any held-out data is read. Changes after that point are
recorded below with a date and reason, never edited in place.

## Data split

Defined once in `src/marginalis/config.py`.

| Split | Window (UTC, half-open) | Use |
|---|---|---|
| Train | 2019-07-01 → 2025-01-01 | Estimate marginal emissions factors; all method development |
| Hold-out 1 | 2025-01-01 → 2026-01-01 | Primary out-of-sample evaluation |
| Hold-out 2 | 2026-01-01 → 2026-09-01 | Second check (2026 YTD) |

No code reads either hold-out split until the method is declared frozen
(`METHOD_FROZEN` in config). The freeze is itself a commit.

## Balancing authorities

ERCO → CISO → MISO, in that order. ERCO first because it is barely
interconnected, so Δdemand ≈ Δin-BA generation.

## Estimand and specifications

- Main specification: regress hourly ΔCO₂ on Δdemand within strata.
- Robustness check: regress ΔCO₂ on Δ(in-BA fossil generation).
- Each BA's hourly net-import share is computed and reported alongside results.
- Minimum stratum cell size: fixed before results are inspected, recorded here
  when the strata code is written. **Recorded 2026-09-27: 120 usable
  observations** (see Estimation details).

## Estimation details

Recorded 2026-09-27, before any marginal factor was estimated. Only observation
counts per cell (min 141, median ≈165) had been looked at.

- **Data.** `v_hour_delta_train` only. Emissions sources: `derived` (Option A)
  and `eia` (EIA published, in-BA generation). Specs: `demand` (Δdemand) and
  `fossil_gen` (Δ in-BA fossil generation).
- **Strata.** BA × spec × source × month × local hour. Month and local hour are
  taken at the **start** of the hour, in the BA's zone (MISO: Central).
- **Exclusions**, per (spec, source), fixed from the documented data caveats:
  1. the previous hour is not the immediately preceding UTC hour;
  2. either hour has any interpolated value (`imputed_either`);
  3. the regressor or ΔCO₂ is NULL;
  4. `derived` only: either hour has incomplete fossil data (`derived_complete_both` false).
  No exclusion is made for the CISO hydro/other gap (Oct 2019 – Aug 2020) in
  the MEF regressions: demand, fossil generation and CO₂ are unaffected by it.
- **Estimator.** Per stratum, OLS with intercept: ΔCO₂ = α + β·Δx + ε. The
  marginal factor is β (kg CO₂/MWh).
- **Minimum cell size: 120 usable observations.** A cell below it is pooled
  with the same local hour in the adjacent months (±1, then ±2, cyclic) until
  it reaches 120. `stratum_id` identifies the pooled cell.
- **Confidence intervals.** Cluster bootstrap resampling local calendar weeks
  (ISO year-week) within each stratum, 2,000 replicates, fixed seed, percentile
  95% interval. Consecutive days share weather and fleet state, so days are not
  treated as independent.
- **Average-intensity baseline**, per stratum and source: Σ CO₂ / Σ net
  generation over the stratum's train hours (hours with both non-NULL). CISO
  hours in the hydro/other gap are excluded from this ratio, because EIA's net
  generation omits hydro and other there and would overstate intensity.
- **Descriptive divergence (in-sample, not the decision rule).** A stratum is
  reported as diverging when |β − average| ≥ 50 kg CO₂/MWh and the bootstrap
  95% CI of (β − average) excludes zero. This describes the training data only.
  The pre-registered decision rule remains the hold-out scheduler comparison
  above, which is not run until the method is frozen.

## Evaluation (on Hold-out 1, repeated on Hold-out 2)

1. **Scheduler comparison.** For each day, pick the contiguous window of
   **W = 4 hours** minimising marginal-factor CO₂ and, separately, the window
   minimising average-intensity CO₂. Compare realised outcomes.
2. **Predictive check.** How well training-period marginal factors predict
   realised hourly ΔCO₂/Δdemand in the hold-out period.

W = 2, 6 and 8 hours are reported as sensitivity analyses only.

## Decision threshold

The average-based scheduler is **"materially worse"** if the marginal-based
schedule beats it by **≥ 50 kg CO₂ per MWh shifted** **and** the 95%
confidence interval of that difference excludes zero.

## Amendments

- **2026-09-27** — Added "Estimation details" and set the minimum cell size,
  as this document reserved. Evaluation and decision threshold unchanged.
  MISO local time is Central, not EIA's Eastern reporting zone, because most
  MISO load is in Central time.
