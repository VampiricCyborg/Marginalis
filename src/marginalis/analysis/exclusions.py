"""Row exclusions for the MEF regressions, exactly as fixed in docs/preregistration.md."""

from __future__ import annotations

import pandas as pd

# Exclusion 5: a local day on which EIA reports natural gas as "Other".
GAS_AS_OTHER_MAX_NG_SHARE = 0.05
GAS_AS_OTHER_MIN_OTH_SHARE = 0.20

# CISO hydro/other absent from EIA net generation (see reports/data_quality.md).
CISO_HYDRO_GAP = (pd.Timestamp("2019-10-01 21:00", tz="UTC"), pd.Timestamp("2020-08-24 18:00", tz="UTC"))

SPECS = {"demand": "d_demand_mwh", "fossil_gen": "d_fossil_generation_mwh"}
SOURCES = {"derived": "d_co2_kg_derived", "eia": "d_co2_kg_eia_generated"}
LEVEL_CO2 = {"derived": "co2_kg_derived", "eia": "co2_kg_eia_generated"}


def gas_as_other_days(fuel: pd.DataFrame, hours: pd.DataFrame) -> pd.DataFrame:
    """(ba_code, local_date) pairs hit by exclusion 5."""
    w = fuel[fuel["fuel_code"].isin(["NG", "OTH"])].pivot_table(
        index=["ba_code", "ts_utc"], columns="fuel_code", values="generation_mwh"
    )
    w = w.join(hours.set_index(["ba_code", "ts_utc"])[["net_generation_mwh", "local_date"]])
    hit = (w["NG"] < GAS_AS_OTHER_MAX_NG_SHARE * w["net_generation_mwh"]) & (
        w["OTH"] > GAS_AS_OTHER_MIN_OTH_SHARE * w["net_generation_mwh"]
    )
    days = w[hit].reset_index()[["ba_code", "local_date"]].drop_duplicates()
    return days.sort_values(["ba_code", "local_date"]).reset_index(drop=True)


def on_days(frame: pd.DataFrame, days: pd.DataFrame) -> pd.Series:
    """Boolean per row of `frame`: its (ba_code, local_date) is in `days`."""
    key = pd.MultiIndex.from_frame(frame[["ba_code", "local_date"]])
    return pd.Series(key.isin(pd.MultiIndex.from_frame(days)), index=frame.index)


def usable_deltas(delta: pd.DataFrame, bad: pd.Series, spec: str, source: str) -> pd.Series:
    """Exclusions 1-5 for one (spec, source). `bad` is aligned to `delta` rows (the hour
    itself); the previous hour's status is taken by shifting within each BA."""
    prev_bad = bad.groupby(delta["ba_code"]).shift(1, fill_value=False).astype(bool)
    ok = (
        delta["consecutive"].fillna(False).astype(bool)
        & ~delta["imputed_either"].fillna(True).astype(bool)
        & delta[SPECS[spec]].notna()
        & delta[SOURCES[source]].notna()
        & ~bad
        & ~prev_bad
    )
    if source == "derived":
        ok &= delta["derived_complete_both"].fillna(False).astype(bool)
    return ok


def usable_levels(hours: pd.DataFrame, bad: pd.Series, source: str) -> pd.Series:
    """Hours entering the average-intensity baseline."""
    ok = hours[LEVEL_CO2[source]].notna() & hours["net_generation_mwh"].notna() & ~bad
    if source == "derived":
        ok &= hours["derived_complete"].fillna(False).astype(bool)
    gap = (
        (hours["ba_code"] == "CISO")
        & (hours["ts_utc"] > CISO_HYDRO_GAP[0])
        & (hours["ts_utc"] <= CISO_HYDRO_GAP[1])
    )
    return ok & ~gap
