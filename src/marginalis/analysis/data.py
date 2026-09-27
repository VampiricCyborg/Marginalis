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


def read_split(kind: str, split) -> pd.DataFrame:
    """Rows of one split: kind 'hour' (v_hour), 'delta' (v_hour_delta) or 'fuel'.

    Held-out splits are refused unless the method is frozen. For 'delta', each BA's first
    row is dropped, because its previous hour belongs to the preceding split.
    """
    require_split(split)
    if kind == "fuel":
        sql = """
            SELECT g.ba_code, g.ts_utc, v.local_date, v.local_hour, g.fuel_code, g.generation_mwh
            FROM generation_by_fuel g JOIN v_hour v USING (ba_code, ts_utc)
            WHERE v.split_name = %s ORDER BY g.ba_code, g.ts_utc"""
    else:
        view = {"hour": "v_hour", "delta": "v_hour_delta"}[kind]
        sql = f"SELECT * FROM {view} WHERE split_name = %s ORDER BY ba_code, ts_utc"
    with db.connect() as conn:
        cur = conn.execute(sql, (split.name,))
        df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    df["local_date"] = pd.to_datetime(df["local_date"])
    if kind == "delta":
        first = df.groupby("ba_code")["ts_utc"].transform("min") == df["ts_utc"]
        df = df[~first].reset_index(drop=True)
    return df


def read_mef_profile() -> pd.DataFrame:
    with db.connect() as conn:
        cur = conn.execute("SELECT * FROM mef_profile ORDER BY 1, 2, 3, 4, 5")
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


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
