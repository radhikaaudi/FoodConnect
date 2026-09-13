# 🌉 FoodBridge — an autonomous food-rescue agent

> **AWS "Agents for Humans" Hackathon · Good Neighbor track**
> Built with the **Strands Agents SDK**, designed to run on **Amazon Bedrock AgentCore**.

**FoodBridge rescues surplus food before it spoils.** It forecasts the day's likely surplus,
watches for donations, judges food safety, matches each donation to the best nearby shelter,
dispatches a driver, confirms delivery, thanks the donor with a tax receipt, and keeps score
— all on its own. It only pings a human coordinator when there's a real decision to make: a
food-safety call, a rescue about to fail, or a donation too big for one site.

Every rescue is counted three ways: **meals delivered · money saved · CO₂ prevented.**

---

## Why it matters

Roughly **a third of all food is wasted** while **1 in 8 people** face food insecurity. The
food and the need both exist — what's missing is someone fast enough to connect them before
the food spoils. Today that coordination is a handful of stretched volunteers making phone
calls, so most surplus is never rescued. FoodBridge is that coordinator, working silently in
the background and surfacing only the calls that genuinely need a human.

---

## Prior art & how we're different

Food rescue is a real, established field — which is exactly why it's worth automating. The
pain and the process are proven; what's missing is autonomy.

| Existing tools | What they are |
|---|---|
| **Food Rescue US**, **412 Food Rescue / Food Rescue Hero** | Apps that dispatch **volunteer drivers** to move surplus food — but a human still runs the matching and coordination. |
| **Feeding America — MealConnect**, **Copia**, **Replate**, **Goodr** | Platforms that **list** donations for food banks / nonprofits to claim and arrange. |
| **Too Good To Go**, **Olio** | Consumer marketplaces that sell/share surplus before it's binned. |

These prove the model works at scale (millions of meals a year), and the mechanisms
FoodBridge uses are real: the **Bill Emerson Good Samaritan Food Donation Act (1996)** shields
donors from liability, enhanced **tax deductions** reward food donations, and countries like
**France (2016)** legally require supermarkets to donate unsold edible food.

**The gap:** every tool above is a *dashboard a human operates* — a person still judges safety,
picks the recipient, messages drivers, and handles fallout. **FoodBridge makes that coordinator
autonomous.** It performs the safety call, the match, the dispatch, and the self-heal itself,
learns across runs, and surfaces only the single decision a human must own. That shift — from
"an app that helps you coordinate" to "a coordinator that works on its own" — is the novel
contribution, and it is precisely the hackathon's theme: *runs in the background, surfaces only
on a real decision.*

---

## Is it a *real* agent, or a script?

Both paths are real, and you choose based on what you have:

| Mode | What drives decisions & messages | Needs | Cost |
|---|---|---|---|
| **Live agent** | A **Strands `Agent`** backed by a language model that **calls the tools itself** — it investigates each donation (checks safety, ranks recipients, estimates impact), then decides | Amazon Bedrock **or** a free local Ollama model | pennies on Bedrock / **$0** on Ollama |
| **Offline** | A deterministic `SimulatedBrain` runs the *identical* workflow — a faithful, clearly-labeled stand-in | nothing | **$0** |

**How the live agent actually works (genuine tool-calling, not a script):** for each donation,
the Strands `Agent` is handed the decision tools (`check_food_safety`, `rank_recipients`,
`estimate_impact`, `consult_guidelines`) **bound to the live recipient roster**, plus the raw
donation. The *model* chooses which tools to call and in what order, reasons over their
results (weighing nutrition and fairness), and returns its choice. Every tool call is recorded
on the decision trace, so its investigation is fully auditable (see `data/trace.jsonl` →
`tool_call` / `rag_retrieval` steps).

**Agentic RAG — grounded judgment with citations:** the agent has a curated knowledge base of
food-safety and food-donation rules (`data/knowledge/` — USDA danger-zone limits, the Good
Samaritan Act, Big-9 allergens, date-label guidance, cold-chain transport, prepared-food
rules, tax deductions). The `consult_guidelines` tool retrieves the most relevant passages
(dependency-free lexical retrieval; swappable for vector embeddings), and every **escalation
carries a citation** — e.g. *"[Grounding: USDA Temperature Danger Zone (40°F–140°F)]"* — so
the coordinator can verify the rule behind every call. Ask it rules questions too:
`python3 -m foodbridge.cli ask "can we donate food past its best-by date?"` → answers with the
guideline and its source.

