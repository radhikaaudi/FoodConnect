"""Generate a self-contained HTML dashboard from a completed run.

Compact, scannable design: a scoreboard on top, then one collapsible row per donation. The
default view is short — each row is a single line (time · item · outcome). Click a row to
expand the agent's reasoning, the messages it sent, and any human-decision moment.

No web server, no dependencies, no external assets — everything is inlined so the file opens
straight in a browser and is safe to screen-record for the demo video.
"""

from __future__ import annotations

import html
from typing import List

from .impact import Impact

_KIND_LABEL = {
    "SAFETY": "Safety call",
    "RESCUE_FAILING": "Rescue about to fail",
    "OVERSIZED": "Oversized donation",
    "NO_RECIPIENT": "No recipient",
}

_OUTCOME = {
    "delivered": ("Delivered", "ok"),
    "rejected": ("Rejected · safety", "warn"),
    "lost": ("Not rescued", "bad"),
}


def _row(ev: dict, idx: int = 0) -> str:
    status_text, cls = _OUTCOME.get(ev["outcome"], ("Pending", "muted"))
    esc = ev.get("escalation")
    dest = f" → {html.escape(ev['recipient'])}" if ev["outcome"] == "delivered" and ev["recipient"] else ""
    full_status = f"{status_text}{dest}"

    esc_pill = sent_pill = delivery_html = ""
    if esc:
        esc_pill = '<span class="pill warn">⚠ human decision</span>'
        dv = esc.get("delivery") or {}
        if dv.get("sent"):
            ch = html.escape(str(dv.get("channel") or "channel"))
            sent_pill = f'<span class="pill sent">📣 Sent to {ch}</span>'
            delivery_html = (f'<div class="delivery ok">📣 Escalation delivered to {ch} '
                             f'· {html.escape(str(dv.get("detail", "")))}</div>')
        else:
            delivery_html = ('<div class="delivery no">Not delivered — configure a channel '
                             '(Discord / Slack / Telegram / Email) to ping the coordinator '
                             'for real.</div>')

    # Expanded body (hidden until the row is clicked).
    body = f'<div class="why">{html.escape(ev["why"] or ev["safety_reason"])}</div>'
    if esc:
        rec = esc.get("recommendation")
        rec_html = f'<div class="rec"><b>Agent recommends:</b> {html.escape(rec)}</div>' if rec else ""
        counted = 1 if ev["outcome"] == "delivered" else 0
        co2 = ev["weight_lbs"] * 2.5
        body += (
            f'<div class="escalation" data-meals="{ev["meals"]}" '
            f'data-money="{ev["value_usd"]:.2f}" data-co2="{co2:.1f}" '
            f'data-counted="{counted}" data-state="{"approved" if counted else "rejected"}">'
            f'<span class="esc-tag">HUMAN DECISION · '
            f'{html.escape(_KIND_LABEL.get(esc["kind"], esc["kind"]))}</span>'
            f'<p>{html.escape(esc["message"])}</p>{rec_html}{delivery_html}'
            '<div class="btns">'
            '<button class="approve" onclick="fbDecide(this,\'approve\')">Approve</button>'
            '<button class="reject" onclick="fbDecide(this,\'reject\')">Reject</button>'
            '</div><div class="resolution"></div></div>'
        )
    for m in ev.get("messages", []):
        body += (f'<div class="msg"><span class="to">{html.escape(m["to"])}</span>'
                 f'{html.escape(m["text"])}</div>')

    return f"""
    <details class="item {cls}" style="animation-delay:{idx * 0.09:.2f}s">
      <summary>
        <span class="tmin">{ev['minute']}m</span>
        <span class="titem">{html.escape(ev['item'])}
          <em>{ev['weight_lbs']:.0f} lbs · {ev['meals']} meals · {html.escape(ev['donor'])}</em>
        </span>
        <span class="tstatus">{esc_pill}{sent_pill}<span class="pill {cls} rstatus"
              data-orig="{full_status}">{full_status}</span></span>
      </summary>
      <div class="body">{body}</div>
    </details>"""


