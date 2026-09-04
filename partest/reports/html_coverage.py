"""Standalone HTML coverage report (self-contained CSS, no external assets)."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from partest.reports.analyzer import CoverageReport, EndpointCoverage
from partest.test_types import TYPE_LABELS


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _status_class(status: str) -> str:
    return {
        "full": "ok",
        "partial": "warn",
        "empty": "bad",
        "exception": "exc",
    }.get(status, "bad")


def _types_html(types) -> str:
    if not types:
        return "<span class='muted'>—</span>"
    chips = []
    for t in sorted(types):
        label = TYPE_LABELS.get(t, t)
        chips.append(f"<span class='chip'>{_esc(label)}</span>")
    return "".join(chips)


def _row_html(ep: EndpointCoverage) -> str:
    return f"""
    <tr class="{_status_class(ep.status)}">
      <td><code>{_esc(ep.method)}</code></td>
      <td><code>{_esc(ep.path)}</code></td>
      <td>{_esc(ep.subtype_label)}</td>
      <td class="num">{ep.calls}</td>
      <td class="num">{ep.coverage_pct:.0f}%</td>
      <td><span class="badge {_status_class(ep.status)}">{_esc(ep.status)}</span></td>
      <td>{_types_html(ep.executed_types)}</td>
      <td>{_types_html(ep.missing_p1)}</td>
      <td class="desc">{_esc(ep.description)}</td>
    </tr>
    """


def render_html(report: CoverageReport, *, title: str = "partest API coverage") -> str:
    """Return full HTML document as string."""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = "\n".join(_row_html(ep) for ep in sorted(
        report.endpoints, key=lambda e: (e.coverage_pct, e.method, e.path)
    ))

    subtype_cards = []
    for key, bucket in sorted(report.by_subtype.items(), key=lambda x: -x[1]["avg_pct"]):
        subtype_cards.append(
            f"""<div class="card">
              <div class="card-title">{_esc(bucket.get('label', key))}</div>
              <div class="card-metric">{bucket['avg_pct']:.0f}%</div>
              <div class="muted">{bucket['count']} endpoints</div>
            </div>"""
        )

    chart_data = {
        "labels": [f"{ep.method} {ep.path}" for ep in report.endpoints[:40]],
        "values": [ep.coverage_pct for ep in report.endpoints[:40]],
        "calls": [ep.calls for ep in report.endpoints[:40]],
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(title)}</title>
<style>
:root {{
  --bg: #0f1419;
  --panel: #1a2332;
  --text: #e7ecf3;
  --muted: #8b9bb4;
  --ok: #3dd68c;
  --warn: #f5a524;
  --bad: #f31260;
  --exc: #0072f5;
  --border: #2a3548;
  --chip: #243044;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; font-family: ui-sans-serif, system-ui, Segoe UI, Roboto, sans-serif;
  background: radial-gradient(1200px 600px at 10% -10%, #1b2a44 0%, var(--bg) 55%);
  color: var(--text); line-height: 1.45;
}}
header {{
  padding: 2rem 2rem 1rem; border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(26,35,50,.9), transparent);
}}
h1 {{ margin: 0 0 .25rem; font-size: 1.75rem; letter-spacing: -0.02em; }}
.sub {{ color: var(--muted); font-size: .95rem; }}
main {{ padding: 1.5rem 2rem 3rem; max-width: 1400px; margin: 0 auto; }}
.grid {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1rem; margin: 1.25rem 0 2rem;
}}
.stat, .card {{
  background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
  padding: 1rem 1.1rem; box-shadow: 0 10px 30px rgba(0,0,0,.2);
}}
.stat .label, .card-title {{ color: var(--muted); font-size: .8rem; text-transform: uppercase; letter-spacing: .06em; }}
.stat .value, .card-metric {{ font-size: 1.8rem; font-weight: 700; margin-top: .35rem; }}
.ok .value, .badge.ok {{ color: var(--ok); }}
.warn .value, .badge.warn {{ color: var(--warn); }}
.bad .value, .badge.bad {{ color: var(--bad); }}
.exc .value, .badge.exc {{ color: var(--exc); }}
.badge {{
  display: inline-block; padding: .15rem .55rem; border-radius: 999px;
  background: #121926; font-size: .75rem; font-weight: 600; text-transform: uppercase;
}}
section h2 {{ margin: 0 0 1rem; font-size: 1.15rem; }}
.table-wrap {{
  overflow: auto; border: 1px solid var(--border); border-radius: 14px; background: var(--panel);
}}
table {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
th, td {{ padding: .65rem .7rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
th {{
  position: sticky; top: 0; background: #121a27; text-align: left; color: var(--muted);
  font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; z-index: 1;
}}
tr:hover td {{ background: rgba(255,255,255,.02); }}
tr.ok td:nth-child(5) {{ color: var(--ok); font-weight: 600; }}
tr.warn td:nth-child(5) {{ color: var(--warn); font-weight: 600; }}
tr.bad td:nth-child(5) {{ color: var(--bad); font-weight: 600; }}
code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .82rem; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.chip {{
  display: inline-block; background: var(--chip); border: 1px solid var(--border);
  border-radius: 8px; padding: .1rem .4rem; margin: .1rem; font-size: .72rem;
}}
.muted {{ color: var(--muted); }}
.desc {{ max-width: 240px; color: var(--muted); font-size: .8rem; }}
.legend {{ display: flex; flex-wrap: wrap; gap: .75rem; margin: 0 0 1rem; color: var(--muted); font-size: .85rem; }}
footer {{ margin-top: 2rem; color: var(--muted); font-size: .8rem; }}
.bars {{ display: grid; gap: .45rem; margin-top: 1rem; }}
.bar-row {{ display: grid; grid-template-columns: minmax(120px, 2fr) 4fr 48px; gap: .6rem; align-items: center; }}
.bar-track {{ height: 10px; background: #121926; border-radius: 999px; overflow: hidden; border: 1px solid var(--border); }}
.bar-fill {{ height: 100%; background: linear-gradient(90deg, #3b82f6, #3dd68c); border-radius: 999px; }}
.bar-label {{ font-size: .75rem; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
</style>
</head>
<body>
<header>
  <h1>{_esc(title)}</h1>
  <div class="sub">Generated {generated} · partest coverage engine</div>
</header>
<main>
  <div class="grid">
    <div class="stat"><div class="label">Average coverage</div><div class="value">{report.average_pct:.1f}%</div></div>
    <div class="stat"><div class="label">Total calls</div><div class="value">{report.total_calls}</div></div>
    <div class="stat ok"><div class="label">Full (P1 set)</div><div class="value">{report.full_count}</div></div>
    <div class="stat warn"><div class="label">Partial</div><div class="value">{report.partial_count}</div></div>
    <div class="stat bad"><div class="label">Empty</div><div class="value">{report.empty_count}</div></div>
    <div class="stat exc"><div class="label">Exception 100%</div><div class="value">{report.exception_count}</div></div>
  </div>

  <section>
    <h2>By method subtype</h2>
    <div class="grid">
      {''.join(subtype_cards) or '<div class="muted">No endpoints</div>'}
    </div>
  </section>

  <section>
    <h2>Coverage bars (first 40 endpoints)</h2>
    <div class="bars" id="bars"></div>
  </section>

  <section style="margin-top:2rem">
    <h2>Endpoint matrix</h2>
    <div class="legend">
      <span>Coverage uses methodology matrix P1 (and conf priorities if configured).</span>
      <span class="badge ok">full</span>
      <span class="badge warn">partial</span>
      <span class="badge bad">empty</span>
      <span class="badge exc">exception</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Method</th>
            <th>Path</th>
            <th>Subtype</th>
            <th>Calls</th>
            <th>Cover</th>
            <th>Status</th>
            <th>Executed TC</th>
            <th>Missing P1</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>
  </section>

  <footer>
    Methodology: method subtype × test-case type × assert steps.
    Explicit <code>type=</code> on requests is recommended when inference confidence is below 99%.
  </footer>
</main>
<script>
const data = {json.dumps(chart_data)};
const root = document.getElementById('bars');
data.labels.forEach((label, i) => {{
  const pct = data.values[i] || 0;
  const row = document.createElement('div');
  row.className = 'bar-row';
  row.innerHTML = `
    <div class="bar-label" title="${{label}}">${{label}}</div>
    <div class="bar-track"><div class="bar-fill" style="width:${{Math.min(100, pct)}}%"></div></div>
    <div class="num">${{pct.toFixed(0)}}%</div>`;
  root.appendChild(row);
}});
</script>
</body>
</html>
"""


def write_html_report(
    report: CoverageReport,
    path: Union[str, Path] = "coverage_report.html",
    *,
    title: str = "partest API coverage",
) -> Path:
    """Write HTML report to disk; return path."""
    out = Path(path)
    out.write_text(render_html(report, title=title), encoding="utf-8")
    return out.resolve()
