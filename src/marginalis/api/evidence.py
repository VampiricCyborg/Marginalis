"""What the confirmatory test supports, per BA, derived from reports/holdout_results.json.

Every number the API (and later the NL layer) states about validation comes from here,
so it always matches the committed hold-out report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from marginalis.config import HOLDOUT, HOLDOUT_YTD, REPORTS_DIR

RESULTS_JSON = REPORTS_DIR / "holdout_results.json"
PRIMARY_SOURCE = "eia"

# Documented investigation findings that numbers alone cannot express (holdout_results.md,
# "Exclusion rule on hold-out data"). Keyed by BA; applies to data from `from_date` on.
KNOWN_RULE_MISFIRES = {
    "CISO": {
        "from_date": HOLDOUT_YTD.start.date(),
        "text": (
            "The frozen gas-as-Other exclusion rule (gas < 5% and Other > 20% of net generation) wrongly "
            "flagged {n} CISO days in {months} {year}. CISO's gas share has fallen so far that ordinary "
            "evening battery discharge, which EIA files under 'Other', crosses both thresholds. The rule may "
            "keep misfiring on CISO data from {from_date} onward. Flagged days here are legitimate data, not "
            "the gas-relabelling artifact the rule was built for (see reports/holdout_results.md)."
        ),
    }
}


@dataclass(frozen=True)
class Estimate:
    value: float
    ci_low: float
    ci_high: float
    unit: str = "kg CO2/MWh"

    @property
    def ci_includes_zero(self) -> bool:
        return self.ci_low <= 0 <= self.ci_high

    def as_dict(self) -> dict:
        return {"value": round(self.value, 1), "ci_low_95": round(self.ci_low, 1),
                "ci_high_95": round(self.ci_high, 1), "unit": self.unit}

    def text(self) -> str:
        return f"{self.value:,.0f} {self.unit} (95% CI {self.ci_low:,.0f} to {self.ci_high:,.0f})"


@lru_cache(maxsize=4)
def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def results() -> dict:
    return _load(RESULTS_JSON)


def _row(period: str, ba: str, source: str, table: str = "main") -> dict:
    rows = [r for r in results()["periods"][period][table] if r["BA"] == ba and r.get("source") == source]
    if len(rows) != 1:
        raise KeyError(f"expected one {table} row for {period}/{ba}/{source}, got {len(rows)}")
    return rows[0]


def realised_gap(ba: str, period: str = HOLDOUT.name, source: str = PRIMARY_SOURCE) -> Estimate:
    r = _row(period, ba, source)
    return Estimate(r["realised"], r["ci_low"], r["ci_high"], "kg CO2 per MWh shifted")


def is_confirmed(ba: str) -> bool:
    return bool(results()["decision"][ba])


def misfire_caveat(ba: str, query_date: date | None = None) -> str | None:
    """Caveat for data the exclusion rule may misclassify; None if it does not apply."""
    spec = KNOWN_RULE_MISFIRES.get(ba)
    if spec is None or (query_date is not None and query_date < spec["from_date"]):
        return None
    days = [d for p in results()["periods"].values() for d in p["gas_as_other_days"] if d["ba_code"] == ba]
    dates = sorted(date.fromisoformat(d["local_date"][:10]) for d in days)
    if not dates:
        return None
    months = list(dict.fromkeys(d.strftime("%B") for d in dates))
    span = f"{months[0]}–{months[-1]}" if len(months) > 1 else months[0]
    return spec["text"].format(n=len(dates), months=span, year=dates[0].year,
                               from_date=spec["from_date"].isoformat())


def misfire_days(ba: str) -> list[str]:
    return sorted(d["local_date"][:10] for p in results()["periods"].values()
                  for d in p["gas_as_other_days"] if d["ba_code"] == ba)


def calibration_note() -> dict:
    """Calibration slopes of the marginal factors in the 2025 predictive check."""
    rows = [r for r in results()["periods"][HOLDOUT.name]["predictive"] if r["source"] == PRIMARY_SOURCE]
    slopes = {r["BA"]: round(r["calib_marginal"], 2) for r in rows}
    return {
        "calibration_slopes_2025": slopes,
        "text": (
            f"Out of sample, hourly marginal factors are over-dispersed (calibration slopes "
            f"{min(slopes.values()):.2f}–{max(slopes.values()):.2f}, where 1 is calibrated). Use them to rank "
            "windows, not to predict the CO2 of a single hour. Always read them with their 95% CI."
        ),
    }


def ba_status(ba: str) -> dict:
    """Structured statement of what the hold-out test supports for this BA."""
    res = results()
    g25 = realised_gap(ba)
    g25_d = realised_gap(ba, source="derived")
    g26 = realised_gap(ba, HOLDOUT_YTD.name)
    eda = res["eda_predicted_gap"][f"{ba}|{PRIMARY_SOURCE}"]
    confirmed = is_confirmed(ba)
    status = {
        "ba_code": ba,
        "status": "hold_out_confirmed" if confirmed else "not_confirmed",
        "scheduling_recommendation_validated": confirmed,
        "realised_gap_2025": g25.as_dict(),
        "realised_gap_2025_derived": g25_d.as_dict(),
        "realised_gap_2026_ytd": g26.as_dict(),
        "eda_predicted_gap": round(eda, 1),
        "decision_rule": (f"Realised gap >= {res['threshold_kg_per_mwh']:.0f} kg CO2/MWh shifted with a 95% CI "
                          "excluding zero, for both emissions sources, in the 2025 hold-out."),
        "sources": ["reports/holdout_results.md", "docs/preregistration.md"],
    }
    if confirmed:
        status["summary"] = (
            f"Hold-out-confirmed. In 2025, scheduling a {res['primary_w']}-hour flexible load in the "
            f"marginal-optimal window instead of the average-optimal one avoided {g25.text()}. The 2026 "
            f"year-to-date check gave {g26.text()}."
        )
    else:
        why = ("the 95% CI includes zero, so the effect was not distinguishable from zero in hold-out testing"
               if g25.ci_includes_zero else
               f"the realised gap was below the {res['threshold_kg_per_mwh']:.0f} kg/MWh threshold")
        status["summary"] = (f"Not confirmed: in 2025 the realised gap was {g25.text()}, and {why}. "
                             "No scheduling recommendation is validated for this BA.")
        if g25.value < eda and g25.ci_high < eda:
            status["eda_estimate_not_confirmed"] = (
                f"The EDA-stage estimate ({eda:,.0f} kg/MWh) was not confirmed: it lies above the 2025 "
                f"realised CI, and the effect shrank to {g26.value:,.0f} kg/MWh "
                f"(CI {g26.ci_low:,.0f} to {g26.ci_high:,.0f}) in 2026 YTD."
            )
    caveat = misfire_caveat(ba)
    if caveat:
        status["data_caveats"] = [caveat]
    return status


def miso_overnight() -> dict:
    """The EDA's named MISO overnight check: marginal factor vs average, train and hold-out."""
    res = results()
    hrs = res["overnight_local_hours"]
    tr = res["train_miso_overnight"][PRIMARY_SOURCE]
    ho = next(r for r in res["periods"][HOLDOUT.name]["miso_overnight"] if r["source"] == PRIMARY_SOURCE)
    return {
        "local_hours": f"{hrs[0]:02d}:00–{hrs[1]:02d}:00",
        "what_this_is": ("Marginal emissions factor of overnight hours vs their average intensity. It is not a "
                         "scheduling saving; see realised_gap_2025 for that."),
        "train": {"marginal": Estimate(tr["mef"], tr["ci_low"], tr["ci_high"]).as_dict(), "average": round(tr["average"], 1)},
        "holdout_2025": {"marginal": Estimate(ho["MEF"], ho["CI low"], ho["CI high"]).as_dict(), "average": round(ho["average"], 1)},
    }
