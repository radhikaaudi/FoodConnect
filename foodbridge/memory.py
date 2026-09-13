"""Memory — the agent's learning across runs.

In a full AgentCore deployment this is backed by AgentCore Memory. For the self-contained
demo it is a small JSON-backed store that records driver reliability and recipient service
history so the agent gets smarter every run (routes around no-show drivers, spreads food
fairly). Kept intentionally simple and inspectable.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Memory:
    path: str
    driver_completions: Dict[str, int] = field(default_factory=dict)
    driver_declines: Dict[str, int] = field(default_factory=dict)
    recipient_last_served: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> "Memory":
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            return cls(
                path=path,
                driver_completions=raw.get("driver_completions", {}),
                driver_declines=raw.get("driver_declines", {}),
                recipient_last_served=raw.get("recipient_last_served", {}),
            )
        return cls(path=path)

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "driver_completions": self.driver_completions,
                    "driver_declines": self.driver_declines,
                    "recipient_last_served": self.recipient_last_served,
                },
                fh,
                indent=2,
            )

    def record_completion(self, driver_id: str) -> None:
        self.driver_completions[driver_id] = self.driver_completions.get(driver_id, 0) + 1

    def record_decline(self, driver_id: str) -> None:
        self.driver_declines[driver_id] = self.driver_declines.get(driver_id, 0) + 1

    def learned_reliability(self, driver_id: str, base: float) -> float:
        """Blend the seed reliability with what we've actually observed."""
        done = self.driver_completions.get(driver_id, 0)
        declined = self.driver_declines.get(driver_id, 0)
        if done + declined == 0:
            return base
        observed = done / (done + declined)
        # Weight observed history more as we gather evidence.
        n = done + declined
        w = min(n / 5.0, 1.0)
        return round(base * (1 - w) + observed * w, 3)
