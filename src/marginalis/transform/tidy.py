"""Raw EIA/Open-Meteo pulls -> typed long tables.

`ts_utc` is the EIA convention throughout: **hour-ending** UTC. Verified by matching
API `period` values against the Grid Monitor workbook, whose local "Hour 24" of
2019-06-30 is UTC 2019-07-01 05:00. Local hour-beginning is therefore
`(ts_utc - 1 hour) AT TIME ZONE tz`.
"""

from __future__ import annotations

import pandas as pd

from marginalis.config import BAS
from marginalis.ingestion import eia, weather

REGION_TYPES = {
    "D": "demand_mwh",
    "DF": "demand_forecast_mwh",
    "NG": "net_generation_mwh",
    "TI": "interchange_mwh",
}


def _ts(period: pd.Series) -> pd.Series:
    return pd.to_datetime(period, format="%Y-%m-%dT%H", utc=True)


def _num(value: pd.Series) -> pd.Series:
    return pd.to_numeric(value, errors="coerce").astype("float64")


def region(ba: str) -> pd.DataFrame:
    """Long: ba_code, ts_utc, series, value (MWh). `value_raw` kept for the reject log."""
    raw = eia.read_raw("region-data", ba)
    return pd.DataFrame(
        {
            "ba_code": raw["respondent"].astype(str),
            "ts_utc": _ts(raw["period"]),
            "series": raw["type"].map(REGION_TYPES).fillna(raw["type"]).astype(str),
            "value": _num(raw["value"]),
            "value_raw": raw["value"],
        }
    )


def fuel(ba: str) -> pd.DataFrame:
    raw = eia.read_raw("fuel-type-data", ba)
    return pd.DataFrame(
        {
            "ba_code": raw["respondent"].astype(str),
            "ts_utc": _ts(raw["period"]),
            "fuel_code": raw["fueltype"].astype(str),
            "value": _num(raw["value"]),
            "value_raw": raw["value"],
        }
    )


def interchange(ba: str) -> pd.DataFrame:
    """Positive = flow out of `ba_code` to `to_ba` (EIA convention; sums to TI)."""
    raw = eia.read_raw("interchange-data", ba)
    return pd.DataFrame(
        {
            "ba_code": raw["fromba"].astype(str),
            "ts_utc": _ts(raw["period"]),
            "to_ba": raw["toba"].astype(str),
            "value": _num(raw["value"]),
            "value_raw": raw["value"],
        }
    )


def temperature(ba: str) -> pd.DataFrame:
    """Simple average of the BA's load-centre cities, shifted to hour-ending.

    Open-Meteo stamps instantaneous temperature at the top of the hour; it is
    assigned to the EIA hour ending at that timestamp.
    """
    raw = weather.read_raw(ba)
    raw["ts_utc"] = pd.to_datetime(raw["time_utc"], utc=True)
    wide = raw.pivot_table(index="ts_utc", columns="city", values="temperature_2m")
    expected = {c.name for c in BAS[ba].weather_cities}
    if set(wide.columns) != expected:
        raise ValueError(f"{ba}: weather cities {sorted(wide.columns)} != {sorted(expected)}")
    return pd.DataFrame(
        {
            "ba_code": ba,
            "ts_utc": wide.index,
            "temp_c": wide.mean(axis=1, skipna=False).to_numpy(),
            "n_cities": wide.notna().sum(axis=1).to_numpy(),
        }
    ).reset_index(drop=True)