The seam is `foodbridge/brain.py`: the orchestrator doesn't know or care which brain it holds,
so the same product runs for free offline and as a genuine LLM agent in the cloud. Every model
call has a deterministic fallback, so a flaky model never breaks a rescue.

**Design principle:** hard guarantees (food-safety rules, fairness, impact math) live in
**tools** (`foodbridge/tools.py`) and remain authoritative in the orchestrator; judgment,
prioritisation, and communication come from the **model** driving those tools. We never let
the LLM be the sole arbiter of food safety — knowing when *not* to hand it the wheel is the
point.

---

## Quick start (zero setup, $0)

No dependencies, no accounts, no keys — the offline demo runs on the Python standard library:

```bash
cd foodbridge
python3 run_demo.py            # full narrated rescue cycle + dashboard
```

You'll see the shift forecast, the agent's step-by-step reasoning, the one moment it surfaces
a decision to a human (with its recommendation), the messages it writes to drivers/donors/
recipients, proof-of-delivery, receipts, a live impact scoreboard, and its own impact report.

### One CLI, several ways to explore

```bash
python3 -m foodbridge.cli demo            # the narrated run above
python3 -m foodbridge.cli add             # YOU add a donation; watch the agent handle it live
python3 -m foodbridge.cli forecast        # proactive forecast of today's surplus
python3 -m foodbridge.cli ask "how many meals today?"     # talk to the agent
python3 -m foodbridge.cli serve           # live dashboard at http://localhost:8000
python3 -m foodbridge.cli check           # model / deployment readiness
python3 -m foodbridge.cli test            # run the test suite
```

`add` lets a judge **drive the agent themselves** — type in a surplus item and watch FoodBridge
judge its safety, choose a recipient (with reasons), dispatch a driver, and — if it needs a
call — ask *you* to approve. Try a spoiled item to see it refuse, or a huge one to see it
escalate.

### Visual dashboard (UI)

Every run writes a self-contained **`dashboard.html`** (no server, no dependencies) with an
animated impact scoreboard, a card per donation showing the agent's reasoning and the messages
it sent, and highlighted **Approve / Reject** human-decision moments. `serve` hosts it at a
shareable local URL — useful for the demo video and the optional "live demo link."

---

## What the agent does (and when it asks a human)

```
Forecast → Scout → Safety → Match → Dispatch → Deliver → Receipt → Impact
```

- **Forecast** — learns each donor's pattern from history and predicts the day's surplus, so
  it can pre-position drivers before food even appears (`predictor.py`).
- **Safety** — judges each donation *safe* / *borderline* (ask a human) / *unsafe* (reject),
  using the 4-hour perishable danger-zone rule (`safety.py`).
