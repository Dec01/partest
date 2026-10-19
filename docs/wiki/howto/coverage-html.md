---
title: Interactive coverage report and CLI
status: current
verified: 2026-10-19
sources: [partest/reports/__init__.py, partest/reports/validate.py, partest/reports/interactive_html.py, partest/reports/writer.py, partest/reports/services.py, partest/reports/__main__.py, partest/reports/payload.py, partest/reports/badge.py, partest/reports/compare.py, partest/reports/_rules.py, partest/reports/stubs.py]
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

A file that is not a JSON object — a list, broken JSON, a missing file — is refused with
`error: <file>: …` on stderr and exit code **1**, and so is, for `stubs` and `history-append`, a
document whose `endpoints` is not a list of objects (for the history also `meta` or `summary`
that is not an object) — no stubs or snapshot are written from it; an output that cannot be
written is exit code 1 too. Exit code **2** is `compare --strict` on a pair that is not
comparable, or a command-line argument error (argparse). `history-append` stores `NaN` /
`Infinity` from its input as `null`. `stubs` writes method and path
as Python string literals and skips a missing type that is not a plain name, so nothing in the
file becomes code in the generated module. The readers take other people's files: a value of
the wrong type in a row or in `meta` is read as absent, `NaN` / `Infinity` are shown as "no
value", and names from the file (services, subtypes, paths) are shown as text, never as markup.

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
merged, one where a fifth of the endpoints went untouched, or two runs that selected different
opt-in marker sets (`meta.selection.optin`), is flagged as not comparable (when only one
carries the opt-in record, a soft entry in `notes` says comparability cannot be confirmed);
`--strict` turns that into exit code 2 (an input that cannot be read is exit code 1, see
above) so a pipeline does not alarm on a partial run or, worse,
stay quiet about a real loss hidden behind one.
The CLI prints `warnings` and `notes` to stderr (`warning: …`, `note: …`), so piping the JSON
stays clean. Notes never change the exit code. The opt-in part of the verdict alone, for a
reader of `coverage.json` that does not need the rest: `partest.reports.optin_comparable(old,
new)` → `(True, [])`, `(False, ["slow: off → env"])` or `(None, [])` when either payload has no
opt-in record.

A run with no endpoints has no average (see below): when either payload says
`"summary": {"avg": null}`, `old_avg` / `new_avg` is `null` on that side, `avg_delta` and
`coverage_delta` are `null` rather than the other run's whole average, and a warning names the
run that measured nothing — so the pair is not `comparable`; `compare --strict` exits with
code 2. An older snapshot that wrote `0.0` for a run with no endpoints (`summary.endpoints` is
`0`, or, without that count, `endpoints` is an empty list — a numeric count decides) is read the same way — not measured — as the validator
reads it: otherwise an empty 2.6 baseline would turn the next run's whole average into a delta
of a pair called comparable. A `0.0` with endpoints is a measured zero; a payload with no
`summary.avg` at all reads as `0.0`, as before. When the two files average under different
rules for `exception` endpoints, the older one is recomputed from its rows first (`avg_recomputed`)
— see "Exception endpoints and `meta.avgRule`" below; the change in depth is `depth_delta`.

## A run with no endpoints

`summary.avg` and `summary.avgAll` are `float | null`. A run that collected no
endpoints — a fixture that failed before the specification was read, an unmerged worker shard,
an empty specification — writes `null` there, as it writes `null` into `meta.unseenRatio`: an
average over nothing is not a measurement, and `0.0` read as "nothing is covered". A measured
zero (endpoints present, none covered) is still `0.0`. `avgCoverage` of a service, subtype or
method row is not `null` for this reason — a row exists only because an endpoint is in it — but
it is `null` when every endpoint in it is `exception` (below).

| Reader | On `null` |
|---|---|
| `python -m partest.reports badge` / `badge_from_payload` | a grey `n/a` badge, not a red `0.0%` — also for an older snapshot's `0.0` with no endpoints |
| `compare` | `null` delta and a warning, as above |
| the HTML page | `—` instead of a percentage |
| `validate_coverage_payload` | `null` is accepted only with zero endpoints (under `meta.avgRule` 2, also with `exception` rows only); `0.0` with zero endpoints is a `DATED` note (how earlier releases wrote it — see `CHANGELOG.md`), any other number there is an error |

A reader of `coverage.json` that does arithmetic on `summary.avg` checks for `null` first —
explicitly: in JavaScript `null < 60` is `true` and `null * 1` is `0`, in `jq` `null < 60` is
`true` as well, so a quality gate written `avg < 60` passes or fails an unmeasured run by
accident. Test `avg == null` before comparing.

Related: [[concepts/coverage-honesty]]

## Exception endpoints and `meta.avgRule`

An endpoint on which a call recorded an exception type — `health`, or a type listed in
`test_types_exception` — has `status` and `kind` `exception` and `coverage` 100. Such
a row is **counted but not averaged**: it is in `summary.exception`, `summary.endpoints` and a
service's `exception` and `totalEndpoints`, and it is not in `summary.avg` / `avgAll`,
`avgCoverage` of a service, subtype or method, a heatmap cell's `avg`, or a service's `covered`
(`full + partial`). The rows that are averaged are counted in `scored` — in `summary` and in
every service, subtype and method row (`scored = totalEndpoints − exception`); `covered` is out
of `scored`, not out of `totalEndpoints`. A set of `exception` rows only — a whole run, a
service of health probes — has no average: `null`, shown as `—` (the service sorts last), with
`scored: 0`.

