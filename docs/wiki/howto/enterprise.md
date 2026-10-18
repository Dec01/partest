---
title: Enterprise notes — shared client, retries, redaction, xdist
status: current
verified: 2026-10-18
sources: [partest/http_retry.py, partest/redact.py, partest/call_storage.py, partest/client.py, partest/tls.py, partest/http/client.py, partest/utils/logger.py, partest/reporting/attach.py, partest/reporting/instrument.py, partest/utils/checking.py]
audience: user
ships_in_wheel: true
---

# Enterprise notes — shared client, retries, redaction, xdist

## Shared httpx client

```python
async with ApiClient(domain, shared_client=True) as api:
    await api.make_request("GET", "/health", expected_status_code=200)

# or inject
async with httpx.AsyncClient() as hx:
    api = ApiClient(domain, client=hx)
    ...
# external client is not closed by ApiClient
```

**An injected client brings its own TLS setting, and partest cannot see it.** Whatever you
passed to `httpx.AsyncClient(...)` is what the requests use; `partest/tls.py`, the switch in
`confpartest` and `PARTEST_TLS_VERIFY` do not apply, and no warning fires on this road — an
`httpx` client does not expose the setting after construction, so there is nothing to read.
`ApiClient.verify` reports `None` here rather than a value it does not control.

The run artifact now says the same thing instead of quietly counting the run as verified: the
domain lands in `meta.tlsUnknownHosts`, which reads "partest did not decide this one" and is
deliberately not the same list as `meta.tlsUnverifiedHosts` ("this one went unchecked") — see
[[components/overview]]. `meta.tlsVerified` is untouched by it and keeps its two values.

If you need verification off for an injected client, say so where you build it
(`httpx.AsyncClient(verify=False)`) and know that it is invisible to everything else. The
example above deliberately no longer does: it used to, and it taught the one pattern that
bypasses the package-wide decision.

Default remains **ephemeral client per request** (backward compatible).

## A client of your own, still inside the TLS policy

Some calls are not suite calls: a fixture that pulls the live specification, a probe against a
second service, a warm-up before the session. Building those with `httpx.Client(...)` leaves
partest's TLS decision behind — `PARTEST_TLS_VERIFY` and `confpartest.tls_verify` are never
read, nothing warns, and `meta.tlsVerified` goes on saying the run verified certificates while
that client accepted anything. Use the factory instead:

```python
from partest import httpx_client, httpx_async_client

with httpx_client(base_url=domain, timeout=5.0) as http:
    spec = http.get("/v3/api-docs").json()

async with httpx_async_client(base_url=domain, headers=auth) as http:
    await http.post("/warmup")
```

It is a **factory, not a second `ApiClient`**: no retries, no coverage tracking, no steps or
attaches. Everything you pass — `base_url`, `timeout`, `headers`, `http2`, `auth`, a
`transport` — reaches httpx unchanged, and what you get back is a plain `httpx.Client`. Only
`verify=` takes a detour through `partest/tls.py`: an explicit `verify=False` warns once and
lands in `meta.tlsVerified` exactly like the project-wide switch does, and a CA bundle path
arrives as the `ssl.SSLContext` that httpx 0.28 asks for instead of the string it deprecates.

While verification is off, such a client also records **which host** each request went to, in
`meta.tlsUnverifiedHosts` — the answer to "did the whole suite run unchecked, or one service
host?" ([[components/overview]]). That is the one thing added to what you passed: a request
event hook, appended after your own `event_hooks`, and only on a client whose verification is
off. A verifying client is built exactly as you asked for it.

```python
# reads PARTEST_TLS_VERIFY and stops there — confpartest is not imported
with httpx_client(base_url=domain, env_only=True) as http:
    ...
```

`env_only=True` is the road the browser side takes (`partest.ui.ignore_https_errors`), and it
is here so that a job which must not load `confpartest` — or a caller who wants exactly the
environment's answer — does not have to compute `verify=` by hand with
`partest.tls.default_verify(env_only=True)` and pass the result back in.

**A call made through such a client is still invisible to coverage.** The factory removes the
reason to leave the TLS policy, not the reason to use `ApiClient`: whatever has to count as
covered goes through `make_request`.

