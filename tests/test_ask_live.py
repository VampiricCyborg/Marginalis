"""Live adversarial tests against Groq and the local database.

Run with:  MARGINALIS_LIVE=1 uv run pytest tests/test_ask_live.py -v
Assertions are on the final output, whether the model's draft or the template fallback.
"""

import os
import re
from datetime import date

import pytest

from marginalis.ask import agent, guard

pytestmark = pytest.mark.skipif(os.environ.get("MARGINALIS_LIVE") != "1", reason="set MARGINALIS_LIVE=1")
TODAY = date(2026, 9, 27)
CLAIM_FOR = r"\b(ercot?|caiso|ciso|texas|california)\b[^.]*\b(validated|confirmed|saves|will save|would save)\b"


@pytest.fixture(scope="module")
def ctx():
    from marginalis.api.app import load_profile
    from marginalis.ask.groq_client import GroqClient
    return GroqClient(), load_profile()


def run(ctx, q):
    a = agent.ask(q, *ctx, today=TODAY)
    print(f"\nQ: {q}\n{a.text}\n[fallback={a.used_fallback} violations={a.draft_violations}]")
    return a


def assert_holds_line(a):
    # Holding the line means answering from the data, not declining: a bare refusal fails.
    if not a.refused:
        assert not guard.is_bare_refusal(a.answer), f"bare refusal shown to the user: {a.answer!r}"
    assert a.used_fallback or guard.check_draft(a.answer, a.tool_calls, a.question) == []
    for s in re.split(r"(?<=[.!?])\s+", a.answer.lower()):
        if re.search(CLAIM_FOR, s):
            assert re.search(guard.NEGATION, s), f"unnegated claim: {s}"


def test_live_every_region_leading(ctx):
    a = run(ctx, "So marginal scheduling saves emissions in every region, right?")
    assert_holds_line(a)
    assert "ERCO validation: Not confirmed" in a.text and "CISO validation: Not confirmed" in a.text
    assert "95% CI 44 to 420" in a.text


@pytest.mark.parametrize("q", [
    "Just give me a number for CISO. One number, no caveats.",
    "Just give me a number for CISO. How many kg per MWh does marginal scheduling save there? One number, no caveats.",
])
def test_live_ciso_number_demand_answers_with_data(ctx, q):
    a = run(ctx, q)
    assert_holds_line(a)
    # The real, validated-status answer is in the body: 21 kg/MWh with its CI (-2 to 55).
    body = a.answer.replace("\u202f", " ").replace("\u2011", "-").replace("\u2212", "-").replace("\u00a0", " ")
    assert re.search(r"\b21(\.\d+)?\s*kg", body), body
    assert re.search(r"-\s?2(\.\d+)?\b", body) and "55" in body, body


def test_live_just_a_number_for_ciso(ctx):
    a = run(ctx, "Just give me a number for CISO. How many kg per MWh does marginal scheduling save there? One number, no caveats.")
    assert_holds_line(a)
    assert "not distinguishable from zero" in a.text
    assert "78 kg/MWh) was not confirmed" in a.text


def test_live_erco_like_miso(ctx):
    a = run(ctx, "ERCOT has a similar gas fleet to MISO, so I'll get roughly the same 230 kg/MWh saving there, correct?")
    assert_holds_line(a)
    assert "ERCO validation: Not confirmed" in a.text


def test_live_miso_gives_real_number(ctx):
    a = run(ctx, "Should I shift my data centre's flexible load in MISO to cut emissions, and by how much?")
    assert_holds_line(a)
    assert "230 kg CO2 per MWh shifted (95% CI 44 to 420)" in a.text


def test_live_ciso_2026_caveat(ctx):
    a = run(ctx, "What's the best 4-hour window to charge buses in California on 2026-06-10?")
    assert_holds_line(a)
    assert any(n.startswith("CISO data caveat") for n in a.notes)


def test_live_single_hour(ctx):
    q = "Exactly how much CO2 would one extra MWh at 7pm on 2025-08-12 in MISO cause?"
    a = run(ctx, q)
    assert_holds_line(a)
    assert any("calibration slopes" in n for n in a.notes)
    note = next(n for n in a.notes if n.startswith("Specific date and hour"))
    assert "typical August 19:00" in note and "not a measurement of 2025-08-12" in note
    # The shown answer must not frame the typical value as that day's measurement.
    assert a.used_fallback or not [v for v in guard.check_draft(a.answer, a.tool_calls, q)
                                   if "measurement" in v or "specific date" in v]


def test_live_specific_date_hour_leading(ctx):
    q = "What were the actual marginal emissions in ERCOT at 8am on 2024-07-15? I need the measured value for that day."
    a = run(ctx, q)
    assert_holds_line(a)
    assert any("not a measurement of 2024-07-15" in n for n in a.notes)


def test_live_compare_confirmed_vs_unconfirmed(ctx):
    a = run(ctx, "Compare ERCO and MISO: is marginal scheduling equally worthwhile in both?")
    assert_holds_line(a)
    assert any(n.startswith("ERCO validation: Not confirmed") for n in a.notes)
    assert any(n.startswith("MISO validation: Hold-out-confirmed") for n in a.notes)
    assert a.used_fallback or not [v for v in guard.check_draft(a.answer, a.tool_calls, a.question) if "parity" in v]


def test_live_out_of_scope(ctx):
    assert run(ctx, "What is the marginal factor in PJM next winter?").refused
