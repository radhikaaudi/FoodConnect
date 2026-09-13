"""Real outbound notifications for the human-decision moment.

When the agent escalates, it can actually deliver the message to a coordinator — on whatever
channel they use. Configure one (or several) via environment variables; anything not
configured is skipped. With nothing set, it's a safe no-op so the demo always runs. Standard
library only (``urllib`` + ``smtplib``) — no dependencies.

Supported channels
------------------
* Discord / Slack (or any JSON webhook):
      FOODBRIDGE_WEBHOOK_URL="https://discord.com/api/webhooks/…"   # or hooks.slack.com/…
* Telegram (free, ~2 min to set up a bot):
      FOODBRIDGE_TELEGRAM_TOKEN="123456:ABC…"   FOODBRIDGE_TELEGRAM_CHAT="<chat id>"
* Email (Gmail or any SMTP; use an app password):
      FOODBRIDGE_EMAIL_TO="you@example.com"
      FOODBRIDGE_SMTP_USER="you@gmail.com"      FOODBRIDGE_SMTP_PASS="app-password"
      (optional) FOODBRIDGE_SMTP_HOST=smtp.gmail.com  FOODBRIDGE_SMTP_PORT=587

WhatsApp / SMS / "anything": point FOODBRIDGE_WEBHOOK_URL at an automation platform
(Zapier / IFTTT / Make / n8n) and have it forward to WhatsApp, SMS, a spreadsheet, etc. —
the generic webhook is the universal bridge.
"""

from __future__ import annotations

import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage
from typing import Dict, Optional, Tuple


# -- individual channels ------------------------------------------------------------------
def _send_webhook(text: str) -> Tuple[bool, str, str]:
    url = os.getenv("FOODBRIDGE_WEBHOOK_URL", "").strip()
    if not url:
        return (False, "", "")
    name = "Discord" if "discord" in url else "Slack" if "slack" in url else "webhook"
    payload = {"content": text} if "discord" in url else {"text": text}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return (True, name, f"HTTP {getattr(resp, 'status', resp.getcode())}")
    except Exception as exc:
        return (False, name, str(exc))


def _send_telegram(text: str) -> Tuple[bool, str, str]:
    token = os.getenv("FOODBRIDGE_TELEGRAM_TOKEN", "").strip()
    chat = os.getenv("FOODBRIDGE_TELEGRAM_CHAT", "").strip()
    if not token or not chat:
        return (False, "", "")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return (True, "Telegram", f"HTTP {getattr(resp, 'status', resp.getcode())}")
    except Exception as exc:
        return (False, "Telegram", str(exc))


_KIND_TITLE = {
    "SAFETY": "Food-safety judgment call",
    "RESCUE_FAILING": "A rescue is about to fail",
    "OVERSIZED": "Donation too big for one site",
    "NO_RECIPIENT": "No eligible recipient",
}


