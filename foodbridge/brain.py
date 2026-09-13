"""The agent's brain — judgment and language.

Two interchangeable implementations behind one interface:

* ``SimulatedBrain`` — deterministic, offline, zero-cost. Every decision is a transparent
  rule and every message a high-quality template. This is what runs in the instant demo so a
  judge can evaluate the whole system with no AWS account, no keys, and no spend. It is a
  faithful *stand-in* for the model, and the console clearly labels it as such.

* ``StrandsBrain`` — a real Strands ``Agent`` backed by a language model (Amazon Bedrock, or
  a free local Ollama model). Here the model actually reasons over the tool outputs: it picks
  the recipient, weighs whether a borderline case needs a human, and writes each message in
  its own words. Every model call has a deterministic fallback, so a flaky model or a bad
  parse never breaks a rescue.

The orchestrator neither knows nor cares which brain it holds — that is the seam that lets
the same product run for free offline and as a genuine LLM agent in the cloud.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from . import comms
from . import matcher as match_mod
from .impact import Impact
from .models import Donation, Recipient
from .strands_agent import STRANDS_AVAILABLE, make_model

SYSTEM_PROMPT = (
    "You are FoodBridge, an autonomous food-rescue coordinator for a network of shelters and "
    "food banks. You rescue surplus food before it spoils. You act on your own for every "
    "routine decision and only ask the human coordinator when (a) food safety is genuinely "
    "borderline, (b) a rescue is about to fail because no driver is available before the "
    "deadline, or (c) a donation is too large for any single recipient. You care about "
    "getting nutritious food to the people who need it most, treating recipients fairly, and "
    "never wasting an edible meal. You are warm, concise, and specific. When you choose, you "
    "explain your reasoning in one sentence. When you write to a person, you sound like a "
    "kind, busy human — never a robot."
)


class SimulatedBrain:
    """Deterministic offline brain. Faithful stand-in for the language model."""

    mode = "simulated (offline, deterministic)"
    is_llm = False

    def observe(self, now: int) -> None:
        """Update the agent's sense of the current time (no-op for the offline brain)."""

    def choose_recipient(
        self,
        donation: Donation,
        options: List[match_mod.MatchOption],
        runner_up: Optional[match_mod.MatchOption],
    ) -> Tuple[match_mod.MatchOption, str]:
        chosen = options[0]
        return chosen, match_mod.explain_pick(donation, chosen, runner_up)

    def recommend(self, kind: str, donation: Donation, detail: str) -> str:
        if kind == "SAFETY":
            return ("Lean reject unless the donor can confirm the cold chain held — the "
                    "downside of serving unsafe food outweighs the meals.")
        if kind == "RESCUE_FAILING":
            return ("Approve the emergency pickup — the food is good and the meals are worth "
                    "the extra drive.")
        if kind == "OVERSIZED":
            return "Split it across the top sites so nothing spoils and no one site is swamped."
        if kind == "NO_RECIPIENT":
            return "Hold briefly for the next open window, then re-offer."
        return "Use your judgment."

    def compose(self, kind: str, **ctx) -> str:
        if kind == "driver_request":
            return comms.driver_request(ctx["driver"], ctx["donation"], ctx["recipient"],
                                        ctx["minutes_left"])
        if kind == "recipient_incoming":
            return comms.recipient_incoming(ctx["recipient"], ctx["donation"], ctx["driver_name"])
        if kind == "donor_thanks":
            return comms.donor_thanks(ctx["donation"], ctx["recipient"])
        if kind == "shift_summary":
            return comms.shift_summary(ctx["impact"], ctx["rescued"], ctx["escalated"])
        return ""

    def answer(self, question: str, snap: dict) -> str:
        """Answer a coordinator's plain-language question about today's rescues."""
        q = question.lower()
        if any(w in q for w in ("meal", "how many people", "fed", "feed")):
            return f"{snap['meals']} meals delivered so far today."
        if any(w in q for w in ("money", "saved", "dollar", "$", "value")):
            return f"${snap['money']:,.0f} of food saved from the dumpster today."
        if any(w in q for w in ("co2", "carbon", "climate", "emission", "planet")):
            return f"{snap['co2']:,.0f} lbs of CO2 prevented today."
        if any(w in q for w in ("escalat", "decision", "need me", "ask")):
            return (f"I needed you for {snap['escalated']} decision(s) today; I handled the "
                    f"other {snap['rescued']} rescues on my own.")
        if any(w in q for w in ("reject", "unsafe", "safety", "spoil")):
            return f"I rejected {snap['rejected']} donation(s) on food-safety grounds."
        if any(w in q for w in ("who", "recipient", "shelter", "where")):
            served = ", ".join(snap["recipients"]) or "no one yet"
            return f"Today's food went to: {served}."
        if any(w in q for w in ("summary", "status", "how are we", "today", "overall")):
            return (f"{snap['rescued']} rescues, {snap['meals']} meals, "
                    f"${snap['money']:,.0f} saved, {snap['co2']:,.0f} lbs CO2 prevented, "
                    f"{snap['escalated']} decision(s) escalated.")
        # Rules / policy questions -> retrieve from the knowledge base (RAG) and cite it.
        try:
            from .knowledge import default_kb

            hits = default_kb().retrieve(question, k=1)
            if hits:
                p = hits[0]
                summary = " ".join(p.text.split())
                if len(summary) > 300:
                    summary = summary[:297] + "..."
                return f"{summary}  — {p.cite()}"
        except Exception:
            pass
        return ("I can tell you about meals, money saved, CO2 prevented, escalations, "
                "safety rejections, recipients served — or ask me a food-safety/donation "
                "rules question and I'll cite the guideline.")


