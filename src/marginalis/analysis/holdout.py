"""Pre-registered confirmatory evaluation on the hold-out splits.

Implements "Evaluation" and "Evaluation details" in docs/preregistration.md. Nothing in
mef_profile, the estimator or the exclusion rules is changed here: the training profile
is read from the database as stored, and the frozen exclusions are applied to hold-out rows.

Realised gap for one BA x source x period:
    G = mean_d [ mean_{h in A_d} bH_s(h) - mean_{h in M_d} bH_s(h) ]  =  sum_s w_s * bH_s
where A_d / M_d are the average / marginal scheduler's windows on day d, s(h) is the
month x local-hour stratum of hour h, and bH_s is the hold-out OLS slope in stratum s.
Because G is linear in the stratum slopes, the predicted gap is the same weights applied
to the training slopes, and the bootstrap re-estimates every bH_s per replicate.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from marginalis.analysis import exclusions as ex
from marginalis.analysis import mef
from marginalis.config import BAS
from marginalis.schedule import best_window_per_day

W_PRIMARY = 4
W_SENSITIVITY = (2, 6, 8)
THRESHOLD_KG = 50.0
N_BOOT = 2000
SEED = 20260927


def factor_series(hours: pd.DataFrame, prof: pd.DataFrame, col: str) -> pd.Series:
    """Per hold-out hour (hour-ending UTC index), the profile value for its month x local hour."""
    lut = prof.set_index(["month", "local_hour"])[col]
    key = pd.MultiIndex.from_arrays([hours["local_start"].dt.month, hours["local_hour"]])
    return pd.Series(lut.reindex(key).to_numpy(), index=pd.DatetimeIndex(hours["ts_utc"]).tz_convert("UTC"))


def complete_days(hours: pd.DataFrame, tz: str) -> pd.DataFrame:
    """Only local days fully inside the split (23/24/25 hours on DST days).

    Split boundaries are UTC, so each split starts and ends on a partial local day. A
    scheduler choosing among a few hours there is not the daily choice being evaluated.
    """
    dates = pd.to_datetime(hours["local_date"])
    start = dates.dt.tz_localize(tz)
    length = ((dates + pd.Timedelta(days=1)).dt.tz_localize(tz) - start) / pd.Timedelta(hours=1)
    n = hours.groupby(dates)["ts_utc"].transform("size")
    return hours[n.to_numpy() == length.to_numpy()]


def daily_windows(hours: pd.DataFrame, prof: pd.DataFrame, tz: str, w: int) -> pd.DataFrame:
    """One row per complete local day with both schedulers' windows (days lacking either dropped)."""
    hours = complete_days(hours, tz)
    m = best_window_per_day(factor_series(hours, prof, "mef_kg_per_mwh"), w, tz)
    a = best_window_per_day(factor_series(hours, prof, "avg_intensity_kg_per_mwh"), w, tz)
    out = m.merge(a, on="local_date", suffixes=("_m", "_a")).dropna(subset=["start_m", "start_a"])
    return out.reset_index(drop=True)


def stratum_weights(hours: pd.DataFrame, windows: pd.DataFrame, w: int) -> pd.Series:
    """w_s such that G = sum_s w_s * beta_s (strata keyed by (month, local_hour))."""
    h = hours.set_index(pd.DatetimeIndex(hours["ts_utc"]).tz_convert("UTC"))
    strat = pd.MultiIndex.from_arrays([h["local_start"].dt.month, h["local_hour"]]).to_numpy()
    s_of = pd.Series(strat, index=h.index)
    acc: dict = {}
    for r in windows.itertuples(index=False):
        for start, end, sign in ((r.start_a, r.end_a, 1.0), (r.start_m, r.end_m, -1.0)):
            for ts in pd.date_range(start + pd.Timedelta(hours=1), end, freq="h"):
                s = s_of[ts]
                acc[s] = acc.get(s, 0.0) + sign / w
    wts = pd.Series(acc) / len(windows)
    wts.index = pd.MultiIndex.from_tuples(wts.index, names=["month", "local_hour"])
    return wts[wts != 0]


@dataclass
class HoldoutSlopes:
    strata: pd.MultiIndex  # (month, local_hour)
    beta: np.ndarray  # point estimates, one per stratum
    beta_boot: np.ndarray  # (N_BOOT, n_strata)
    n_obs: np.ndarray


