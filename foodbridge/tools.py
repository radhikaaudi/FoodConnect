"""The FoodBridge tool surface — the capabilities the agent can call.

These are exposed to a Strands ``Agent`` as ``@tool`` functions, so a language model can
decide *when* to check safety, *which* recipients to rank, and *how* to act — genuine
tool-calling, not a hard-coded script. The same functions are used directly by the offline
``SimulatedBrain``, so behaviour is identical across both paths.

Each tool is deterministic and side-effect-light: safety rules, ranking math, and impact
accounting are things that must be *guaranteed*, so they live in code. The language model
supplies judgment, prioritisation, and communication around them. That separation — hard
guarantees in tools, judgment in the model — is the core of the design.
"""

from __future__ import annotations

from typing import Dict, List

from . import matcher as _matcher
from . import safety as _safety
from .impact import CO2_LBS_PER_LB_FOOD, LBS_PER_MEAL
from .models import Donation, Recipient
from .strands_agent import tool


@tool
def check_food_safety(donation: Dict) -> Dict:
    """Assess whether a food donation is safe to rescue.

    Returns a verdict of 'safe' (rescue automatically), 'escalate' (borderline — a human
    must decide), or 'reject' (unsafe — decline). Uses the 4-hour perishable danger-zone
    rule.
    """
    v = _safety.assess(Donation(**donation))
    return {"verdict": v.verdict, "reason": v.reason}


@tool
def rank_recipients(donation: Dict, recipients: List[Dict], now_minute: int) -> List[Dict]:
    """Rank eligible recipients for a donation.

    Scores by need match, nutrition priority (fresh food to sites serving children),
    fairness (spread food to sites not served recently), capacity, refrigeration, dietary
    safety, and distance. Ineligible recipients are returned with a 'disqualified' reason.
    """
    d = Donation(**donation)
    rs = [Recipient(**{**r, "location": tuple(r["location"])}) for r in recipients]
    options = _matcher.rank_recipients(d, rs, now_minute)
    return [
        {
            "recipient_id": o.recipient.id,
            "recipient_name": o.recipient.name,
            "score": None if o.disqualified else round(o.score, 1),
            "reasons": o.reasons,
            "disqualified": o.disqualified,
        }
        for o in options
    ]


@tool
def estimate_impact(weight_lbs: float, value_usd: float) -> Dict:
    """Estimate the impact of rescuing a donation: meals, dollars saved, and CO2 prevented."""
    return {
        "meals": int(round(weight_lbs / LBS_PER_MEAL)),
        "money_usd": round(value_usd, 2),
        "co2_lbs": round(weight_lbs * CO2_LBS_PER_LB_FOOD, 1),
    }


