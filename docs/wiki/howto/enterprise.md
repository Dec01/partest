---
title: Enterprise notes — shared client, retries, redaction, xdist
status: current
verified: 2026-09-04
sources: [partest/http_retry.py, partest/redact.py, partest/call_storage.py, partest/client.py]
audience: user
ships_in_wheel: true
---

# Enterprise notes — shared client, retries, redaction, xdist

## Shared httpx client

```python
async with ApiClient(domain, shared_client=True) as api:
    await api.make_request("GET", "/health", expected_status_code=200)

# or inject
async with httpx.AsyncClient(verify=False) as hx:
    api = ApiClient(domain, client=hx)
    ...
# external client is not closed by ApiClient
```

Default remains **ephemeral client per request** (backward compatible).

## Retries

Default: **no retries** (tests must be deterministic).

```python
api = ApiClient(domain, max_retries=2, retry_statuses=(429, 502, 503), retry_backoff=0.5)
await api.make_request("GET", "/slow", max_retries=3)  # per-call override
```

Retries apply only to listed statuses and (optionally) network errors.  
Business 4xx are **not** retried.

## Secret redaction

```python
from partest.redact import redact_headers, redact_mapping, mask_secret
```

Used by status mismatch messages and `partest.reporting.attach_request`.  
Body keys like `password`, `token`, `access_token`, `client_secret` are masked.

## Status hint locale

```python
from partest.reporting import set_status_hints_locale
set_status_hints_locale("ru")  # or "en"
```

## GraphQL

```python
await api.graphql("{ me { id } }", variables=None, endpoint="/graphql")
# same as make_request(..., graphql_query=..., graphql_variables=...)
```

## Coverage under pytest-xdist

Each xdist worker is a **separate process** → separate `call_storage`.

```python
# conftest.py (worker)
import os
from pathlib import Path
from partest.call_storage import dump_storage_file

def pytest_sessionfinish(session, exitstatus):
    worker = os.getenv("PYTEST_XDIST_WORKER")  # gw0, gw1, …
    if worker:
        dump_storage_file(Path("reports") / f"coverage_{worker}.json")

# controller / local merge job
from partest.call_storage import merge_storage_files, reset_storage
from pathlib import Path
reset_storage()
merge_storage_files(Path("reports").glob("coverage_gw*.json"))
# then zorro() / HTML analyzer on merged storage
```

Within one process, `record_call` is **thread-locked**.

## Soft Allure dependency

`ApiClient` steps and `partest.reporting.attach_*` degrade gracefully when
`allure` is not installed (no-op attaches / plain steps).
