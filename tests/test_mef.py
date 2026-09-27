import numpy as np
import pandas as pd

from marginalis.analysis import exclusions as ex
from marginalis.analysis.mef import MIN_CELL, estimate_cell, pooled_months, slope


def test_slope_matches_numpy_polyfit():
    rng = np.random.default_rng(0)
    x = rng.normal(size=200)
    y = 3 + 450 * x + rng.normal(scale=50, size=200)
    s = np.array([len(x), x.sum(), y.sum(), (x * x).sum(), (x * y).sum()])
    assert np.isclose(slope(s), np.polyfit(x, y, 1)[0])


def test_cell_recovers_known_mef_and_ci_covers_it():
    rng = np.random.default_rng(1)
    n = 180
    x = rng.normal(0, 1500, n)
    week = np.repeat(np.arange(n // 6), 6)
    y = 600 * x + np.repeat(rng.normal(0, 2e5, n // 6), 6) + rng.normal(0, 1e5, n)
    gen = np.full(n, 40_000.0)
    co2 = gen * 400
    r = estimate_cell(x, y, week, co2, gen, week, np.random.default_rng(2), n_boot=1000)
    assert abs(r.mef - 600) < 40
    assert r.ci_low < 600 < r.ci_high
    assert r.avg == 400
    assert r.diff_ci_low > 0  # 600 vs 400: clearly different
    assert (r.n_obs, r.n_clusters) == (n, n // 6)


def test_bootstrap_is_deterministic_given_seed():
    rng = np.random.default_rng(3)
    x, y = rng.normal(size=150), rng.normal(size=150)
    wk = np.arange(150) // 7
    args = (x, y, wk, np.ones(150), np.ones(150), wk)
    a = estimate_cell(*args, np.random.default_rng(9), n_boot=200)
    b = estimate_cell(*args, np.random.default_rng(9), n_boot=200)
    assert a == b


def test_pooling_widens_only_when_needed_and_wraps_year():
    full = pd.Series({(m, 5): MIN_CELL for m in range(1, 13)})
    assert pooled_months(1, 5, full) == (1,)
    thin = full.copy()
    thin[(1, 5)] = 10
    assert pooled_months(1, 5, thin) == (1, 2, 12)
    very = pd.Series({(m, 5): 10 for m in range(1, 13)})
    assert pooled_months(1, 5, very) == (1, 2, 3, 11, 12)


def _frame(ng, oth, net, date):
    ts = pd.Timestamp(date, tz="UTC")
    fuel = pd.DataFrame({"ba_code": "X", "ts_utc": [ts, ts], "fuel_code": ["NG", "OTH"],
                         "generation_mwh": [ng, oth]})
    hours = pd.DataFrame({"ba_code": ["X"], "ts_utc": [ts], "net_generation_mwh": [net],
                          "local_date": [pd.Timestamp(date).normalize()]})
    return fuel, hours


def test_gas_as_other_rule_needs_both_conditions():
    assert len(ex.gas_as_other_days(*_frame(900, 22_000, 44_000, "2019-12-18 08:00"))) == 1
    # Battery discharge in Other exceeding gas, but gas still > 5%: not excluded.
    assert len(ex.gas_as_other_days(*_frame(4_000, 12_000, 30_000, "2024-05-06 03:00"))) == 0


def test_usable_deltas_drops_rows_touching_bad_hours():
    delta = pd.DataFrame({
        "ba_code": ["X"] * 4, "consecutive": [True] * 4, "imputed_either": [False] * 4,
        "d_demand_mwh": [1.0] * 4, "d_co2_kg_eia_generated": [1.0] * 4,
        "derived_complete_both": [True] * 4,
    })
    bad = pd.Series([False, True, False, False])
    ok = ex.usable_deltas(delta, bad, "demand", "eia")
    assert ok.tolist() == [True, False, False, True]
