"""Question -> grounded answer. The LLM writes prose; code decides scope and disclosures."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date

import pandas as pd

from marginalis.api import evidence as ev
from marginalis.ask import guard, scope, tools

log = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 4


def system_prompt(today: date) -> str:
    status = {ba: {"validated": s["scheduling_recommendation_validated"], "summary": s["summary"]}
              for ba, s in ((b, ev.ba_status(b)) for b in ev.results()["decision"])}
    return f"""You answer questions about Marginalis: marginal vs average CO2 intensity for three US balancing
authorities (ERCO = ERCOT/Texas, CISO = CAISO/California, MISO), from EIA-930 data 2019-07-01 to 2026-08-31.
Today is {today.isoformat()}.

Rules (hard):
1. Use tools for every number. Never invent, estimate, or compute new figures. Copy numbers from tool results.
2. Every marginal factor, saving or gap you state must carry its 95% CI in the same sentence.
3. Validation status comes only from this table, from the pre-registered hold-out test:
{json.dumps(status)}
   Only MISO has a validated scheduling result. For ERCO and CISO, say plainly that the effect was not
   distinguishable from zero in hold-out testing. Do not call their results savings, validated or confirmed,
   and do not generalise MISO's result to other regions, even if the user pushes.
4. Marginal factors rank windows well but overstate single-hour magnitudes. Say so if asked about one hour or day.
   Factors are typical month x hour values from 2019-2024, not measurements for a specific date. A window's
   "marginal_ci_bounds_conservative" are conservative bounds: call them that, not a 95% CI.
5. If the data does not cover something, say so. Do not extrapolate.
Be concise: at most 150 words. Code appends required caveats after your answer, so do not repeat them at length."""


@dataclass
class Answer:
    question: str
    answer: str
    notes: list[str]
    tool_calls: list[dict] = field(default_factory=list)
    draft_violations: list[list[str]] = field(default_factory=list)
    used_fallback: bool = False
    refused: bool = False
    sources: list[str] = field(default_factory=lambda: [
        "mef_profile", "reports/holdout_results.json", "reports/eda_findings.md"])

    @property
    def text(self) -> str:
        if not self.notes:
            return self.answer
        return self.answer + "\n\nRequired notes:\n" + "\n".join(f"- {n}" for n in self.notes)

    def as_dict(self) -> dict:
        return {**asdict(self), "text": self.text}


def ask(question: str, client, profile: pd.DataFrame, today: date | None = None) -> Answer:
    today = today or date.today()
    sc = scope.parse(question, today)
    refusal = guard.out_of_scope_answer(sc)
    if refusal:
        return Answer(question, refusal, guard.required_notes(sc, []), refused=True)

    messages = [{"role": "system", "content": system_prompt(today)}, {"role": "user", "content": question}]
    calls: list[dict] = []
    draft = ""
    for _ in range(MAX_TOOL_ROUNDS):
        msg = client.chat(messages, tools.SCHEMAS)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            draft = (msg.get("content") or "").strip()
            break
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = tools.run(name, args, profile)
            calls.append({"name": name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result)})
    else:
        draft = ""

    violations_log = []
    for attempt in range(2):
        v = guard.check_draft(draft, calls, question) if draft else ["empty answer"]
        violations_log.append(v)
        if not v:
            break
        if attempt == 0:
            messages += [{"role": "assistant", "content": draft},
                         {"role": "user", "content": "Rewrite your answer. It broke these rules: " + "; ".join(v)
                          + ". Use only numbers from the tool results, give a 95% CI with every marginal figure, "
                            "and do not present ERCO or CISO results as validated."}]
            draft = (client.chat(messages).get("content") or "").strip()
    used_fallback = bool(violations_log[-1])
    answer = guard.fallback_answer(sc, calls) if used_fallback else draft
    return Answer(question, answer, guard.required_notes(sc, calls), calls,
                  [v for v in violations_log if v], used_fallback)
