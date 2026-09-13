"""Dispatcher agent — assigns a driver, races the spoilage clock, and self-heals.

Tries drivers best-first (by learned reliability, refrigeration fit, and proximity). If a
driver declines, it immediately tries the next — this is the autonomous self-healing loop.
It returns either a completed assignment or a signal that the rescue is about to FAIL, which
the orchestrator escalates to a human.

Driver responses are simulated deterministically from a seeded RNG so demo runs are
reproducible.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional

from .memory import Memory
from .models import Donation, Driver, Recipient, distance


@dataclass
class DispatchResult:
    status: str  # assigned | failed
    driver: Optional[Driver] = None
    attempts: Optional[List[str]] = None
    reason: str = ""


def _rank_drivers(d: Donation, drivers: List[Driver], mem: Memory) -> List[Driver]:
    def key(dr: Driver):
        needs_fridge = d.storage_temp in ("refrigerated", "frozen")
        fridge_ok = (not needs_fridge) or dr.refrigerated_transport
        rel = mem.learned_reliability(dr.id, dr.reliability)
        dist = distance(dr.location, (5.0, 4.0))
        # Sort: fridge-capable first, then reliability, then proximity.
        return (0 if fridge_ok else 1, -rel, dist)

    return sorted([dr for dr in drivers if dr.available], key=key)


def dispatch(
    d: Donation,
    recipient: Recipient,
    drivers: List[Driver],
    mem: Memory,
    rng: random.Random,
    log,
) -> DispatchResult:
    needs_fridge = d.storage_temp in ("refrigerated", "frozen")
    ranked = _rank_drivers(d, drivers, mem)
    attempts: List[str] = []

    for dr in ranked:
        if needs_fridge and not dr.refrigerated_transport:
            log(f"      skip {dr.name}: no refrigerated transport for perishable load")
            continue
        rel = mem.learned_reliability(dr.id, dr.reliability)
        attempts.append(dr.name)
        log(f"      asking {dr.name} (learned reliability {rel:.0%})...")
        accepted = rng.random() <= rel
        if accepted:
            log(f"      -> {dr.name} ACCEPTED")
            mem.record_completion(dr.id)
            dr.available = False  # now out on delivery for the rest of the shift
            return DispatchResult("assigned", driver=dr, attempts=attempts)
        log(f"      -> {dr.name} declined; self-healing to next driver")
        mem.record_decline(dr.id)

    return DispatchResult(
        "failed",
        attempts=attempts,
        reason="every eligible driver declined before the pickup deadline",
    )
