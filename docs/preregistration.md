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
  when the strata code is written.

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

_None._