- **Match** — ranks recipients by need, **nutrition** (fresh food to sites serving children),
  **fairness** (spread food, don't just feed the closest), capacity, refrigeration, dietary
  safety, and distance — and **explains every pick** (`matcher.py` + the brain).
- **Dispatch** — assigns the best driver and **self-heals**: if one declines, it instantly
  tries the next, racing the deadline, and **learns** driver reliability across runs.
- **Deliver** — a rescue is only counted once **delivery is confirmed**.
- **Receipt** — sends the donor a **tax-deduction receipt** + **Good Samaritan liability
  reassurance**, removing the two biggest reasons businesses don't donate — which grows future
  supply.
- **Impact** — tallies meals / money / CO₂ and writes its own report.

**The human is contacted only for:** a borderline safety call, a rescue about to fail, or a
donation too large for any single recipient. Everything else, the agent just does — and each
escalation comes with the agent's **recommendation**.

Every step is written to a structured decision trace (`data/trace.jsonl`) — the same idea as
Strands/OpenTelemetry tracing, so nothing the agent does is a black box.

### Real notifications (the human actually gets pinged)

When the agent escalates, it can **really deliver** the message to a coordinator — on whatever
channel they use — not just print it. Configure one (or several); the escalation is sent to all
of them, and the dashboard shows a **📣 Sent to …** badge on the row.

```bash
# Discord / Slack (or any JSON webhook)
export FOODBRIDGE_WEBHOOK_URL="https://discord.com/api/webhooks/…"

# Telegram (free, ~2 min)
export FOODBRIDGE_TELEGRAM_TOKEN="123456:ABC…"  FOODBRIDGE_TELEGRAM_CHAT="<chat id>"

# Email (Gmail or any SMTP; use an app password)
export FOODBRIDGE_EMAIL_TO="you@example.com"
export FOODBRIDGE_SMTP_USER="you@gmail.com"  FOODBRIDGE_SMTP_PASS="app-password"

python3 run_demo.py     # the escalation now arrives on your channel(s)
```

**WhatsApp / SMS / anything else:** point `FOODBRIDGE_WEBHOOK_URL` at an automation platform
(Zapier, IFTTT, Make, n8n) and let it forward to WhatsApp, SMS, a spreadsheet — the generic
webhook is the universal bridge. With nothing set it's a safe no-op, so the demo always runs.
(Standard library only — `urllib` + `smtplib`, no dependencies.)

---

## Running the live LLM agent

**Option A — free, local, no cloud (Ollama):**
```bash
pip install strands-agents strands-agents-tools
# install Ollama from ollama.com, then:
ollama pull llama3.2
FOODBRIDGE_MODEL_PROVIDER=ollama python3 run_demo.py     # brain shows "Strands agent · ollama"
```

**Option B — Amazon Bedrock (production path for AgentCore):**
```bash
pip install -r requirements.txt
aws configure                     # enable a Bedrock model in your region
python3 run_demo.py               # brain shows "Strands agent · bedrock"
```

`python3 -m foodbridge.cli check` tells you exactly what's wired up.

## Deploying to Amazon Bedrock AgentCore

The included **`agentcore_app.py`** is the AgentCore Runtime entrypoint — the background
runner that expresses the hackathon theme literally:

```bash
pip install bedrock-agentcore strands-agents
python3 agentcore_app.py          # run one cycle locally (prints JSON result)
agentcore configure --entrypoint agentcore_app.py
agentcore launch                  # deploy the always-on runner
```

It returns the impact tally plus any escalations that need a human — the same behaviour you
see in the demo.

See **[SETUP.md](SETUP.md)** for a step-by-step AWS account + free-credits + billing-alarm
guide, and **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full diagram.

---

## Project layout

```
foodbridge/
├── run_demo.py               # narrated end-to-end demo (writes dashboard.html)
├── agentcore_app.py          # Amazon Bedrock AgentCore Runtime entrypoint
├── dashboard.html            # generated visual UI (open in a browser)
├── data/                     # seeded mock data + learned memory + history + trace
├── foodbridge/
│   ├── orchestrator.py       # the autonomous rescue loop + escalation logic
│   ├── brain.py              # SimulatedBrain (offline) + StrandsBrain (LLM) — the seam
│   ├── tools.py              # Strands @tool surface the agent calls
│   ├── strands_agent.py      # SDK detection + model providers (bedrock/ollama/litellm)
│   ├── comms.py              # agent-authored messages to drivers/donors/recipients
│   ├── notify.py             # real Slack/Discord delivery of escalations (urllib)
│   ├── safety.py             # food-safety judgment (safe / escalate / reject)
│   ├── matcher.py            # recipient ranking + explanations
│   ├── dispatcher.py         # driver assignment + self-healing
│   ├── knowledge.py          # RAG layer: curated KB + retrieval with citations
│   ├── predictor.py          # proactive surplus forecasting from history
│   ├── receipts.py           # tax receipt + Good Samaritan liability note
│   ├── impact.py             # meals / money / CO2 accounting
│   ├── reporting.py          # self-written impact report
│   ├── memory.py             # cross-run learning (driver reliability)
│   ├── observability.py      # structured JSONL decision trace
│   ├── dashboard.py          # generates the self-contained animated UI
│   ├── serve.py              # stdlib HTTP server for a live demo link
│   └── cli.py                # unified CLI (demo/add/serve/ask/forecast/check/test)
├── tests/test_foodbridge.py  # 13 tests: safety, matching, dispatch, impact, brain, e2e
├── ARCHITECTURE.md · SETUP.md · requirements.txt · LICENSE (MIT)
```

## Impact math (honest & reproducible)

- Meals: ~**1.2 lbs of food = 1 meal** (Feeding America convention).
- CO₂: a conservative **2.5 lbs CO₂e avoided per lb** of food diverted from landfill.
- Money: the donor-stated fair value of rescued food.

## Tests

```bash
python3 -m foodbridge.cli test        # or: python3 tests/test_foodbridge.py
```

## License

MIT — see [LICENSE](LICENSE).
