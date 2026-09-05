<!-- Part of the partest package: generated documentation, not hand-written.
     Read it with `python -m partest.docs`. Local edits are lost on upgrade. -->

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

See [Migration between partest versions](howto-migration.md) — disable if you already attach titles.

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

See [Interactive coverage report and CLI](howto-coverage-html.md).

