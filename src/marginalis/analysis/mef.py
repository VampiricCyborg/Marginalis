"""Marginal emissions factors per BA x spec x source x month x local hour.

Implements "Estimation details" in docs/preregistration.md:
OLS with intercept of dCO2 on dx within each stratum; strata below MIN_CELL usable
observations are pooled with the same hour of adjacent months (+-1, then +-2, cyclic);
95% CIs from a cluster bootstrap over local calendar weeks (N_BOOT replicates, fixed
seed); average-intensity baseline = sum CO2 / sum net generation over the stratum's
hours, bootstrapped jointly with the slope so the difference gets its own interval.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from marginalis.analysis import exclusions as ex

MIN_CELL = 120
N_BOOT = 2000
SEED = 20260927
DIVERGENCE_KG = 50.0

PROFILE_COLUMNS = [
    "ba_code", "spec", "emissions_source", "month", "local_hour",
    "mef_kg_per_mwh", "ci_low_95", "ci_high_95", "n_obs", "stratum_id",
    "avg_intensity_kg_per_mwh",
]


def slope(s: np.ndarray) -> np.ndarray:
    """OLS slope with intercept from sufficient statistics [..., (n, Sx, Sy, Sxx, Sxy)]."""
    n, sx, sy, sxx, sxy = np.moveaxis(s, -1, 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (n * sxy - sx * sy) / (n * sxx - sx * sx)


def pooled_months(month: int, hour: int, counts: pd.Series) -> tuple[int, ...]:
    """Months pooled for (month, hour): widen +-1, then +-2 (cyclic) until MIN_CELL is met."""
    months = [month]
    for k in (1, 2):
        if sum(counts.get((m, hour), 0) for m in months) >= MIN_CELL:
            break
        months += [(month - 1 - k) % 12 + 1, (month - 1 + k) % 12 + 1]
    return tuple(sorted(set(months)))


def _week(dates: pd.Series) -> np.ndarray:
    iso = dates.dt.isocalendar()
    return (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()


@dataclass(frozen=True)
class CellResult:
    mef: float
    ci_low: float
    ci_high: float
    avg: float
    diff_ci_low: float
    diff_ci_high: float
    n_obs: int
    n_clusters: int


def estimate_cell(
    x: np.ndarray, y: np.ndarray, d_cluster: np.ndarray,
    co2: np.ndarray, gen: np.ndarray, l_cluster: np.ndarray,
    rng: np.random.Generator, n_boot: int = N_BOOT,
) -> CellResult:
    clusters, d_idx = np.unique(np.concatenate([d_cluster, l_cluster]), return_inverse=True)
    k = len(clusters)
    d_idx, l_idx = d_idx[: len(d_cluster)], d_idx[len(d_cluster):]
    sd = np.zeros((k, 5))
    np.add.at(sd, d_idx, np.column_stack([np.ones_like(x), x, y, x * x, x * y]))
    sl = np.zeros((k, 2))
    np.add.at(sl, l_idx, np.column_stack([co2, gen]))

    mef = float(slope(sd.sum(0)))
    avg = float(sl[:, 0].sum() / sl[:, 1].sum())
    w = rng.multinomial(k, np.full(k, 1.0 / k), size=n_boot).astype(float)
    mef_b = slope(w @ sd)
    lb = w @ sl
    with np.errstate(invalid="ignore", divide="ignore"):
        diff_b = mef_b - lb[:, 0] / lb[:, 1]
    lo, hi = np.nanpercentile(mef_b, [2.5, 97.5])
    dlo, dhi = np.nanpercentile(diff_b, [2.5, 97.5])
    return CellResult(mef, float(lo), float(hi), avg, float(dlo), float(dhi), len(x), k)


def estimate(delta: pd.DataFrame, hours: pd.DataFrame, bad_days: pd.DataFrame) -> pd.DataFrame:
    """Full stratum table (one row per BA x spec x source x month x hour) with diagnostics."""
    d_bad = ex.on_days(delta, bad_days)
    h_bad = ex.on_days(hours, bad_days)
    rows = []
    for ba in sorted(delta["ba_code"].unique()):
        for spec, xcol in ex.SPECS.items():
            for source, ycol in ex.SOURCES.items():
                dm = ex.usable_deltas(delta, d_bad, spec, source) & (delta["ba_code"] == ba)
                lm = ex.usable_levels(hours, h_bad, source) & (hours["ba_code"] == ba)
                d = delta.loc[dm, ["local_date", "local_hour", xcol, ycol]]
                lv = hours.loc[lm, ["local_date", "local_hour", ex.LEVEL_CO2[source], "net_generation_mwh"]]
                d_month, l_month = d["local_date"].dt.month.to_numpy(), lv["local_date"].dt.month.to_numpy()
                d_week, l_week = _week(d["local_date"]), _week(lv["local_date"])
                counts = d.groupby([d["local_date"].dt.month, "local_hour"]).size()
                cache: dict[tuple, tuple[str, CellResult]] = {}
                for hour in range(24):
                    dh, lh = d["local_hour"].to_numpy() == hour, lv["local_hour"].to_numpy() == hour
                    for month in range(1, 13):
                        months = pooled_months(month, hour, counts)
                        if (months, hour) not in cache:
                            dsel = dh & np.isin(d_month, months)
                            lsel = lh & np.isin(l_month, months)
                            sid = f"{ba}|{spec}|{source}|m{'-'.join(map(str, months))}|h{hour:02d}"
                            rng = np.random.default_rng([SEED, zlib.crc32(sid.encode())])
                            res = estimate_cell(
                                d.loc[dsel, xcol].to_numpy(float), d.loc[dsel, ycol].to_numpy(float),
                                d_week[dsel],
                                lv.loc[lsel, ex.LEVEL_CO2[source]].to_numpy(float),
                                lv.loc[lsel, "net_generation_mwh"].to_numpy(float), l_week[lsel],
                                rng,
                            )
                            cache[(months, hour)] = (sid, res)
                        sid, r = cache[(months, hour)]
                        rows.append({
                            "ba_code": ba, "spec": spec, "emissions_source": source,
                            "month": month, "local_hour": hour,
                            "mef_kg_per_mwh": r.mef, "ci_low_95": r.ci_low, "ci_high_95": r.ci_high,
                            "n_obs": r.n_obs, "stratum_id": sid,
                            "avg_intensity_kg_per_mwh": r.avg,
                            "diff_kg_per_mwh": r.mef - r.avg,
                            "diff_ci_low_95": r.diff_ci_low, "diff_ci_high_95": r.diff_ci_high,
                            "n_clusters": r.n_clusters, "pooled": len(months) > 1,
                        })
    out = pd.DataFrame(rows)
    out["diverges"] = (out["diff_kg_per_mwh"].abs() >= DIVERGENCE_KG) & (
        (out["diff_ci_low_95"] > 0) | (out["diff_ci_high_95"] < 0)
    )
    return out


def load_profile(conn, detail: pd.DataFrame) -> None:
    """Replace mef_profile with the estimated strata (schema fixed by migration 004)."""
    prof = detail[PROFILE_COLUMNS]
    with conn.transaction():
        conn.execute("DELETE FROM mef_profile")
        with conn.cursor().copy(f"COPY mef_profile ({', '.join(PROFILE_COLUMNS)}) FROM STDIN") as cp:
            for rec in prof.itertuples(index=False, name=None):
                cp.write_row([None if isinstance(v, float) and np.isnan(v) else v for v in rec])
