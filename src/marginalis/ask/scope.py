"""Deterministic reading of a question: which BAs, which dates, what kind of claim.

Runs before the LLM so scope limits and mandatory disclosures never depend on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from marginalis.config import DATA_END, DATA_START

COVERAGE = (DATA_START.date(), DATA_END.date() - timedelta(days=1))  # 2019-07-01 .. 2026-08-31

BA_ALIASES = {
    "ERCO": r"\b(ercot?|texas)\b",
    "CISO": r"\b(caiso|ciso|california)\b",
    "MISO": r"\b(miso|midcontinent|mid-continent)\b",
}
OTHER_GRIDS = (r"\b(pjm|spp|swpp|nyiso|new york iso|iso-?ne|new england|bpa|bonneville|tva|"
               r"southern company|duke energy|pacificorp|ieso|aeso|nem|national grid|entso-?e)\b")
ALL_REGIONS = r"\b(every|all|each|any)\s+(region|regions|ba|bas|grid|grids|market|markets|iso|isos)\b|\beverywhere\b|\ball three\b"
SAVINGS = (r"\b(schedul\w*|shift\w*|sav(e|es|ed|ing|ings)|recommend\w*|should\s+(i|we)|cut\w*|reduc\w*|"
           r"switch\w*|worth|best time|better time|when (should|to)|charg\w*|avoid\w*|benefit\w*|work\w*)\b")
SPECIFIC_HOUR = r"\b(\d{1,2}\s?(am|pm)|\d{1,2}:\d{2}|at\s+\d{1,2}\b|noon|midnight|this hour|next hour|single hour|specific hour|one hour)\b"
QUANTITY = r"\b(how much|predict\w*|impact|co2|co₂|emission\w*|kg|tonnes?|tons?|number|figure|estimate)\b"
RELATIVE_DAYS = {"today": 0, "tonight": 0, "now": 0, "tomorrow": 1, "yesterday": -1}
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"], start=1)}


@dataclass
class Scope:
    bas: list[str] = field(default_factory=list)
    all_regions: bool = False
    other_grids: list[str] = field(default_factory=list)
    dates: list[date] = field(default_factory=list)  # explicit or relative days
    periods: list[tuple[date, date]] = field(default_factory=list)  # months / years mentioned
    savings_intent: bool = False
    specific_hour: bool = False
    quantity_intent: bool = False

    @property
    def out_of_range(self) -> list[str]:
        lo, hi = COVERAGE
        bad = [d.isoformat() for d in self.dates if not lo <= d <= hi]
        bad += [f"{a.isoformat()}..{b.isoformat()}" for a, b in self.periods if b < lo or a > hi]
        return bad

    @property
    def touches_2026(self) -> bool:
        return any(d >= date(2026, 1, 1) for d in self.dates) or any(b >= date(2026, 1, 1) for _, b in self.periods)

    @property
    def specific_day(self) -> bool:
        return bool(self.dates)


def parse(question: str, today: date | None = None) -> Scope:
    q = question.lower()
    today = today or date.today()
    s = Scope()
    s.bas = [ba for ba, pat in BA_ALIASES.items() if re.search(pat, q)]
    s.all_regions = bool(re.search(ALL_REGIONS, q))
    s.other_grids = sorted({m.group(0) for m in re.finditer(OTHER_GRIDS, q)})
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", q):
        try:
            s.dates.append(date(int(m[1]), int(m[2]), int(m[3])))
        except ValueError:
            pass
    month_names = "|".join(MONTHS)
    for m in re.finditer(rf"\b({month_names})\s+(\d{{1,2}})(st|nd|rd|th)?,?\s+(\d{{4}})\b", q):
        s.dates.append(date(int(m[4]), MONTHS[m[1]], int(m[2])))
    for m in re.finditer(rf"\b({month_names})\s+(\d{{4}})\b", q):
        y, mo = int(m[2]), MONTHS[m[1]]
        end = date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1)
        s.periods.append((date(y, mo, 1), end))
    for word, offset in RELATIVE_DAYS.items():
        if re.search(rf"\b{word}\b", q):
            s.dates.append(today + timedelta(days=offset))
    if re.search(r"\bnext (week|month|year)\b", q):
        s.dates.append(today + timedelta(days=7))
    for m in re.finditer(r"\b(19\d{2}|20\d{2})\b", q):
        y = int(m[1])
        if not any(d.year == y for d in s.dates) and not any(a.year == y for a, _ in s.periods):
            s.periods.append((date(y, 1, 1), date(y, 12, 31)))
    s.savings_intent = bool(re.search(SAVINGS, q))
    s.specific_hour = bool(re.search(SPECIFIC_HOUR, q))
    s.quantity_intent = bool(re.search(QUANTITY, q))
    return s
