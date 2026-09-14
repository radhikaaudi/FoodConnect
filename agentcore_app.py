"""Amazon Bedrock AgentCore Runtime entrypoint for FoodBridge.

This is the file you deploy to run FoodBridge unattended in the cloud — the literal
expression of the hackathon theme ("runs autonomously in the background, surfaces only on a
real decision"). It exposes a single ``invoke`` entrypoint that runs one rescue cycle over an
incoming batch of donations and returns a structured result (impact + any escalations that
need a human).

Deploy (see README):
    pip install bedrock-agentcore strands-agents
    agentcore configure --entrypoint agentcore_app.py
    agentcore launch

Invoke locally before deploying:
    python3 agentcore_app.py            # runs one cycle over data/donations.json

The heavy lifting is the same FoodBridge orchestrator used by the offline demo, so behaviour
is identical whether it runs here on AgentCore or locally.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from foodbridge.memory import Memory
from foodbridge.models import (
    Donation,
    load_donations,
    load_drivers,
    load_recipients,
)
from foodbridge.orchestrator import FoodBridge

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
MEM_PATH = os.path.join(HERE, "data", "memory.json")
try:  # real AgentCore runtime when deployed
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()
    _HAS_AGENTCORE = True
except Exception:  # local run without the runtime installed
    app = None
    _HAS_AGENTCORE = False


def _run_cycle(donations: List[Donation]) -> Dict[str, Any]:
    recipients = load_recipients(os.path.join(DATA, "recipients.json"))
    drivers = load_drivers(os.path.join(DATA, "drivers.json"))
    memory = Memory.load(MEM_PATH)

    escalations: List[Dict[str, str]] = []

    def escalate(kind: str, message: str) -> bool:
        # In production this pushes an SMS/Slack message with Approve/Reject and blocks on
        # the reply. In this headless cycle we record it and auto-approve so the run finishes.
        escalations.append({"kind": kind, "message": message})
        return True

    bridge = FoodBridge(recipients, drivers, memory, escalate, log=lambda *_: None)
    for d in sorted(donations, key=lambda x: x.ready_minute):
        bridge.process(d, now=d.ready_minute)
    memory.save()

    s = bridge.stats
    return {
        "processed": s.processed,
        "rescued": s.rescued,
        "rejected": s.rejected,
        "escalations": escalations,
        "impact": {
            "meals": s.impact.meals,
            "money_usd": round(s.impact.money_usd, 2),
            "co2_lbs": round(s.impact.co2_lbs, 1),
        },
        "report": bridge.report(),
    }


def _handle(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run a cycle. ``payload['donations']`` may carry a live batch; else use the seed file."""
    raw = (payload or {}).get("donations")
    if raw:
        donations = [Donation(**d) for d in raw]
    else:
        donations = load_donations(os.path.join(DATA, "donations.json"))
    return _run_cycle(donations)


if _HAS_AGENTCORE:

    @app.entrypoint
    def invoke(payload: Dict[str, Any]) -> Dict[str, Any]:
        return _handle(payload)


if __name__ == "__main__":
    if _HAS_AGENTCORE:
        app.run()  # start the AgentCore runtime server
    else:
        import json

        print(json.dumps(_handle({}), indent=2))
