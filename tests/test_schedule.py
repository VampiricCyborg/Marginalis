import numpy as np
import pandas as pd
import pytest

from marginalis.schedule import best_window, best_window_per_day, candidate_windows

T0 = pd.Timestamp("2024-07-01 00:00", tz="UTC")


def _factors(values, start=T0):
    """Hour-ending series whose first hour covers [start, start+1h)."""
    idx = pd.date_range(start + pd.Timedelta(hours=1), periods=len(values), freq="h")
    return pd.Series(values, index=idx, dtype=float)


def test_finds_minimum_window_and_reports_covered_time():
    f = _factors([9, 9, 1, 2, 9, 9])
    w = best_window(f, 2)
    assert w.start == T0 + pd.Timedelta(hours=2)
    assert w.end == T0 + pd.Timedelta(hours=4)
    assert w.mean_factor_kg_per_mwh == 1.5
    assert w.co2_kg(load_mwh=100) == 150
    assert list(w.hours) == list(f.index[2:4])


def test_ties_go_to_earliest_start():
    w = best_window(_factors([5, 1, 1, 5, 1, 1]), 2)
    assert w.start == T0 + pd.Timedelta(hours=1)


def test_float_noise_counts_as_tie():
    w = best_window(_factors([5, 0.1 + 0.2, 5, 0.3, 5]), 1)
    assert w.start == T0 + pd.Timedelta(hours=1)


def test_nan_hour_invalidates_windows_touching_it():
    w = best_window(_factors([9, 1, np.nan, 1, 9, 8]), 2)
    # [1, nan] and [nan, 1] are ineligible; best remaining is [9, 1] or [1, 9] -> earliest.
    assert w.start == T0 and w.mean_factor_kg_per_mwh == 5


def test_missing_timestamp_is_a_gap_not_adjacency():
    f = _factors([9, 1, 1, 9]).drop(T0 + pd.Timedelta(hours=2))  # hours 1 and 3 not adjacent
    cands = candidate_windows(f, 2)
    assert len(cands) == 1  # only the window over the last two hours
    assert cands.loc[0, "start"] == T0 + pd.Timedelta(hours=2)


def test_bounds_are_inclusive_covered_time():
    f = _factors([1, 1, 5, 5, 5, 1])
    w = best_window(f, 2, earliest=T0 + pd.Timedelta(hours=2), latest=T0 + pd.Timedelta(hours=5))
    assert (w.start, w.end) == (T0 + pd.Timedelta(hours=2), T0 + pd.Timedelta(hours=4))
    assert best_window(f, 2, earliest=T0 + pd.Timedelta(hours=4)).end == T0 + pd.Timedelta(hours=6)


def test_no_valid_window_returns_none():
    assert best_window(_factors([1, np.nan, 1]), 2) is None
    assert best_window(_factors([1, 2]), 3) is None


def test_duration_equal_to_series_length():
    assert best_window(_factors([3, 5]), 2).mean_factor_kg_per_mwh == 4


@pytest.mark.parametrize("bad", [0, -1, 2.5])
def test_rejects_bad_duration(bad):
    with pytest.raises(ValueError):
        best_window(_factors([1, 2, 3]), bad)


def test_rejects_naive_or_duplicate_or_offhour_index():
    f = _factors([1, 2, 3])
    with pytest.raises(ValueError):
        best_window(f.tz_localize(None), 1)
    with pytest.raises(ValueError):
        best_window(pd.concat([f, f.iloc[:1]]), 1)
    with pytest.raises(ValueError):
        best_window(f.set_axis(f.index + pd.Timedelta(minutes=30)), 1)


def test_input_order_does_not_matter():
    f = _factors([9, 9, 1, 2, 9, 9])
    assert best_window(f.iloc[::-1], 2) == best_window(f, 2)


def test_per_day_windows_stay_inside_local_day_including_dst():
    tz = "America/Chicago"
    # Local 2024-03-09 00:00 (CST) through 2024-03-11 00:00 (CDT); 03-10 has 23 hours.
    start = pd.Timestamp("2024-03-09 00:00", tz=tz).tz_convert("UTC")
    n = 24 + 23
    vals = np.full(n, 10.0)
    vals[23] = vals[24] = 0.0  # cheapest pair straddles local midnight 03-09/03-10
    out = best_window_per_day(_factors(vals, start), 2, tz)
    assert [str(d) for d in out["local_date"]] == ["2024-03-09", "2024-03-10"]
    for _, row in out.iterrows():
        local_day = (row["start"]).tz_convert(tz).date()
        assert local_day == row["local_date"]
        assert (row["end"] - pd.Timedelta(hours=1)).tz_convert(tz).date() == row["local_date"]
    # The straddling pair is not allowed; each day gets a window containing one cheap hour.
    assert out["mean_factor_kg_per_mwh"].tolist() == [5.0, 5.0]


def test_per_day_marks_days_without_valid_window():
    vals = [1.0] * 24
    vals[1::2] = [np.nan] * 12  # no two adjacent valid hours
    out = best_window_per_day(_factors(vals), 2, "UTC")
    assert len(out) == 1 and pd.isna(out.loc[0, "start"])