def holdout_slopes(delta: pd.DataFrame, bad: pd.Series, source: str, tag: str) -> HoldoutSlopes:
    """Per-stratum hold-out OLS slopes (demand spec) with a joint week-cluster bootstrap."""
    ok = ex.usable_deltas(delta, bad, "demand", source)
    d = delta[ok]
    x = d["d_demand_mwh"].to_numpy(float)
    y = d[ex.SOURCES[source]].to_numpy(float)
    strata = pd.MultiIndex.from_arrays([d["local_date"].dt.month, d["local_hour"]], names=["month", "local_hour"])
    s_codes, s_uni = pd.factorize(strata, sort=True)
    k_codes, _ = pd.factorize(mef._week(d["local_date"]), sort=True)
    K, S = k_codes.max() + 1, len(s_uni)
    suff = np.zeros((K, S, 5))
    np.add.at(suff, (k_codes, s_codes), np.column_stack([np.ones_like(x), x, y, x * x, x * y]))
    beta = mef.slope(suff.sum(0))
    rng = np.random.default_rng([SEED, zlib.crc32(tag.encode())])
    wts = rng.multinomial(K, np.full(K, 1.0 / K), size=N_BOOT).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        beta_boot = mef.slope(np.einsum("bk,ksf->bsf", wts, suff))
    return HoldoutSlopes(pd.MultiIndex.from_tuples(s_uni, names=["month", "local_hour"]),
                         beta, beta_boot, suff.sum(0)[:, 0].astype(int))


def gap(weights: pd.Series, slopes: HoldoutSlopes, prof: pd.DataFrame) -> dict:
    """Realised (with CI) and predicted gap for one set of stratum weights."""
    missing = weights.index.difference(slopes.strata)
    if len(missing):
        raise ValueError(f"no hold-out slope for strata {list(missing)[:5]}")
    pos = slopes.strata.get_indexer(weights.index)
    wv = weights.to_numpy()
    realised = float(slopes.beta[pos] @ wv)
    with np.errstate(invalid="ignore"):
        boot = slopes.beta_boot[:, pos] @ wv
    # A replicate can omit every week of some stratum (single-year hold-out, 4-5 weeks per
    # month); its slope is undefined and the replicate is dropped. The share is reported.
    lo, hi = np.nanpercentile(boot, [2.5, 97.5])
    train = prof.set_index(["month", "local_hour"])["mef_kg_per_mwh"].reindex(weights.index).to_numpy()
    return {"realised": realised, "ci_low": float(lo), "ci_high": float(hi),
            "predicted": float(train @ wv),
            "min_stratum_n": int(slopes.n_obs[pos].min()),
            "dropped_replicates_pct": float(100 * np.isnan(boot).mean())}


def window_hours(windows: pd.DataFrame, which: str) -> pd.DatetimeIndex:
    """Hour-ending UTC stamps of every hour inside a scheduler's daily windows."""
    stamps = [pd.date_range(s + pd.Timedelta(hours=1), e, freq="h")
              for s, e in zip(windows[f"start_{which}"], windows[f"end_{which}"])]
    return stamps[0].append(stamps[1:])


def realised_avg_intensity(hours: pd.DataFrame, bad: pd.Series, source: str, stamps) -> float:
    """What an average-based tool would report for the chosen hours (context only)."""
    ok = ex.usable_levels(hours, bad, source) & pd.DatetimeIndex(hours["ts_utc"]).isin(stamps)
    h = hours[ok]
    return float(h[ex.LEVEL_CO2[source]].sum() / h["net_generation_mwh"].sum())


def predictive_check(delta: pd.DataFrame, bad: pd.Series, prof: pd.DataFrame, source: str) -> dict:
    ok = ex.usable_deltas(delta, bad, "demand", source)
    d = delta[ok]
    key = pd.MultiIndex.from_arrays([d["local_date"].dt.month, d["local_hour"]])
    p = prof.set_index(["month", "local_hour"])
    y = d[ex.SOURCES[source]].to_numpy(float)
    out = {"n": int(len(d))}
    for name, col in (("marginal", "mef_kg_per_mwh"), ("average", "avg_intensity_kg_per_mwh")):
        pred = p[col].reindex(key).to_numpy() * d["d_demand_mwh"].to_numpy(float)
        out[f"r2_{name}"] = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
        out[f"calib_{name}"] = float(np.polyfit(pred, y, 1)[0])
    return out
