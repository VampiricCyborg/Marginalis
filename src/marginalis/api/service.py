"""Request logic, independent of HTTP: scheduling, MEF lookup, hourly data."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from marginalis.api import evidence as ev
from marginalis.config import BAS, DATA_END
from marginalis.schedule import best_window

SPECS = ("demand", "fossil_gen")
SOURCES = ("eia", "derived")


class BadRequest(ValueError):
    pass


def check_ba(ba: str) -> str:
    ba = ba.upper()
    if ba not in BAS:
        raise BadRequest(f"unknown BA {ba!r}; expected one of {list(BAS)}")
    return ba


def _profile_rows(profile: pd.DataFrame, ba: str, spec: str, source: str) -> pd.DataFrame:
    if spec not in SPECS or source not in SOURCES:
        raise BadRequest(f"spec must be one of {SPECS}, source one of {SOURCES}")
    p = profile[(profile["ba_code"] == ba) & (profile["spec"] == spec) & (profile["emissions_source"] == source)]
    return p.set_index(["month", "local_hour"]).sort_index()


def mef_rows(profile: pd.DataFrame, ba: str, spec: str, source: str,
             month: int | None, hour: int | None) -> dict:
    ba = check_ba(ba)
    p = _profile_rows(profile, ba, spec, source).reset_index()
    if month is not None:
        p = p[p["month"] == month]
    if hour is not None:
        p = p[p["local_hour"] == hour]
    rows = [{
        "month": int(r.month), "local_hour": int(r.local_hour),
        "marginal": ev.Estimate(r.mef_kg_per_mwh, r.ci_low_95, r.ci_high_95).as_dict(),
        "average_intensity_kg_per_mwh": round(r.avg_intensity_kg_per_mwh, 1),
        "n_obs": int(r.n_obs), "stratum_id": r.stratum_id,
    } for r in p.itertuples()]
    return {"ba_code": ba, "spec": spec, "emissions_source": source,
            "estimated_on": "train split 2019-07 to 2024-12 (frozen)",
            "usage": ev.calibration_note(), "validation": ev.ba_status(ba), "rows": rows}


def _day_hours(d: date, tz: str) -> pd.DatetimeIndex:
    """Local hour starts of calendar day d (23/24/25 hours across DST)."""
    z = ZoneInfo(tz)
    start = pd.Timestamp(datetime.combine(d, time(0), z))
    end = pd.Timestamp(datetime.combine(d + timedelta(days=1), time(0), z))
    return pd.date_range(start, end, freq="h", inclusive="left")


def _window_detail(win, starts_by_end: dict, p: pd.DataFrame, tz: str) -> dict:
    hours = []
    for ts in win.hours:
        ls = starts_by_end[ts]
        r = p.loc[(ls.month, ls.hour)]
        hours.append({"local_start": ls.isoformat(),
                      "marginal": ev.Estimate(r.mef_kg_per_mwh, r.ci_low_95, r.ci_high_95).as_dict(),
                      "average_intensity_kg_per_mwh": round(r.avg_intensity_kg_per_mwh, 1)})
    mean = lambda k: sum(h["marginal"][k] for h in hours) / len(hours)
    return {
        "start_local": win.start.tz_convert(tz).isoformat(),
        "end_local": win.end.tz_convert(tz).isoformat(),
        "window_marginal_mean": {
            "value": round(mean("value"), 1),
            "ci_bounds_conservative": [round(mean("ci_low_95"), 1), round(mean("ci_high_95"), 1)],
            "ci_note": "Average of the hours' 95% CI bounds; wider than the true window CI.",
            "unit": "kg CO2/MWh",
        },
        "window_average_intensity_kg_per_mwh": round(
            sum(h["average_intensity_kg_per_mwh"] for h in hours) / len(hours), 1),
        "hours": hours,
    }


def schedule(profile: pd.DataFrame, ba: str, day: date, duration_h: int, load_mwh: float,
             earliest_hour: int | None, latest_hour: int | None, source: str) -> dict:
    ba = check_ba(ba)
    if not 1 <= duration_h <= 24:
        raise BadRequest("duration_h must be between 1 and 24")
    if load_mwh <= 0:
        raise BadRequest("load_mwh must be positive")
    tz = BAS[ba].timezone
    p = _profile_rows(profile, ba, "demand", source)
    starts = _day_hours(day, tz)
    if earliest_hour is not None:
        starts = starts[starts.hour >= earliest_hour]
    if latest_hour is not None:
        starts = starts[starts.hour < latest_hour]
    ends = (starts + pd.Timedelta(hours=1)).tz_convert("UTC")
    starts_by_end = dict(zip(ends, starts))
    key = list(zip(starts.month, starts.hour))
    mef = pd.Series(p["mef_kg_per_mwh"].reindex(key).to_numpy(), index=ends)
    avg = pd.Series(p["avg_intensity_kg_per_mwh"].reindex(key).to_numpy(), index=ends)
    wm, wa = best_window(mef, duration_h), best_window(avg, duration_h)
    if wm is None or wa is None:
        raise BadRequest(f"no {duration_h}-hour window fits between the given hours")

    status = ev.ba_status(ba)
    marginal_w = _window_detail(wm, starts_by_end, p, tz)
    average_w = _window_detail(wa, starts_by_end, p, tz)
    out = {
        "ba_code": ba, "date": day.isoformat(), "timezone": tz, "duration_h": duration_h,
        "load_mwh": load_mwh, "emissions_source": source,
        "marginal_optimal_window": marginal_w, "average_optimal_window": average_w,
        "same_window": wm.start == wa.start,
        "factors_from": "mef_profile (train 2019-07 to 2024-12, frozen), by month x local hour",
        "usage": ev.calibration_note(),
        "validation": status,
    }
    gap = ev.realised_gap(ba, source=source)
    if status["scheduling_recommendation_validated"]:
        out["recommendation"] = {
            "validated": True,
            "label": "hold-out-confirmed",
            "advice": ("Run in the marginal-optimal window." if not out["same_window"]
                       else "Both schedulers pick the same window for this day."),
            "realised_saving_per_mwh_2025": gap.as_dict(),
            "realised_saving_for_this_load_kg": {
                "value": round(gap.value * load_mwh, 0), "ci_low_95": round(gap.ci_low * load_mwh, 0),
                "ci_high_95": round(gap.ci_high * load_mwh, 0),
                "basis": ("2025 hold-out average across days (realised, not predicted), scaled to load_mwh. "
                          "It is not specific to this date."),
            },
        }
    else:
        out["recommendation"] = {
            "validated": False,
            "label": "not validated",
            "advice": (f"No validated recommendation for {ba}. In hold-out testing the difference between "
                       f"marginal- and average-optimal scheduling was {gap.text()}"
                       + (", which is not distinguishable from zero." if gap.ci_includes_zero else ".")
                       + " The windows above are exploratory and shown for transparency only."),
        }
    caveats = []
    if day >= DATA_END.date():
        caveats.append("This date is after the data (ends 2026-08); factors are training-period profiles.")
    mc = ev.misfire_caveat(ba, day)
    if mc:
        caveats.append(mc)
    out["caveats"] = caveats
    return out


def hours(conn, ba: str, start: date, end: date) -> dict:
    ba = check_ba(ba)
    if end <= start or (end - start).days > 31:
        raise BadRequest("end must be after start and at most 31 days later")
    cols = ("ts_utc, local_start, split_name, demand_mwh, net_generation_mwh, interchange_mwh, "
            "fossil_generation_mwh, wind_solar_mwh, co2_kg_derived, co2_kg_eia_generated, "
            "avg_intensity_eia_kg_per_mwh, net_import_share, demand_flag, is_imputed")
    cur = conn.execute(
        f"SELECT {cols} FROM v_hour WHERE ba_code = %s AND local_date >= %s AND local_date < %s ORDER BY ts_utc",
        (ba, start, end))
    names = [d.name for d in cur.description]
    rows = [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in zip(names, r)} for r in cur.fetchall()]
    flagged = [d for d in ev.misfire_days(ba) if start.isoformat() <= d < end.isoformat()]
    caveats = []
    mc = ev.misfire_caveat(ba, end - timedelta(days=1))
    if mc:
        caveats.append(mc)
    return {"ba_code": ba, "start": start.isoformat(), "end": end.isoformat(),
            "timestamps": "ts_utc is hour-ending UTC; local_start is the hour's local start",
            "exclusion_rule_flagged_days_in_range": flagged,
            "exclusion_rule_note": ("Rows are returned as reported. The frozen gas-as-Other rule would exclude "
                                    "the flagged days from estimation."
                                    + (" These flags are known misfires for this BA." if ba in ev.KNOWN_RULE_MISFIRES else "")),
            "caveats": caveats, "rows": rows}
