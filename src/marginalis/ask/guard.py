"""Deterministic guarantees around the LLM.

- `required_notes`: disclosures attached verbatim by code (validation status, CISO rule
  misfire, calibration), so the model cannot drop or soften them.
- `check_draft`: rejects drafts with ungrounded numbers, marginal figures without a CI,
  or validation/savings claims for BAs the hold-out did not confirm.
- `fallback_answer`: template answer from evidence when a draft fails twice.
"""

from __future__ import annotations

import json
import re

from marginalis.api import evidence as ev
from marginalis.ask.scope import COVERAGE, Scope

BA_WORDS = {"ERCO": r"\b(ercot?|texas)\b", "CISO": r"\b(caiso|ciso|california)\b", "MISO": r"\b(miso)\b"}
CLAIM = r"\b(validated|confirmed|proven|guarantee[sd]?|will save|would save|saves|saved|reduces|cuts|works)\b"
NEGATION = (r"\b(not|no|never|none|isn't|wasn't|aren't|weren't|cannot|can't|couldn't|unconfirmed|unvalidated|"
            r"neither|nor|without)\b|n't\b")
GENERAL = r"\b(every|all|each)\s+(region|regions|ba|bas|grid|grids)\b|\beverywhere\b|\ball three\b"
KG_NUMBER = r"-?\d[\d,]*(\.\d+)?\s*(kg|t\b|tonnes?)"
CI_MARKER = r"(\bci\b|95\s?%|confidence|interval|-?\d[\d,.]*\s*(–|-|to)\s*-?\d[\d,.]*)"
MARGINAL_WORDS = r"\b(margin\w*|mef|factor|saving|savings|gap|avoid\w*|shift\w*|save\w*)\b"
NUMBER = r"(?<![\w.])-?\d[\d,]*(\.\d+)?"
ALWAYS_OK = {95.0, 50.0}
REFUSAL = re.compile(r"\b(i['’]?m sorry|i am sorry|i can(?:no|['’])?t (?:provide|help|give|answer|share|do)|"
                     r"i(?: am|['’]m) (?:unable|not able)|unable to (?:provide|help|answer)|i won['’]?t)\b")
REFUSAL_VIOLATION = "declined instead of answering from the data (bare refusal)"


def is_bare_refusal(text: str) -> bool:
    """A short decline that answers nothing (the model never looked at the data)."""
    return bool(REFUSAL.search(text.lower())) and len(text) < 400


def required_notes(scope: Scope, tools_used: list[dict]) -> list[str]:
    notes: list[str] = []
    bas = list(ev.results()["decision"]) if scope.all_regions else list(scope.bas)
    for call in tools_used:
        ba = call["args"].get("ba")
        if ba and ba.upper() in ev.results()["decision"] and ba.upper() not in bas:
            bas.append(ba.upper())
    schedule_called = any(c["name"] == "get_schedule" for c in tools_used)
    # Validation status rides along with every answer that involves a BA. Keyword triggers
    # are too easy to phrase around ("so I'll get about 230 there too?").
    for ba in bas:
        st = ev.ba_status(ba)
        notes.append(f"{ba} validation: {st['summary']}")
        if "eda_estimate_not_confirmed" in st:
            notes.append(f"{ba}: {st['eda_estimate_not_confirmed']}")
    ciso_2026 = "CISO" in bas and (scope.touches_2026 or any(
        c["name"] == "get_schedule" and c["args"].get("ba", "").upper() == "CISO"
        and str(c["args"].get("date", "")) >= "2026-01-01" for c in tools_used))
    if ciso_2026:
        notes.append("CISO data caveat: " + ev.misfire_caveat("CISO"))
    hour_call = any(c["name"] == "get_mef" and c["args"].get("hour") is not None for c in tools_used)
    if scope.specific_hour or hour_call or ((scope.specific_day or schedule_called) and scope.quantity_intent):
        notes.append("Single-hour caution: " + ev.calibration_note()["text"])
    notes += [date_hour_note(d, h) for d, h in scope.date_hours]
    return notes


