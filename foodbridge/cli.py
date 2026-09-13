"""FoodBridge command-line interface.

    python3 -m foodbridge.cli demo            # full narrated rescue cycle + dashboard
    python3 -m foodbridge.cli add             # YOU add a donation; watch the agent handle it
    python3 -m foodbridge.cli serve [port]    # serve the dashboard at a local URL
    python3 -m foodbridge.cli ask "..."       # ask the agent about today's rescues
    python3 -m foodbridge.cli forecast        # proactive forecast of today's surplus
    python3 -m foodbridge.cli check           # show model/deploy readiness
    python3 -m foodbridge.cli test            # run the test suite

`add` flags (all optional; you're prompted for anything missing):
    --item "…" --category produce|protein|dairy|bakery|prepared --weight 30
    --value 60 --hours 0.5 --deadline 120 --temp refrigerated|ambient --donor "…" --yes
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")

CATEGORIES = ["produce", "protein", "dairy", "bakery", "prepared"]


def _quiet_run():
    """Run one rescue cycle silently and return (bridge, brain)."""
    from .brain import build_brain
    from .memory import Memory
    from .models import load_donations, load_drivers, load_recipients
    from .orchestrator import FoodBridge

    donations = sorted(load_donations(os.path.join(DATA, "donations.json")),
                       key=lambda d: d.ready_minute)
    recipients = load_recipients(os.path.join(DATA, "recipients.json"))
    brain = build_brain(prefer_llm=True, recipients=recipients)
    bridge = FoodBridge(recipients,
                        load_drivers(os.path.join(DATA, "drivers.json")),
                        Memory(os.path.join(DATA, "memory.json")),
                        escalate=lambda *_: True, brain=brain, log=lambda *_: None)
    for d in donations:
        bridge.process(d, now=d.ready_minute)
    return bridge, brain


def _snapshot(bridge) -> dict:
    s = bridge.stats
    return {
        "meals": s.impact.meals,
        "money": s.impact.money_usd,
        "co2": s.impact.co2_lbs,
        "rescued": s.rescued,
        "escalated": s.escalated,
        "rejected": s.rejected,
        "recipients": sorted(set(s.recipients_served)),
    }


def cmd_demo(_args):
    from run_demo import main as demo_main

    sys.path.insert(0, HERE)
    demo_main()


def cmd_serve(args):
    from .serve import main as serve_main

    serve_main(int(args[0]) if args else 8000)


def cmd_ask(args):
    if not args:
        print('Usage: ... ask "how many meals today?"')
        return
    question = " ".join(args)
    bridge, brain = _quiet_run()
    print(f"You:   {question}")
    print(f"Agent: {brain.answer(question, _snapshot(bridge))}")


def _parse_flags(args):
    opts, i = {}, 0
    while i < len(args):
        a = args[i]
        if a == "--yes":
            opts["yes"] = True
            i += 1
        elif a.startswith("--") and i + 1 < len(args):
            opts[a[2:]] = args[i + 1]
            i += 2
        else:
            i += 1
    return opts


def build_donation(opts: dict):
    """Build a Donation from flag options, applying sensible defaults. Testable."""
    from .models import Donation

    cat = (opts.get("category") or "produce").lower()
    if cat not in CATEGORIES:
        cat = "produce"
    temp = (opts.get("temp") or ("refrigerated" if cat in ("protein", "dairy", "prepared")
                                 else "ambient")).lower()
    weight = float(opts.get("weight", 30))
    return Donation(
        id=opts.get("id", "D-NEW"),
        donor_name=opts.get("donor", "Your Donation"),
        donor_type=opts.get("donor_type", "business"),
        item=opts.get("item", f"Surplus {cat}"),
        category=cat,
        weight_lbs=weight,
        value_usd=float(opts.get("value", round(weight * 2.5, 2))),
        ready_minute=0,
        pickup_deadline_minute=int(opts.get("deadline", 120)),
        storage_temp=temp,
        hours_unrefrigerated=float(opts.get("hours", 0.5)),
        allergens=[a.strip() for a in opts.get("allergens", "").split(",") if a.strip()],
    )


def _prompt_donation():
    print("\nAdd a food donation — the agent will handle it live. Press Enter for defaults.\n")

    def ask(label, default):
        v = input(f"  {label} [{default}]: ").strip()
        return v or str(default)

    opts = {
        "item": ask("Item description", "Surplus sandwiches"),
        "category": ask(f"Category {CATEGORIES}", "prepared"),
        "weight": ask("Weight (lbs)", "30"),
        "value": ask("Fair value ($)", "75"),
        "hours": ask("Hours unrefrigerated", "0.5"),
        "deadline": ask("Minutes until it must be picked up", "120"),
        "donor": ask("Donor name", "Your Cafe"),
    }
    return opts


def run_single(donation, interactive: bool, auto_yes: bool = False):
    """Run one donation through the agent. Returns the bridge. Testable."""
    from .brain import build_brain
    from .memory import Memory
    from .models import load_drivers, load_recipients
    from .orchestrator import FoodBridge

    def escalate(kind, message):
        if auto_yes or not interactive:
            return True
        print(f"\n  *** THE AGENT NEEDS YOUR DECISION [{kind}] ***")
        return input("  Approve? [y/N]: ").strip().lower() in ("y", "yes", "approve", "a")

    recipients = load_recipients(os.path.join(DATA, "recipients.json"))
    bridge = FoodBridge(recipients,
                        load_drivers(os.path.join(DATA, "drivers.json")),
                        Memory(os.path.join(DATA, "memory.json")),
                        escalate=escalate, brain=build_brain(prefer_llm=True, recipients=recipients),
                        log=(print if interactive else (lambda *_: None)))
    bridge.process(donation, now=0)
    return bridge


def cmd_add(args):
    opts = _parse_flags(args)
    interactive = not opts.get("yes") and not opts.get("item")
    if interactive:
        opts.update(_prompt_donation())
    donation = build_donation(opts)
    print(f"\nHanding the agent: {donation.item} "
          f"({donation.weight_lbs:.0f} lbs {donation.category}) from {donation.donor_name}\n")
    bridge = run_single(donation, interactive=True, auto_yes=bool(opts.get("yes")))
    ev = bridge.stats.events[-1] if bridge.stats.events else {}
    print(f"\n  Result: {ev.get('outcome', 'unknown').upper()}")
    if bridge.stats.impact.meals:
        print(f"  Impact: {bridge.stats.impact.scoreboard()}")


def cmd_forecast(_args):
    from .predictor import forecast_summary

    print(forecast_summary(os.path.join(DATA, "history.json")))


def cmd_check(_args):
    from .strands_agent import (DEFAULT_BEDROCK_MODEL, DEFAULT_OLLAMA_MODEL,
                                STRANDS_AVAILABLE, make_model)

    print("FoodBridge readiness check")
    print(f"  Strands SDK installed : {STRANDS_AVAILABLE}")
    provider = os.getenv("FOODBRIDGE_MODEL_PROVIDER", "bedrock")
    print(f"  Model provider        : {provider}")
    model = make_model() if STRANDS_AVAILABLE else None
    print(f"  Model constructs      : {model is not None}")
    print(f"  Bedrock default model : {DEFAULT_BEDROCK_MODEL}")
    print(f"  Ollama default model  : {DEFAULT_OLLAMA_MODEL}")
    if not STRANDS_AVAILABLE:
        print("  -> Offline mode: runs free with the deterministic brain. "
              "pip install strands-agents to enable the live LLM agent.")
    elif model is None:
        print("  -> SDK present but no model/creds. Set AWS creds (Bedrock) or run Ollama, "
              "or use FOODBRIDGE_MODEL_PROVIDER=ollama.")
    else:
        print("  -> Ready to run as a live LLM agent.")


def cmd_test(_args):
    import subprocess

    subprocess.call([sys.executable, os.path.join(HERE, "tests", "test_foodbridge.py")])


COMMANDS = {
    "demo": cmd_demo,
    "add": cmd_add,
    "serve": cmd_serve,
    "ask": cmd_ask,
    "forecast": cmd_forecast,
    "check": cmd_check,
    "test": cmd_test,
}


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return
    COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    main()