class StrandsBrain(SimulatedBrain):
    """Real Strands agent brain — a language model that drives the tools itself.

    The agent is given the FoodBridge decision tools (``check_food_safety``,
    ``rank_recipients``, ``estimate_impact``) bound to the live recipient roster. For each
    donation it *investigates on its own* — deciding which tools to call and in what order —
    and returns its choice. The deterministic safety and ranking logic remain authoritative
    guardrails in the orchestrator; the agent reasons through the same tools. Every model call
    falls back to the deterministic brain, so a flaky model never breaks a rescue.
    """

    is_llm = True

    def __init__(self, recipients=None, provider: Optional[str] = None,
                 model_id: Optional[str] = None, trace=None) -> None:
        import os

        self._agent = None
        self._recipients = list(recipients or [])
        self._ctx = {"now": 0}
        self._trace = trace
        # Resolve the provider label the same way make_model() does, so the banner is honest.
        self._provider = (provider or os.getenv("FOODBRIDGE_MODEL_PROVIDER") or "bedrock").lower()
        model = make_model(provider, model_id)
        if model is not None:
            try:
                from strands import Agent

                from .tools import make_decision_tools

                tools = make_decision_tools(self._recipients, self._ctx, trace)
                # callback_handler=None silences Strands' default stdout streaming so the
                # agent's raw token stream doesn't interleave with our narration.
                self._agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=tools,
                                    callback_handler=None)
            except Exception:
                self._agent = None
        self.mode = (
            f"Strands agent · {self._provider} (LLM-driven, tool-calling)"
            if self._agent is not None
            else "simulated (offline, deterministic)"
        )
        self.is_llm = self._agent is not None

    def observe(self, now: int) -> None:
        self._ctx["now"] = now

    def _ask(self, prompt: str) -> Optional[str]:
        """One model call with a hard wall-clock timeout.

        Small local models can wander in tool-call loops; a rescue must never wait on one.
        On timeout (default 90s, FOODBRIDGE_LLM_TIMEOUT to change) we return None and the
        caller falls back to the deterministic brain.
        """
        if self._agent is None:
            return None
        import concurrent.futures
        import os

        timeout = float(os.getenv("FOODBRIDGE_LLM_TIMEOUT", "90"))
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            fut = pool.submit(self._agent, prompt)
            result = fut.result(timeout=timeout)
            return self._clean(str(result).strip())
        except Exception:  # timeout, model error, parse error -> deterministic fallback
            return None
        finally:
            # Never block on a stuck generation; the demo moves on without it.
            pool.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _clean(text: Optional[str]) -> Optional[str]:
        """Reject junk a small model sometimes emits (raw tool-call JSON, empties).

        Returning None makes every caller fall back to the deterministic wording, so a
        human never sees `{"type":"function",...}` in a message.
        """
        if not text:
            return None
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return None
        if '"type"' in stripped and '"function"' in stripped:
            return None
        return stripped

    def choose_recipient(self, donation, options, runner_up):
        """Genuine agentic investigation: the model calls tools, then decides."""
        if self._agent is None:
            return super().choose_recipient(donation, options, runner_up)
        deadline = donation.pickup_deadline_minute - self._ctx["now"]
        allergens = ", ".join(donation.allergens) or "none"
        prompt = (
            "A new food donation just arrived:\n"
            f"- item: {donation.item}\n"
            f"- category: {donation.category}\n"
            f"- amount: {donation.weight_lbs:.0f} lbs\n"
            f"- storage: {donation.storage_temp}\n"
            f"- hours out of refrigeration: {donation.hours_unrefrigerated}\n"
            f"- allergens: {allergens}\n"
            f"- must be picked up within: {deadline} minutes\n\n"
            "Investigate with your tools: call rank_recipients (and check_food_safety / "
            "estimate_impact if useful), weigh nutrition and fairness, then choose the single "
            "best recipient. Finish with exactly one line:\n"
            "DECISION: <recipient_id> | <one-sentence reason a coordinator would give>"
        )
        ans = self._ask(prompt)
        if not ans or "DECISION:" not in ans:
            return super().choose_recipient(donation, options, runner_up)
        decision = ans.split("DECISION:", 1)[1]
        rid, _, reason = decision.partition("|")
        rid = rid.strip()
        for o in options:
            if o.recipient.id == rid or (rid and rid in o.recipient.id):
                return o, reason.strip() or match_mod.explain_pick(donation, o, runner_up)
        return super().choose_recipient(donation, options, runner_up)

    def recommend(self, kind, donation, detail):
        ans = self._ask(
            f"Situation ({kind}): {detail}. In one sentence, what do you recommend the human "
            f"coordinator do, and why?"
        )
        return ans or super().recommend(kind, donation, detail)

    def compose(self, kind, **ctx):
        template = super().compose(kind, **ctx)
        # LLM judgment (choose/recommend/answer) is always on; rewriting every outbound
        # message in the model's own voice is opt-in (FOODBRIDGE_LLM_COMPOSE=1) so a live
        # run stays fast — judgment calls are where the model earns its keep.
        import os

        if self._agent is None or not template or os.getenv("FOODBRIDGE_LLM_COMPOSE") != "1":
            return template
        ans = self._ask(
            f"Rewrite this message warmly and concisely in your own voice, keeping every fact "
            f"exactly the same. Return only the message:\n{template}"
        )
        return ans or template

    def answer(self, question, snap):
        if self._agent is None:
            return super().answer(question, snap)
        import json

        ans = self._ask(
            f"Here is today's rescue data as JSON:\n{json.dumps(snap)}\n"
            f"Answer this coordinator's question in one short, warm sentence using only these "
            f"numbers: {question}"
        )
        return ans or super().answer(question, snap)


def build_brain(prefer_llm: bool = True, provider: Optional[str] = None,
                recipients=None, trace=None) -> SimulatedBrain:
    """Return the best available brain: a real Strands agent if possible, else simulated.

    ``recipients`` and ``trace`` are bound into the agent's decision tools so the model can
    investigate the live roster and its tool calls are recorded.
    """
    if prefer_llm and STRANDS_AVAILABLE:
        brain = StrandsBrain(recipients=recipients, provider=provider, trace=trace)
        if brain.is_llm:
            return brain
    return SimulatedBrain()
