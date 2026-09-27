"""Optimal run window: the single definition shared by the API and the scheduler evaluation.

Given an hourly factor series (kg CO2/MWh, marginal or average), find the contiguous
block of `duration_h` hours that minimises total CO2 for a load spread evenly across it.

Semantics, fixed here so every caller agrees:

- **Timestamps.** The series is indexed by tz-aware, hour-ENDING UTC stamps (the EIA
  convention used throughout the database). A window is reported by the time it
  covers: `start` = stamp of its first hour - 1h, `end` = stamp of its last hour.
- **Gaps.** A window is valid only if every one of its hours is present with a
  non-NaN factor. Nothing is interpolated here; missing hours make every window
  that touches them ineligible.
- **Bounds.** With `earliest`/`latest`, a window must lie entirely inside
  [earliest, latest] (covered time, inclusive at both ends).
- **Ties.** Windows whose totals are equal within `TIE_TOLERANCE` kg/MWh (on the
  mean factor) tie, and the earliest-starting window wins.
- **No valid window** returns None; callers decide what that means.
- **Days** (`best_window_per_day`) are local calendar days in the given IANA zone,
  and a window must lie entirely within its day. DST days have 23 or 25 hours.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

HOUR = pd.Timedelta(hours=1)
TIE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class Window:
    start: pd.Timestamp  # covered-time start (UTC)
    end: pd.Timestamp  # covered-time end (UTC) = hour-ending stamp of the last hour
    duration_h: int
    mean_factor_kg_per_mwh: float

    def co2_kg(self, load_mwh: float) -> float:
        """CO2 for `load_mwh` spread evenly across the window's hours."""
        return self.mean_factor_kg_per_mwh * load_mwh

    @property
    def hours(self) -> pd.DatetimeIndex:
        """Hour-ending stamps of the hours in the window."""
        return pd.date_range(self.start + HOUR, self.end, freq="h")


def _validate(factors: pd.Series, duration_h: int) -> pd.Series:
    if not isinstance(duration_h, (int, np.integer)) or duration_h < 1:
        raise ValueError(f"duration_h must be a positive integer, got {duration_h!r}")
    idx = factors.index
    if not isinstance(idx, pd.DatetimeIndex) or idx.tz is None:
        raise ValueError("factors must be indexed by tz-aware timestamps")
    if not idx.is_unique:
        raise ValueError("factors index has duplicate timestamps")
    if len(idx) and ((idx - idx.floor("h")) != pd.Timedelta(0)).any():
        raise ValueError("factors index must be on whole hours")
    return factors.astype(float).tz_convert("UTC").sort_index()


def candidate_windows(
    factors: pd.Series,
    duration_h: int,
    earliest: pd.Timestamp | None = None,
    latest: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Every valid window, ordered by start: columns start, end, mean_factor_kg_per_mwh."""
    s = _validate(factors, duration_h)
    if earliest is not None:
        s = s[s.index - HOUR >= pd.Timestamp(earliest)]
    if latest is not None:
        s = s[s.index <= pd.Timestamp(latest)]
    empty = pd.DataFrame(columns=["start", "end", "mean_factor_kg_per_mwh"])
    if s.empty:
        return empty
    full = s.reindex(pd.date_range(s.index[0], s.index[-1], freq="h"))
    # min_periods=duration_h: any missing/NaN hour makes the window NaN (ineligible).
    total = full.rolling(duration_h, min_periods=duration_h).sum().dropna()
    if total.empty:
        return empty
    return pd.DataFrame(
        {
            "start": total.index - duration_h * HOUR,
            "end": total.index,
            "mean_factor_kg_per_mwh": (total / duration_h).to_numpy(),
        }
    ).reset_index(drop=True)


def _pick(cands: pd.DataFrame, duration_h: int) -> Window | None:
    if cands.empty:
        return None
    means = cands["mean_factor_kg_per_mwh"].to_numpy()
    best = means.min()
    i = int(np.flatnonzero(means <= best + TIE_TOLERANCE)[0])  # earliest among ties
    row = cands.iloc[i]
    return Window(row["start"], row["end"], duration_h, float(row["mean_factor_kg_per_mwh"]))


def best_window(
    factors: pd.Series,
    duration_h: int,
    earliest: pd.Timestamp | None = None,
    latest: pd.Timestamp | None = None,
) -> Window | None:
    """Lowest-CO2 contiguous window, or None if no window is valid."""
    return _pick(candidate_windows(factors, duration_h, earliest, latest), duration_h)


def best_window_per_day(factors: pd.Series, duration_h: int, tz: str) -> pd.DataFrame:
    """Best window within each local calendar day.

    Returns one row per local date that has any data: local_date, start, end,
    mean_factor_kg_per_mwh (start/end/mean are NaT/NaN when the day has no valid window).
    """
    s = _validate(factors, duration_h)
    local_date = (s.index - HOUR).tz_convert(tz).date
    rows = []
    for day, part in s.groupby(local_date):
        w = _pick(candidate_windows(part, duration_h), duration_h)
        rows.append(
            {
                "local_date": day,
                "start": w.start if w else pd.NaT,
                "end": w.end if w else pd.NaT,
                "mean_factor_kg_per_mwh": w.mean_factor_kg_per_mwh if w else np.nan,
            }
        )
    return pd.DataFrame(rows, columns=["local_date", "start", "end", "mean_factor_kg_per_mwh"])
