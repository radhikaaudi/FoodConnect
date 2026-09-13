"""Reporting — the agent's self-written, numbers-backed impact report."""

from __future__ import annotations

from typing import List

from .impact import Impact


def write_report(
    processed: int,
    rescued: int,
    escalated: int,
    rejected: int,
    recipients_served: List[str],
    impact: Impact,
) -> str:
    served = ", ".join(sorted(set(recipients_served))) or "none"
    lines = [
        "==================  FoodBridge Impact Report  ==================",
        f"  Donations processed : {processed}",
        f"  Rescues delivered   : {rescued}",
        f"  Decisions escalated : {escalated}",
        f"  Rejected for safety : {rejected}",
        f"  Recipients served   : {served}",
        "  --------------------------------------------------------------",
        f"  Food rescued        : {impact.lbs:,.0f} lbs",
        f"  MEALS delivered     : {impact.meals:,}",
        f"  MONEY saved         : ${impact.money_usd:,.0f}",
        f"  CO2 prevented       : {impact.co2_lbs:,.0f} lbs",
        "================================================================",
    ]
    return "\n".join(lines)
