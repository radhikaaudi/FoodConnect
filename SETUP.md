# FoodBridge — Setup

You can run FoodBridge three ways, cheapest first. **You never have to spend money to have a
complete, working submission.**

---

## 0. Offline — free, zero setup (recommended first run)

```bash
cd foodbridge
python3 run_demo.py
```

No account, no keys, no dependencies. The deterministic brain runs the full workflow and
writes `dashboard.html`. This alone is a runnable, judge-evaluable submission.

---

## 1. Free live LLM agent — local, via Ollama ($0)

Run a genuinely LLM-driven agent with no cloud account at all.

```bash
pip install strands-agents strands-agents-tools
# install Ollama from https://ollama.com , then:
ollama pull llama3.2
FOODBRIDGE_MODEL_PROVIDER=ollama python3 run_demo.py
```

The banner should read `Brain: Strands agent · ollama (LLM-driven)`. Verify anytime with:

```bash
python3 -m foodbridge.cli check
```

---

## 2. Amazon Bedrock + AgentCore (the production path)

This is the deployment that most strengthens the Technical Implementation score. Real usage
for a demo is **pennies**, and new AWS accounts get **free signup credits** that cover it.

### 2a. Create an AWS account (stay free)
1. Sign up at https://aws.amazon.com/ (a card is required for verification; you won't be
   charged while within free credits).
2. Billing console → **Credits** — confirm your new-account credits.
3. **Set a billing alarm at $5:** Billing → Budgets → Create budget → alert at $5. This is
   your safety net; you'll be emailed long before any real charge.

### 2b. Enable a model
- Bedrock console → **Model access** → request access to a Claude model in your region.
- `aws configure` (or set `AWS_*` env vars) so the SDK can authenticate.

### 2c. Run the live agent
```bash
pip install -r requirements.txt
python3 -m foodbridge.cli check        # should say "Ready to run as a live LLM agent"
python3 run_demo.py                    # Brain: Strands agent · bedrock (LLM-driven)
```

### 2d. Deploy the background runner to AgentCore
```bash
pip install bedrock-agentcore strands-agents
python3 agentcore_app.py               # run one cycle locally first (prints JSON)
agentcore configure --entrypoint agentcore_app.py
agentcore launch                       # deploy
```
**Tear down** the deployment after you record your demo so nothing keeps running.

---

## 3. Real escalation notifications (optional, free)

Make the human-decision moment actually reach a coordinator. Configure any of these (you can
set several — it delivers to all, and the dashboard shows a "📣 Sent to …" badge):

| Channel | Setup | Env vars |
|---|---|---|
| **Discord** (easiest) | Server → Integrations → Webhooks → New → Copy URL | `FOODBRIDGE_WEBHOOK_URL` |
| **Slack** | Create an Incoming Webhook | `FOODBRIDGE_WEBHOOK_URL` |
| **Telegram** | Create a bot with @BotFather, get your chat id | `FOODBRIDGE_TELEGRAM_TOKEN`, `FOODBRIDGE_TELEGRAM_CHAT` |
| **Email / Gmail** | Use an app password | `FOODBRIDGE_EMAIL_TO`, `FOODBRIDGE_SMTP_USER`, `FOODBRIDGE_SMTP_PASS` |
| **WhatsApp / SMS / anything** | Point the webhook at Zapier / IFTTT / Make and forward | `FOODBRIDGE_WEBHOOK_URL` |

```bash
export FOODBRIDGE_WEBHOOK_URL="https://discord.com/api/webhooks/…"
python3 run_demo.py        # escalations now post to your channel
```

No channel set = safe no-op. Uses the standard library only.

---

## Cost summary

| What | Cost |
|---|---|
| Offline demo, dashboard, tests, CLI | **$0** |
| Local LLM agent (Ollama) | **$0** |
| Bedrock calls for a demo | pennies (covered by free signup credits) |
| AgentCore while running | small; tear down after recording |

Set the **$5 billing alarm** and you cannot be surprised.
