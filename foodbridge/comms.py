"""Agent-authored communications.

FoodBridge doesn't just move data around — it talks to the people involved like a thoughtful
human coordinator would. These are the messages the agent sends to drivers, donors,
recipients, and the human coordinator.

In offline mode these high-quality templates are used directly. When a language model is
available (``StrandsBrain``), the agent rewrites them in its own words, personalised to the
situation — but the templates are always the safe fallback, so the product never sends a
blank or broken message.
"""

from __future__ import annotations

from typing import Optional

from .impact import Impact, LBS_PER_MEAL
from .models import Donation, Driver, Recipient


def _meals(weight_lbs: float) -> int:
    return int(round(weight_lbs / LBS_PER_MEAL))


def driver_request(driver: Driver, d: Donation, r: Recipient, minutes_left: int) -> str:
    fridge = " (refrigerated van needed)" if d.storage_temp in ("refrigerated", "frozen") else ""
    return (
        f"Hi {driver.name} — quick rescue run{fridge}: pick up {d.weight_lbs:.0f} lbs of "
        f"{d.item.lower()} from {d.donor_name} and drop at {r.name}. That's about "
        f"{_meals(d.weight_lbs)} meals, and the food is good for another {minutes_left} min. "
        f"Can you take it? Reply YES or NO."
    )


def recipient_incoming(r: Recipient, d: Donation, driver_name: str) -> str:
    return (
        f"Hi {r.name} — a delivery is on the way: {d.weight_lbs:.0f} lbs of {d.item.lower()} "
        f"(~{_meals(d.weight_lbs)} meals) with {driver_name}. Please have cold storage ready "
        f"if needed. Thank you for being there for your community."
    )


def donor_thanks(d: Donation, r: Recipient) -> str:
    return (
        f"Thank you, {d.donor_name}! Your {d.item.lower()} became ~{_meals(d.weight_lbs)} "
        f"meals at {r.name} today instead of going to waste. A tax-deduction receipt for "
        f"${d.value_usd:,.0f} is attached, and you're protected under the Good Samaritan Food "
        f"Donation Act. We'd love to make this a regular pickup — just say the word."
    )


def coordinator_escalation(kind: str, d: Donation, detail: str, recommendation: str) -> str:
    headline = {
        "SAFETY": "Food-safety judgment call",
        "RESCUE_FAILING": "A rescue is about to fail",
        "OVERSIZED": "Donation too big for one site",
        "NO_RECIPIENT": "No eligible recipient right now",
    }.get(kind, kind)
    return (
        f"[{headline}] {d.item} ({d.weight_lbs:.0f} lbs, ~{_meals(d.weight_lbs)} meals) from "
        f"{d.donor_name}. {detail}\n      My recommendation: {recommendation}\n      "
        f"Reply APPROVE or REJECT."
    )


def shift_summary(impact: Impact, rescued: int, escalated: int) -> str:
    return (
        f"Shift wrapped. I completed {rescued} rescues on my own and needed you for "
        f"{escalated} decision(s). Together that's {impact.meals} meals delivered, "
        f"${impact.money_usd:,.0f} saved, and {impact.co2_lbs:,.0f} lbs of CO2 kept out of "
        f"the air. See you tomorrow — I'll keep watch."
    )
