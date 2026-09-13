"""Matcher agent — chooses the best recipient for a donation, and explains why.

Scoring balances several real constraints so the choice is a reasoning step, not a
nearest-neighbour lookup:

* need match       -> recipient actually wants this food category
* nutrition        -> fresh produce / protein prioritised to sites serving children
* fairness         -> recipients not served recently are favoured (spread the food)
* capacity         -> must physically fit (refrigeration for perishables)
* distance         -> closer is better, but never at the expense of the above
* dietary safety   -> hard filter on allergen / restriction conflicts

Returns the ranked, *eligible* recipients plus a human-readable explanation of the pick.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .models import Donation, Recipient, distance


@dataclass
class MatchOption:
    recipient: Recipient
    score: float
    reasons: List[str]
    disqualified: Optional[str] = None


def _eligible(d: Donation, r: Recipient, now: int) -> Optional[str]:
    """Return a disqualification reason, or None if eligible."""
    if d.category not in r.needs:
        return f"{r.name} does not need '{d.category}'"
    if d.weight_lbs > r.storage_capacity_lbs:
        return f"{r.name} lacks capacity ({d.weight_lbs:.0f} > {r.storage_capacity_lbs:.0f} lbs)"
    if d.storage_temp in ("refrigerated", "frozen") and not r.refrigeration:
        return f"{r.name} has no refrigeration for perishable food"
    conflict = set(a.lower() for a in d.allergens) & set(x.lower() for x in r.dietary_restrictions)
    if conflict:
        return f"{r.name} has a dietary conflict ({', '.join(sorted(conflict))})"
    if not (r.open_from_minute <= now <= r.open_to_minute):
        return f"{r.name} is closed right now"
    return None


def _score(d: Donation, r: Recipient, now: int) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    score = 0.0

    # Need match (baseline).
    score += 30
    reasons.append(f"needs {d.category}")

    # Nutrition: fresh produce / protein to sites serving children.
    if r.serves_children and d.category in ("produce", "protein"):
        score += 25
        reasons.append("serves children who need fresh food (nutrition priority)")

    # Fairness: reward recipients not served recently.
    idle = now - r.last_served_minute
    fairness = min(idle / 10.0, 25.0)  # cap the fairness bonus
    score += fairness
    if idle >= 120:
        reasons.append(f"not served in {idle} min (fairness)")

    # Distance: closer is better (small weight so it never overrides need/fairness).
    dist = distance(d_location(d), r.location)
    score -= dist * 2.0

    return score, reasons


def d_location(_d: Donation) -> Tuple[float, float]:
    # Donations don't carry a coordinate in the demo data; assume a central depot.
    return (5.0, 4.0)


def rank_recipients(d: Donation, recipients: List[Recipient], now: int) -> List[MatchOption]:
    options: List[MatchOption] = []
    for r in recipients:
        dq = _eligible(d, r, now)
        if dq:
            options.append(MatchOption(r, float("-inf"), [], disqualified=dq))
            continue
        score, reasons = _score(d, r, now)
        options.append(MatchOption(r, score, reasons))
    options.sort(key=lambda o: o.score, reverse=True)
    return options


def explain_pick(d: Donation, chosen: MatchOption, runner_up: Optional[MatchOption]) -> str:
    why = f"Matched {d.item} -> {chosen.recipient.name}: " + ", ".join(chosen.reasons)
    if runner_up and runner_up.score != float("-inf"):
        why += (
            f". Chose over {runner_up.recipient.name} "
            f"(score {chosen.score:.0f} vs {runner_up.score:.0f})."
        )
    return why
