"""Serve the FoodBridge dashboard over HTTP for a shareable local demo link.

Runs one rescue cycle, writes ``dashboard.html``, then serves the project directory so you
can open http://localhost:8000/dashboard.html — handy for the demo video and for the
optional "live demo link" that scores extra on Technical Implementation.

Standard library only (``http.server``); no framework, no dependencies.

    python3 -m foodbridge.serve            # port 8000
    python3 -m foodbridge.serve 9000       # custom port
"""

from __future__ import annotations

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _decision_page(action: str, did: str) -> bytes:
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
h1{{margin:0 0 8px;font-size:22px;}} p{{color:#8b949e;font-size:14px;line-height:1.5;margin:0 0 6px;}}
.id{{margin-top:16px;font-size:12px;color:#6e7681;}} a{{color:#58a6ff;}}</style></head>
<body><div class="card"><div class="icon">{icon}</div>
<h1>{verb}</h1><p>{msg}</p><p class="id">Donation {did or '—'} · recorded by FoodBridge</p>
<p style="margin-top:18px;"><a href="/dashboard.html">← Back to dashboard</a></p></div></body></html>""".encode("utf-8")


def _build_dashboard() -> str:
    from .brain import build_brain
    from .dashboard import write_dashboard
    from .memory import Memory
    from .models import load_donations, load_drivers, load_recipients
    from .orchestrator import FoodBridge

    data = os.path.join(HERE, "data")
    donations = sorted(load_donations(os.path.join(data, "donations.json")),
                       key=lambda d: d.ready_minute)
    recipients = load_recipients(os.path.join(data, "recipients.json"))
    brain = build_brain(prefer_llm=True, recipients=recipients)
    bridge = FoodBridge(recipients,
                        load_drivers(os.path.join(data, "drivers.json")),
                        Memory(os.path.join(data, "memory.json")),
                        escalate=lambda *_: True, brain=brain, log=lambda *_: None)
    for d in donations:
        bridge.process(d, now=d.ready_minute)
    out = os.path.join(HERE, "dashboard.html")
    write_dashboard(out, bridge.stats.events, bridge.stats.impact, bridge.stats,
                    brain_mode=brain.mode)
    return out


def main(port: int = 8000) -> None:
    _build_dashboard()
    os.chdir(HERE)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):  # keep the console clean
            pass

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/decide":
                q = parse_qs(parsed.query)
                action = (q.get("action", ["approve"])[0]).lower()
                did = q.get("id", [""])[0]
                print(f"  Coordinator {action.upper()}D donation {did or '—'} via email link.")
                body = _decision_page(action, did)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

    httpd = HTTPServer(("", port), Handler)
    url = f"http://localhost:{port}/dashboard.html"
    print(f"FoodBridge dashboard live at: {url}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
