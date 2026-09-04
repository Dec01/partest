---
title: Coverage honesty — when the number lies
status: current
verified: 2026-09-04
sources: [partest/call_storage.py, partest/coverage.py, partest/reports/analyzer.py]
audience: agent
ships_in_wheel: true
---

# Coverage honesty

A coverage percentage is only useful if it fails loudly rather than quietly reading low or high.
Three ways the number currently lies, and what to do about each.

## 1. Parallel runs under pytest-xdist

`call_storage` is **per process** (`partest/call_storage.py`). Each xdist worker counts only its
own calls, and `test_zorro` runs on one worker — so it reports that worker's slice as if it were
the whole suite.

Measured on a live suite: `pytest -n 3` produced average 25.7% and 58 endpoints marked unseen,
while the same suite serial was green.

**Until worker merging lands: do not run `zorro` under `-n`.** Run the
coverage pass serially, or merge shards yourself with `dump_storage` / `merge_storage` from a
`pytest_sessionfinish` hook — see [[howto/enterprise]].

## 2. "Unseen" vs "no tests"

Zero recorded calls for an endpoint has two very different causes: no test exists, or tests exist
but did not run in this selection (`-k`, marker filter, failed fixture). Today both render the
same. A planned change splits them into `unseen / empty / partial / full / exception`.

Practical consequence: a low number after a filtered run is not a coverage regression. Compare
only full runs; use `python -m partest.reports compare` on two payloads rather than eyeballing
percentages.

## 3. Unmatched paths

Coverage matches a concrete request URL against the OpenAPI path template. Nested templates such
as `/parents/{parentId}/items/{id}` can fail to match and land in "unmatched", which reads as
missing coverage while the test is fine.

Workarounds today: pass `defining_url` equal to the OpenAPI template, or use `add_url*` so the
tracker rewrites concrete values back to `{param}`. A proper resolver is planned.

## What to trust

| Question | Trust |
|---|---|
| Did this endpoint get its required P1 cases? | `report.endpoints[*].missing_p1` |
| Did the suite get better or worse? | `compare` of two full-run payloads |
| Single average percentage from a filtered or parallel run | no |

Related: [[concepts/methodology]] · [[howto/coverage-html]] · [[howto/enterprise]]
