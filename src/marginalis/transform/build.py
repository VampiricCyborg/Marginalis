"""Tidy -> clean -> validate -> load, one BA at a time."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
import psycopg

from marginalis.config import BAS, DATA_END, DATA_START, SPLITS
from marginalis.emission_factors import FACTOR_SOURCE, fuel_factors
from marginalis.ingestion import grid_monitor_xlsx
from marginalis.transform import schemas, tidy
from marginalis.transform.clean import (
    THERMAL_FUELS,
    THERMAL_NEG_TOLERANCE,
    POSITIVE_SERIES,
    QualityLog,
    clean_series,
    dedupe,
    hourly_index,
)

log = logging.getLogger(__name__)

# EIA-930 reference table "Energy Sources".
FUELS = {
    "COL": "Coal", "NG": "Natural gas", "OIL": "Petroleum", "NUC": "Nuclear",
    "WAT": "Hydro and pumped storage", "SUN": "Solar", "WND": "Wind", "GEO": "Geothermal",
    "OTH": "Other", "UNK": "Unknown",
    "BAT": "Battery storage", "SNB": "Solar with integrated battery storage",
    "WNB": "Wind with integrated battery storage", "PS": "Pumped storage",
    "OES": "Other energy storage", "UES": "Unknown energy storage",
}
FOSSIL = ("COL", "NG", "OIL")
STORAGE = ("BAT", "PS", "OES", "UES")


@dataclass
class BuiltBA:
    grid_hour: pd.DataFrame
    generation_by_fuel: pd.DataFrame
    interchange_by_pair: pd.DataFrame
    hourly_emissions: pd.DataFrame
    quality: pd.DataFrame


def _grid(ba: str, idx: pd.DatetimeIndex, qlog: QualityLog) -> pd.DataFrame:
    reg = tidy.region(ba)
    reg = reg[reg["ts_utc"].isin(idx)]
    reg = dedupe(reg, ["ts_utc", "series"], qlog, ba, "grid_hour")
    out = pd.DataFrame(index=idx)
    for series in tidy.REGION_TYPES.values():
        part = reg[reg["series"] == series].set_index("ts_utc").reindex(idx)
        values, flag = clean_series(
            part["value"], part["value_raw"], name=series, ba=ba, table="grid_hour", log=qlog,
            positive=series in POSITIVE_SERIES or series == "demand_forecast_mwh",
            outliers=series in POSITIVE_SERIES,
            signed=series == "interchange_mwh",
        )
        out[series] = values
        out[series.removesuffix("_mwh") + "_flag"] = flag
    temp = tidy.temperature(ba).set_index("ts_utc").reindex(idx)
    out["temp_c"] = temp["temp_c"]
    qlog.add(ba, "grid_hour", "temp_c", "missing", idx[out["temp_c"].isna()])
    out["is_imputed"] = (
        out[["demand_flag", "net_generation_flag", "interchange_flag"]] == "interpolated"
    ).any(axis=1)
    out = out.drop(columns="demand_forecast_flag").reset_index()
    out.insert(0, "ba_code", ba)
    return out


def _fuel(ba: str, idx: pd.DatetimeIndex, qlog: QualityLog, net_gen: pd.Series) -> pd.DataFrame:
    fu = tidy.fuel(ba)
    fu = fu[fu["ts_utc"].isin(idx)]
    unknown = set(fu["fuel_code"]) - set(FUELS)
    if unknown:
        raise ValueError(f"{ba}: unknown fuel codes {sorted(unknown)}")
    fu = dedupe(fu, ["ts_utc", "fuel_code"], qlog, ba, "generation_by_fuel")
    frames = []
    for code, part in fu.groupby("fuel_code"):
        # Expected only between the fuel's first and last report.
        span = idx[(idx >= part["ts_utc"].min()) & (idx <= part["ts_utc"].max())]
        part = part.set_index("ts_utc").reindex(span)
        values, flag = clean_series(
            part["value"], part["value_raw"], name=code, ba=ba, table="generation_by_fuel",
            log=qlog,
            neg_limit=THERMAL_NEG_TOLERANCE * net_gen if code in THERMAL_FUELS else None,
        )
        frames.append(
            pd.DataFrame({"ba_code": ba, "ts_utc": span, "fuel_code": code,
                          "generation_mwh": values.to_numpy(), "flag": flag.to_numpy(),
                          "is_imputed": (flag == "interpolated").to_numpy()})
        )
    return pd.concat(frames, ignore_index=True)


def _interchange(ba: str, idx: pd.DatetimeIndex, qlog: QualityLog) -> pd.DataFrame:
    ic = tidy.interchange(ba)
    ic = ic[ic["ts_utc"].isin(idx)]
    ic = dedupe(ic, ["ts_utc", "to_ba"], qlog, ba, "interchange_by_pair")
    return pd.DataFrame(
        {"ba_code": ba, "ts_utc": ic["ts_utc"], "to_ba": ic["to_ba"], "flow_mwh": ic["value"]}
    ).reset_index(drop=True)


def _emissions(ba: str, idx: pd.DatetimeIndex, gen: pd.DataFrame) -> pd.DataFrame:
    rates = fuel_factors()
    wide = gen[gen["fuel_code"].isin(FOSSIL)].pivot(
        index="ts_utc", columns="fuel_code", values="generation_mwh"
    ).reindex(idx)
    # A fossil fuel is expected in an hour if it falls inside that fuel's reporting span.
    spans = gen[gen["fuel_code"].isin(FOSSIL)].groupby("fuel_code")["ts_utc"].agg(["min", "max"])
    expected = pd.DataFrame(
        {f: (idx >= spans.at[f, "min"]) & (idx <= spans.at[f, "max"]) for f in spans.index},
        index=idx,
    )
    complete = (wide.notna() | ~expected).all(axis=1)
    # Negative net generation (station service at idle units) burns no fuel: zero CO2.
    co2 = sum(wide[f].fillna(0).clip(lower=0) * rates[f] for f in wide.columns)
    out = pd.DataFrame(
        {"ba_code": ba, "ts_utc": idx,
         "co2_kg_derived": co2.where(complete).to_numpy(),
         "derived_complete": complete.to_numpy()}
    )
    try:
        eia = pd.read_parquet(grid_monitor_xlsx.build(ba))
    except FileNotFoundError:
        log.warning("%s: no Grid Monitor workbook; EIA CO2 columns left NULL", ba)
        eia = pd.DataFrame(columns=["ts_utc"])
    eia = eia.drop_duplicates("ts_utc").set_index("ts_utc").reindex(idx)
    for col in ("generated", "imported", "exported", "consumed"):
        src = f"co2_t_{col}"
        out[f"co2_kg_eia_{col}"] = (
            eia[src].astype(float).to_numpy() * 1000 if src in eia else np.nan
        )
    return out


def build_ba(ba: str) -> BuiltBA:
    idx = hourly_index(pd.Timestamp(DATA_START), pd.Timestamp(DATA_END))
    qlog = QualityLog()
    grid = schemas.GRID_HOUR.validate(_grid(ba, idx, qlog))
    net_gen = grid.set_index("ts_utc")["net_generation_mwh"]
    gen = schemas.GENERATION_BY_FUEL.validate(_fuel(ba, idx, qlog, net_gen))
    ic = schemas.INTERCHANGE_BY_PAIR.validate(_interchange(ba, idx, qlog))
    em = schemas.HOURLY_EMISSIONS.validate(_emissions(ba, idx, gen))
    return BuiltBA(grid, gen, ic, em, qlog.frame())


# --- Loading --------------------------------------------------------------------------

def load_reference(conn: psycopg.Connection) -> None:
    rates = fuel_factors()
    with conn.transaction():
        for b in BAS.values():
            conn.execute(
                "INSERT INTO balancing_authority VALUES (%s, %s, %s, %s) ON CONFLICT (ba_code) DO "
                "UPDATE SET ba_name = EXCLUDED.ba_name, timezone = EXCLUDED.timezone, "
                "region = EXCLUDED.region",
                (b.code, b.name, b.timezone, b.region),
            )
        for code, name in FUELS.items():
            rate = rates.get(code)
            conn.execute(
                "INSERT INTO fuel_type VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (fuel_code) DO "
                "UPDATE SET fuel_name = EXCLUDED.fuel_name, is_fossil = EXCLUDED.is_fossil, "
                "is_storage = EXCLUDED.is_storage, co2_kg_per_mwh = EXCLUDED.co2_kg_per_mwh, "
                "factor_source = EXCLUDED.factor_source",
                (code, name, code in FOSSIL, code in STORAGE, rate,
                 FACTOR_SOURCE if rate is not None else None),
            )
        conn.execute("DELETE FROM study_split")
        for s in SPLITS:
            conn.execute("INSERT INTO study_split VALUES (%s, %s, %s)", (s.name, s.start, s.end))


def _copy(conn: psycopg.Connection, table: str, df: pd.DataFrame) -> None:
    cols = list(df.columns)
    records = df.astype(object).where(df.notna(), None).itertuples(index=False, name=None)
    with conn.cursor().copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
        for rec in records:
            cp.write_row(rec)


def load_ba(conn: psycopg.Connection, ba: str, built: BuiltBA) -> None:
    with conn.transaction():
        for table in ("hourly_emissions", "interchange_by_pair", "generation_by_fuel",
                      "grid_hour", "quality_log"):
            conn.execute(f"DELETE FROM {table} WHERE ba_code = %s", (ba,))
        _copy(conn, "grid_hour", built.grid_hour)
        _copy(conn, "generation_by_fuel", built.generation_by_fuel)
        _copy(conn, "interchange_by_pair", built.interchange_by_pair)
        _copy(conn, "hourly_emissions", built.hourly_emissions)
        _copy(conn, "quality_log", built.quality)
    log.info("%s loaded: %d hours", ba, len(built.grid_hour))
