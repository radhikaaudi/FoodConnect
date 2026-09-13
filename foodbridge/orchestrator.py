"""Orchestrator — the autonomous rescue loop that ties the agents together.

For each incoming donation, FoodBridge runs end to end WITHOUT a human, and surfaces exactly
one decision to the coordinator only when it must:

    Scout -> Safety -> Matcher -> Dispatcher -> Delivery -> Receipt -> Impact

The ``escalate`` callback is where a human is pinged. In the demo it is answered
automatically so the run completes; in production it would be an SMS/Slack Approve-Reject.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from . import comms
from . import dispatcher as dispatch_mod
from . import matcher as match_mod
from . import notify as notify_mod
from . import receipts as receipt_mod
from . import safety as safety_mod
from .brain import SimulatedBrain
from .impact import Impact
from .memory import Memory
from .models import Donation, Driver, Recipient
from .observability import Trace
from .reporting import write_report

Escalation = Callable[[str, str], bool]  # (kind, message) -> approved?


@dataclass
class RunStats:
    processed: int = 0
    rescued: int = 0
    escalated: int = 0
    rejected: int = 0
    recipients_served: List[str] = field(default_factory=list)
    impact: Impact = field(default_factory=Impact)
    receipts: List[str] = field(default_factory=list)
    events: List[dict] = field(default_factory=list)  # structured records for the UI
    messages: List[dict] = field(default_factory=list)  # agent-authored comms


class FoodBridge:
    def __init__(
        self,
        recipients: List[Recipient],
        drivers: List[Driver],
        memory: Memory,
        escalate: Escalation,
        log: Callable[[str], None] = print,
        seed: int = 7,
        brain: Optional[SimulatedBrain] = None,
        trace: Optional[Trace] = None,
        notifier: Optional[Callable[[str], dict]] = None,
    ) -> None:
        self.recipients = recipients
        self.drivers = drivers
        self.memory = memory
        self.escalate = escalate
        self.log = log
        self.rng = random.Random(seed)
        self.stats = RunStats()
        self.brain = brain or SimulatedBrain()
        self.trace = trace or Trace()
        self.notifier = notifier or notify_mod.send

    # -- main entry point -------------------------------------------------------------
    def process(self, donation: Donation, now: int) -> None:
        s = self.stats
        s.processed += 1
        ev = {
            "id": donation.id,
            "minute": now,
            "donor": donation.donor_name,
            "item": donation.item,
            "weight_lbs": donation.weight_lbs,
            "value_usd": donation.value_usd,
            "category": donation.category,
            "meals": self._meals(donation),
            "safety": "",
            "safety_reason": "",
            "recipient": None,
            "why": "",
            "driver": None,
            "escalation": None,
            "messages": [],
            "outcome": "",  # delivered | rejected | lost
        }
        s.events.append(ev)
        self.brain.observe(now)  # keep the agent's tool context at the current minute
        self.trace.emit("donation_received", donation.id, donor=donation.donor_name,
                        weight_lbs=donation.weight_lbs, minute=now)
        self.log(f"\n[{now:>3} min] Donation {donation.id}: {donation.item} "
                 f"({donation.weight_lbs:.0f} lbs) from {donation.donor_name}")

        # 1) SAFETY -------------------------------------------------------------------
        verdict = safety_mod.assess(donation)
        ev["safety"] = verdict.verdict
        ev["safety_reason"] = verdict.reason
        self.trace.emit("safety_assessed", donation.id, verdict=verdict.verdict)
        self.log(f"    SAFETY: {verdict.verdict.upper()} — {verdict.reason}")
        if verdict.verdict == "reject":
            s.rejected += 1
            ev["outcome"] = "rejected"
            self.log(f"    ACTION: declined; notified {donation.donor_name}. Not counted.")
            return
        if verdict.verdict == "escalate":
            self._escalate(ev, "SAFETY", donation, verdict.reason,
                           f"{donation.item} from {donation.donor_name} is borderline "
                           f"({verdict.reason})")
            approved = self.escalate("SAFETY", ev["escalation"]["message"])
            if not approved:
                s.rejected += 1
                ev["outcome"] = "rejected"
                self.log("    HUMAN: rejected on safety. Not counted.")
                return
            self.log("    HUMAN: approved. Continuing autonomously.")

        # 2) MATCH --------------------------------------------------------------------
        options = match_mod.rank_recipients(donation, self.recipients, now)
        eligible = [o for o in options if o.disqualified is None]
        for o in options:
            if o.disqualified:
                self.log(f"    - {o.recipient.name}: not eligible ({o.disqualified})")
        if not eligible:
            self._escalate(ev, "NO_RECIPIENT", donation, "no eligible recipient",
                           f"No eligible recipient for {donation.item} right now.")
            ev["outcome"] = "lost"
            self.escalate("NO_RECIPIENT", ev["escalation"]["message"])
            self.log("    RESULT: no recipient; surfaced to coordinator.")
            return

        # Oversized-donation judgment call.
        primary = eligible[0]
        if donation.weight_lbs > primary.recipient.storage_capacity_lbs and len(eligible) > 1:
            names = ", ".join(o.recipient.name for o in eligible[:3])
            self._escalate(ev, "OVERSIZED", donation, f"larger than one site can take",
                           f"{donation.weight_lbs:.0f} lbs is large for one site "
                           f"(candidates: {names}).")
            self.escalate("OVERSIZED", ev["escalation"]["message"])
            self.log("    HUMAN: approved split (demo). Proceeding with primary recipient.")

        # The brain (LLM when available) chooses the recipient and explains why.
        runner_up = eligible[1] if len(eligible) > 1 else None
        chosen, why = self.brain.choose_recipient(donation, eligible, runner_up)
        ev["recipient"] = chosen.recipient.name
        ev["why"] = why
        self.trace.emit("recipient_chosen", donation.id, recipient=chosen.recipient.name,
                        brain=self.brain.mode)
        self.log("    WHY : " + why)

        # 3) DISPATCH (self-healing) --------------------------------------------------
        minutes_left = donation.pickup_deadline_minute - now
        result = dispatch_mod.dispatch(
            donation, chosen.recipient, self.drivers, self.memory, self.rng, self.log
        )
        if result.status == "failed":
            self._escalate(ev, "RESCUE_FAILING", donation, result.reason,
                           f"{self._meals(donation)} meals from {donation.donor_name} will be "
                           f"WASTED in {minutes_left} min — {result.reason}.")
            approved = self.escalate("RESCUE_FAILING", ev["escalation"]["message"])
            if not approved:
                ev["outcome"] = "lost"
                self.log("    HUMAN: declined emergency pickup. Food lost.")
                return
            self.log("    HUMAN: approved emergency pickup; coordinator drives.")
            driver_name = "Coordinator (emergency)"
            driver_obj = None
        else:
            driver_name = result.driver.name
            driver_obj = result.driver
        ev["driver"] = driver_name
        self.trace.emit("driver_assigned", donation.id, driver=driver_name)

        # Agent-authored driver request (shows how it actually talks to people).
        if driver_obj is not None:
            self._say(ev, "to " + driver_name, self.brain.compose(
                "driver_request", driver=driver_obj, donation=donation,
                recipient=chosen.recipient, minutes_left=minutes_left))

        # 4) DELIVERY (close the loop) ------------------------------------------------
        self.log(f"    DISPATCH: {driver_name} en route -> {chosen.recipient.name}")
        self._say(ev, "to " + chosen.recipient.name, self.brain.compose(
            "recipient_incoming", recipient=chosen.recipient, donation=donation,
            driver_name=driver_name))
        self.log(f"    DELIVERED: confirmed drop-off at {chosen.recipient.name}. Rescue complete.")
        self.trace.emit("delivery_confirmed", donation.id, recipient=chosen.recipient.name)
        chosen.recipient.last_served_minute = now
        self.memory.recipient_last_served[chosen.recipient.id] = now

        # 5) RECEIPT + donor thank-you ------------------------------------------------
        receipt = receipt_mod.generate_donor_receipt(donation, chosen.recipient.name, now)
        s.receipts.append(receipt)
        self._say(ev, "to " + donation.donor_name, self.brain.compose(
            "donor_thanks", donation=donation, recipient=chosen.recipient))
        self.log("    RECEIPT: tax-deduction receipt + liability protection sent to donor.")

        # 6) IMPACT -------------------------------------------------------------------
        s.rescued += 1
        ev["outcome"] = "delivered"
        s.recipients_served.append(chosen.recipient.name)
        s.impact.add(donation.weight_lbs, donation.value_usd)
        self.trace.emit("impact_recorded", donation.id, meals=ev["meals"])
        self.log(f"    IMPACT so far: {s.impact.scoreboard()}")

    # -- helpers ----------------------------------------------------------------------
    def _escalate(self, ev: dict, kind: str, donation: Donation, detail: str,
                  situation: str) -> None:
        """Build the human-facing escalation message and actually deliver it."""
        self.stats.escalated += 1
        recommendation = self.brain.recommend(kind, donation, detail)
        # RAG grounding: cite the guideline behind this judgment so the human can verify it.
        grounding = None
        try:
            from .knowledge import default_kb

            hits = default_kb().retrieve(f"{kind} {situation} {donation.category} "
                                         f"{donation.storage_temp}", k=1)
            if hits:
                grounding = hits[0].cite()
                recommendation = f"{recommendation} [Grounding: {grounding}]"
                self.trace.emit("rag_retrieval", donation.id, sources=[hits[0].id])
        except Exception:
            pass
        message = comms.coordinator_escalation(kind, donation, situation, recommendation)
        # Really send it to the coordinator's channel(s) if configured; meta enriches the email.
        meta = {
            "id": donation.id,
            "kind": kind,
            "situation": situation,
            "recommendation": recommendation,
            "donor": donation.donor_name,
            "item": donation.item,
            "weight_lbs": donation.weight_lbs,
            "meals": self._meals(donation),
        }
        try:
            delivery = self.notifier(message, meta)
        except TypeError:
            delivery = self.notifier(message)  # notifiers that only accept text
        ev["escalation"] = {"kind": kind, "message": message, "recommendation": recommendation,
                            "delivery": delivery}
        if delivery.get("sent"):
            self.log(f"    NOTIFY: delivered to {delivery.get('channel')} "
                     f"({delivery.get('detail')}).")
        self.trace.emit("escalation", donation.id, kind=kind,
                        delivered=bool(delivery.get("sent")), channel=delivery.get("channel"))

    def _say(self, ev: dict, to: str, text: str) -> None:
        if not text:
            return
        rec = {"to": to, "text": text, "donation_id": ev["id"]}
        ev["messages"].append(rec)
        self.stats.messages.append(rec)

    def _meals(self, d: Donation) -> int:
        from .impact import LBS_PER_MEAL

        return int(round(d.weight_lbs / LBS_PER_MEAL))

    def report(self) -> str:
        s = self.stats
        return write_report(
            s.processed, s.rescued, s.escalated, s.rejected, s.recipients_served, s.impact
        )
