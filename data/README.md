# Data sources

All raw pulls land in `data/raw/` (gitignored, immutable) and are reproducible
with `uv run marginalis ingest`. Small reference tables used to derive emission
factors are committed in `data/reference/`.

Access date for every source below: **2026-09-27**.

## EIA-930 Hourly Electric Grid Monitor

- API v2, routes `electricity/rto/region-data`, `fuel-type-data`,
  `interchange-data`, hourly UTC. <https://www.eia.gov/opendata/>
- Reference tables (BA time zones, energy-source codes, dates new sources
  begin): <https://www.eia.gov/electricity/930-content/EIA930_Reference_Tables.xlsx>
  - Time zones used for local-time derivation: ERCO Central, CISO Pacific,
    MISO **Eastern** (EIA's reporting zone, although MISO's footprint is
    largely Central).
  - Storage categories (BAT, SNB, WNB, PS, OES, UES) appear partway through
    the sample: ERCO from 2024-10-23, MISO from 2025-01-15; CISO not yet.
- Public domain (U.S. government work).

## Emission factors (Option A: derived)

One CO₂ rate per fuel:

```
rate (kg CO₂/MWh) = CO₂ coefficient (kg/MMBtu) × heat rate (Btu/kWh) / 1000
```

| Fuel | Coefficient (kg CO₂/MMBtu) | Heat rate, 2019–2024 mean (Btu/kWh) | Rate (kg CO₂/MWh) |
|---|---|---|---|
| COL | 95.99 (coal, all types) | 10,666.7 | 1,023.9 |
| NG | 52.91 | 7,725.7 | 408.8 |
| OIL | 74.14 (distillate fuel oil) | 11,253.2 | 834.3 |

Computed by `src/marginalis/emission_factors.py` from the CSVs in
`data/reference/`.

- **CO₂ coefficients:** EIA, *Carbon Dioxide Emissions Coefficients*
  (values from EPA's GHG Inventory 1990–2022, used by EIA for 2023 onward).
  <https://www.eia.gov/environment/emissions/co2_vol_mass.php>
  → `data/reference/co2_coefficients.csv`
- **Heat rates:** EIA, *Electric Power Annual*, Table 8.1, "Average Operating
  Heat Rate for Selected Energy Sources, 2014 through 2024". Utility and IPP
  electric-power plants; CHP excluded.
  <https://www.eia.gov/electricity/annual/html/epa_08_01.html>
  → `data/reference/heat_rates.csv`
- **Cross-check:** EPA eGRID2023 (released Jan 2025, rev. 2 Jun 2025), BA and
  US annual CO₂ output emission rates by fuel (fields `BACCO2RT`, `BAOCO2RT`,
  `BAGCO2RT`, `USxCO2RT`, kg/MWh, metric workbook).
  Data: <https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_metric_rev2.xlsx>
  Technical guide: <https://www.epa.gov/system/files/documents/2025-01/egrid2023_technical_guide.pdf>
  → `data/reference/egrid2023_fuel_rates.csv`

| Scope | COL | OIL | NG |
|---|---|---|---|
| Derived (this project) | 1,023.9 | 834.3 | 408.8 |
| eGRID2023 US | 1,010.6 | 705.2 | 407.8 |
| eGRID2023 ERCO | 1,054.5 | 1,312.9 | 393.5 |
| eGRID2023 CISO | 514.1 | 817.6 | 391.1 |
| eGRID2023 MISO | 993.9 | 85.9 | 391.5 |

Coal and gas agree with eGRID's national rates within 1.3%. BA-level oil (and
CISO coal) rates are volatile because those fuels are a tiny share of the BA's
generation, which is why a national rate is used.

### Choices and limitations

- **Heat rate is fixed across the sample** (2019–2024 mean) so that the derived
  series has no step changes at year boundaries that would contaminate
  first differences. 2025 heat rates are not yet published.
- **Oil uses the distillate coefficient.** Oil-fired generation in these BAs is
  mostly combustion turbines burning distillate; residual oil (75.09 kg/MMBtu)
  would change the rate by about 1%.
- **Non-emitting:** NUC, WAT, SUN, WND, GEO and all storage categories.
  Storage discharge carries the emissions of the charging energy, which this
  method does not track.
- **OTH and UNK are not assigned a rate** (treated as 0 in the derived series,
  flagged). EIA's "Other" mixes biomass, waste and miscellaneous sources with
  no single defensible rate.
- **What this means for marginal factors:** with one rate per fuel, derived
  marginal factors reflect **which fuel ramps**, not **the efficiency of the
  plants that ramp**. A combined-cycle unit and a gas peaker get the same rate.

## Weather

Open-Meteo Historical Weather API, hourly `temperature_2m`, UTC.
<https://open-meteo.com/en/docs/historical-weather-api> (CC BY 4.0).
Per-BA series is the simple average of four load centres:

| BA | Cities |
|---|---|
| ERCO | Houston, Dallas, San Antonio, Austin |
| CISO | Los Angeles, San Francisco, Sacramento, San Diego |
| MISO | Minneapolis, Detroit, St. Louis, New Orleans |
