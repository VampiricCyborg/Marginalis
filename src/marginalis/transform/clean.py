"""Cleaning rules. Thresholds are fixed here, up front, and are never tuned on held-out data.

Rules run in this order for each hourly series, and every value they touch is counted:

1. duplicate_dropped   identical duplicate rows for the same (BA, hour, series): keep one
   duplicate_conflict  duplicates that disagree: value nulled
2. unparseable         non-numeric value from the source: nulled
3. nonpositive_nulled  demand or net generation <= 0
   negative_nulled     negative COL/NG/OIL/NUC generation larger in magnitude than
                       THERMAL_NEG_TOLERANCE of the BA's net generation that hour.
                       Smaller negatives are station-service load at idle units
                       (e.g. CISO coal, a 2020 CISO nuclear outage) and are kept.
4. outlier_nulled      demand or net generation more than OUTLIER_RATIO away from the
                       centred rolling median over OUTLIER_WINDOW hours
5. interpolated        gaps of <= MAX_INTERP_GAP hours between two valid values:
                       linear interpolation
   missing             every other hour without a value (left NULL)

Signed series (interchange) are exempt from sign rules. Small negatives from SUN, WND, WAT and OTH (station load at night) and negatives from
storage (charging) are kept as reported; they are counted as `negative_kept`.
Fuel series are only expected between a fuel's first and last report, because EIA added
storage categories partway through the sample.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MAX_INTERP_GAP = 2
OUTLIER_WINDOW = 24
OUTLIER_RATIO = 0.5
THERMAL_FUELS = frozenset({"COL", "NG", "OIL", "NUC"})
THERMAL_NEG_TOLERANCE = 0.01
POSITIVE_SERIES = frozenset({"demand_mwh", "net_generation_mwh"})


@dataclass
class QualityLog:
    rows: list[dict] = field(default_factory=list)

    def add(self, ba: str, table: str, column: str, rule: str, ts: pd.Series) -> None:
        if len(ts) == 0:
            return
        # Year of the hour's start (stamps are hour-ending).
        years = (pd.DatetimeIndex(ts) - pd.Timedelta(hours=1)).year
        for year, n in pd.Series(1, index=years).groupby(level=0).sum().items():
            self.rows.append(
                {"ba_code": ba, "table_name": table, "column_name": column,
                 "rule": rule, "year": int(year), "n_rows": int(n)}
            )

    def frame(self) -> pd.DataFrame:
        cols = ["ba_code", "table_name", "column_name", "rule", "year", "n_rows"]
        df = pd.DataFrame(self.rows, columns=cols)
        return df.groupby(cols[:-1], as_index=False)["n_rows"].sum()


def hourly_index(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Hour-ending stamps for the time window [start, end): (start, end]."""
    return pd.date_range(start + pd.Timedelta(hours=1), end, freq="h", tz="UTC", name="ts_utc")


def dedupe(df: pd.DataFrame, keys: list[str], log: QualityLog, ba: str, table: str) -> pd.DataFrame:
    """Rule 1. `keys` identifies one observation; the last key names the series column."""
    dup = df.duplicated(keys, keep=False)
    if not dup.any():
        return df
    grp = df[dup].groupby(keys, dropna=False)["value"]
    conflict = grp.transform("nunique", dropna=False) > 1
    conflict_idx = conflict[conflict].index
    series_col = keys[-1]
    for name, part in df.loc[dup].groupby(series_col):
        part_conflict = part.index.isin(conflict_idx)
        extra = part[~part_conflict].duplicated(keys)
        log.add(ba, table, str(name), "duplicate_dropped", part[~part_conflict][extra]["ts_utc"])
        log.add(ba, table, str(name), "duplicate_conflict",
                part[part_conflict].drop_duplicates(keys)["ts_utc"])
    df = df.copy()
    df.loc[conflict_idx, "value"] = np.nan
    return df.drop_duplicates(keys, keep="first")


def clean_series(
    s: pd.Series,
    raw: pd.Series,
    *,
    name: str,
    ba: str,
    table: str,
    log: QualityLog,
    positive: bool = False,
    neg_limit: pd.Series | None = None,
    outliers: bool = False,
    signed: bool = False,
) -> tuple[pd.Series, pd.Series]:
    """Rules 2-5 on one series already reindexed to the full hourly grid.

    Returns (cleaned values, flag per hour).
    """
    s = s.astype(float).copy()
    flag = pd.Series("ok", index=s.index, dtype=object)

    def null(mask: pd.Series, rule: str) -> None:
        mask = mask & s.notna()
        log.add(ba, table, name, rule, s.index[mask])
        s[mask] = np.nan
        flag[mask] = rule

    bad = raw.notna() & (raw.astype("string").str.strip() != "") & s.isna()
    log.add(ba, table, name, "unparseable", s.index[bad])
    flag[bad] = "unparseable"
    if positive:
        null(s <= 0, "nonpositive_nulled")
    if neg_limit is not None:
        null(s < -neg_limit.reindex(s.index).abs().fillna(0), "negative_nulled")
    if not (positive or signed):
        neg = s < 0
        log.add(ba, table, name, "negative_kept", s.index[neg])
    if outliers:
        med = s.rolling(OUTLIER_WINDOW + 1, center=True, min_periods=OUTLIER_WINDOW // 2).median()
        null((s / med - 1).abs() > OUTLIER_RATIO, "outlier_nulled")

    # Rule 5: interpolate short interior gaps only.
    isna = s.isna()
    run_id = (isna != isna.shift()).cumsum()
    run_len = isna.groupby(run_id).transform("sum")
    interior = s.ffill().notna() & s.bfill().notna()
    fill = isna & interior & (run_len <= MAX_INTERP_GAP)
    s = s.where(~fill, s.interpolate(method="time", limit_area="inside"))
    log.add(ba, table, name, "interpolated", s.index[fill])
    flag[fill] = "interpolated"
    still = s.isna()
    log.add(ba, table, name, "missing", s.index[still & (flag == "ok")])
    flag[still & (flag == "ok")] = "missing"
    return s, flag
