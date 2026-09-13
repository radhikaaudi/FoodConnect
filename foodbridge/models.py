"""Data models for FoodBridge.

Plain dataclasses loaded from the JSON files in ``data/``. Kept dependency-free so the
whole simulation runs on a stock Python install with no external services.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Donation:
    id: str
    donor_name: str
    donor_type: str
    item: str
    category: str  # produce | protein | dairy | bakery | prepared
    weight_lbs: float
    value_usd: float
    ready_minute: int
    pickup_deadline_minute: int
    storage_temp: str  # refrigerated | ambient | frozen
    hours_unrefrigerated: float
    allergens: List[str] = field(default_factory=list)


@dataclass
class Recipient:
    id: str
    name: str
    type: str
    location: Tuple[float, float]
    needs: List[str]
    storage_capacity_lbs: float
    refrigeration: bool
    open_from_minute: int
    open_to_minute: int
    serves_children: bool
    dietary_restrictions: List[str]
    last_served_minute: int


@dataclass
class Driver:
    id: str
    name: str
    location: Tuple[float, float]
    available: bool
    reliability: float
    refrigerated_transport: bool


def distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Euclidean distance on the demo grid (1 grid unit ~= a few minutes of driving)."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _load(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_donations(path: str) -> List[Donation]:
    return [Donation(**d) for d in _load(path)]


def load_recipients(path: str) -> List[Recipient]:
    out = []
    for r in _load(path):
        r = dict(r)
        r["location"] = tuple(r["location"])
        out.append(Recipient(**r))
    return out


def load_drivers(path: str) -> List[Driver]:
    out = []
    for d in _load(path):
        d = dict(d)
        d["location"] = tuple(d["location"])
        out.append(Driver(**d))
    return out
