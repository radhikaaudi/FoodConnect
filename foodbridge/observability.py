"""Observability — a structured, replayable trace of every decision the agent makes.

Each step the agent takes is written as one JSON line to ``data/trace.jsonl``. This is the
same idea as Strands' built-in telemetry / OpenTelemetry traces: a judge (or an on-call
operator) can read exactly what the agent did, in order, and why. It also powers the
"explainable decisions" requirement — nothing the agent does is a black box.

Kept dependency-free (standard library only) so it works in the offline demo and on
AgentCore alike.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional


class Trace:
    def __init__(self, path: Optional[str] = None, clock=None) -> None:
        self.path = path
        self.records: List[Dict[str, Any]] = []
        # Injectable clock keeps demo output reproducible; defaults to wall time.
        self._clock = clock or time.time
        if path and os.path.exists(path):
            os.remove(path)

    def emit(self, step: str, donation_id: Optional[str] = None, **fields: Any) -> None:
        rec: Dict[str, Any] = {"t": round(self._clock(), 3), "step": step}
        if donation_id:
            rec["donation_id"] = donation_id
        rec.update(fields)
        self.records.append(rec)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")

    def steps_for(self, donation_id: str) -> List[Dict[str, Any]]:
        return [r for r in self.records if r.get("donation_id") == donation_id]

    def summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for r in self.records:
            counts[r["step"]] = counts.get(r["step"], 0) + 1
        return counts