def date_hour_note(d, h: int) -> str:
    slopes = ev.calibration_note()["calibration_slopes_2025"].values()
    return (f"Specific date and hour: this reflects the typical {d:%B} {h:02d}:00 (local) pattern from "
            f"2019–2024 (calibration slopes {min(slopes):.2f}–{max(slopes):.2f}), not a measurement of "
            f"{d.isoformat()}.")


def _date_patterns(d) -> str:
    month = d.strftime("%B").lower()
    return (rf"({d.isoformat()}|\b{d.day}(st|nd|rd|th)?\s+{month}\b|\b{month}\s+{d.day}(st|nd|rd|th)?\b|"
            rf"\bthat (day|date|hour)\b|\bthis (day|date)\b)")


def _numbers(text: str) -> list[float]:
    out = []
    for m in re.finditer(NUMBER, text):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return out


def evidence_numbers(tool_results: list[dict], extra_texts: list[str]) -> list[float]:
    nums = _numbers(json.dumps(tool_results)) + [n for t in extra_texts for n in _numbers(t)]
    return nums


def _grounded(x: float, pool: list[float]) -> bool:
    ax = abs(x)
    if x in ALWAYS_OK or (float(x).is_integer() and 0 <= x <= 24):  # hours, months, durations
        return True
    if 2019 <= x <= 2026 and float(x).is_integer():  # years
        return True
    return any(abs(ax - abs(e)) <= max(1.0, 0.01 * abs(e)) or abs(ax - round(abs(e), -1)) < 1e-9 for e in pool)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


MEASUREMENT = r"\b(measured|observed|actual|actually|recorded|was emitted|emitted|caused|did cause)\b"
TYPICAL = r"\b(typical\w*|pattern|profile|2019|historical|on average|usual\w*)\b"
PARITY = r"\b(both|similar\w*|same|equal\w*|comparable|likewise|as well|too|matches|match)\b"


def check_draft(draft: str, tool_results: list[dict], question: str, sc: Scope | None = None) -> list[str]:
    """List of rule violations; empty means the draft may be shown."""
    from marginalis.ask.scope import parse

    sc = sc or parse(question)
    violations = []
    pool = evidence_numbers(tool_results, [question, json.dumps(_status_facts())])
    stripped = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}:\d{2}\b", " ", draft)
    ungrounded = sorted({x for x in _numbers(stripped) if not _grounded(x, pool)})
    if ungrounded:
        violations.append(f"numbers not found in the tool results: {ungrounded[:6]}")
    for s in _sentences(draft):
        low = s.lower()
        average_only = "average" in low and not re.search(MARGINAL_WORDS, low)
        # Rejecting the user's own figure ("230 kg/MWh cannot be assumed for ERCOT") needs no CI.
        q_nums = _numbers(question)
        kg_nums = [float(m.group(0).split()[0].replace(",", "")) for m in re.finditer(r"-?\d[\d,]*(\.\d+)?(?=\s*kg)", low)]
        rebuttal = bool(re.search(NEGATION, low)) and kg_nums and all(
            any(abs(k - qn) < 1e-9 for qn in q_nums) for k in kg_nums)
        if re.search(KG_NUMBER, low) and not average_only and not rebuttal and not re.search(CI_MARKER, low):
            violations.append(f"marginal figure without its 95% CI: {s.strip()[:120]!r}")
        if re.search(CLAIM, low) and not re.search(NEGATION, low):
            for ba in ("ERCO", "CISO"):
                if not ev.is_confirmed(ba) and re.search(BA_WORDS[ba], low):
                    violations.append(f"presents an unvalidated {ba} result as validated: {s.strip()[:120]!r}")
            if re.search(GENERAL, low):
                violations.append(f"generalises a result to all regions: {s.strip()[:120]!r}")
        negated = bool(re.search(NEGATION, low))
        # A typical month x hour factor must not be presented as a measurement of one day.
        if re.search(KG_NUMBER, low) and not re.search(TYPICAL, low):
            if re.search(MEASUREMENT, low) and not negated:
                violations.append(f"presents a typical factor as a measurement: {s.strip()[:120]!r}")
            elif any(re.search(_date_patterns(d), low) for d, _ in sc.date_hours):
                violations.append(f"ties a typical factor to a specific date: {s.strip()[:120]!r}")
        # Parity between a hold-out-confirmed and an unconfirmed BA.
        named = {ba for ba, pat in BA_WORDS.items() if re.search(pat, low)}
        confirmed = {ba for ba in named if ev.is_confirmed(ba)}
        if confirmed and named - confirmed and re.search(PARITY, low) and not negated:
            violations.append(f"implies parity between confirmed and unconfirmed BAs: {s.strip()[:120]!r}")
    return violations


