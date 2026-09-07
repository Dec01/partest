---
title: Interactive coverage report and CLI
status: current
verified: 2026-09-07
sources: [partest/reports/__init__.py, partest/reports/interactive_html.py, partest/reports/writer.py, partest/reports/services.py, partest/reports/__main__.py]
audience: user
ships_in_wheel: true
---

# Interactive coverage report and CLI

Project-agnostic reporting layer on top of `partest.reports.analyzer`.

Analysis stays in `partest.reports.analyzer` (methodology P1).  
This package adds JSON payload, interactive HTML, compare / badge / stubs / history.

## Write from a suite

```python
from partest.reports import ServiceMap, zorro_enhanced

# optional consumer map (prefixes / tags). Omit → first segment after /api/v1/
smap = ServiceMap.load("src/api/resources/coverage/services.yaml")
zorro_enhanced(service_map=smap)
```

Or from an existing `CoverageReport`:

```python
from partest.reports import write_enhanced_report
write_enhanced_report(report, html_path="coverage_report.html", json_path="coverage.json")
```

`zorro()` still writes the **simple** HTML. Use `zorro_enhanced()` for the interactive vitrine.

## CLI (no stand)

```bash
python -m partest.reports render --json coverage.json --html coverage_report.html
python -m partest.reports compare --a old.json --b coverage.json
python -m partest.reports badge --json coverage.json --out coverage.svg
python -m partest.reports stubs --json coverage.json --out coverage_stubs.py
python -m partest.reports history-append --json coverage.json --dir coverage_history
```

Stubs use `type=types.request_*` (never `"type_default"`).

The history helpers are importable directly, for a pipeline that keeps its own snapshots:

```python
from partest.reports import append_snapshot, list_snapshots, previous_snapshot, prune_snapshots
```

## Service map (consumer)

YAML example — **stays in the suite project**:

```yaml
api_prefixes: ["/api/v1/"]
services:
  items:
    label: Items
    prefixes: ["/api/v1/items"]
tags:
  Item Controller: items
```

Longest prefix wins. Unknown path → first segment after the api prefix.

## HTML

Filters (service / method / subtype / status / missing P1 / search), heatmap,
CSV/JSON export of the current view, light/dark. No product names in the library template.

## Comparing two runs

```bash
python -m partest.reports compare --a previous.json --b coverage.json
python -m partest.reports compare --a previous.json --b coverage.json --strict
```

Coverage falls for two different reasons, and only one of them is a regression. An endpoint that
was covered before and simply was not called this time is reported under `not_run`, never under
`regressed`, and its `missing` list is ignored — it is an artefact of not running.

The result carries `comparable` and `warnings`. A run made with parallel workers that were not
merged, or one where a fifth of the endpoints went untouched, is flagged as not comparable;
`--strict` turns that into exit code 2 so a pipeline does not alarm on a partial run or, worse,
stay quiet about a real loss hidden behind one.

Related: [[concepts/coverage-honesty]]

## Reading the page honestly

The report opens with a red banner when the run behind it does not describe the whole suite —
parallel workers that were never merged, or a large share of endpoints never called. Do not
compare an average from such a run with anything.

Counters are clickable: **Not called this run** filters the matrix down to exactly the endpoints
nothing touched, which is the difference between "we have no tests here" and "this selection did
not reach it". `Reset filters` clears everything, including the presets.

Latency appears once calls carry timings: average and p95 in the header, a **p95 ms** column in
the matrix coloured by the usual thresholds (under 100 fine, under 300 worth a look, above that
bad), and per-endpoint detail in the JSON under `timing`. Endpoints with no measurement sort to
the bottom whichever way you sort that column — "unknown" is neither fast nor slow.

The current filter lives in the URL, so a filtered view is a link you can send: click
**Not called this run**, copy the address, and the person who opens it sees the same list. A link
wins over whatever the browser remembered locally.

**Markdown** exports the current view as a table ready to paste into a ticket, with the run caveat
appended when the numbers came from a partial or unmerged run — the table travels, so the warning
has to travel with it.

Filters persist between visits where the browser allows it; opened from a restricted context the
page still renders, it simply stops remembering.
