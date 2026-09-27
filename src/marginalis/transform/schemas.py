"""Pandera contracts for the frames loaded into Postgres."""

from __future__ import annotations

import pandas as pd
from pandera.pandas import Check, Column, DataFrameSchema

FLAGS = [
    "ok", "interpolated", "missing", "unparseable",
    "nonpositive_nulled", "negative_nulled", "outlier_nulled", "duplicate_conflict",
]

# Any resolution, but always tz-aware UTC.
_ts = Column(
    checks=Check(
        lambda s: isinstance(s.dtype, pd.DatetimeTZDtype) and str(s.dtype.tz) == "UTC",
        element_wise=False,
        name="utc_timestamp",
    ),
    nullable=False,
)
_flag = Column(str, Check.isin(FLAGS))

GRID_HOUR = DataFrameSchema(
    {
        "ba_code": Column(str),
        "ts_utc": _ts,
        "demand_mwh": Column(float, Check.gt(0), nullable=True),
        "demand_forecast_mwh": Column(float, nullable=True),
        "net_generation_mwh": Column(float, Check.gt(0), nullable=True),
        "interchange_mwh": Column(float, nullable=True),
        "temp_c": Column(float, Check.in_range(-50, 60), nullable=True),
        "demand_flag": _flag,
        "net_generation_flag": _flag,
        "interchange_flag": _flag,
        "is_imputed": Column(bool),
    },
    unique=["ba_code", "ts_utc"],
    strict=True,
)

GENERATION_BY_FUEL = DataFrameSchema(
    {
        "ba_code": Column(str),
        "ts_utc": _ts,
        "fuel_code": Column(str),
        "generation_mwh": Column(float, nullable=True),
        "flag": _flag,
        "is_imputed": Column(bool),
    },
    checks=[
        # Fuels that cannot consume power must never be negative after cleaning.
        Check(
            lambda df: ~(df["fuel_code"].isin(["COL", "NG", "OIL", "NUC"])
                         & (df["generation_mwh"] < 0)),
            element_wise=False,
            name="no_negative_thermal",
        )
    ],
    unique=["ba_code", "ts_utc", "fuel_code"],
    strict=True,
)

INTERCHANGE_BY_PAIR = DataFrameSchema(
    {
        "ba_code": Column(str),
        "ts_utc": _ts,
        "to_ba": Column(str),
        "flow_mwh": Column(float, nullable=True),
    },
    unique=["ba_code", "ts_utc", "to_ba"],
    strict=True,
)

HOURLY_EMISSIONS = DataFrameSchema(
    {
        "ba_code": Column(str),
        "ts_utc": _ts,
        "co2_kg_derived": Column(float, Check.ge(0), nullable=True),
        "derived_complete": Column(bool),
        "co2_kg_eia_generated": Column(float, nullable=True),
        "co2_kg_eia_imported": Column(float, nullable=True),
        "co2_kg_eia_exported": Column(float, nullable=True),
        "co2_kg_eia_consumed": Column(float, nullable=True),
    },
    unique=["ba_code", "ts_utc"],
    strict=True,
)

