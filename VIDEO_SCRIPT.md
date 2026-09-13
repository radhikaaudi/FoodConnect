# FoodBridge — 5-Minute Demo Video Script

> Target: 4:45–5:00. Screen recording + voiceover (no camera needed — allowed by the rules).
> Covers the three required pitch points: (1) the problem, (2) who it's for, (3) why it
> matters — plus the working end-to-end demo.

## Before you record (10-min prep)

```bash
cd /Users/macbook/Documents/PROJECTS/agent_for_good/foodbridge
brew services start ollama                      # make sure the local LLM is up
rm -f data/memory.json data/trace.jsonl

# Terminal: font size 18–20pt, dark theme, full screen.
# Browser: close extra tabs. Have Gmail open in one tab (logged in).
# Optional email beat: in a SECOND terminal run the server, and export your email vars
#   python3 -m foodbridge.cli serve         (leave running — it's also your live-demo link)
#   export FOODBRIDGE_EMAIL_TO=... FOODBRIDGE_SMTP_USER=... FOODBRIDGE_SMTP_PASS=...
#   export FOODBRIDGE_APP_URL="http://localhost:8000"
```

Record with QuickTime (File → New Screen Recording) or OBS. Speak slowly; you have time.

---

## 0:00 – 0:35 — The problem (slide or plain title screen)

**Show:** a title card: "FoodBridge" + one line: *A third of all food is wasted. 1 in 8 people are hungry.*

**Say:**
> "A third of all the food we produce is thrown away — while one in eight people don't have
> enough to eat. The food exists. The need exists. What's missing is speed: surplus food has
> a clock on it, and if nobody coordinates a rescue in a few hours, it goes in the dumpster.
> Today, that coordination is done by a handful of exhausted volunteers making phone calls.
> Meet Maria — she runs volunteer dispatch for a food bank, alone, every single day. She
> doesn't need another app to manage. She needs the coordination to just… happen."

## 0:35 – 1:00 — The idea

**Show:** title card line 2: *FoodBridge — an autonomous food-rescue agent. Built with Strands Agents SDK on AWS.*

**Say:**
> "FoodBridge is an autonomous agent built with the Strands Agents SDK. It watches for food
> donations, judges safety, picks the best shelter, dispatches a driver, confirms delivery,
> and thanks the donor with a tax receipt — entirely on its own. It only contacts a human
> for the decisions a human must own. Let me show you a real run."

## 1:00 – 2:20 — The live run (terminal)

**Do:** in the terminal, run:
```bash
FOODBRIDGE_MODEL_PROVIDER=ollama ./.venv/bin/python run_demo.py
```
(If the LLM is slow on your machine, `python3 run_demo.py` — the offline run — is fine;
just say "deterministic mode" honestly.)

**Say, as output scrolls (pause scrolling as needed):**
> "First — before any food even arrives — FoodBridge forecasts today's donations from each
> donor's history and pre-alerts drivers. It's proactive, not reactive."

*(point at the SHIFT FORECAST block)*

> "Now donations start arriving. Watch the brain line — this is a genuine Strands agent, a
> language model that investigates each donation by calling tools: it checks food safety,
> ranks recipients, weighs nutrition and fairness — fresh produce goes to the shelter that
> feeds children — and explains every choice in plain English."

*(point at a WHY line)*

> "Here's my favorite part. A driver declines. The agent doesn't panic — it self-heals,
> tries the next driver… and when every driver says no and twenty-five meals are one hundred
> minutes from the dumpster — *that's* when it calls a human. One decision. With its own
> recommendation, grounded in an actual USDA guideline it retrieved and cited."

*(point at the HUMAN DECISION block + the [Grounding: …] citation)*

> "And notice what it did with the spoiled deli meat — it refused it. Food safety rules are
> hard-coded guardrails; the model is never the sole arbiter of safety."

## 2:20 – 2:50 — The human gets pinged for real (Gmail)

**Do:** switch to the Gmail tab, open the "🌉 FoodBridge — a rescue needs your decision" email.

**Say:**
> "That escalation isn't a console message — it's real. The coordinator gets an email — or
> Slack, Discord, Telegram — with the facts, the agent's recommendation, and one-click
> Approve or Reject. Five rescues handled silently. One email. That's the entire ask on the
> human."

*(click Approve → show the green "Approved — emergency pickup dispatched" page)*

## 2:50 – 3:40 — The dashboard

**Do:** open http://localhost:8000/dashboard.html (or `open dashboard.html`).

**Say:**
> "This is the coordinator's window into what the agent already did. The scoreboard counts
> three kinds of impact for every rescue: meals delivered, money saved — and CO₂ prevented,
> because food rotting in landfills is nearly ten percent of global emissions. Each row is
> one donation; the flagged row is the one human decision."

*(click the ⚠ row to expand — show reasoning + agent messages; click Reject, watch the
scoreboard drop; click Approve, watch it restore)*

> "The buttons are live — reject it and the impact disappears from the board. Every message
> the agent sent — to the driver, the shelter, the donor — is right here. And the donor gets
> a tax receipt plus Good Samaritan Act protection automatically, which removes the two real
> reasons businesses don't donate."

## 3:40 – 4:10 — You can drive it (add + ask)

**Do:** in the terminal:
```bash
python3 -m foodbridge.cli add --item "Wedding buffet trays" --category prepared --weight 60 --value 150 --hours 1 --yes
python3 -m foodbridge.cli ask "can we donate food past its best-by date?"
```

**Say:**
> "You can hand it your own donation and watch it decide in real time. And you can ask it
> questions — including rules questions. It answers from a curated food-safety and legal
> knowledge base — USDA guidance, the Good Samaritan Act — with citations. That's
> retrieval-augmented judgment, not a model guessing about food safety."

## 4:10 – 4:40 — Architecture (slide: use ARCHITECTURE.md diagram)

**Say:**
> "Under the hood: a Strands agent drives four bound tools — safety, ranking, impact, and a
> RAG guideline lookup — with memory that learns driver reliability across runs, a structured
> decision trace for full auditability, and a deterministic fallback so a flaky model never
> breaks a rescue. It runs on Amazon Bedrock in production — with an AgentCore Runtime
> entrypoint for continuous background operation — or on a free local model, and the whole
> demo runs offline with zero setup so you can verify everything yourself."

## 4:40 – 5:00 — Close

**Show:** the dashboard scoreboard one more time.

**Say:**
> "In one shift, FoodBridge rescued 350 pounds of food — 291 meals, a thousand dollars, 875
> pounds of CO₂ — and asked a human for exactly one decision. Tools like Food Rescue US
> prove this model works with humans doing the coordination. FoodBridge makes the
> coordinator autonomous. That's an agent for humans."

*(End card: FoodBridge — repo URL — Built with Strands Agents SDK + Amazon Bedrock AgentCore)*

---

## After recording
1. Trim to under 5:00. Export 1080p.
2. Upload to YouTube — set **Public** (required).
3. Paste the link in the Devpost submission.

## Submission checklist (deadline: Sept 14, 5:00 pm PT)
- [ ] Video ≤5 min, public on YouTube/Vimeo
- [ ] Public GitHub repo, **MIT license visible in the About section**
- [ ] README + ARCHITECTURE diagram (done — in the repo)
- [ ] Text description on Devpost (problem → who → why; reuse the script's 0:00–1:00 lines)
- [ ] AWS Builder ID
- [ ] (Optional) live demo link + builder.aws blog post titled with "Agents for Humans"