def _status_facts() -> dict:
    return {ba: ev.ba_status(ba) for ba in ev.results()["decision"]}


def out_of_scope_answer(scope: Scope) -> str | None:
    parts = []
    if scope.other_grids:
        parts.append(f"Marginalis only covers ERCOT (ERCO), CAISO (CISO) and MISO; "
                     f"{', '.join(g.upper() for g in scope.other_grids)} is not in the pipeline, so I can't answer "
                     "for it without extrapolating from other grids.")
    if scope.out_of_range:
        parts.append(f"The data covers {COVERAGE[0]:%Y-%m-%d} to {COVERAGE[1]:%Y-%m-%d}. "
                     f"{', '.join(scope.out_of_range)} is outside that range, and I won't extrapolate. "
                     "I can describe the typical pattern for a month from the 2019–2024 training profile, "
                     "but that is not a forecast for a specific date.")
    return " ".join(parts) or None


def fallback_answer(scope: Scope, tool_results: list[dict]) -> str:
    """Conservative answer assembled from evidence only (used when drafts keep failing)."""
    lines = ["Here is what the evidence supports (a template answer, because the generated text did not "
             "pass the grounding checks):"]
    for r in tool_results:
        out = r["result"]
        if "error" in out:
            lines.append(f"- {out['error']}")
        elif r["name"] == "get_schedule":
            m, a = out["marginal_optimal_window"], out["average_optimal_window"]
            lo, hi = m["marginal_ci_bounds_conservative"]
            lines.append(f"- {out['ba']} on {out['date']}: marginal-optimal window {m['start_local'][11:]}–"
                         f"{m['end_local'][11:]} (marginal {m['marginal_mean_kg_per_mwh']:,.0f} kg/MWh, "
                         f"conservative 95% CI bounds {lo:,.0f} to {hi:,.0f}); average-optimal window "
                         f"{a['start_local'][11:]}–{a['end_local'][11:]}.")
        elif r["name"] == "get_mef":
            for h, v, lo, hi, avg in out["rows"][:24]:
                lines.append(f"- {out['ba']} month {out['month']} hour {h:02d}: marginal {v:,.0f} kg/MWh "
                             f"(95% CI {lo:,.0f} to {hi:,.0f}), average {avg:,.0f}.")
        elif r["name"] == "get_ba_status":
            lines.append(f"- {out['ba']}: {out['summary']}")
            if "eda_estimate_not_confirmed" in out:
                lines.append(f"- {out['ba']}: {out['eda_estimate_not_confirmed']}")
        elif r["name"] == "get_miso_overnight":
            ho = out["holdout_2025"]
            lines.append(f"- MISO overnight, 2025: marginal {ho['marginal']['value']:,.0f} kg/MWh (95% CI "
                         f"{ho['marginal']['ci_low_95']:,.0f} to {ho['marginal']['ci_high_95']:,.0f}) vs average "
                         f"{ho['average']:,.0f}. This is a factor comparison, not a scheduling saving.")
    if len(lines) == 1:
        lines.append("- See the notes below.")
    return "\n".join(lines)
