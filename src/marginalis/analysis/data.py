"""Train-only data access. The only way analysis code reads the database."""

from __future__ import annotations

import pandas as pd

from marginalis import db
from marginalis.config import TRAIN, require_split

TRAIN_VIEWS = ("v_hour_train", "v_hour_delta_train")


def read_view(view: str, ba: str | None = None) -> pd.DataFrame:
    if view not in TRAIN_VIEWS:
        raise ValueError(f"analysis may only read {TRAIN_VIEWS}, not {view!r}")
    require_split(TRAIN)
    sql = f"SELECT * FROM {view}" + (" WHERE ba_code = %s" if ba else "") + " ORDER BY ba_code, ts_utc"
    with db.connect() as conn:
        cur = conn.execute(sql, (ba,) if ba else None)
        df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    if (df["split_name"] != "train").any():
        raise AssertionError(f"{view} returned non-train rows")
    df["local_date"] = pd.to_datetime(df["local_date"])
    return df


def read_fuel_mix(ba: str | None = None) -> pd.DataFrame:
    """Hourly generation by fuel for train hours (joined through v_hour_train)."""
    require_split(TRAIN)
    sql = """
        SELECT g.ba_code, g.ts_utc, v.local_date, v.local_hour, g.fuel_code, g.generation_mwh
        FROM generation_by_fuel g
        JOIN v_hour_train v USING (ba_code, ts_utc)
    """ + (" WHERE g.ba_code = %s" if ba else "")
    with db.connect() as conn:
        cur = conn.execute(sql, (ba,) if ba else None)
        df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    df["local_date"] = pd.to_datetime(df["local_date"])
    return df
