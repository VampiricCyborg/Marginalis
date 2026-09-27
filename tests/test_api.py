import json
from datetime import date

import pandas as pd
import pytest

from marginalis.api import evidence as ev
from marginalis.api import service


def _main(ba, src, realised, lo, hi):
    return {"BA": ba, "source": src, "realised": realised, "ci_low": lo, "ci_high": hi}


@pytest.fixture
def fake_results(tmp_path, monkeypatch):
    res = {
        "threshold_kg_per_mwh": 50.0, "primary_w": 4, "overnight_local_hours": [0, 5],
        "decision": {"MISO": True, "ERCO": False, "CISO": False},
        "eda_predicted_gap": {"MISO|eia": 213.0, "ERCO|eia": 191.0, "CISO|eia": 78.0},
        "train_miso_overnight": {"eia": {"mef": 732, "ci_low": 703, "ci_high": 760, "average": 459, "n": 1}},
        "periods": {
            "holdout_2025": {
                "main": [_main("MISO", s, 230, 44, 420) for s in ("eia", "derived")]
                + [_main("ERCO", s, 157, -51, 277) for s in ("eia", "derived")]
                + [_main("CISO", s, 21, -2, 55) for s in ("eia", "derived")],
                "predictive": [{"BA": b, "source": "eia", "calib_marginal": c}
                               for b, c in (("MISO", 0.84), ("ERCO", 0.59), ("CISO", 0.62))],
                "miso_overnight": [{"source": "eia", "MEF": 632, "CI low": 555, "CI high": 710, "average": 452}],
                "gas_as_other_days": [],
            },
            "holdout_2026ytd": {
                "main": [_main("MISO", s, 319, 149, 475) for s in ("eia", "derived")]
                + [_main("ERCO", s, 209, -111, 441) for s in ("eia", "derived")]
                + [_main("CISO", s, 3, -46, 29) for s in ("eia", "derived")],
                "predictive": [], "miso_overnight": [],
                "gas_as_other_days": [{"ba_code": "CISO", "local_date": f"2026-0{m}-{d:02d}T00:00:00"}
                                      for m, d in ((5, 14), (5, 15), (6, 29))],
            },
        },
    }
    path = tmp_path / "holdout_results.json"
    path.write_text(json.dumps(res))
    monkeypatch.setattr(ev, "RESULTS_JSON", path)
    return res


def test_miso_confirmed_uses_realised_gap_not_overnight_factor(fake_results):
    s = ev.ba_status("MISO")
    assert s["status"] == "hold_out_confirmed" and s["scheduling_recommendation_validated"]
    assert s["realised_gap_2025"]["value"] == 230
    assert "632" not in s["summary"]  # the overnight factor is not the scheduling saving
    on = ev.miso_overnight()
    assert on["holdout_2025"]["marginal"] == {"value": 632, "ci_low_95": 555, "ci_high_95": 710, "unit": "kg CO2/MWh"}


def test_erco_not_confirmed_says_indistinguishable_from_zero(fake_results):
    s = ev.ba_status("ERCO")
    assert s["status"] == "not_confirmed"
    assert "not distinguishable from zero" in s["summary"]
    assert "data_caveats" not in s


def test_ciso_flags_eda_estimate_and_rule_misfire(fake_results):
    s = ev.ba_status("CISO")
    assert "78" in s["eda_estimate_not_confirmed"] and "2026 YTD" in s["eda_estimate_not_confirmed"]
    assert "3 CISO days in May–June 2026" in s["data_caveats"][0]
    assert ev.misfire_caveat("CISO", date(2025, 6, 1)) is None
    assert ev.misfire_caveat("CISO", date(2027, 1, 1)) is not None  # going forward
    assert ev.misfire_caveat("ERCO", date(2026, 5, 15)) is None


def test_calibration_note_range(fake_results):
    assert "0.59–0.84" in ev.calibration_note()["text"]


def _profile(ba="MISO"):
    rows = []
    for spec in ("demand", "fossil_gen"):
        for src in ("eia", "derived"):
            for m in range(1, 13):
                for h in range(24):
                    mef = 300.0 if 19 <= h < 23 else 800.0  # marginal-optimal 19-23
                    avg = 300.0 if h < 4 else 500.0  # average-optimal 00-04
                    rows.append({"ba_code": ba, "spec": spec, "emissions_source": src, "month": m,
                                 "local_hour": h, "mef_kg_per_mwh": mef, "ci_low_95": mef - 100,
                                 "ci_high_95": mef + 100, "n_obs": 160, "stratum_id": f"{m}-{h}",
                                 "avg_intensity_kg_per_mwh": avg})
    return pd.DataFrame(rows)


def test_schedule_miso_confirmed(fake_results):
    out = service.schedule(_profile("MISO"), "miso", date(2026, 3, 10), 4, 100.0, None, None, "eia")
    assert out["marginal_optimal_window"]["start_local"].startswith("2026-03-10T19:00")
    assert out["average_optimal_window"]["start_local"].startswith("2026-03-10T00:00")
    rec = out["recommendation"]
    assert rec["validated"] and rec["label"] == "hold-out-confirmed"
    assert rec["realised_saving_for_this_load_kg"]["value"] == 23000
    w = out["marginal_optimal_window"]["window_marginal_mean"]
    assert w["value"] == 300 and w["ci_bounds_conservative"] == [200, 400]


def test_schedule_ciso_not_validated_and_caveated(fake_results):
    out = service.schedule(_profile("CISO"), "CISO", date(2026, 5, 20), 4, 100.0, None, None, "eia")
    rec = out["recommendation"]
    assert rec["validated"] is False and "not distinguishable from zero" in rec["advice"]
    assert "realised_saving_for_this_load_kg" not in rec
    assert any("exclusion rule" in c for c in out["caveats"])


def test_schedule_respects_hour_bounds_and_dst(fake_results):
    out = service.schedule(_profile("MISO"), "MISO", date(2025, 3, 9), 4, 50.0, 6, 18, "eia")
    s = out["marginal_optimal_window"]["start_local"]
    assert "T06:00" <= s[10:16] and len(out["marginal_optimal_window"]["hours"]) == 4


def test_bad_requests():
    with pytest.raises(service.BadRequest):
        service.check_ba("PJM")
    with pytest.raises(service.BadRequest):
        service.schedule(_profile(), "MISO", date(2025, 1, 1), 0, 1.0, None, None, "eia")
