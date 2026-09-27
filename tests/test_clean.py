import numpy as np
import pandas as pd
import pytest

from marginalis.transform.clean import QualityLog, clean_series, dedupe, hourly_index


def _series(values, start="2021-01-01 01:00"):
    idx = pd.date_range(start, periods=len(values), freq="h", tz="UTC", name="ts_utc")
    s = pd.Series(values, index=idx, dtype=float)
    return s, s.astype(object).where(s.notna(), None)


def _counts(log):
    df = log.frame()
    return dict(zip(df["rule"], df["n_rows"]))


def test_short_gap_interpolated_long_gap_left_missing():
    s, raw = _series([10, np.nan, np.nan, 40, 50, np.nan, np.nan, np.nan, 90])
    log = QualityLog()
    out, flag = clean_series(s, raw, name="x", ba="T", table="t", log=log)
    assert out.iloc[1:3].tolist() == [20.0, 30.0]
    assert out.iloc[5:8].isna().all()
    assert flag.iloc[1:3].eq("interpolated").all() and flag.iloc[5:8].eq("missing").all()
    assert _counts(log) == {"interpolated": 2, "missing": 3}


def test_edge_gaps_are_not_extrapolated():
    s, raw = _series([np.nan, 5, 6, np.nan])
    out, flag = clean_series(s, raw, name="x", ba="T", table="t", log=QualityLog())
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[-1])
    assert flag.iloc[[0, -1]].eq("missing").all()


def test_nonpositive_demand_nulled_then_filled():
    s, raw = _series([100, 0, 102])
    log = QualityLog()
    out, flag = clean_series(s, raw, name="demand_mwh", ba="T", table="t", log=log, positive=True)
    assert out.iloc[1] == 101
    assert _counts(log) == {"nonpositive_nulled": 1, "interpolated": 1}


def test_thermal_negative_nulled_only_beyond_station_service_tolerance():
    s, raw = _series([5, -3, 5, -300, 5])
    limit = pd.Series(10.0, index=s.index)  # e.g. 1% of a 1,000 MWh hour
    log = QualityLog()
    out, flag = clean_series(s, raw, name="COL", ba="T", table="t", log=log, neg_limit=limit)
    assert out.iloc[1] == -3 and flag.iloc[1] == "ok"
    assert out.iloc[3] == 5 and flag.iloc[3] == "interpolated"
    assert _counts(log) == {"negative_nulled": 1, "negative_kept": 1, "interpolated": 1}


def test_solar_negative_kept():
    s, raw = _series([5, -3, 5])
    log2 = QualityLog()
    out2, flag2 = clean_series(s, raw, name="SUN", ba="T", table="t", log=log2)
    assert out2.iloc[1] == -3 and flag2.iloc[1] == "ok"
    assert _counts(log2) == {"negative_kept": 1}


def test_spike_nulled_as_outlier():
    vals = [1000.0] * 30
    vals[15] = 10_000.0
    s, raw = _series(vals)
    log = QualityLog()
    out, flag = clean_series(s, raw, name="demand_mwh", ba="T", table="t", log=log,
                             positive=True, outliers=True)
    assert out.iloc[15] == 1000.0 and flag.iloc[15] == "interpolated"
    assert _counts(log)["outlier_nulled"] == 1


def test_unparseable_is_logged():
    s, _ = _series([1, np.nan, 3])
    raw = pd.Series(["1", "n/a", "3"], index=s.index)
    log = QualityLog()
    clean_series(s, raw, name="x", ba="T", table="t", log=log)
    assert _counts(log)["unparseable"] == 1


def test_dedupe_identical_and_conflicting():
    ts = pd.Timestamp("2021-01-01 01:00", tz="UTC")
    df = pd.DataFrame({
        "ts_utc": [ts, ts, ts, ts],
        "series": ["a", "a", "b", "b"],
        "value": [1.0, 1.0, 2.0, 3.0],
    })
    log = QualityLog()
    out = dedupe(df, ["ts_utc", "series"], log, "T", "t")
    assert len(out) == 2
    assert out.set_index("series").loc["a", "value"] == 1.0
    assert np.isnan(out.set_index("series").loc["b", "value"])
    assert _counts(log) == {"duplicate_dropped": 1, "duplicate_conflict": 1}


@pytest.mark.parametrize("year,hours", [(2021, 8760), (2024, 8784)])
def test_hourly_index_has_every_utc_hour_including_dst_days(year, hours):
    idx = hourly_index(pd.Timestamp(f"{year}-01-01", tz="UTC"),
                       pd.Timestamp(f"{year + 1}-01-01", tz="UTC"))
    assert len(idx) == idx.nunique() == hours
    assert idx[0] == pd.Timestamp(f"{year}-01-01 01:00", tz="UTC")
    assert idx[-1] == pd.Timestamp(f"{year + 1}-01-01 00:00", tz="UTC")