def make_decision_tools(recipients: List[Recipient], ctx: Dict, trace=None) -> List:
    """Build the tools a language-model agent uses to *investigate a donation on its own*.

    Unlike the stateless tools above (which take everything as arguments), these are bound to
    the live recipient roster and a mutable time context, and take simple primitive arguments
    a model fills easily. When the agent calls one, it is recorded on ``trace`` so its
    investigation is fully auditable. This is what makes FoodBridge a genuine tool-calling
    agent rather than a script: the model decides which tool to call, and when.

    ``ctx`` is a mutable dict carrying ``ctx['now']`` (the current minute, updated per
    donation), so the same bound tools stay correct across a whole shift.
    """
    rs = list(recipients)

    @tool
    def check_food_safety(category: str, storage_temp: str, hours_unrefrigerated: float) -> Dict:
        """Judge whether a food donation is safe to rescue.

        category: produce | protein | dairy | bakery | prepared.
        storage_temp: refrigerated | ambient | frozen.
        hours_unrefrigerated: how long it has been out of the cold chain.
        Returns verdict 'safe' (rescue now), 'escalate' (ask a human), or 'reject' (unsafe).
        """
        d = Donation(id="_probe", donor_name="", donor_type="", item="", category=category,
                     weight_lbs=1.0, value_usd=0.0, ready_minute=ctx["now"],
                     pickup_deadline_minute=ctx["now"], storage_temp=storage_temp,
                     hours_unrefrigerated=float(hours_unrefrigerated), allergens=[])
        v = _safety.assess(d)
        if trace:
            trace.emit("tool_call", tool="check_food_safety", verdict=v.verdict)
        return {"verdict": v.verdict, "reason": v.reason}

    @tool
    def rank_recipients(category: str, weight_lbs: float, storage_temp: str = "ambient",
                        allergens: str = "") -> List[Dict]:
        """Rank the shelters/food banks that can take this donation, best first.

        Each result carries the reason it ranked where it did, or why it was disqualified
        (capacity, refrigeration, dietary conflict, hours). allergens: comma-separated, e.g.
        'nuts,dairy'. Scoring weighs need, nutrition (fresh food to sites serving children),
        fairness (sites not served recently), and distance.
        """
        d = Donation(id="_probe", donor_name="", donor_type="", item="", category=category,
                     weight_lbs=float(weight_lbs), value_usd=0.0, ready_minute=ctx["now"],
                     pickup_deadline_minute=ctx["now"] + 120, storage_temp=storage_temp,
                     hours_unrefrigerated=0.0,
                     allergens=[a.strip() for a in allergens.split(",") if a.strip()])
        options = _matcher.rank_recipients(d, rs, ctx["now"])
        if trace:
            trace.emit("tool_call", tool="rank_recipients",
                       eligible=len([o for o in options if not o.disqualified]))
        return [
            {
                "recipient_id": o.recipient.id,
                "name": o.recipient.name,
                "score": None if o.disqualified else round(o.score, 1),
                "reasons": o.reasons,
                "disqualified": o.disqualified,
            }
            for o in options
        ]

    @tool
    def estimate_impact(weight_lbs: float, value_usd: float) -> Dict:
        """Estimate meals delivered, dollars saved, and lbs of CO2 prevented for a rescue."""
        if trace:
            trace.emit("tool_call", tool="estimate_impact")
        return {
            "meals": int(round(float(weight_lbs) / LBS_PER_MEAL)),
            "money_usd": round(float(value_usd), 2),
            "co2_lbs": round(float(weight_lbs) * CO2_LBS_PER_LB_FOOD, 1),
        }

    @tool
    def consult_guidelines(question: str) -> List[Dict]:
        """Look up food-safety and food-donation rules in the curated knowledge base (RAG).

        Use for judgment calls: temperature/danger-zone limits, donor liability (Good
        Samaritan Act), allergen rules, date labels ('best by' vs 'use by'), cold-chain
        transport, donating prepared/catered food, and tax deductions. Returns the most
        relevant guideline passages with their sources — cite them in your reasoning.
        """
        from .knowledge import default_kb

        hits = default_kb().retrieve(question, k=2)
        if trace:
            trace.emit("rag_retrieval", tool="consult_guidelines",
                       sources=[p.id for p in hits])
        return [{"title": p.title, "source": p.source, "text": p.text} for p in hits]

    return [check_food_safety, rank_recipients, estimate_impact, consult_guidelines]


# Tools that carry live state (drivers, memory) are bound at runtime by the brain, so they
# are provided as factory functions rather than bare module-level tools.
def make_dispatch_tool(drivers, memory, rng, log):
    from . import dispatcher as _dispatcher
    from .models import Driver, Recipient

    @tool
    def find_driver(donation: Dict, recipient: Dict) -> Dict:
        """Find and assign the best available driver for a pickup, self-healing past declines.

        Returns {'status': 'assigned', 'driver': name} or {'status': 'failed', 'reason': ...}
        when no driver will take it before the deadline (a human must then approve an
        emergency pickup).
        """
        d = Donation(**donation)
        r = Recipient(**{**recipient, "location": tuple(recipient["location"])})
        res = _dispatcher.dispatch(d, r, drivers, memory, rng, log)
        if res.status == "assigned":
            return {"status": "assigned", "driver": res.driver.name, "attempts": res.attempts}
        return {"status": "failed", "reason": res.reason, "attempts": res.attempts}

    return find_driver


ALL_STATELESS_TOOLS = [check_food_safety, rank_recipients, estimate_impact]
