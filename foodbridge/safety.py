"""Safety agent — reasons about whether a donation is safe to rescue.

This is a *judgment* step, not a lookup. It returns one of three verdicts:

* ``safe``      -> proceed automatically
* ``escalate``  -> borderline; a human must approve or reject (the "real decision")
* ``reject``    -> clearly unsafe; decline and notify the donor

The 4-hour rule for perishable food out of refrigeration is a standard food-safety
guideline (the "danger zone").
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Donation

PERISHABLE = {"protein", "dairy", "prepared"}
DANGER_ZONE_HOURS = 4.0
ESCALATE_MARGIN_HOURS = 1.0  # within this margin of the limit -> ask a human


@dataclass
class SafetyVerdict:
    donation_id: str
    verdict: str  # safe | escalate | reject
    reason: str


def assess(d: Donation) -> SafetyVerdict:
    perishable = d.category in PERISHABLE or d.storage_temp in ("refrigerated", "frozen")

    if perishable and d.hours_unrefrigerated >= DANGER_ZONE_HOURS:
        return SafetyVerdict(
            d.id,
            "reject",
            f"{d.category} left unrefrigerated {d.hours_unrefrigerated:.1f}h "
            f"(>= {DANGER_ZONE_HOURS:.0f}h danger-zone limit) — not safe to serve.",
        )

    if perishable and d.hours_unrefrigerated >= (DANGER_ZONE_HOURS - ESCALATE_MARGIN_HOURS):
        return SafetyVerdict(
            d.id,
            "escalate",
            f"{d.category} unrefrigerated {d.hours_unrefrigerated:.1f}h — borderline "
            f"(limit {DANGER_ZONE_HOURS:.0f}h). Needs a human safety call.",
        )

    return SafetyVerdict(
        d.id,
        "safe",
        f"Within safe limits (unrefrigerated {d.hours_unrefrigerated:.1f}h, "
        f"category '{d.category}').",
    )