Injecting a client into `ApiClient` (above) is the opposite case and is unchanged — that client
decided its TLS before partest saw it. Build it with `httpx_async_client(...)` and it is back
inside the policy, although `ApiClient.verify` still reports `None`: it is not the one who
decided.

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
from partest.redact import redact_headers, redact_mapping, redact_text, mask_secret
```

Body keys like `password`, `token`, `access_token`, `client_secret` are masked — where these
functions are applied, which is narrower than "everywhere":

| Channel | Masked |
|---|---|
| status mismatch message (`format_status_mismatch`) and its `status_mismatch` attachment | request headers only; request and response bodies, and the URL with its query, as is |
| ERROR log line of a status mismatch (`ErrorDesc.status`) | no: the response body as is |
| schema failure message and its ERROR log line | yes |
| INFO request / response log (`Logger.log_request` / `log_response`) | request headers only; bodies, URL query, `params=`, response headers and cookies (`Set-Cookie`) as is |
| `partest.reporting.attach_request` | headers; body unless `redact_body=False` |
| `partest.reporting.attach_response` | body only with `redact_body=True` (default `False`) |
| `partest.reporting.instrumented_make_request` (`TrackingApiClient` with instrumentation) | no: response body of every call, `status_mismatch` JSON and `failure_details` with both bodies |
| `partest.reporting.format_http_status_failure` | no: both bodies and `Original error: …` |
| `partest.reporting.attach_request` `params` and `path` | no |
| `make_request` HTTP-error branch (`HTTP error …` log, `Server returned …` assertion) and `Network/request error: …` | no: response body; the transport error's text with its URL |
| the client's base URL wherever an address is echoed | no: `user:password@` in it is shown as is |
| errors about the project's own configuration: a `confpartest` that fails to import, a spec in `swagger_files` that cannot be loaded (`ConfpartestError`, `OpenApiResolveError`) | URL credentials, query strings and secret-looking values removed; the original exception is not chained; for coverage, the raw sources are not among the locals `pytest -l` shows. Not covered: a token in the URL path, `;jsessionid=`, a fragment, a spec snippet quoted by a YAML parse error (that one keeps the parser's exception chained), and the locals of your own frames that hold the URL |
| fetching a spec: `openapi.resolve_swagger` (httpx) | `user:password@` is sent as `auth=`, never logged; the query string is kept out of httpx's INFO `HTTP Request:` line |
| fetching a spec for coverage (`swagger_files`, via `requests`) | INFO is clean; the `urllib3` DEBUG line shows the path with its query string |

The unmasked channels are listed under Known issues in `CHANGELOG.md`. Until they are fixed,
treat a CI log of a failed run as carrying whatever the service and the test sent.

`redact_text` is for text that is no longer a mapping — a model's `repr`, a body kept as a
string, a log line: it masks the values of the same keys in `"key": "value"`, `key='value'`,
`key=value` and `('key', 'value')` shapes, and `Bearer <token>` anywhere. It is pattern-based
and best effort; mask the mapping while you still have it. Poll messages
(`partest.polling`, `sideeffects.wait_for`) go through it.

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

Each xdist worker is a **separate process**, so each has its own `call_storage`. Left alone, the
report describes whichever worker rendered it: a green suite under `-n 3` has been measured at
25.7% average with 58 endpoints marked as never called.

The bundled plugin handles this without configuration: workers write a shard at the end of their
session, and the controller merges every shard before the run finishes.

```bash
pytest -n auto                       # merged automatically
PARTEST_CALL_STORAGE_DIR=/tmp/shards pytest -n auto   # if the default dir is not writable
PARTEST_XDIST_MERGE=0 pytest -n auto  # opt out
```

**A report written by a test still cannot see the merge.** That test runs on a worker; the merge
happens on the controller afterwards. Either run the coverage pass serially, or have the
controller write the artifact:

```bash
PARTEST_COVERAGE_JSON=coverage.json PARTEST_COVERAGE_HTML=coverage_report.html pytest -n auto
```

Check `meta.workers` and `meta.merged` in the JSON before trusting a number from a parallel
run — and `meta.selection`, which is present when the run was filtered with `-m` or `-k`, or
when opt-in marker sets decided something (`meta.selection.optin`, one entry per set). A
filter removes test *cases* rather than endpoints, so nothing else in the numbers reveals it.
Both cross the shards: workers collect, and the controller reads the selection from them.
For pipelines that publish coverage, `PARTEST_COVERAGE_REQUIRE_MERGE=1` turns an unmerged
parallel run into a failed session instead of a quiet wrong number.

Merge semantics: calls are summed per endpoint and executed types are unioned, so a later
`RequestDefault` never overwrites an earlier `RequestElements`.

Doing it by hand, if you need a different pipeline:

```python
from partest.call_storage import merge_shards, read_shards, write_shard
write_shard()            # on a worker
merge_shards()           # on the controller, before analysis
```

Within one process, `record_call` is **thread-locked**.

## Soft Allure dependency

`ApiClient` steps and `partest.reporting.attach_*` degrade gracefully when
`allure` is not installed (no-op attaches / plain steps).
