---
title: Reporting cookbook — checks, steps, attaches
status: current
verified: 2026-09-24
sources: [partest/reporting/__init__.py, partest/reporting/checks.py, partest/reporting/measured.py, partest/reporting/steps.py, partest/reporting/attach.py, partest/reporting/instrument.py]
audience: user
ships_in_wheel: true
---

# Reporting cookbook (`partest.reporting` + `partest.reports`)

Import as Allure helper façade::

```python
import partest.reporting as ah
```

Allure is a **soft dependency** for attach/step APIs: when `allure` is not
installed, steps degrade or skip attaches (instrument path still runs HTTP).

## Checks

| Helper | Purpose |
|--------|---------|
| `check_eq` / `check_ne` | equality |
| `check_true` / `check_false` | booleans |
| `check_in` / `check_not_in` / `check_in_list` | membership |
| `check_len` / `check_not_empty` / `check_is_none` | size/null |
| `check_lt` / `check_between` | numeric ranges |
| `check_isinstance` / `check_not_startswith` | type/prefix |
| `check_status` / `check_status_in` | HTTP status from response/int |

All checks attach `check:field` JSON when Allure is available and raise
`AssertionError` with a short message on failure.

```python
ah.check_eq(body["name"], "Acme", field="name")
ah.check_status_in(response_status, (200, 201), field="status")
```

## The third outcome: «not measured»

Those seventeen checks have two outcomes, and two outcomes are enough only while there is
something to measure. When the data the assertion reads was never collected — the file is
absent, the broker is unreachable, the sample is empty — the comparison still runs and
still passes, and the report shows a green nobody earned. Aggregates are the sharp case: a
difference, a share or a mean over an empty sample is `0` or `1` **by construction**, so
the check guarding it cannot fail even in principle.

`check_measured` runs an assertion **only** under a stated premise of measurability, and
otherwise records that the assertion was not made and why.

```python
ah.check_measured(
    ah.measurable(samples, what="latency samples"),   # premise: positional, required
    lambda: ah.check_lt(mean(samples), 200, field="mean latency"),
    what="mean latency under the budget",
)
```

An aggregate over two samples needs both, and premises combine with `&`:

```python
ah.check_measured(
    ah.measurable(before, what="baseline") & ah.measurable(after, what="current"),
    lambda: ah.check_eq(sum(after.values()) - sum(before.values()), 0, field="growth"),
    what="growth against the baseline",
)
```

A plain boolean works too, and then the reason is **mandatory** — the third outcome
without a reason reads like a pass:

```python
ah.check_measured(
    bundle_path.exists(),
    lambda: ah.check_not_in("http://", bundle_path.read_text(), field="offline bundle"),
    what="the bundle is self-contained",
    reason="the bundle was not built in this environment — there was nothing to scan",
)
```

| Helper | Purpose |
|--------|---------|
| `check_measured(premise, assertion, *, what, reason="")` | assert under a premise; returns `True` when the assertion actually ran |
| `measurable(sample, *, what, min_size=1)` | premise «the sample exists and is big enough»; `None` and «too few» get different reasons |
| `Premise(ok, reason, what)` | a premise by hand; one that does **not** hold cannot be built without a reason |
| `mark_not_measured(*, what, reason)` | the third outcome with no assertion to run at all |
| `not_measured_records()` / `reset_not_measured()` | the run's ledger of assertions never made |
| `NotMeasuredWarning` | the warning category raised for each of them |

How the three outcomes look apart:

| Outcome | Allure step | Attachment | Elsewhere |
|---|---|---|---|
| measured, passed | `Measured: <what>` (green) | `check:<field>` with `passed: true` | — |
| measured, failed | `Measured: <what>` (red) | `check:<field>` with `passed: false`, `failure_details` | the test fails |
| **not measured** | `NOT MEASURED: <what> — <reason>` | `not_measured:<what>` with `passed: null` | test tagged `not-measured`, `NotMeasuredWarning`, a `NOT MEASURED` section in the pytest summary |

It is **not** `pytest.skip`: the test goes on, the other assertions in it are made as
usual, and only the unmeasurable one is set aside. It does not fail the run either — an
absent sample is not a defect of the service under test. A project that wants the stricter
reading asks for it:

```ini
[pytest]
filterwarnings = error::partest.reporting.NotMeasuredWarning
```

## Steps & templates

```python
with ah.step("Prepare seed"):
    ...
with ah.step_http("POST", "/items", expected=201):
    ...
ah.step_as_role("admin")  # context label helper
```

| Template | Use |
|----------|-----|
| `StepTemplates.http(...)` | HTTP step titles |
| `ErrorTemplates.status(...)` | status mismatch text |
| `format_http_status_failure(...)` | rich 4xx/5xx message |
| `DescriptionTemplates` | Allure description blocks |
| `Severity` | severity constants |

## Attaches

```python
ah.attach_request(method="POST", path="/x", headers=h, body=body)
ah.attach_response(status=201, body=result)
ah.attach_json("seed", seed)
ah.attach_failure(msg, exc)
```

Authorization headers are **masked** in `attach_request`.

## Testcase decorator

```python
@ah.testcase(title="Create item default", story="RequestDefault", severity="normal")
async def test_create(...):
    ...
```

## Instrumentation

```python
from partest.reporting import instrumented_make_request
result = await instrumented_make_request(api_client.make_request, "GET", "/health")
```

`TrackingApiClient(instrument=True)` wraps this automatically.

## Conflict provider (domain stays consumer)

```python
# consumer
def explain_entity_conflict(response_body) -> str:
    ...

# in test after 409
ah.attach_text("conflict_hint", explain_entity_conflict(body))
```

Library does **not** embed product 409 rules.

## Pytest plugin

See [[howto/migration]] — disable if you already attach titles.

## Coverage extras (`partest.reports`)

Interactive HTML + JSON + CLI. Service map is **injected** (consumer YAML); library fallback = first path segment after `/api/` / `/api/v1/`.

```python
from partest.reports import ServiceMap, zorro_enhanced, write_enhanced_report

smap = ServiceMap.from_dict({
    "api_prefixes": ["/api/v1/"],
    "services": {"items": {"label": "Items", "prefixes": ["/api/v1/items"]}},
})
zorro_enhanced(service_map=smap)  # coverage_report.html + coverage.json
```

```bash
python -m partest.reports render --json coverage.json --html coverage_report.html
python -m partest.reports compare --a old.json --b coverage.json
python -m partest.reports badge --json coverage.json --out coverage.svg
python -m partest.reports stubs --json coverage.json --out coverage_stubs.py
python -m partest.reports history-append --json coverage.json --dir coverage_history
```

See [[howto/coverage-html]].

