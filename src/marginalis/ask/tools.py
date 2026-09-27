"""Tools the LLM may call. Each wraps the API's own service/evidence functions (one source
of truth) and returns compact JSON-able dicts to fit Groq's token budget."""

from __future__ import annotations

import re
from datetime import date

import pandas as pd

from marginalis.api import evidence as ev
from marginalis.api import service
from marginalis.ask.scope import COVERAGE
from marginalis.config import REPORTS_DIR

EDA_REPORT = REPORTS_DIR / "eda_findings.md"
EDA_SECTIONS = {"summary": "## Summary", "methodology": "## Methodology used",
                "data_issues": "### Data issues and how they were handled",
                "recommendation": "## Recommendation", "limitations": "## Limitations"}
BA_ENUM = ["ERCO", "CISO", "MISO"]


class ToolError(ValueError):
    pass


def _fn(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required}}}


SCHEMAS = [
    _fn("get_ba_status", "What the pre-registered hold-out test supports for a BA (validated or not, realised gap with CI).",
        {"ba": {"type": "string", "enum": BA_ENUM}}, ["ba"]),
    _fn("get_schedule", "Marginal- vs average-optimal window for one local day (date within 2019-07-01..2026-08-31).",
        {"ba": {"type": "string", "enum": BA_ENUM}, "date": {"type": "string", "description": "YYYY-MM-DD"},
         "duration_h": {"type": "integer"}, "load_mwh": {"type": "number"},
         "earliest_hour": {"type": "integer"}, "latest_hour": {"type": "integer"}}, ["ba", "date"]),
    _fn("get_mef", "Marginal emissions factors (with 95% CI) and average intensity for a BA and month, optionally one local hour.",
        {"ba": {"type": "string", "enum": BA_ENUM}, "month": {"type": "integer"}, "hour": {"type": "integer"}},
        ["ba", "month"]),
    _fn("get_miso_overnight", "MISO overnight (00-05 local) marginal factor vs average intensity, train and 2025 hold-out.",
        {}, []),
    _fn("get_eda_section", "Text of a section of the EDA findings report.",
        {"section": {"type": "string", "enum": list(EDA_SECTIONS)}}, ["section"]),
]


def _date(s: str) -> date:
    try:
        d = date.fromisoformat(s)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"invalid date {s!r}; use YYYY-MM-DD") from exc
    if not COVERAGE[0] <= d <= COVERAGE[1]:
        raise ToolError(f"{s} is outside the data coverage {COVERAGE[0]} to {COVERAGE[1]}; not extrapolating")
    return d


def get_ba_status(ba: str) -> dict:
    s = ev.ba_status(service.check_ba(ba))
    keep = ("status", "scheduling_recommendation_validated", "summary", "realised_gap_2025",
            "realised_gap_2026_ytd", "eda_predicted_gap", "eda_estimate_not_confirmed")
    return {"ba": s["ba_code"], **{k: s[k] for k in keep if k in s}}


def get_schedule(profile: pd.DataFrame, ba: str, date: str, duration_h: int = 4, load_mwh: float = 100.0,
                 earliest_hour: int | None = None, latest_hour: int | None = None) -> dict:
    out = service.schedule(profile, ba, _date(date), int(duration_h), float(load_mwh),
                           earliest_hour, latest_hour, "eia")

    def w(x):
        return {"start_local": x["start_local"][:16], "end_local": x["end_local"][:16],
                "marginal_mean_kg_per_mwh": x["window_marginal_mean"]["value"],
                "marginal_ci_bounds_conservative": x["window_marginal_mean"]["ci_bounds_conservative"],
                "average_intensity_kg_per_mwh": x["window_average_intensity_kg_per_mwh"]}

    return {"ba": out["ba_code"], "date": out["date"], "duration_h": out["duration_h"], "load_mwh": out["load_mwh"],
            "marginal_optimal_window": w(out["marginal_optimal_window"]),
            "average_optimal_window": w(out["average_optimal_window"]),
            "same_window": out["same_window"], "recommendation": out["recommendation"],
            "caveats": out["caveats"]}


def get_mef(profile: pd.DataFrame, ba: str, month: int, hour: int | None = None) -> dict:
    if not 1 <= int(month) <= 12 or (hour is not None and not 0 <= int(hour) <= 23):
        raise ToolError("month must be 1-12 and hour 0-23")
    out = service.mef_rows(profile, ba, "demand", "eia", int(month), None if hour is None else int(hour))
    rows = [[r["local_hour"], r["marginal"]["value"], r["marginal"]["ci_low_95"], r["marginal"]["ci_high_95"],
             r["average_intensity_kg_per_mwh"]] for r in out["rows"]]
    return {"ba": out["ba_code"], "month": int(month), "estimated_on": out["estimated_on"],
            "columns": ["local_hour", "marginal_kg_per_mwh", "ci_low_95", "ci_high_95", "average_kg_per_mwh"],
            "rows": rows}


def get_miso_overnight() -> dict:
    return ev.miso_overnight()


def get_eda_section(section: str) -> dict:
    if section not in EDA_SECTIONS:
        raise ToolError(f"unknown section {section!r}")
    text = EDA_REPORT.read_text(encoding="utf-8")
    head = EDA_SECTIONS[section]
    start = text.index(head)
    level = head.split(" ")[0]
    nxt = re.search(rf"^{level} ", text[start + len(head):], flags=re.MULTILINE)
    body = text[start: start + len(head) + (nxt.start() if nxt else len(text))]
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)  # drop figure links
    return {"section": section, "source": "reports/eda_findings.md", "text": body[:3000]}


def run(name: str, args: dict, profile: pd.DataFrame) -> dict:
    try:
        if name == "get_ba_status":
            return get_ba_status(**args)
        if name == "get_schedule":
            return get_schedule(profile, **args)
        if name == "get_mef":
            return get_mef(profile, **args)
        if name == "get_miso_overnight":
            return get_miso_overnight()
        if name == "get_eda_section":
            return get_eda_section(**args)
        return {"error": f"unknown tool {name}"}
    except (ToolError, service.BadRequest, TypeError) as exc:
        return {"error": str(exc)}
