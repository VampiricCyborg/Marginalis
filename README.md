# Marginalis

*When you run flexible load matters. The obvious answer is often wrong.*

Most "run it when the grid is green" advice uses **average** carbon intensity.
The quantity that matters for a scheduling decision is the **marginal**
emissions factor: how much CO₂ changes when one more MWh of load is added.
Marginalis estimates marginal emissions factors from public EIA-930 hourly data
for three US balancing authorities (ERCOT, CAISO, MISO), 2019-07 → 2026-08,
and measures how often scheduling by average intensity picks a worse hour.

> Status: pipeline under construction. No results yet.

## Methodology

- **Data.** EIA-930 hourly demand, net generation, interchange and generation by
  fuel type, stored in UTC; local time is derived in the database. Hourly
  temperature from Open-Meteo, simple average of four load centres per BA.
- **Emissions.** Two series, compared against each other:
  - *Derived* — generation by fuel × a published CO₂ rate per fuel (sources in
    [`data/README.md`](data/README.md)).
  - *Published* — EIA's own hourly CO₂ estimates from the Grid Monitor files.
- **Estimator.** First-difference regression of ΔCO₂ on Δdemand within strata
  (Hawkes 2010; Siler-Evans, Azevedo & Morgan 2012). Robustness check on
  Δ(in-BA fossil generation). Net-import share reported per BA.
- **Validation.** Train 2019-07 → 2024-12; hold out 2025, with 2026 YTD as a
  second check. Evaluation criteria are fixed in
  [`docs/preregistration.md`](docs/preregistration.md) before any hold-out read.

### What the derived marginal factors mean

Because the derived series uses **one CO₂ rate per fuel**, its marginal factors
reflect **which fuel ramps** from hour to hour, **not the efficiency of the
plants that ramp**. A modern combined-cycle unit and an old gas peaker get the
same rate. Plant-level CEMS data (EPA CAMPD) would address this and is a
stretch goal.