`meta.avgRule` says which rule the averages of a file follow:

| `meta.avgRule` | Meaning | Read by this package |
|---|---|---|
| absent | rule 1 — every earlier release: an `exception` row counts as 100 % inside every average and in `covered` | as rule 1; the validator notes it as `DATED` |
| `1` | the same, written explicitly | as rule 1 |
| `2` | `exception` rows outside every average and `covered` — what this release writes | as written |
| an integer above `2` | a rule newer than this package | not recomputed: the validator notes it as `NEWER`, `compare` warns, the HTML page shows the file's own `summary.avg` |
| anything else (`0`, `"2"`, `2.0`, `true`, `null`) | not a rule | an error in the validator; `compare` warns, as for an unknown rule |

The HTML page reads the key, so a page rendered from an older file shows the average that file
recorded.

`compare` puts both averages under one rule before it subtracts them. A file without the key
that has `exception` rows gets its average **recomputed from its own rows** without them — by
the same code that writes the current format; `old_avg` / `new_avg` carry the recomputed
number, `avg_recomputed` says which side and both values (`{"side", "recorded",
"recomputed"}`), a line in `notes` says so, and the pair stays comparable. Only when that file's
rows cannot be used — `summary.endpoints` or its status counts (`full`, `partial`, `empty`,
`exception`) disagree with the list, or a row carries a value the format does not write — is
there nothing to recompute from: a warning, and the pair is not `comparable`. A file without `exception` rows
gives the same number under both rules, and nothing is added. A rule this package does not
know is never guessed at: a warning, not `comparable`.

## Depth (axis C)

The percentage scores axes A and B: whether a call of each required `type=` reached the
endpoint. How deep those calls checked is a separate field, so the percentage does not move:

```json
"depth": {"cells": 3, "status": 3, "schema": 1, "values": null}
```

Per endpoint: of the required cells this run filled, `status` — in how many some call of that
type **asked for** a status check (`expected_status_code` passed), `schema` — in how many for a
schema check on top of it (`validate_model` passed too; a model without a status check is not
validated by `make_request`, and is not counted). The flags are the call's arguments, recorded
before the request is sent: what was asked, not what passed. A cell counts at its deepest call.
`values` is `null`: value asserts are the suite's own code and are not measured. `depth` is
`null` for an endpoint with no filled required cell, for an `exception` row, and for calls
recorded without the flags — by hand, from an older storage dump, or through a tracked function
with no `expected_status_code` parameter (its depth is "not measured", not a measured zero).

`summary.depth` pools the cells of the run (outside `exception`) and adds the shares:

```json
"depth": {"cells": 120, "status": 114, "schema": 41, "values": null, "statusPct": 95.0, "schemaPct": 34.17}
```

`null` when no cell was measured. The HTML page shows the two shares in the header ("Cells:
status asked", "Cells: schema asked", over the selected services) and a Depth column in the
matrix; `compare` gives `depth_delta` — `{"statusPct", "schemaPct"}` in points, `null` when either
file has no `summary.depth`. Whether a cell is deep enough is the methodology's question
([[concepts/methodology]]): status-only is not enough for Default, Elements or Benchmark.

## Checking a document against the format

`coverage.json` is an observable interface, and some consumers **write** it as well as read it —
a fixture generator, a demonstration set, an importer that synthesises a run. Such a producer
imitates the format by hand, and until now it had nothing to check itself against.

```python
from partest.reports import Severity, validate_coverage_payload

problems = validate_coverage_payload(json.loads(path.read_text("utf-8")))
errors = [p for p in problems if p.severity is Severity.ERROR]
assert not errors, "\n".join(str(p) for p in errors)
```

It returns findings, raises nothing, and prints nothing: what a divergence costs is the caller's
decision. Beyond keys and types it checks the agreements a hand-written producer gets wrong —
`unseenRatio`, `summary.avg` and `summary.avgAll` are `float | null` and `null` belongs to
exactly one state (no endpoints; under `meta.avgRule` 2, no endpoint outside `exception`),
`kind` must agree with `calls`, `callsTotal` must agree with the rows under it, and `depth`
must be consistent — `cells` ≥ `status` ≥ `schema`, `null` rather than a zero-cell object, none
on an `exception` row or a row without calls, `summary.depth` the sum of the rows with its
shares; `summary.full` / `partial` / `empty` / `exception` must agree with the rows' statuses
(`empty` takes any other status). A file older than `meta.avgRule` or `summary.depth` gets a
`DATED` note for each; a
file whose rows carry `depth` and whose summary does not is an error. A rule newer than this
package (`meta.avgRule` above 2) is `Severity.NEWER` — not wrong, not checkable here. Numbers a
float cannot hold (`Infinity`, `NaN`, an integer of hundreds of digits) are errors, not
exceptions.

**`Severity.DATED` is not a small error.** It means the document predates a field: internally
consistent, simply older. Artefacts outlive releases, and a check that fails on last month's file
is a check people switch off. Errors and dated notes come back in one list and are separated by
`Problem.severity`.

The rule it exists for, stated once: `status` is about methodology (all required cells, some,
none), `kind` is about what *this* run observed, and `unseen` — never called here — is not
`empty` — called, no required cell executed. A producer that copies one into the other passes
every type check and lies in the only field that can say "we did not look". That is not a
hypothetical; it is where this function came from.

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
