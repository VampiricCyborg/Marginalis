import numpy as np
import pandas as pd

from marginalis.analysis import holdout


def _hours(days=3, tz="UTC", start="2025-03-01"):
    local = pd.date_range(pd.Timestamp(start, tz=tz), periods=24 * days, freq="h")
    return pd.DataFrame({
        "ts_utc": (local + pd.Timedelta(hours=1)).tz_convert("UTC"),
        "local_start": local.tz_localize(None),
        "local_hour": local.hour,
        "local_date": pd.to_datetime(local.date),
    })


def _profile(mef, avg):
    return pd.DataFrame({"month": 3, "local_hour": range(24),
                         "mef_kg_per_mwh": mef, "avg_intensity_kg_per_mwh": avg})


def test_windows_and_weights_reproduce_direct_gap():
    mef = np.full(24, 500.0); mef[18:22] = 100.0      # marginal scheduler -> 18:00-22:00
    avg = np.full(24, 400.0); avg[2:6] = 200.0        # average scheduler  -> 02:00-06:00
    prof = _profile(mef, avg)
    h = _hours()
    win = holdout.daily_windows(h, prof, "UTC", 4)
    assert len(win) == 3
    assert (win["start_m"].dt.hour == 18).all() and (win["start_a"].dt.hour == 2).all()
    w = holdout.stratum_weights(h, win, 4)
    # Predicted gap = mean MEF in average window - mean MEF in marginal window.
    train = prof.set_index(["month", "local_hour"])["mef_kg_per_mwh"].reindex(w.index).to_numpy()
    assert np.isclose(train @ w.to_numpy(), 500 - 100)
    assert np.isclose(w.sum(), 0)


def test_identical_windows_give_zero_weight():
    prof = _profile(np.arange(24.0), np.arange(24.0))
    h = _hours()
    win = holdout.daily_windows(h, prof, "UTC", 4)
    assert holdout.stratum_weights(h, win, 4).empty


def test_partial_boundary_days_are_dropped():
    h = _hours(days=3).iloc[5:-3]  # first and last local days incomplete
    assert holdout.complete_days(h, "UTC")["local_date"].nunique() == 1
    # DST spring-forward day has 23 hours and is still complete.
    dst = _hours(days=3, tz="America/Chicago", start="2025-03-08")
    days = holdout.complete_days(dst, "America/Chicago")["local_date"].dt.day.unique().tolist()
    assert days == [8, 9, 10]


def test_window_hours_are_hour_ending_stamps():
    prof = _profile(np.r_[np.zeros(4), np.ones(20)], np.ones(24))
    h = _hours(days=1)
    win = holdout.daily_windows(h, prof, "UTC", 4)
    stamps = holdout.window_hours(win, "m")
    assert list(stamps.hour) == [1, 2, 3, 4]
