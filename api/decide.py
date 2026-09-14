"""Vercel Python serverless function: the coordinator's one-click Approve/Reject endpoint.

Deployed at /api/decide?id=<donation>&action=approve|reject — this is what the buttons in
the escalation email hit, so the decision works from a phone or any browser (not just
localhost). Stateless: it renders a confirmation page. Wire it to a datastore later to
persist the decision.
"""

from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


def _page(action: str, did: str) -> str:
    ok = action == "approve"
    color = "#2ea043" if ok else "#cf222e"
    icon = "✓" if ok else "✗"
    verb = "Approved" if ok else "Rejected"
    msg = ("Emergency pickup dispatched — the rescue is confirmed. Thank you."
           if ok else "Understood — this donation will not be rescued.")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Decision recorded</title>
<style>body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#0d1117;font-family:-apple-system,Segoe UI,Arial,sans-serif;color:#e6edf3;}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:16px;padding:40px 44px;text-align:center;max-width:420px;}}
.icon{{width:64px;height:64px;border-radius:50%;background:{color};color:#fff;font-size:34px;line-height:64px;margin:0 auto 18px;}}
h1{{margin:0 0 8px;font-size:22px;}} p{{color:#8b949e;font-size:14px;margin:0 0 6px;}}
.id{{margin-top:16px;font-size:12px;color:#6e7681;}}</style></head>
<body><div class="card"><div class="icon">{icon}</div>
<h1>{verb}</h1><p>{msg}</p><p class="id">Donation {did or '—'} · recorded by FoodBridge</p>
</div></body></html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        action = (q.get("action", ["approve"])[0]).lower()
        did = q.get("id", [""])[0]
        body = _page(action, did).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)
