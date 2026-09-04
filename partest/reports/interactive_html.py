"""Self-contained interactive HTML showcase for coverage.json (LIB-COV-HTML)."""

from __future__ import annotations

import html
import json
from typing import Any

PLACEHOLDER_DATA = "%%COVERAGE_DATA%%"
PLACEHOLDER_TITLE = "%%COVERAGE_TITLE%%"


def render_html(payload: dict[str, Any], *, title: str = "partest API coverage") -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c")
    return (
        _TEMPLATE.replace(PLACEHOLDER_TITLE, html.escape(title))
        .replace(PLACEHOLDER_DATA, data)
    )


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ru" data-theme="dark">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>%%COVERAGE_TITLE%%</title>
<style>
:root, [data-theme=dark] {
  --bg: #0f1419; --panel: #1a2332; --text: #e7ecf3; --muted: #8b9bb4;
  --ok: #3dd68c; --warn: #f5a524; --bad: #f31260; --exc: #0072f5;
  --border: #2a3548; --chip: #243044; --accent: #3b82f6; --hover: rgba(255,255,255,.04);
  --track: #121926; --header: #121a27;
}
[data-theme=light] {
  --bg: #f4f6fa; --panel: #fff; --text: #1b2430; --muted: #5b6b82;
  --ok: #128a55; --warn: #b7791f; --bad: #c01048; --exc: #005bc4;
  --border: #d5dce8; --chip: #eef2f8; --accent: #2563eb; --hover: rgba(15,20,25,.04);
  --track: #e8edf5; --header: #eef2f8;
}
* { box-sizing: border-box; }
body {
  margin: 0; font-family: ui-sans-serif, system-ui, Segoe UI, Roboto, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.45;
}
header {
  padding: 1.4rem 1.6rem 1rem; border-bottom: 1px solid var(--border);
  background: var(--panel);
}
header .row { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; align-items: flex-start; }
h1 { margin: 0 0 .2rem; font-size: 1.55rem; letter-spacing: -0.02em; }
.sub { color: var(--muted); font-size: .9rem; }
.toolbar { display: flex; gap: .5rem; flex-wrap: wrap; }
button, select, input[type=number], input[type=search], input[type=text] {
  background: var(--track); color: var(--text); border: 1px solid var(--border);
  border-radius: 8px; padding: .35rem .6rem; font: inherit;
}
button { cursor: pointer; }
button.primary { background: var(--accent); border-color: transparent; color: #fff; }
button:hover { filter: brightness(1.08); }
main { padding: 1.2rem 1.6rem 3rem; max-width: 1480px; margin: 0 auto; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: .8rem; margin: 1rem 0 1.4rem; }
.stat, .card {
  background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
  padding: .85rem 1rem;
}
.stat .label, .card-title { color: var(--muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; }
.stat .value, .card-metric { font-size: 1.55rem; font-weight: 700; margin-top: .25rem; }
.ok .value, .badge.ok, .heat-hi { color: var(--ok); }
.warn .value, .badge.warn, .heat-mid { color: var(--warn); }
.bad .value, .badge.bad, .heat-lo { color: var(--bad); }
.exc .value, .badge.exc { color: var(--exc); }
.badge {
  display: inline-block; padding: .12rem .5rem; border-radius: 999px;
  background: var(--track); font-size: .72rem; font-weight: 600; text-transform: uppercase;
}
section h2 { margin: 0 0 .75rem; font-size: 1.05rem; }
.checks { display: flex; flex-wrap: wrap; gap: .45rem .8rem; margin: .4rem 0 0.8rem; }
.checks label { display: flex; align-items: center; gap: .35rem; font-size: .85rem; cursor: pointer; }
.card { cursor: pointer; }
.card:hover, .card.active { outline: 2px solid var(--accent); }
.card-metric { font-size: 1.35rem; }
.muted { color: var(--muted); font-size: .8rem; }
.filters {
  display: flex; flex-wrap: wrap; gap: .5rem; align-items: end;
  margin: 0 0 .75rem; padding: .75rem; background: var(--panel);
  border: 1px solid var(--border); border-radius: 12px;
}
.filters .field { display: flex; flex-direction: column; gap: .2rem; min-width: 120px; }
.filters .field span { font-size: .7rem; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
.filters select[multiple] { min-height: 72px; min-width: 150px; }
.banner { display: block; margin: 0 0 1rem; padding: .7rem .9rem; border-radius: 10px;
  border: 1px solid var(--bad); background: color-mix(in srgb, var(--bad) 14%, transparent);
  font-size: .86rem; line-height: 1.45; }
.banner b { display: block; margin-bottom: .15rem; }
.stat.clickable { cursor: pointer; }
.stat.clickable:hover { filter: brightness(1.1); }
.table-wrap { overflow: auto; border: 1px solid var(--border); border-radius: 12px; background: var(--panel); max-height: 70vh; }
table { width: 100%; border-collapse: collapse; font-size: .84rem; }
th, td { padding: .5rem .55rem; border-bottom: 1px solid var(--border); vertical-align: top; }
th {
  position: sticky; top: 0; background: var(--header); text-align: left; color: var(--muted);
  font-size: .7rem; text-transform: uppercase; letter-spacing: .04em; z-index: 2; cursor: pointer; user-select: none;
}
th.sort-asc::after { content: " ↑"; }
th.sort-desc::after { content: " ↓"; }
tr:hover td { background: var(--hover); }
tr.ok td.cover { color: var(--ok); font-weight: 600; }
tr.warn td.cover { color: var(--warn); font-weight: 600; }
tr.bad td.cover { color: var(--bad); font-weight: 600; }
tr.exc td.cover { color: var(--exc); font-weight: 600; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .8rem; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.chip {
  display: inline-block; background: var(--chip); border: 1px solid var(--border);
  border-radius: 7px; padding: .08rem .35rem; margin: .08rem; font-size: .7rem;
}
.chip.miss { cursor: pointer; }
.chip.miss.active { outline: 1px solid var(--accent); }
.path { cursor: copy; }
.details { display: none; background: var(--track); }
.details.open { display: table-row; }
.details td { font-size: .8rem; color: var(--muted); }
.pager { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin-top: .7rem; font-size: .85rem; }
.bars { display: grid; gap: .4rem; }
.bar-row { display: grid; grid-template-columns: minmax(140px, 2.2fr) 4fr 48px; gap: .55rem; align-items: center; }
.bar-track { height: 10px; background: var(--track); border-radius: 999px; overflow: hidden; border: 1px solid var(--border); }
.bar-fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--ok)); border-radius: 999px; }
.bar-label { font-size: .72rem; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.heat { overflow: auto; border: 1px solid var(--border); border-radius: 12px; }
.heat table { font-size: .75rem; }
.heat td, .heat th { text-align: center; min-width: 56px; }
.heat td { font-variant-numeric: tabular-nums; }
.legend { display: flex; flex-wrap: wrap; gap: .65rem; margin: 0 0 .6rem; color: var(--muted); font-size: .82rem; }
footer { margin-top: 1.6rem; color: var(--muted); font-size: .78rem; }
.help {
  display: none; margin-top: .6rem; padding: .7rem .85rem; background: var(--track);
  border: 1px solid var(--border); border-radius: 10px; font-size: .82rem; color: var(--muted);
}
.help.open { display: block; }
.presets { display: flex; flex-wrap: wrap; gap: .35rem; margin: 0 0 .6rem; }
@media (max-width: 720px) {
  main, header { padding-left: .8rem; padding-right: .8rem; }
  .bar-row { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<header>
  <div class="row">
    <div>
      <h1>%%COVERAGE_TITLE%%</h1>
      <div class="sub" id="meta-line"></div>
    </div>
    <div class="toolbar">
      <button type="button" id="btn-help" title="Как считается coverage">?</button>
      <button type="button" id="btn-theme">Тема</button>
      <button type="button" id="btn-csv">CSV</button>
      <button type="button" id="btn-json">JSON</button>
    </div>
  </div>
  <div class="help" id="help">
    Coverage = доля выполненных P1 тест-кейсов методологии (subtype × Request* matrix) на эндпоинт.
    Average — среднее по выбранным сервисам. Full = все P1 есть; Partial = часть; Empty = 0 P1.
    Чекбоксы сервисов пересчитывают шапку, карточки и bars; matrix фильтруется отдельно.
    Клавиши: <code>/</code> поиск, <code>Esc</code> сброс фильтров matrix.
  </div>
</header>
<main>
  <div class="banner" id="run-banner" hidden></div>
  <div class="grid" id="stats"></div>

  <section>
    <h2>Сервисы (включить в оценку)</h2>
    <div class="checks" id="service-checks"></div>
    <div class="toolbar">
      <button type="button" class="primary" id="btn-recalc">Пересчитать</button>
      <button type="button" id="btn-reset-svc">Сбросить</button>
    </div>
  </section>

  <section>
    <h2>By service</h2>
    <div class="grid" id="service-cards"></div>
  </section>

  <section>
    <h2>By method subtype</h2>
    <div class="grid" id="subtype-cards"></div>
  </section>

  <section>
    <h2>By HTTP method</h2>
    <div class="grid" id="method-cards"></div>
  </section>

  <section>
    <h2>Top missing P1</h2>
    <div id="missing-top"></div>
  </section>

  <section>
    <h2>Heatmap (service × subtype)</h2>
    <div class="heat" id="heatmap"></div>
  </section>

  <section>
    <h2>Coverage bars</h2>
    <div class="muted" id="bars-caption"></div>
    <div class="bars" id="bars"></div>
  </section>

  <section style="margin-top:1.6rem">
    <h2>Endpoint matrix</h2>
    <div class="legend">
      <span id="matrix-count"></span>
      <span class="badge ok">full</span>
      <span class="badge warn">partial</span>
      <span class="badge bad">empty</span>
      <span class="badge exc">exception</span>
    </div>
    <div class="presets" id="presets"></div>
    <div class="filters" id="filters"></div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr id="thead"></tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
    <div class="pager" id="pager"></div>
  </section>

  <footer>
    Methodology: method subtype × test-case type × assert steps.
    This page is a view over <code>coverage.json</code>; the service map is supplied by the project.
  </footer>
</main>
<script id="coverage-data" type="application/json">%%COVERAGE_DATA%%</script>
<script>
(function () {
  const LS_SVC = "partest-cov-services";
  const LS_FILT = "partest-cov-filters";
  const LS_THEME = "partest-cov-theme";

  // localStorage throws outright when the page is opened from a sandboxed or data:
  // context. Persisting filters is a convenience; losing the whole report because of
  // it is not acceptable, so every access is guarded.
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* ignore */ } }
  };
  const DATA = JSON.parse(document.getElementById("coverage-data").textContent);
  const ALL = DATA.endpoints || [];
  const SERVICE_META = {};
  (DATA.services || []).forEach(s => { SERVICE_META[s.key] = s.label; });
  ALL.forEach(e => { if (e.service && !SERVICE_META[e.service]) SERVICE_META[e.service] = e.serviceLabel || e.service; });

  const state = {
    selected: new Set(),
    filters: {
      services: [],
      methods: [],
      subtypes: [],
      statuses: [],
      kinds: [],
      coverage: "",
      callsMin: "",
      callsMax: "",
      missing: [],
      search: ""
    },
    sort: [{ key: "coverage", dir: 1 }],
    page: 1,
    pageSize: 25,
    expanded: null
  };

  function unique(arr) { return [...new Set(arr)]; }
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }
  function statusClass(st) {
    return { full: "ok", partial: "warn", empty: "bad", exception: "exc" }[st] || "bad";
  }
  function heatClass(pct) {
    if (pct >= 67) return "heat-hi";
    if (pct >= 34) return "heat-mid";
    return "heat-lo";
  }
  function avg(list) {
    if (!list.length) return 0;
    return list.reduce((s, e) => s + (e.coverage || 0), 0) / list.length;
  }
  function summarize(list) {
    const s = { avg: avg(list), calls: 0, full: 0, partial: 0, empty: 0, exception: 0,
                unseen: 0, endpoints: list.length };
    list.forEach(e => {
      s.calls += e.calls || 0;
      if (e.status === "exception") s.exception++;
      else if (e.status === "full") s.full++;
      else if (e.status === "partial") s.partial++;
      else s.empty++;
      // kind is about this run: nothing called it, which is not the same as
      // "it has no tests". Counted separately so the two are never conflated.
      if (e.kind === "unseen") s.unseen++;
    });
    return s;
  }

  function scoredEndpoints() {
    return ALL.filter(e => state.selected.has(e.service));
  }

  const EMPTY_FILTERS = {
    services: [], methods: [], subtypes: [], statuses: [], kinds: [],
    coverage: "", callsMin: "", callsMax: "", missing: [], search: ""
  };

  function matrixEndpoints() {
    const f = state.filters;
    const covRange = {
      "0": [0, 0],
      "1-33": [0.0001, 33],
      "34-66": [34, 66],
      "67-99": [67, 99.9999],
      "100": [100, 100]
    }[f.coverage];
    const q = (f.search || "").trim().toLowerCase();
    return scoredEndpoints().filter(e => {
      if (f.services.length && !f.services.includes(e.service)) return false;
      if (f.methods.length && !f.methods.includes(e.method)) return false;
      if (f.subtypes.length && !f.subtypes.includes(e.subtype)) return false;
      if (f.statuses.length && !f.statuses.includes(e.status)) return false;
      if (f.kinds.length && !f.kinds.includes(e.kind || "unseen")) return false;
      if (covRange) {
        const c = e.coverage || 0;
        if (c < covRange[0] || c > covRange[1]) return false;
      }
      if (f.callsMin !== "" && (e.calls || 0) < Number(f.callsMin)) return false;
      if (f.callsMax !== "" && (e.calls || 0) > Number(f.callsMax)) return false;
      if (f.missing.length && !f.missing.some(m => (e.missing || []).includes(m))) return false;
      if (q) {
        const blob = [e.path, e.description, e.method, e.service, e.serviceLabel].join(" ").toLowerCase();
        if (!blob.includes(q)) return false;
      }
      return true;
    });
  }

  function cmp(a, b, key) {
    const av = a[key], bv = b[key];
    if (typeof av === "number" && typeof bv === "number") return av - bv;
    return String(av ?? "").localeCompare(String(bv ?? ""), undefined, { numeric: true, sensitivity: "base" });
  }
  function sortRows(list) {
    const rules = state.sort.length ? state.sort : [{ key: "coverage", dir: 1 }, { key: "path", dir: 1 }];
    return [...list].sort((a, b) => {
      for (const r of rules) {
        const d = cmp(a, b, r.key) * r.dir;
        if (d) return d;
      }
      return 0;
    });
  }

  function persist() {
    try {
      store.set(LS_SVC, JSON.stringify([...state.selected]));
      store.set(LS_FILT, JSON.stringify({ filters: state.filters, pageSize: state.pageSize }));
    } catch (_) {}
  }
  function restore() {
    const theme = store.get(LS_THEME) || "dark";
    document.documentElement.setAttribute("data-theme", theme);
    const allKeys = Object.keys(SERVICE_META);
    let selected = allKeys.slice();
    try {
      const raw = JSON.parse(store.get(LS_SVC) || "null");
      if (Array.isArray(raw) && raw.length) selected = raw.filter(k => allKeys.includes(k));
    } catch (_) {}
    const excluded = new Set(DATA.meta?.defaultExcluded || []);
    if (!store.get(LS_SVC) && excluded.size) {
      selected = allKeys.filter(k => !excluded.has(k));
    }
    state.selected = new Set(selected.length ? selected : allKeys);
    try {
      const saved = JSON.parse(store.get(LS_FILT) || "null");
      if (saved?.filters) Object.assign(state.filters, saved.filters);
      if (saved?.pageSize) state.pageSize = saved.pageSize;
    } catch (_) {}
  }

  function renderStats() {
    const all = summarize(ALL);
    const sel = summarize(scoredEndpoints());
    const timing = DATA.timing;
    document.getElementById("stats").innerHTML = `
      <div class="stat"><div class="label">Average coverage</div><div class="value">${all.avg.toFixed(1)}%</div></div>
      <div class="stat"><div class="label">Coverage (selected)</div><div class="value">${sel.avg.toFixed(1)}%</div></div>
      <div class="stat"><div class="label">Total calls</div><div class="value">${sel.calls}</div></div>
      <div class="stat ok clickable" data-kind="full"><div class="label">Full (P1)</div><div class="value">${sel.full}</div></div>
      <div class="stat warn clickable" data-kind="partial"><div class="label">Partial</div><div class="value">${sel.partial}</div></div>
      <div class="stat bad clickable" data-kind="empty"><div class="label">Empty</div><div class="value">${sel.empty}</div></div>
      <div class="stat bad clickable" data-kind="unseen"><div class="label">Not called this run</div><div class="value">${sel.unseen}</div></div>
      <div class="stat exc"><div class="label">Exception</div><div class="value">${sel.exception}</div></div>` +
      (timing ? `
      <div class="stat"><div class="label">Latency avg</div><div class="value">${timing.msAvg} ms</div></div>
      <div class="stat"><div class="label">Latency p95</div><div class="value">${timing.msP95} ms</div></div>` : "");

    document.querySelectorAll("#stats .stat.clickable").forEach(tile => {
      tile.addEventListener("click", () => {
        state.filters = { ...EMPTY_FILTERS, kinds: [tile.getAttribute("data-kind")] };
        state.page = 1;
        persist();
        renderAll();
      });
    });

    renderRunBanner(sel);
    document.getElementById("meta-line").textContent =
      `Generated ${DATA.meta?.generated || "—"} · ${DATA.meta?.engine || "partest"} · ${sel.endpoints} / ${all.endpoints} endpoints in score`;
  }

  function renderRunBanner(sel) {
    // The number is only as honest as the run behind it. Say so at the top, where a
    // reader cannot miss it, rather than leaving it in the JSON.
    const meta = DATA.meta || {};
    const el = document.getElementById("run-banner");
    const reasons = [];
    const workers = Number(meta.workers || 1);
    if (workers > 1 && meta.merged === false) {
      reasons.push(`Ran on ${workers} parallel workers whose results were never merged, so these
        counts belong to one worker, not to the suite.`);
    }
    if (meta.partialRun && sel.unseen) {
      const pct = meta.unseenRatio != null ? ` (${Math.round(meta.unseenRatio * 100)}%)` : "";
      reasons.push(`${sel.unseen} endpoint(s)${pct} were never called in this run — a filtered
        selection or a failed fixture reads the same as "no tests" in the average.`);
    }
    if (!reasons.length) { el.hidden = true; return; }
    el.hidden = false;
    el.innerHTML = `<b>This run does not describe the whole suite</b>` +
      reasons.map(r => `<div>${r}</div>`).join("");
  }

  function renderServiceChecks() {
    const keys = Object.keys(SERVICE_META).sort((a, b) => SERVICE_META[a].localeCompare(SERVICE_META[b]));
    document.getElementById("service-checks").innerHTML = keys.map(k => `
      <label><input type="checkbox" data-svc="${esc(k)}" ${state.selected.has(k) ? "checked" : ""}/>
      ${esc(SERVICE_META[k])}</label>`).join("");
  }

  function renderCards(id, items, onClick) {
    const root = document.getElementById(id);
    root.innerHTML = items.map(it => `
      <div class="card" data-key="${esc(it.key)}">
        <div class="card-title">${esc(it.title)}</div>
        <div class="card-metric">${it.avg.toFixed(0)}%</div>
        <div class="muted">${it.count} endpoints · ${it.calls} calls</div>
      </div>`).join("") || `<div class="muted">Нет данных</div>`;
    root.querySelectorAll(".card").forEach(el => {
      el.addEventListener("click", () => onClick(el.getAttribute("data-key")));
    });
  }

  function groupServices(list) {
    const map = {};
    list.forEach(e => {
      const k = e.service;
      (map[k] ||= { key: k, title: e.serviceLabel || SERVICE_META[k] || k, items: [] }).items.push(e);
    });
    return Object.values(map).map(g => {
      const s = summarize(g.items);
      return { key: g.key, title: g.title, avg: s.avg, count: s.endpoints, calls: s.calls };
    }).sort((a, b) => b.avg - a.avg);
  }
  function groupSubtypes(list) {
    const map = {};
    list.forEach(e => {
      (map[e.subtype] ||= { key: e.subtype, title: e.subtype, items: [] }).items.push(e);
    });
    return Object.values(map).map(g => {
      const s = summarize(g.items);
      return { key: g.key, title: g.title, avg: s.avg, count: s.endpoints, calls: s.calls };
    }).sort((a, b) => b.avg - a.avg);
  }
  function groupMethods(list) {
    const map = {};
    list.forEach(e => {
      (map[e.method] ||= { key: e.method, title: e.method, items: [] }).items.push(e);
    });
    return Object.values(map).map(g => {
      const s = summarize(g.items);
      return { key: g.key, title: g.title, avg: s.avg, count: s.endpoints, calls: s.calls };
    });
  }

  function renderMissing(list) {
    const c = {};
    list.forEach(e => (e.missing || []).forEach(t => { c[t] = (c[t] || 0) + 1; }));
    const top = Object.entries(c).sort((a, b) => b[1] - a[1]).slice(0, 12);
    document.getElementById("missing-top").innerHTML = top.map(([tc, n]) =>
      `<span class="chip miss ${state.filters.missing.includes(tc) ? "active" : ""}" data-tc="${esc(tc)}">${esc(tc)} · ${n}</span>`
    ).join("") || `<span class="muted">Нет missing P1</span>`;
    document.querySelectorAll("#missing-top .chip").forEach(el => {
      el.addEventListener("click", () => {
        const tc = el.getAttribute("data-tc");
        const set = new Set(state.filters.missing);
        set.has(tc) ? set.delete(tc) : set.add(tc);
        state.filters.missing = [...set];
        state.page = 1;
        persist();
        renderAll();
      });
    });
  }

  function renderHeatmap(list) {
    const services = unique(list.map(e => e.service)).sort();
    const subtypes = unique(list.map(e => e.subtype)).sort();
    const cell = {};
    list.forEach(e => {
      const k = e.service + "||" + e.subtype;
      (cell[k] ||= []).push(e.coverage || 0);
    });
    let html = "<table><thead><tr><th></th>" + subtypes.map(s => `<th>${esc(s)}</th>`).join("") + "</tr></thead><tbody>";
    services.forEach(sv => {
      html += `<tr><th>${esc(SERVICE_META[sv] || sv)}</th>`;
      subtypes.forEach(st => {
        const vals = cell[sv + "||" + st];
        if (!vals) { html += "<td class='muted'>—</td>"; return; }
        const a = vals.reduce((x, y) => x + y, 0) / vals.length;
        html += `<td class="${heatClass(a)}">${a.toFixed(0)}%</td>`;
      });
      html += "</tr>";
    });
    html += "</tbody></table>";
    document.getElementById("heatmap").innerHTML = html;
  }

  function renderBars(list) {
    const rows = sortRows(list).slice(0, 40);
    document.getElementById("bars-caption").textContent =
      `Первые ${rows.length} из ${list.length} (сортировка как в matrix)`;
    document.getElementById("bars").innerHTML = rows.map(e => {
      const label = `${e.method} ${e.path}`;
      return `<div class="bar-row">
        <div class="bar-label" title="${esc(label)}">${esc(label)}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.min(100, e.coverage || 0)}%"></div></div>
        <div class="num">${(e.coverage || 0).toFixed(0)}%</div></div>`;
    }).join("");
  }

  function multiOptions(values, selected) {
    return values.map(v => `<option value="${esc(v)}" ${selected.includes(v) ? "selected" : ""}>${esc(v)}</option>`).join("");
  }

  function renderFilters() {
    const src = scoredEndpoints();
    const f = state.filters;
    document.getElementById("filters").innerHTML = `
      <div class="field"><span>Service</span><select multiple id="f-svc">${multiOptions(unique(src.map(e => e.service)).sort(), f.services)}</select></div>
      <div class="field"><span>Method</span><select multiple id="f-meth">${multiOptions(unique(src.map(e => e.method)).sort(), f.methods)}</select></div>
      <div class="field"><span>Subtype</span><select multiple id="f-sub">${multiOptions(unique(src.map(e => e.subtype)).sort(), f.subtypes)}</select></div>
      <div class="field"><span>Status</span><select multiple id="f-st">${multiOptions(["full","partial","empty","exception"], f.statuses)}</select></div>
      <div class="field"><span>Coverage</span>
        <select id="f-cov">
          <option value="">все</option>
          <option value="0" ${f.coverage==="0"?"selected":""}>0%</option>
          <option value="1-33" ${f.coverage==="1-33"?"selected":""}>1–33%</option>
          <option value="34-66" ${f.coverage==="34-66"?"selected":""}>34–66%</option>
          <option value="67-99" ${f.coverage==="67-99"?"selected":""}>67–99%</option>
          <option value="100" ${f.coverage==="100"?"selected":""}>100%</option>
        </select></div>
      <div class="field"><span>Calls min</span><input type="number" id="f-cmin" min="0" value="${esc(f.callsMin)}"/></div>
      <div class="field"><span>Calls max</span><input type="number" id="f-cmax" min="0" value="${esc(f.callsMax)}"/></div>
      <div class="field" style="min-width:200px;flex:1"><span>Search</span><input type="search" id="f-q" placeholder="path / description" value="${esc(f.search)}"/></div>
      <div class="field"><span>&nbsp;</span><button type="button" id="f-clear">Clear all</button></div>`;
    const selected = sel => [...sel.selectedOptions].map(o => o.value);
    const apply = () => {
      state.filters.services = selected(document.getElementById("f-svc"));
      state.filters.methods = selected(document.getElementById("f-meth"));
      state.filters.subtypes = selected(document.getElementById("f-sub"));
      state.filters.statuses = selected(document.getElementById("f-st"));
      state.filters.coverage = document.getElementById("f-cov").value;
      state.filters.callsMin = document.getElementById("f-cmin").value;
      state.filters.callsMax = document.getElementById("f-cmax").value;
      state.filters.search = document.getElementById("f-q").value;
      state.page = 1;
      persist();
      renderMatrix();
      renderBars(matrixEndpoints());
    };
    ["f-svc","f-meth","f-sub","f-st","f-cov"].forEach(id => document.getElementById(id).addEventListener("change", apply));
    ["f-cmin","f-cmax","f-q"].forEach(id => document.getElementById(id).addEventListener("input", apply));
    document.getElementById("f-clear").addEventListener("click", () => {
      state.filters = { services: [], methods: [], subtypes: [], statuses: [], coverage: "", callsMin: "", callsMax: "", missing: [], search: "" };
      state.page = 1;
      persist();
      renderAll();
    });
    const PRESETS = [
      ["Not called this run", { kinds: ["unseen"] }],
      ["Partial", { kinds: ["partial"] }],
      ["Called, no cells", { kinds: ["empty"] }],
      ["Write queue", { kinds: ["partial", "empty"] }],
      ["Writes only", { methods: ["POST", "PUT", "PATCH", "DELETE"] }]
    ];
    document.getElementById("presets").innerHTML =
      PRESETS.map(([name], i) => `<button type="button" data-preset="${i}">${name}</button>`).join("")
      + `<button type="button" id="btn-reset-filters">Reset filters</button>`;
    const presets = PRESETS.map(([, p]) => p);
    document.getElementById("btn-reset-filters").addEventListener("click", () => {
      state.filters = { ...EMPTY_FILTERS };
      state.page = 1;
      persist();
      renderAll();
    });
    document.querySelectorAll("#presets button[data-preset]").forEach(btn => {
      btn.addEventListener("click", () => {
        const p = presets[Number(btn.getAttribute("data-preset"))];
        state.filters = { ...EMPTY_FILTERS, ...p };
        state.page = 1;
        persist();
        renderAll();
      });
    });
  }

  const COLS = [
    ["method", "Method"], ["path", "Path"], ["service", "Service"],
    ["subtype", "Subtype"], ["calls", "Calls"], ["coverage", "Cover"],
    ["status", "Status"]
  ];

  function renderHead() {
    document.getElementById("thead").innerHTML = COLS.map(([k, label]) => {
      const rule = state.sort.find(s => s.key === k);
      const cls = rule ? (rule.dir === 1 ? "sort-asc" : "sort-desc") : "";
      return `<th data-k="${k}" class="${cls}">${label}</th>`;
    }).join("") + "<th>Executed</th><th>Missing P1</th><th>Description</th>";
    document.querySelectorAll("#thead th[data-k]").forEach(th => {
      th.addEventListener("click", ev => {
        const key = th.getAttribute("data-k");
        if (ev.shiftKey) {
          const hit = state.sort.find(s => s.key === key);
          if (hit) hit.dir *= -1;
          else state.sort.push({ key, dir: 1 });
        } else {
          const hit = state.sort[0];
          state.sort = [{ key, dir: hit && hit.key === key ? -hit.dir : (key === "coverage" ? 1 : 1) }];
        }
        renderMatrix();
      });
    });
  }

  function chips(arr) {
    if (!arr || !arr.length) return `<span class="muted">—</span>`;
    return arr.map(t => `<span class="chip">${esc(t)}</span>`).join("");
  }

  function renderMatrix() {
    renderHead();
    const rows = sortRows(matrixEndpoints());
    const total = rows.length;
    const allMode = state.pageSize === "all";
    if (!allMode && total > 200 && state.pageSize > 100) {
      /* keep */
    }
    const size = allMode ? total : Number(state.pageSize);
    const pages = Math.max(1, allMode ? 1 : Math.ceil(total / size) || 1);
    if (state.page > pages) state.page = pages;
    const start = allMode ? 0 : (state.page - 1) * size;
    const slice = rows.slice(start, allMode ? total : start + size);
    document.getElementById("matrix-count").textContent = `Показано ${slice.length} из ${total} (оценка: ${scoredEndpoints().length} / ${ALL.length})`;
    const body = document.getElementById("tbody");
    body.innerHTML = slice.map((e, i) => {
      const id = start + i;
      return `<tr class="${statusClass(e.status)}" data-i="${id}">
        <td><code>${esc(e.method)}</code></td>
        <td class="path" title="клик — копировать"><code>${esc(e.path)}</code></td>
        <td>${esc(e.serviceLabel || e.service)}</td>
        <td>${esc(e.subtype)}</td>
        <td class="num">${e.calls}</td>
        <td class="num cover">${(e.coverage || 0).toFixed(0)}%</td>
        <td><span class="badge ${statusClass(e.status)}">${esc(e.status)}</span></td>
        <td>${chips(e.executed)}</td>
        <td>${chips(e.missing)}</td>
        <td class="muted">${esc(e.description)}</td>
      </tr>
      <tr class="details" data-d="${id}"><td colspan="10">
        Executed: ${chips(e.executed)} · Missing P1: ${chips(e.missing)} · ${esc(e.description || "нет описания")}
      </td></tr>`;
    }).join("");
    body.querySelectorAll("tr[data-i]").forEach(tr => {
      tr.addEventListener("click", ev => {
        if (ev.target.closest(".path")) {
          const code = tr.querySelector(".path code");
          if (code) navigator.clipboard?.writeText(code.textContent || "");
          return;
        }
        const id = tr.getAttribute("data-i");
        document.querySelectorAll(".details").forEach(d => d.classList.toggle("open", d.getAttribute("data-d") === id && !d.classList.contains("open")));
      });
    });
    const sizes = [25, 50, 100, "all"];
    document.getElementById("pager").innerHTML = `
      <span>Страница ${state.page} / ${pages}</span>
      <button type="button" id="pg-prev" ${state.page<=1?"disabled":""}>←</button>
      <button type="button" id="pg-next" ${state.page>=pages?"disabled":""}>→</button>
      <label>Jump <input type="number" id="pg-jump" min="1" max="${pages}" value="${state.page}" style="width:4.2rem"/></label>
      <label>Rows <select id="pg-size">${sizes.map(s => `<option value="${s}" ${String(s)===String(state.pageSize)?"selected":""}>${s==="all"?"все":s}</option>`).join("")}</select></label>`;
    document.getElementById("pg-prev").onclick = () => { state.page--; renderMatrix(); };
    document.getElementById("pg-next").onclick = () => { state.page++; renderMatrix(); };
    document.getElementById("pg-jump").onchange = ev => { state.page = Math.max(1, Math.min(pages, Number(ev.target.value)||1)); renderMatrix(); };
    document.getElementById("pg-size").onchange = ev => {
      const v = ev.target.value;
      if (v === "all" && total > 200 && !confirm("Показать все " + total + " строк?")) {
        ev.target.value = String(state.pageSize);
        return;
      }
      state.pageSize = v === "all" ? "all" : Number(v);
      state.page = 1;
      persist();
      renderMatrix();
    };
  }

  function renderDashboard() {
    const scored = scoredEndpoints();
    renderStats();
    renderCards("service-cards", groupServices(scored), key => {
      state.filters.services = [key];
      state.page = 1;
      persist();
      renderAll();
      document.querySelector("h2 + .legend")?.scrollIntoView({ behavior: "smooth" });
      document.getElementById("matrix-count")?.scrollIntoView({ behavior: "smooth" });
    });
    renderCards("subtype-cards", groupSubtypes(scored), key => {
      state.filters.subtypes = [key];
      state.page = 1;
      persist();
      renderAll();
    });
    renderCards("method-cards", groupMethods(scored), key => {
      state.filters.methods = [key];
      state.page = 1;
      persist();
      renderAll();
    });
    renderMissing(scored);
    renderHeatmap(scored);
    renderBars(matrixEndpoints());
  }

  function renderAll() {
    renderServiceChecks();
    renderDashboard();
    renderFilters();
    renderMatrix();
  }

  function bind() {
    document.getElementById("service-checks").addEventListener("change", ev => {
      const cb = ev.target.closest("input[data-svc]");
      if (!cb) return;
      if (cb.checked) state.selected.add(cb.getAttribute("data-svc"));
      else state.selected.delete(cb.getAttribute("data-svc"));
      persist();
      state.page = 1;
      renderAll();
    });
    document.getElementById("btn-recalc").addEventListener("click", () => {
      state.page = 1;
      renderAll();
    });
    document.getElementById("btn-reset-svc").addEventListener("click", () => {
      state.selected = new Set(Object.keys(SERVICE_META));
      persist();
      state.page = 1;
      renderAll();
    });
    document.getElementById("btn-theme").addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      store.set(LS_THEME, next);
    });
    document.getElementById("btn-help").addEventListener("click", () => {
      document.getElementById("help").classList.toggle("open");
    });
    document.getElementById("btn-csv").addEventListener("click", () => downloadCsv(sortRows(matrixEndpoints())));
    document.getElementById("btn-json").addEventListener("click", () => {
      const blob = new Blob([JSON.stringify({ ...DATA, endpoints: matrixEndpoints(), filtered: true }, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "coverage.filtered.json";
      a.click();
    });
    document.addEventListener("keydown", ev => {
      if (ev.key === "/" && ev.target.tagName !== "INPUT" && ev.target.tagName !== "SELECT" && ev.target.tagName !== "TEXTAREA") {
        ev.preventDefault();
        document.getElementById("f-q")?.focus();
      }
      if (ev.key === "Escape") {
        state.filters = { services: [], methods: [], subtypes: [], statuses: [], coverage: "", callsMin: "", callsMax: "", missing: [], search: "" };
        persist();
        renderAll();
      }
    });
  }

  function downloadCsv(rows) {
    const header = ["method","path","service","subtype","calls","coverage","status","executed","missing","description"];
    const lines = [header.join(",")];
    rows.forEach(e => {
      const vals = [
        e.method, e.path, e.service, e.subtype, e.calls, e.coverage, e.status,
        (e.executed || []).join("|"), (e.missing || []).join("|"), e.description || ""
      ].map(v => `"${String(v).replace(/"/g, '""')}"`);
      lines.push(vals.join(","));
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" }));
    a.download = "coverage.csv";
    a.click();
  }

  restore();
  bind();
  renderAll();
})();
</script>
</body>
</html>
"""