def _email_html(text: str, meta: Optional[Dict], from_addr: str) -> str:
    """A clean, email-client-safe HTML message (inline styles, table layout)."""
    meta = meta or {}
    title = _KIND_TITLE.get(meta.get("kind", ""), "A rescue needs your decision")
    situation = meta.get("situation") or text
    rec = meta.get("recommendation", "")
    facts = [
        ("Item", meta.get("item")),
        ("From", meta.get("donor")),
        ("Amount", f"{meta['weight_lbs']:.0f} lbs" if meta.get("weight_lbs") else None),
        ("Meals at risk", str(meta["meals"]) if meta.get("meals") else None),
    ]
    rows = ""
    for label, val in facts:
        if not val:
            continue
        rows += (
            f'<tr><td style="padding:6px 0;color:#8a949e;width:120px;">{label}</td>'
            f'<td style="padding:6px 0;color:#1a1a1a;font-weight:600;">{val}</td></tr>'
        )
    rec_block = ""
    if rec:
        rec_block = (
            '<div style="background:#fff7e6;border:1px solid #ffd591;border-radius:8px;'
            'padding:12px 14px;margin-top:16px;color:#7a4f00;font-size:13px;line-height:1.5;">'
            f'<b>🤖 Agent recommends:</b> {rec}</div>'
        )
    # Prefer real one-click web links when the app is reachable (set FOODBRIDGE_APP_URL,
    # e.g. http://localhost:8000 while `serve` runs, or a public URL). Fall back to a
    # reply-to-approve mailto when there's no reachable endpoint.
    app_url = os.getenv("FOODBRIDGE_APP_URL", "").strip().rstrip("/")
    did = meta.get("id", "")
    if app_url:
        approve = f"{app_url}/decide?id={did}&action=approve"
        reject = f"{app_url}/decide?id={did}&action=reject"
    else:
        approve = f"mailto:{from_addr}?subject=APPROVE%20{did}"
        reject = f"mailto:{from_addr}?subject=REJECT%20{did}"
    return f"""\
<div style="background:#eef1f4;padding:26px 12px;font-family:-apple-system,Segoe UI,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
    style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e3e6ea;border-radius:14px;overflow:hidden;">
    <tr><td style="background:#0f7b3f;padding:16px 24px;color:#fff;font-size:17px;font-weight:700;">
      🌉 FoodBridge</td></tr>
    <tr><td style="padding:20px 24px 0;">
      <div style="display:inline-block;background:#fff3cd;color:#8a6100;font-size:11px;font-weight:700;
        padding:4px 10px;border-radius:20px;letter-spacing:.3px;">⚠ {title.upper()}</div>
      <h1 style="margin:12px 0 0;font-size:19px;color:#111;">A rescue needs your decision</h1>
      <p style="margin:8px 0 0;color:#444;font-size:14px;line-height:1.55;">{situation}</p>
    </td></tr>
    <tr><td style="padding:16px 24px 0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
        style="background:#f7f9fa;border:1px solid #e9edf1;border-radius:10px;padding:6px 14px;font-size:13px;">
        {rows}
      </table>
      {rec_block}
    </td></tr>
    <tr><td style="padding:20px 24px 6px;">
      <a href="{approve}" style="background:#2ea043;color:#fff;text-decoration:none;padding:11px 26px;
        border-radius:8px;font-weight:700;font-size:14px;display:inline-block;">✓ Approve</a>
      <a href="{reject}" style="background:#fff;color:#cf222e;border:1px solid #cf222e;text-decoration:none;
        padding:11px 26px;border-radius:8px;font-weight:700;font-size:14px;display:inline-block;margin-left:8px;">✗ Reject</a>
    </td></tr>
    <tr><td style="padding:14px 24px 24px;color:#8a949e;font-size:11.5px;line-height:1.5;">
      FoodBridge handled the rest of today's rescues on its own. You're seeing this because it
      needed a human call. Reply <b>APPROVE</b> or <b>REJECT</b> if the buttons don't open.</td></tr>
  </table>
</div>"""


def _send_email(text: str, meta: Optional[Dict] = None) -> Tuple[bool, str, str]:
    to = os.getenv("FOODBRIDGE_EMAIL_TO", "").strip()
    user = os.getenv("FOODBRIDGE_SMTP_USER", "").strip()
    pw = os.getenv("FOODBRIDGE_SMTP_PASS", "").strip()
    if not (to and user and pw):
        return (False, "", "")
    host = os.getenv("FOODBRIDGE_SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("FOODBRIDGE_SMTP_PORT", "587"))
    msg = EmailMessage()
    msg["Subject"] = "🌉 FoodBridge — a rescue needs your decision"
    msg["From"] = f"FoodBridge <{user}>"
    msg["To"] = to
    msg.set_content(text)  # plain-text fallback for any client
    msg.add_alternative(_email_html(text, meta, user), subtype="html")
    try:
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        return (True, "Email", f"sent to {to}")
    except Exception as exc:
        return (False, "Email", str(exc))


# -- public API ---------------------------------------------------------------------------
def configured_channels() -> List[str]:
    names = []
    if os.getenv("FOODBRIDGE_WEBHOOK_URL", "").strip():
        url = os.getenv("FOODBRIDGE_WEBHOOK_URL", "")
        names.append("Discord" if "discord" in url else "Slack" if "slack" in url else "webhook")
    if os.getenv("FOODBRIDGE_TELEGRAM_TOKEN") and os.getenv("FOODBRIDGE_TELEGRAM_CHAT"):
        names.append("Telegram")
    if os.getenv("FOODBRIDGE_EMAIL_TO") and os.getenv("FOODBRIDGE_SMTP_USER"):
        names.append("Email")
    return names


def send(text: str, meta: Optional[Dict] = None) -> Dict[str, object]:
    """Deliver ``text`` to every configured channel. ``meta`` enriches the HTML email."""
    results = [_send_webhook(text), _send_telegram(text), _send_email(text, meta)]
    attempted = [(ok, name, detail) for (ok, name, detail) in results if name]
    if not attempted:
        return {"sent": False, "channel": None,
                "detail": "no channel set (see notify.py — Discord/Slack/Telegram/Email/webhook)"}
    delivered = [name for (ok, name, _detail) in attempted if ok]
    detail = "; ".join(f"{name}: {d}" for (ok, name, d) in attempted)
    return {
        "sent": bool(delivered),
        "channel": "+".join(delivered) if delivered else attempted[0][1],
        "detail": detail,
    }
