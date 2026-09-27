"""Option A emission factors: one CO2 rate per fuel, in kg/MWh.

rate = EIA CO2 coefficient (kg/MMBtu) x EIA average operating heat rate (Btu/kWh) / 1000,
with the heat rate averaged over HEAT_RATE_YEARS. Inputs and citations: data/README.md.
"""

from __future__ import annotations

import pandas as pd

from marginalis.config import DATA_DIR

REFERENCE_DIR = DATA_DIR / "reference"
HEAT_RATE_YEARS = range(2019, 2025)
NON_EMITTING = ("NUC", "WAT", "SUN", "WND", "GEO", "BAT", "SNB", "WNB", "PS", "OES", "UES")
FACTOR_SOURCE = (
    "EIA CO2 coefficients (co2_vol_mass) x EIA Electric Power Annual Table 8.1 "
    "heat rate, 2019-2024 mean"
)


def fuel_factors() -> dict[str, float]:
    coef = pd.read_csv(REFERENCE_DIR / "co2_coefficients.csv").set_index("fuel_code")
    hr = pd.read_csv(REFERENCE_DIR / "heat_rates.csv").set_index("year")
    hr = hr.loc[list(HEAT_RATE_YEARS)].mean()
    return {
        fuel: round(float(coef.at[fuel, "kg_co2_per_mmbtu"] * hr[fuel] / 1000), 1)
        for fuel in coef.index
    }


if __name__ == "__main__":
    for fuel, rate in fuel_factors().items():
        print(f"{fuel}: {rate} kg CO2/MWh")
