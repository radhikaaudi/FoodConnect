#!/usr/bin/env python3
"""FoodBridge end-to-end demo.

Runs one autonomous rescue cycle over the seeded mock data in ``data/`` and prints:
  * the agent's step-by-step reasoning for every donation,
  * the exact moments it surfaces a decision to a human,
  * the messages the agent writes to drivers, donors, and recipients,
  * proof-of-delivery + donor receipts,
  * a live impact scoreboard and a self-written impact report.

Runs with zero external services. When a language model is available (Amazon Bedrock, or a
free local Ollama model), the agent's judgment and messages are genuinely LLM-driven; without
one, a faithful deterministic brain runs the identical workflow so evaluation costs nothing.

Usage:
    python3 run_demo.py
    FOODBRIDGE_MODEL_PROVIDER=ollama python3 run_demo.py   # free local LLM
"""

from __future__ import annotations

import os

from foodbridge.brain import build_brain
from foodbridge.dashboard import write_dashboard
from foodbridge.memory import Memory
from foodbridge.models import load_donations, load_drivers, load_recipients
from foodbridge.observability import Trace
from foodbridge.orchestrator import FoodBridge
from foodbridge.predictor import forecast_summary

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
MEM_PATH = os.path.join(HERE, "data", "memory.json")
TRACE_PATH = os.path.join(HERE, "data", "trace.jsonl")
HISTORY_PATH = os.path.join(HERE, "data", "history.json")
DASHBOARD_PATH = os.path.join(HERE, "dashboard.html")


def make_escalator():
    """Simulated coordinator. Auto-approves safety/emergency calls so the demo completes.

    In production this is an SMS/Slack message with Approve / Reject buttons.
    """

    def escalate(kind: str, message: str) -> bool:
        print(f"\n    *** HUMAN DECISION NEEDED [{kind}] ***\n    >> {message}\n"
              "    << Coordinator: APPROVE\n")
        return True

    return escalate


def main() -> None:
    donations = sorted(load_donations(os.path.join(DATA, "donations.json")),
                       key=lambda d: d.ready_minute)
    recipients = load_recipients(os.path.join(DATA, "recipients.json"))
    drivers = load_drivers(os.path.join(DATA, "drivers.json"))
    memory = Memory.load(MEM_PATH)
    trace = Trace(TRACE_PATH, clock=_step_clock())
    brain = build_brain(prefer_llm=True, recipients=recipients, trace=trace)

    print("=" * 68)
    print("  FoodBridge — autonomous food-rescue agent")
    print(f"  Brain: {brain.mode}")
    print(f"  Loaded: {len(donations)} donations, {len(recipients)} recipients, "
          f"{len(drivers)} drivers")
    print("=" * 68)

    # Proactive: forecast the day's likely surplus before anything arrives.
    print("\nSHIFT FORECAST (proactive, learned from history)")
    print("  " + forecast_summary(HISTORY_PATH).replace("\n", "\n  "))

    bridge = FoodBridge(recipients, drivers, memory, make_escalator(),
                        brain=brain, trace=trace)

    for d in donations:
        bridge.process(d, now=d.ready_minute)

    print("\n" + bridge.report())

    # The agent's own end-of-shift note to the coordinator.
    print("\n  Agent to coordinator:")
    print("    " + brain.compose("shift_summary", impact=bridge.stats.impact,
                                  rescued=bridge.stats.rescued,
                                  escalated=bridge.stats.escalated))

    print("\n  Sample message the agent sent (it talks to people, not just databases):")
    if bridge.stats.messages:
        m = bridge.stats.messages[0]
        print(f"    [{m['to']}] {m['text']}")

    print(f"\n  Decision trace -> {TRACE_PATH} ({len(trace.records)} steps logged)")
    memory.save()
    print(f"  Memory updated -> {MEM_PATH} (agent learns driver reliability across runs)")

    write_dashboard(DASHBOARD_PATH, bridge.stats.events, bridge.stats.impact, bridge.stats,
                    brain_mode=brain.mode)
    print(f"  UI dashboard   -> {DASHBOARD_PATH} (open in a browser)")


def _step_clock():
    """Monotonic integer 'time' so the trace is reproducible across runs."""
    counter = {"n": 0}

    def clock() -> float:
        counter["n"] += 1
        return float(counter["n"])

    return clock


if __name__ == "__main__":
    main()
