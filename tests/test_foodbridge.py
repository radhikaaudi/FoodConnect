"""FoodBridge test suite.

Runs with pytest (``python3 -m pytest``) or standalone (``python3 tests/test_foodbridge.py``).
Covers the safety guardrails, the matcher's eligibility + reasoning, impact math, dispatch
self-healing, the offline brain, and a full end-to-end run.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from foodbridge import safety
from foodbridge.brain import SimulatedBrain, build_brain
from foodbridge.dispatcher import dispatch
from foodbridge.impact import Impact
from foodbridge.matcher import rank_recipients
from foodbridge.memory import Memory
from foodbridge.models import Donation, Driver, Recipient

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def _donation(**over):
    base = dict(id="D-T", donor_name="Test", donor_type="grocery", item="Test produce",
                category="produce", weight_lbs=24, value_usd=48, ready_minute=0,
                pickup_deadline_minute=120, storage_temp="refrigerated",
                hours_unrefrigerated=0.5, allergens=[])
    base.update(over)
    return Donation(**base)


def _recipient(**over):
    base = dict(id="R-T", name="Test Shelter", type="shelter", location=(5, 4),
                needs=["produce", "protein"], storage_capacity_lbs=100, refrigeration=True,
                open_from_minute=0, open_to_minute=600, serves_children=True,
                dietary_restrictions=[], last_served_minute=-600)
    base.update(over)
    return Recipient(**base)


# -- safety -------------------------------------------------------------------------------
def test_safety_rejects_spoiled_perishable():
    d = _donation(category="dairy", hours_unrefrigerated=4.5)
    assert safety.assess(d).verdict == "reject"


def test_safety_escalates_borderline():
    d = _donation(category="protein", hours_unrefrigerated=3.2)
    assert safety.assess(d).verdict == "escalate"


def test_safety_passes_fresh():
    assert safety.assess(_donation(hours_unrefrigerated=0.2)).verdict == "safe"


# -- matcher ------------------------------------------------------------------------------
def test_matcher_disqualifies_on_capacity():
    d = _donation(weight_lbs=500)
    opts = rank_recipients(d, [_recipient()], now=10)
    assert opts[0].disqualified is not None


def test_matcher_rewards_nutrition_and_fairness():
    kids = _recipient(id="K", name="Kids", serves_children=True, last_served_minute=-600)
    adults = _recipient(id="A", name="Adults", serves_children=False, last_served_minute=0)
    opts = rank_recipients(_donation(category="produce"), [adults, kids], now=100)
    assert opts[0].recipient.id == "K"  # nutrition + fairness win


def test_matcher_respects_dietary_conflict():
    r = _recipient(dietary_restrictions=["nuts"])
    opts = rank_recipients(_donation(allergens=["nuts"]), [r], now=10)
    assert opts[0].disqualified is not None


# -- impact -------------------------------------------------------------------------------
def test_impact_math():
    imp = Impact()
    imp.add(120, 100)  # 120 lbs
    assert imp.meals == 100          # 120 / 1.2
    assert imp.money_usd == 100
    assert imp.co2_lbs == 300        # 120 * 2.5


# -- dispatch -----------------------------------------------------------------------------
def test_dispatch_self_heals_to_reliable_driver():
    d = _donation(storage_temp="ambient", category="produce")
    flaky = Driver("F", "Flaky", (5, 4), True, 0.0, True)   # always declines
    solid = Driver("S", "Solid", (5, 4), True, 1.0, True)   # always accepts
    res = dispatch(d, _recipient(), [flaky, solid], Memory("/dev/null"),
                   random.Random(1), log=lambda *_: None)
    assert res.status == "assigned" and res.driver.id == "S"


def test_dispatch_fails_when_all_decline():
    d = _donation(storage_temp="ambient")
    none = Driver("N", "None", (5, 4), True, 0.0, True)
    res = dispatch(d, _recipient(), [none], Memory("/dev/null"),
                   random.Random(1), log=lambda *_: None)
    assert res.status == "failed"


# -- brain --------------------------------------------------------------------------------
def test_offline_brain_is_simulated():
    brain = build_brain(prefer_llm=False)
    assert isinstance(brain, SimulatedBrain) and not brain.is_llm


def test_brain_composes_messages():
    brain = SimulatedBrain()
    driver = Driver("V", "Sam", (5, 4), True, 0.9, True)
    msg = brain.compose("driver_request", driver=driver, donation=_donation(),
                        recipient=_recipient(), minutes_left=90)
    assert "Sam" in msg and "YES" in msg


# -- end to end ---------------------------------------------------------------------------
def test_predictor_finds_recurring_donors():
    from foodbridge.predictor import forecast

    fs = forecast(os.path.join(DATA, "history.json"))
    names = [f.donor_name for f in fs]
    assert "Sunrise Bakery" in names and "Main St Grocery" in names
    # A one-off donor should not become a confident forecast.
    assert "Corner Deli" not in names
    # Most confident first.
    assert fs[0].confidence >= fs[-1].confidence


def test_decision_tools_are_bound_and_callable():
    # The tools an LLM agent would call: bound to the live roster + a mutable time context.
    from foodbridge.tools import make_decision_tools

    ctx = {"now": 100}
    recs = [_recipient(id="R-1", name="Alpha", needs=["produce"], serves_children=True),
            _recipient(id="R-2", name="Beta", needs=["bakery"])]
    check_safety, rank, impact, consult = make_decision_tools(recs, ctx)
    assert consult("danger zone hours dairy")[0]["source"].startswith("USDA")

    assert check_safety("dairy", "refrigerated", 5.0)["verdict"] == "reject"
    assert check_safety("produce", "ambient", 0.2)["verdict"] == "safe"

    ranked = rank("produce", 24, "refrigerated")
    eligible = [r for r in ranked if not r["disqualified"]]
    assert eligible and eligible[0]["recipient_id"] == "R-1"   # only Alpha needs produce

    imp = impact(120, 100)
    assert imp["meals"] == 100 and imp["co2_lbs"] == 300


def test_agentic_choose_recipient_parses_and_falls_back():
    # Prove the tool-calling decision loop parses the agent's choice and degrades safely.
    from foodbridge.brain import StrandsBrain
    from foodbridge.matcher import rank_recipients as rank

    recs = [_recipient(id="R-1", name="Alpha", needs=["produce"], last_served_minute=-600),
            _recipient(id="R-2", name="Beta", needs=["produce"], last_served_minute=0)]
    d = _donation(category="produce", weight_lbs=24)
    opts = rank(d, recs, now=100)

    class _FakeStrands(StrandsBrain):
        def __init__(self, answer):
            self._recipients, self._ctx, self._trace = recs, {"now": 100}, None
            self._agent, self._provider = object(), "fake"
            self.mode, self.is_llm, self._answer = "fake", True, answer

        def _ask(self, prompt):
            return self._answer

    chosen, why = _FakeStrands("reasoning... DECISION: R-2 | best on fairness").choose_recipient(
        d, opts, opts[1] if len(opts) > 1 else None)
    assert chosen.recipient.id == "R-2" and "fairness" in why

    # Unparseable model output -> deterministic fallback to the top-ranked option.
    fb, _ = _FakeStrands("i am not sure").choose_recipient(d, opts, None)
    assert fb.recipient.id == opts[0].recipient.id


def test_rag_retrieves_relevant_guidelines():
    from foodbridge.knowledge import default_kb

    kb = default_kb()
    assert len(kb.passages) >= 6
    assert kb.retrieve("dairy unrefrigerated danger zone hours", k=1)[0].id == "usda-danger-zone"
    assert kb.retrieve("donor liability lawsuit protection", k=1)[0].id == "good-samaritan-act"
    assert kb.retrieve("best by date expired canned", k=1)[0].id == "date-labels"
    assert kb.retrieve("zzz unrelated quantum blockchain", k=1) == []  # no false hits


def test_escalation_is_grounded_with_citation():
    # A borderline-safety donation should escalate with a knowledge-base citation attached.
    from foodbridge.memory import Memory
    from foodbridge.models import load_drivers, load_recipients
    from foodbridge.orchestrator import FoodBridge

    seen = {}

    def escalate(kind, message):
        seen["kind"], seen["message"] = kind, message
        return True

    bridge = FoodBridge(load_recipients(os.path.join(DATA, "recipients.json")),
                        load_drivers(os.path.join(DATA, "drivers.json")),
                        Memory("/dev/null"), escalate=escalate, log=lambda *_: None)
    bridge.process(_donation(category="protein", hours_unrefrigerated=3.2,
                             storage_temp="refrigerated"), now=0)
    assert seen["kind"] == "SAFETY"
    assert "Grounding:" in seen["message"]           # a knowledge-base citation is attached


def test_ask_answers_rules_questions_with_citation():
    from foodbridge.brain import SimulatedBrain

    snap = {"meals": 0, "money": 0, "co2": 0, "rescued": 0, "escalated": 0,
            "rejected": 0, "recipients": []}
    ans = SimulatedBrain().answer("can we donate food past its best by date?", snap)
    assert "USDA" in ans or "date" in ans.lower()
    assert "—" in ans                                 # includes the citation


def test_notify_is_safe_noop_without_channel():
    import os

    from foodbridge import notify

    old = os.environ.pop("FOODBRIDGE_WEBHOOK_URL", None)
    try:
        r = notify.send("test")
        assert r["sent"] is False and r["channel"] is None
    finally:
        if old is not None:
            os.environ["FOODBRIDGE_WEBHOOK_URL"] = old


def test_add_builds_donation_with_defaults():
    from foodbridge.cli import build_donation

    d = build_donation({"item": "Surplus bread", "category": "bakery", "weight": "20"})
    assert d.category == "bakery" and d.weight_lbs == 20
    assert d.storage_temp == "ambient"           # bakery defaults to ambient
    assert d.value_usd == round(20 * 2.5, 2)     # value derived from weight


def test_add_runs_a_single_donation():
    from foodbridge.cli import build_donation, run_single

    d = build_donation({"item": "Fresh greens", "category": "produce", "weight": "24",
                        "hours": "0.3"})
    bridge = run_single(d, interactive=False, auto_yes=True)
    assert bridge.stats.events[-1]["outcome"] == "delivered"
    assert bridge.stats.impact.meals > 0


def test_end_to_end_run():
    from foodbridge.models import load_donations, load_drivers, load_recipients
    from foodbridge.orchestrator import FoodBridge

    donations = sorted(load_donations(os.path.join(DATA, "donations.json")),
                       key=lambda d: d.ready_minute)
    bridge = FoodBridge(load_recipients(os.path.join(DATA, "recipients.json")),
                        load_drivers(os.path.join(DATA, "drivers.json")),
                        Memory("/dev/null"), escalate=lambda *_: True,
                        log=lambda *_: None)
    for d in donations:
        bridge.process(d, now=d.ready_minute)
    s = bridge.stats
    assert s.processed == len(donations)
    assert s.rescued >= 1
    assert s.rejected >= 1          # the spoiled deli meat
    assert s.impact.meals > 0
    assert len(s.messages) > 0      # the agent talked to people


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
