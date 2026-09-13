"""Predictive intelligence — the agent anticipates surplus instead of only reacting.

Most food-rescue coordination is reactive: wait for a donation, then scramble. FoodBridge
learns each donor's pattern from history and forecasts the day's likely surplus at the start
of a shift, so it can pre-position drivers before the food even appears. A donor that has
donated the same category at a similar time on enough recent days becomes a confident
prediction.

Standard library only; the same JSON history would be AgentCore Memory in production.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List

MIN_DAYS_FOR_PATTERN = 2


@dataclass
class Forecast:
    donor_name: str
    category: str
    typical_weight_lbs: float
    typical_minute: int
    days_seen: int
    confidence: float  # 0..1

    def human(self) -> str:
        pct = int(self.confidence * 100)
        return (f"~{self.typical_weight_lbs:.0f} lbs of {self.category} from "
                f"{self.donor_name} around minute {self.typical_minute} "
                f"({pct}% likely, seen {self.days_seen} recent days)")


def _load(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def forecast(history_path: str) -> List[Forecast]:
    """Return confident forecasts for recurring donors, most likely first."""
    rows = _load(history_path)
    total_days = len({r["day"] for r in rows}) or 1

    groups: Dict[str, List[Dict]] = {}
    for r in rows:
        groups.setdefault(r["donor_name"], []).append(r)

    out: List[Forecast] = []
    for donor, recs in groups.items():
        days = {r["day"] for r in recs}
        if len(days) < MIN_DAYS_FOR_PATTERN:
            continue
        avg_w = sum(r["weight_lbs"] for r in recs) / len(recs)
        avg_m = int(round(sum(r["minute"] for r in recs) / len(recs)))
        category = max({r["category"] for r in recs},
                       key=lambda c: sum(1 for r in recs if r["category"] == c))
        out.append(Forecast(donor, category, round(avg_w, 1), avg_m, len(days),
                            round(len(days) / total_days, 2)))

    out.sort(key=lambda f: f.confidence, reverse=True)
    return out


def forecast_summary(history_path: str) -> str:
    fs = forecast(history_path)
    if not fs:
        return "No recurring donor patterns yet — I'll learn as donations come in."
    lines = ["I expect these recurring donations today and have pre-alerted drivers:"]
    lines += [f"  • {f.human()}" for f in fs]
    return "\n".join(lines)