def render(events: List[dict], impact: Impact, stats, brain_mode: str = "") -> str:
    rows = "\n".join(_row(e, i) for i, e in enumerate(events))
    brain_badge = (f'<span class="brain">🧠 {html.escape(brain_mode)}</span>'
                   if brain_mode else "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FoodBridge — Rescue Dashboard</title>
<style>
  :root {{ --bg:#0d1117; --card:#161b22; --line:#30363d; --txt:#e6edf3;
           --muted:#8b949e; --ok:#2ea043; --warn:#d29922; --bad:#f85149; --acc:#58a6ff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
          background:var(--bg); color:var(--txt); font-size:14px; }}
  .wrap {{ max-width:860px; margin:0 auto; padding:0 16px 40px; }}
  header {{ padding:24px 16px 8px; max-width:860px; margin:0 auto; }}
  header h1 {{ margin:0 0 3px; font-size:21px; }}
  header p {{ margin:0; color:var(--muted); font-size:13px; }}
  .brain {{ display:inline-block; margin-top:8px; font-size:12px; color:#a371f7;
            background:#1a1030; border:1px solid #3a2a5a; border-radius:20px; padding:3px 11px; }}
  .scoreboard {{ display:flex; gap:10px; flex-wrap:wrap; padding:16px 0 18px; }}
  .stat {{ flex:1; min-width:120px; background:var(--card); border:1px solid var(--line);
           border-radius:10px; padding:12px 14px; }}
  .stat .n {{ font-size:24px; font-weight:700; line-height:1.1; }}
  .stat .l {{ color:var(--muted); font-size:12px; margin-top:2px; }}
  .stat.meals .n {{ color:var(--ok); }} .stat.money .n {{ color:var(--acc); }}
  .stat.co2 .n {{ color:#a371f7; }}
  .section-h {{ font-size:12px; color:var(--muted); text-transform:uppercase;
                letter-spacing:.5px; margin:6px 2px 8px; }}

  @keyframes fadeIn {{ from {{ opacity:0; transform:translateY(6px); }}
                       to {{ opacity:1; transform:translateY(0); }} }}
  .item {{ background:var(--card); border:1px solid var(--line); border-left:3px solid var(--muted);
           border-radius:10px; margin-bottom:8px; opacity:0; animation:fadeIn .4s ease forwards; }}
  .item.ok {{ border-left-color:var(--ok); }}
  .item.warn {{ border-left-color:var(--warn); }}
  .item.bad {{ border-left-color:var(--bad); }}
  summary {{ list-style:none; cursor:pointer; display:flex; align-items:center; gap:12px;
             padding:11px 14px; }}
  summary::-webkit-details-marker {{ display:none; }}
  summary::after {{ content:"⌄"; color:var(--muted); margin-left:auto; font-size:15px; }}
  details[open] summary::after {{ content:"⌃"; }}
  .tmin {{ color:var(--muted); font-variant-numeric:tabular-nums; min-width:34px; font-size:13px; }}
  .titem {{ flex:1; font-weight:600; min-width:0; }}
  .titem em {{ display:block; font-weight:400; font-style:normal; color:var(--muted);
               font-size:12px; margin-top:1px; }}
  .tstatus {{ display:flex; gap:6px; align-items:center; flex-shrink:0; }}
  .pill {{ font-size:11px; font-weight:700; padding:3px 9px; border-radius:20px;
           background:#21262d; white-space:nowrap; }}
  .pill.ok {{ color:var(--ok); }} .pill.warn {{ color:var(--warn); }}
  .pill.bad {{ color:var(--bad); }} .pill.muted {{ color:var(--muted); }}
  .pill.sent {{ color:#3fb950; background:#0f2a17; border:1px solid #1c5c30; }}
  .delivery {{ font-size:11.5px; margin:6px 0 8px; }}
  .delivery.ok {{ color:#3fb950; }}
  .delivery.no {{ color:var(--muted); }}
  .delivery code {{ background:#0d1117; border:1px solid var(--line); border-radius:4px;
                    padding:1px 5px; font-size:11px; }}
  .body {{ padding:2px 14px 14px 60px; }}
  .why {{ font-size:12.5px; color:#c9d1d9; font-style:italic; margin-bottom:8px; }}
  .escalation {{ background:#2d2110; border:1px solid var(--warn); border-radius:8px;
                 padding:10px; margin:8px 0; }}
  .esc-tag {{ font-size:10px; font-weight:700; color:var(--warn); letter-spacing:.4px; }}
  .escalation p {{ margin:6px 0 7px; font-size:12.5px; white-space:pre-line; }}
  .rec {{ font-size:12px; color:#e3b341; margin-bottom:8px; }} .rec b {{ color:#f0c674; }}
  .btns {{ display:flex; gap:8px; }}
  .btns button {{ font-size:11.5px; font-weight:700; padding:6px 15px; border-radius:6px;
                  cursor:pointer; font-family:inherit; border:1px solid transparent; }}
  .btns button:hover {{ filter:brightness(1.12); }}
  .btns button:disabled {{ opacity:.4; cursor:default; filter:none; }}
  .approve {{ background:var(--ok); color:#03150a; }}
  .reject {{ background:#21262d; color:var(--bad); border-color:var(--bad); }}
  .resolution {{ font-size:12px; font-weight:600; margin-top:8px; }}
  .resolution.ok {{ color:var(--ok); }} .resolution.bad {{ color:var(--bad); }}
  .msg {{ font-size:12px; color:#c9d1d9; background:#0d1117; border:1px solid var(--line);
          border-radius:8px; padding:7px 9px; margin:5px 0; }}
  .msg .to {{ font-weight:700; color:var(--acc); margin-right:6px; }}
  .hint {{ color:var(--muted); font-size:11.5px; margin:2px 2px 10px; }}
  footer {{ color:var(--muted); font-size:11.5px; padding-top:18px; }}
</style></head>
<body>
  <header>
    <h1>🌉 FoodBridge — Rescue Dashboard</h1>
    <p>An autonomous agent rescuing surplus food — it acts on its own and surfaces to a human
       only when a row is flagged ⚠.</p>
    {brain_badge}
  </header>
  <div class="wrap">
    <div class="scoreboard">
      <div class="stat meals"><div class="n" id="s-meals" data-val="{impact.meals}">{impact.meals:,}</div><div class="l">Meals delivered</div></div>
      <div class="stat money"><div class="n" id="s-money" data-val="{impact.money_usd:.0f}" data-prefix="$">${impact.money_usd:,.0f}</div><div class="l">Money saved</div></div>
      <div class="stat co2"><div class="n" id="s-co2" data-val="{impact.co2_lbs:.0f}">{impact.co2_lbs:,.0f}</div><div class="l">lbs CO₂ prevented</div></div>
      <div class="stat"><div class="n" id="s-rescued" data-val="{stats.rescued}" data-suffix="/{stats.processed}">{stats.rescued}/{stats.processed}</div><div class="l">Rescued</div></div>
      <div class="stat"><div class="n">{stats.escalated}</div><div class="l">Human decisions</div></div>
    </div>
    <div class="section-h">Today's donations</div>
    <div class="hint">Click a row to expand. On a ⚠ row you're the coordinator — try
      <b>Approve</b> or <b>Reject</b> and watch the scoreboard update.</div>
    {rows}
    <footer>Impact uses standard factors (1.2 lbs = 1 meal, 2.5 lbs CO₂e avoided per lb).
      Approve/Reject let you override the agent live; in production these are the coordinator's
      SMS / Slack buttons.</footer>
  </div>
  <script>
  // Format a stat element from a numeric value, respecting its prefix/suffix.
  function fbSet(el, val) {{
    var prefix = el.dataset.prefix || '';
    var suffix = el.dataset.suffix || '';
    el.dataset.val = val;
    el.textContent = prefix + Math.round(val).toLocaleString() + suffix;
  }}
  // Coordinator override: Approve/Reject an escalation and update the scoreboard live.
  function fbDecide(btn, action) {{
    try {{
      var esc = btn.closest('.escalation');
      var det = btn.closest('details');
      var pill = det.querySelector('.rstatus');
      var res = esc.querySelector('.resolution');
      var meals = +esc.dataset.meals, money = +esc.dataset.money, co2 = +esc.dataset.co2;
      var state = esc.dataset.state;   // 'approved' (counted) or 'rejected'
      var mEl = document.getElementById('s-meals'), moEl = document.getElementById('s-money'),
          cEl = document.getElementById('s-co2'), rEl = document.getElementById('s-rescued');
      function bump(sign) {{
        fbSet(mEl, (+mEl.dataset.val) + sign * meals);
        fbSet(moEl, (+moEl.dataset.val) + sign * money);
        fbSet(cEl, (+cEl.dataset.val) + sign * co2);
        fbSet(rEl, (+rEl.dataset.val) + sign * 1);
      }}
      if (action === 'reject' && state !== 'rejected') {{
        if (state === 'approved') bump(-1);
        esc.dataset.state = 'rejected';
        pill.textContent = 'Not rescued'; pill.className = 'pill bad rstatus';
        det.className = 'item bad';
        res.textContent = '✗ You overrode the agent — this food was not rescued.';
        res.className = 'resolution bad';
      }} else if (action === 'approve' && state !== 'approved') {{
        if (state === 'rejected') bump(+1);
        esc.dataset.state = 'approved';
        pill.textContent = pill.dataset.orig; pill.className = 'pill ok rstatus';
        det.className = 'item ok';
        res.textContent = '✓ Approved — emergency pickup dispatched, rescue completed.';
        res.className = 'resolution ok';
      }} else if (action === 'approve') {{
        res.textContent = '✓ Approved — emergency pickup dispatched, rescue completed.';
        res.className = 'resolution ok';
      }}
    }} catch (e) {{}}
  }}
  // Count-up animation for the scoreboard (reads data-val).
  (function () {{
    try {{
      document.querySelectorAll('.stat .n').forEach(function (el) {{
        var target = parseFloat((el.dataset.val || el.textContent).replace(/[^0-9.]/g, '')) || 0;
        if (target <= 0) return;
        var start = null, dur = 1000;
        function tick(ts) {{
          if (!start) start = ts;
          var p = Math.min((ts - start) / dur, 1);
          fbSet(el, target * (0.2 + 0.8 * p * (2 - p)));
          if (p < 1) requestAnimationFrame(tick); else fbSet(el, target);
        }}
        requestAnimationFrame(tick);
      }});
    }} catch (e) {{}}
  }})();
  </script>
</body></html>"""


def write_dashboard(path: str, events, impact, stats, brain_mode: str = "") -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render(events, impact, stats, brain_mode))
