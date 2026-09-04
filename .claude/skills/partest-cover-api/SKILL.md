---
name: partest-cover-api
description: >
  Cover an API with partest tests: classify each operation into a method subtype, pick the
  required P1 test cases from the methodology matrix, implement them with ApiClient, and close
  missing_p1 from the coverage report. Use when writing or extending API autotests, raising
  coverage, choosing test-case types, or writing transport IncorrectBody cases.
---

# Covering an API with partest

## When to use this

- Writing new API tests, or extending an existing partest suite
- Deciding which test cases an endpoint actually needs
- Raising coverage against `missing_p1` from the report
- Writing transport-level IncorrectBody (raw body / bad Content-Type)

**Not this skill:** generating a new project → `partest-scaffold`. Publishing a version →
`partest-release`. Working on the library itself → `AGENTS.md` + `docs/wiki/howto/contribute.md`.

## Hard rules

1. **All suite HTTP goes through `ApiClient`.** Raw `httpx` calls are invisible to coverage —
   they count as no test at all.
2. **Always pass `type=`.** Inference is high-confidence only for 405, 404 and a broken raw body.
   Everything else — permissions, new/update object, elements, extra data, env, benchmark — is
   ambiguous on the wire.
3. **Canonical names:** `type=types.request_default`, not the string `"type_default"`.
4. **Coverage means the required P1 set exists**, not "a test file exists" or "the endpoint was
   called once".
5. **Create/update endpoints need a vertical case** (`request_new_object` /
   `request_update_object`), not just a Default on seed data.
6. **Assertion depth: status → `validate_model` → values.** Status-only does not count for
   Default, Elements or Benchmark.
7. **Domain stays in the project**: entity paths, DTO, roles, PROFILES, SQL cleanup.
8. **Only delete test data carrying the marker** (`marked_name` / `TEST_MARKER`).

## Step 1 — wire the project

```text
confpartest.py            # swagger_files: {"service": ["local"|"url", "<path or url>"]}
conftest.py               # domain, api_client, reset_storage()
src/tests/test_zorro.py   # calls zorro() last
```

```python
from partest import ApiClient, TypesTestCases, reset_storage
from partest.zorro_report import zorro
```

## Step 2 — classify the operation (axis A)

| Pattern | Subtype |
|---|---|
| GET collection, no id | `get_list_objects` |
| GET `.../{id}` | `get_dynamic_object` |
| GET static catalog / enums | `get_static_object` |
| GET `.../{parent}/{id}/children` | `get_by_parent` |
| GET `.../me` / `/self` | `get_by_self` |
| POST create | `post_create_object` |
| POST multipart / upload | `post_upload_file` |
| POST create under a parent | `post_create_object_to_object` |
| POST filter/sort over a list | `post_filter_sort_list` |
| PUT / PATCH | `put_object` / `patch_object` / `patch_elem_on_object` |
| DELETE | `delete_object` (+ soft / physical / blocked when known) |
| non-CRUD verb as last segment | `action` |

The library classifier is `partest.methodology.classify_endpoint`. It is a heuristic — check its
answer on unusual paths rather than trusting it silently.

## Step 3 — required cases (axis A × B)

Read `partest/methodology/matrix.py`, or `references/methodology-cheatsheet.md` for the compact
form. Do not memorize the matrix from any document — the code is the source of truth.

Rough shape: GET STATIC → Default + Benchmark · GET DYNAMIC → Default + Permissions + NotFound ·
GET LIST → Default + Permissions · POST CREATE → Default, Permissions, NewObject, IncorrectBody,
Elements, ExtraData · PUT/PATCH → same plus UpdateObject and NotFound · DELETE → Default,
Permissions, NotFound.

## Step 4 — implement

```python
types = TypesTestCases

await api_client.make_request(
    "GET",
    "/items/{id}",
    add_url1=f"/{item_id}",
    defining_url="/items/{id}",      # OpenAPI template — makes coverage match
    expected_status_code=200,
    validate_model=ItemValidation,
    type=types.request_default,
)
```

Path matching: prefer `defining_url` equal to the OpenAPI path template when parameters are
dynamic, or use `add_url*` so the tracker rewrites concrete values back to `{param}`. Nested
templates are the known weak spot — see `docs/wiki/concepts/coverage-honesty.md`.

## Step 5 — transport IncorrectBody

```python
await api_client.make_request(
    "POST", "/items",
    content=b'{"a":',
    content_type="application/json",
    expected_status_code=(400, 415),   # multi-status is supported
    type=types.request_incorrect_body,
)
```

Ready-made set: `from partest.validation import RAW_INCORRECT_BODY_CASES, assert_raw_incorrect_body`.

## Step 6 — measure

```python
report = zorro()                       # Allure + simple HTML
from partest.reports import zorro_enhanced
zorro_enhanced()                       # interactive HTML + coverage.json
# report.endpoints[*].missing_p1 → the backlog for the next cases
```

CLI without a stand: `python -m partest.reports compare|badge|stubs|render`.

**Do not run the coverage pass under `pytest -n`** — `call_storage` is per process, and the
number will be wrong. Run it serially until shard merging lands.

Order of work: endpoint impact first (auth, money, PII), then P1 depth. Do not polish P3 on a
low-risk catalog before P1 on a critical write.

## Imports you will need

```python
from partest import (
    ApiClient, TrackingApiClient, CreatedRegistry, TokenManager,
    BaseRequestBody, Config, HeadersBind, TypesTestCases, marked_name,
    RiskProfile, CollectionsManager, SecHttp, build_tampered_set,
)
from partest.validation import BaseResponseValidator, ProblemDetailValidation
import partest.reporting as ah
from partest.env import load_project_env, require_env
```

`TokenManager` takes an injected `credentials_provider(role) -> (user, password)` — roles and
credentials stay in the project. The pytest plugin enriches Allure titles automatically; disable
it with `PARTEST_PYTEST_PLUGIN=0` or `pytest_plugin = False` if the project owns Allure hooks.

## Before claiming an endpoint is covered

- [ ] Subtype identified and sanity-checked
- [ ] Every P1 case for that subtype present with the correct `type=`
- [ ] Vertical case where create/update exists
- [ ] Status + schema validation on positive cases
- [ ] Value assertions for Default / Benchmark / Elements where data is deterministic
- [ ] Created resources cleaned up (tracking registry), test data carries the marker
- [ ] `missing_p1` empty for that endpoint in a **serial** run

## Known limits

- Coverage under pytest-xdist is unreliable until shard merging ships.
- Nested OpenAPI templates can land in "unmatched" even when the test is correct.
- The classifier can mis-read unusual paths; an explicit subtype override is not available yet.
