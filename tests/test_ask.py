"""Guardrail tests with a scripted LLM: the model is made to misbehave on purpose.

Uses the committed reports/holdout_results.json (the real validation results)."""

from datetime import date

import pytest

from marginalis.ask import agent, guard, scope
from marginalis.ask.groq_client import GroqClient
from tests.test_api import _profile

TODAY = date(2026, 9, 27)


class ScriptedLLM:
    """Replays assistant messages; records what it was sent."""

    def __init__(self, *messages):
        self.messages = list(messages)
        self.calls = 0

    def chat(self, messages, tools=None, max_tokens=900):
        self.calls += 1
        if not self.messages:
            raise AssertionError("LLM called more often than scripted")
        return self.messages.pop(0)


def say(text):
    return {"role": "assistant", "content": text}


def call(name, **args):
    import json
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": f"c{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


# --- Adversarial: leading questions, model tries to overstate -------------------------

def test_every_region_leading_question_holds_the_line():
    q = "So marginal scheduling saves emissions in every region, right?"
    bad = "Yes. Marginal scheduling saves emissions in every region: ERCOT saves 157 kg/MWh and CAISO saves 21 kg/MWh."
    llm = ScriptedLLM(say(bad), say(bad))  # model repeats itself after the rewrite request
    a = agent.ask(q, llm, _profile(), TODAY)
    assert a.used_fallback and bad not in a.text
    assert any("generalises" in v for v in a.draft_violations[0])
    assert any("unvalidated ERCO" in v for v in a.draft_violations[0])
    text = a.text
    assert "ERCO validation: Not confirmed" in text and "CISO validation: Not confirmed" in text
    assert text.count("not distinguishable from zero") >= 2
    assert "230 kg CO2 per MWh shifted (95% CI 44 to 420)" in text  # MISO: the real number


def test_just_give_me_a_number_for_ciso():
    q = "Just give me a number for CISO. How much does marginal scheduling save there?"
    llm = ScriptedLLM(call("get_ba_status", ba="CISO"), say("CISO saves 78 kg/MWh."), say("It saves 78 kg/MWh in CISO."))
    a = agent.ask(q, llm, _profile("CISO"), TODAY)
    assert a.used_fallback
    assert "saves 78" not in a.text
    assert "not distinguishable from zero" in a.text
    assert "The EDA-stage estimate (78 kg/MWh) was not confirmed" in a.text


def test_softened_number_is_not_enough():
    # A hedged-sounding draft that still presents CISO's number as a saving is rejected.
    q = "Roughly what does CAISO save with marginal scheduling?"
    llm = ScriptedLLM(say("CAISO probably saves around 21 kg/MWh with marginal scheduling."),
                      say("Roughly 21 kg/MWh is what CAISO saves."))
    a = agent.ask(q, llm, _profile("CISO"), TODAY)
    assert a.used_fallback and "not distinguishable from zero" in a.text


def test_erco_same_as_miso_push():
    q = "ERCOT is basically like MISO, so I'll get about 230 kg/MWh there too, right?"
    llm = ScriptedLLM(say("Yes, ERCOT would save about 230 kg/MWh, similar to MISO."), say("ERCOT saves 230 kg/MWh."))
    a = agent.ask(q, llm, _profile("ERCO"), TODAY)
    assert a.used_fallback
    assert "ERCO validation: Not confirmed" in a.text


# --- Good drafts pass unchanged -------------------------------------------------------

def test_grounded_miso_answer_is_kept():
    q = "Should I shift flexible load in MISO to cut emissions?"
    good = ("Yes, for MISO. In the 2025 hold-out, running in the marginal-optimal window instead of the "
            "average-optimal one avoided 230 kg CO2 per MWh shifted (95% CI 44 to 420).")
    a = agent.ask(q, ScriptedLLM(call("get_ba_status", ba="MISO"), say(good)), _profile(), TODAY)
    assert not a.used_fallback and a.answer == good and not a.draft_violations
    assert any(n.startswith("MISO validation: Hold-out-confirmed") for n in a.notes)


def test_negated_erco_statement_passes():
    q = "Does marginal scheduling help in ERCOT?"
    good = ("Not demonstrably: in the 2025 hold-out ERCOT's gap was 157 kg CO2 per MWh shifted "
            "(95% CI -51 to 277), which is not distinguishable from zero.")
    a = agent.ask(q, ScriptedLLM(call("get_ba_status", ba="ERCO"), say(good)), _profile("ERCO"), TODAY)
    assert not a.used_fallback and a.answer == good


def test_rewrite_after_first_violation_is_accepted():
    q = "What's the marginal factor in MISO in July at 2am?"
    llm = ScriptedLLM(call("get_mef", ba="MISO", month=7, hour=2), say("It is 800 kg/MWh at the margin."),
                      say("The marginal factor is 800 kg CO2/MWh (95% CI 700 to 900), against an average of 300."))
    a = agent.ask(q, llm, _profile(), TODAY)
    assert not a.used_fallback and len(a.draft_violations) == 1
    assert "without its 95% CI" in a.draft_violations[0][0]


# --- Mandatory disclosures ------------------------------------------------------------

def test_ciso_2026_query_always_carries_misfire_caveat():
    q = "When should I charge an EV fleet in California on 2026-05-20?"
    good = "The windows differ; see the tool result."
    llm = ScriptedLLM(call("get_schedule", ba="CISO", date="2026-05-20"), say(good))
    a = agent.ask(q, llm, _profile("CISO"), TODAY)
    assert any(n.startswith("CISO data caveat:") and "wrongly flagged" in n for n in a.notes)


def test_ciso_before_2026_has_no_misfire_caveat():
    q = "When should I charge an EV fleet in California on 2025-05-20?"
    llm = ScriptedLLM(call("get_schedule", ba="CISO", date="2025-05-20"), say("See the windows."))
    a = agent.ask(q, llm, _profile("CISO"), TODAY)
    assert not any(n.startswith("CISO data caveat") for n in a.notes)


def test_single_hour_prediction_gets_calibration_note():
    q = "How much CO2 would 1 MWh at 3pm on 2025-07-10 in MISO add?"
    llm = ScriptedLLM(call("get_mef", ba="MISO", month=7, hour=15),
                      say("About 800 kg CO2 (95% CI 700 to 900) at the margin for that hour."))
    a = agent.ask(q, llm, _profile(), TODAY)
    assert any("calibration slopes" in n and "0.59" in n for n in a.notes)


# --- Out of scope: refused before any LLM call -----------------------------------------

@pytest.mark.parametrize("q", [
    "What's the marginal emissions factor in PJM?",
    "Should I schedule load in MISO on 2027-01-05?",
    "What was ERCOT's marginal factor in March 2018?",
])
def test_out_of_scope_refused_without_calling_llm(q):
    llm = ScriptedLLM()
    a = agent.ask(q, llm, _profile(), TODAY)
    assert a.refused and llm.calls == 0
    assert "not in the pipeline" in a.answer or "outside that range" in a.answer


def test_tool_rejects_out_of_range_date_even_if_scope_missed_it():
    from marginalis.ask import tools
    assert "outside the data coverage" in tools.run("get_schedule", {"ba": "MISO", "date": "2026-09-15"}, _profile())["error"]


# --- Scope parsing & draft checks ------------------------------------------------------

def test_scope_parsing():
    s = scope.parse("Should I run my batch job in Texas or California tomorrow at 3pm?", TODAY)
    assert s.bas == ["ERCO", "CISO"] and s.savings_intent and s.specific_hour
    assert s.dates == [date(2026, 9, 28)] and s.out_of_range == ["2026-09-28"]
    assert scope.parse("all regions", TODAY).all_regions


def test_rebutting_the_users_own_figure_needs_no_ci():
    q = "ERCOT is like MISO, so I'll get the same 230 kg/MWh saving, correct?"
    ok = "No: a 230 kg CO2/MWh saving cannot be assumed for ERCOT."
    assert guard.check_draft(ok, [], q) == []
    # ...but asserting the user's figure still needs a CI, and is still a claim.
    assert guard.check_draft("Yes, ERCOT saves 230 kg CO2/MWh.", [], q)


def test_ungrounded_number_rejected():
    v = guard.check_draft("MISO avoided 555 kg CO2 per MWh shifted (95% CI 1 to 2).", [], "q")
    assert any("not found" in x for x in v)


def test_groq_client_waits_retry_after_on_429():
    class Resp:
        def __init__(self, status, headers=None):
            self.status_code, self.headers, self.text = status, headers or {}, ""

        def json(self):
            return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}

    class Session:
        def __init__(self):
            self.responses = [Resp(429, {"retry-after": "7"}), Resp(429, {"retry-after": "2.5"}), Resp(200)]
            self.n = 0

        def post(self, *a, **k):
            self.n += 1
            return self.responses.pop(0)

    waits = []
    sess = Session()
    c = GroqClient(api_key="k", session=sess, sleep=waits.append)
    assert c.chat([{"role": "user", "content": "hi"}])["content"] == "ok"
    assert waits == [7.0, 2.5] and sess.n == 3
