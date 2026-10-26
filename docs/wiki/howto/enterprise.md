---
title: Enterprise notes — shared client, retries, redaction, xdist
status: current
verified: 2026-10-26
sources: [partest/http_retry.py, partest/redact.py, partest/openapi.py, partest/conf.py, partest/call_storage.py, partest/client.py, partest/tls.py, partest/http/client.py, partest/utils/logger.py, partest/reporting/attach.py, partest/reporting/instrument.py, partest/reporting/templates.py, partest/reporting/checks.py, partest/sideeffects.py, partest/utils/checking.py, partest/auth/token_manager.py, partest/ui/allure_ui.py, partest/pytest_plugin.py]
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
from partest.redact import redact_headers, redact_mapping, redact_text, redact_url, mask_secret
```

Body keys like `password`, `token`, `access_token`, `client_secret` and the headers
`Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key` are secret. Every channel the package
writes to applies one rule:

- a structure (a parsed body, headers, `params`) is walked: a value under a secret key becomes
  `***` whole — no prefix kept — at any depth; deeper than 32 levels the whole value is
  replaced. Any other string gets only narrow patterns: URL credentials and secret query
  values, `Bearer` / `Basic` credentials, a JWT. So `{"missing": ["password", "email"]}` and
  `{"field": "password"}` stay readable and the JSON stays valid. A string holding JSON is
  walked too; pydantic models, dataclasses, bytes and sets are walked; a cycle is cut as
  `"<cycle>"`, and one walk opens at most 100 000 containers — past that a container reads
  `"<too large>"` (shared references, a DAG or YAML anchors, would otherwise take exponential
  time). A key matches in any case and with `-`, `_` or a space alike
  (`client-secret`), an Enum key by its value — for a body key the name must match exactly,
  as before (`accessToken`, `new_password` are not secret). A header is secret when it is one
  of the secret names (`Authorization`, `Cookie`, `X-Api-Key` …) or when its name — lower
  case, without separators and a numeric or `sha…` tail — ends with `token`, `key`, `secret`,
  `password`, `passwd`, `pwd`, `passphrase`, `signature`, `cookie`, `auth`, `authorization`,
  `authentication`, `session`, `sessionid`, `sid`, `jwt`, `ticket`, `otp`, `pass`, `cred`,
  `assertion`, `hmac`, `credential(s)` (a `v2`-style tail is dropped too):
  `CSRFPreventionToken`, `X-Authtoken`, `PVEAuthCookie`, `X-Session-Id`,
  `X-Hub-Signature-256` are masked; `WWW-Authenticate`, `Proxy-Authenticate`,
  `Authentication-Info`, `Signature-Input`, `Access-Control-Allow-Credentials`,
  `X-Session-Expires`, `X-Api-Key-Id`, `X-RateLimit-Remaining-Tokens` are not. The rule errs towards masking: a cursor such as
  `X-Next-Page-Token` is masked too, and a project cannot add names of its own;
- a message that quotes one element of a body (a schema failure's `in <path> = …`) masks it
  as the whole body would: `***` when a key on the path is secret;
- a JSON body in a message is re-serialised after masking: duplicate keys collapse, numbers
  and spacing are normalised. For a defect of the format itself attach the raw response
  yourself (`attach_response(redact_body=False)`);
- text that is not JSON — a plain-text body, an exception message — gets the full
  `redact_text`;
- in a URL, `user:password@` is removed (an `@` or a `/` in the password included); without
  a scheme — the DSN a database driver quotes, `app:S3cr3t@db.internal/prod` — it becomes
  `***@db.internal/prod` (`mailto:a@b.example` is an address and stays); an address whose
  password holds a raw `?`, `#` or an apostrophe — what is left reads `user:pa` before a
  stray `@`, `https://user:pa?ss@host` — is `https://<redacted>` whole; `?token=…`
  becomes `?token=***` — in the query (`&` or `;`) and in the
  fragment (`#access_token=…`), for the secret keys and for `X-Amz-Signature`,
  `X-Amz-Security-Token`, `X-Amz-Credential`, `X-Goog-Signature`, `signature`, `sig`,
  `auth_token`, `sessionid`, `session_id`, `jsessionid` — also `;jsessionid=` in a path, and
  such a pair in text outside a URL (`sv=1&sig=…`) — while `key` and `code` are not masked:
  `?code=RU` is not a secret, see [[howto/security]];
- in free text, where a secret value ends is decided towards masking more: a quoted value to
  its own quote not followed by a letter or digit, else to the end of the line; an object or
  array to its balancing bracket (a bracket inside either quotes does not count), else to the
  end of the indented block it opens; a bare value to whitespace or a separator, quotes
  included. The `... [truncated, N chars total]` marker ends a value only at the very end of
  the text. A PEM private key is masked whole wherever it appears;
- what the package has already masked — the ERROR lines of `ErrorDesc`, the message of a
  status mismatch or a schema failure — is not masked a second time;
- then the body is shortened; a value that cannot be masked is a placeholder, never raw.

`redact_mapping` and `redact_headers` themselves are unchanged (they keep an eight-character
prefix); the channels do not use them. Which keys count as secret has not changed — a key
that only *contains* one (`accessToken`, `clientSecret`, `sessionId`) is not masked; widening
that is a separate, breaking decision.

| Channel | Masked |
|---|---|
| status mismatch message (`format_status_mismatch`, `StatusMismatchError`) and its `status_mismatch` attachment | yes: URL, request headers, request and response bodies |
| ERROR log lines: `ErrorDesc.status` / `element`, `HTTP error …`, `Network/request error: …`, `response hook failed: …` | yes |
| schema failure message and its ERROR log line | yes |
| the pytest traceback of a schema failure | yes: the `AssertionError` has no chained pydantic error, so no `input_value=`; the message and `validation_errors` name each failing path, type and message |
| stdout of `PydanticResponseError.print_error` | yes: the rejected value is shown by its type only, the error list without `input` |
| INFO request / response log (`Logger.log_request` / `log_response`) | yes: URL, `params=` and the body as JSON (the body shortened to 8000 characters), headers (a `Location` / `Referer` URL by the URL rule), cookie values `***`; `Files:` as field, file name, size, content type. Nothing is computed when INFO is off |
| `Logger.error`, `warning`, `log_str` | yes: the text by the free-text rule |
| httpx's own INFO line `HTTP Request: <method> <url>` (logger `httpx`) | yes: a filter on the `httpx` logger, added once when partest builds a client (`ApiClient`, `httpx_client`, `httpx_async_client`), not on import |
| `partest.reporting.attach_request` | headers, `params`, the query in `path`; body unless `redact_body=False` |
| `partest.reporting.attach_response` | body only with `redact_body=True`; **the default is `False`** for a suite's own calls (it flips in 3.0) — every call inside partest passes `True` |
| `partest.reporting.attach_check`, `check_*` step titles and messages (`ErrorTemplates.mismatch`, `type_mismatch`, `not_in_list`) | under a secret field name (`token`, `password` …) the value is `***` whole; otherwise free text at every level — each string or `bytes` in it, nested ones too, gets the whole text rule (`password: …`), the structure staying; prose like `token: expired` is masked there (HTTP bodies keep the body rule) |
| `partest.reporting.attach_failure` | yes: its text by the free-text rule |
| `partest.reporting.instrumented_make_request` (`TrackingApiClient` with instrumentation) | yes: step title, response attachments, the `status_mismatch` JSON and its `entity_hint`, `failure_details` |
| `partest.reporting.format_http_status_failure`, `ErrorTemplates.status` / `conflict_409` | yes: path, both bodies, the Problem Detail summary, `Entity context:` and `Original error: …` |
| `sideeffects.assert_locator`, `assert_status_enum`, `Observation.require` | yes: the body in the message; a value read from it is masked like a check value (free text at every level) |
| `StepTemplates.assert_field`, `assert_list_contains`, `assert_status` (step titles) | yes: a check value as above, `***` under a secret field name; a status as a number |
| errors about the project's own configuration: a `confpartest` that fails to import, a spec in `swagger_files` that cannot be loaded (`ConfpartestError`, `OpenApiResolveError`) | URL credentials and query strings removed, a fragment and `;jsessionid=` masked by key, secret-looking values masked; an address is closed on doubt as `redact_url` closes it — any `@` outside its userinfo, a password with a quote, `<` or `>`, a "port" that is not a number give `scheme://<redacted>`; a `swagger_files` URL that cannot be read as an address (a raw `/`, `?`, `#` or `@` in the password, a non-numeric port, `＠` U+FF20 in the host) is refused before any request (`percent-encode` in the message: an HTTP client would quote part of that password back); the original exception is not chained; for coverage, the raw sources are not among the locals `pytest -l` shows. Not covered: a token in the URL path, a spec snippet quoted by a YAML parse error (that one keeps the parser's exception chained), and the locals of your own frames that hold the URL |
| fetching a spec: `openapi.resolve_swagger` (httpx) | `user:password@` is sent as `auth=`, never logged; the query string is kept out of httpx's INFO `HTTP Request:` line; a redirect to another origin drops the caller's headers and the credentials, one from `https` to `http` is refused, `max_redirects` (20) at most; the body is plain or one layer of `gzip` / `deflate`, decoded here within `max_bytes` (64 MiB) — `br`, `zstd` and several layers are refused; a compressed body cut short is refused; `total_timeout`, when given, is checked between steps and chunks and cuts each step's timeout (the body and redirects overrun it by at most one `timeout`; the headers are bounded only by `timeout` per read, DNS not at all); a `url` must start with `http://` or `https://`; every failure is `OpenApiResolveError`, unchained, naming the location as `redact_url` shows it |
| fetching a spec for coverage (`swagger_files`, via `requests`) | INFO is clean; the `urllib3` DEBUG line shows the path with its query string |

Masking is by key, so it is only as good as the key list: a value under a key it does not know
is shown as is, and so is a secret inside an XML body (`<password>…</password>`), a multipart
body sent through `content=`, an `Authorization: Token …` / `Digest …` / `AWS4-…` value in
plain text (in a header dict the whole value is masked), and a value a custom validator puts
into its message without the key. Addresses in free text — log lines, messages, `redact_text`
— are not covered in these shapes (`redact_url`, for one address, closes the ones marked †):

- a bare DSN with a `/` in its password (`app:pa/ss@db.internal`), and Oracle's
  `scott/tiger@db`;
- a token in a path: a bot API `/bot<id>:<token>/…`, a Slack webhook
  `/services/T…/B…/<secret>`, an access key id `/AKIA…/`;
- a URL nested in a query value (`?next=https%3A%2F%2Fu%3Ap%40h`) — encoded, it is not seen
  as a URL;
- a scheme-relative `//user:password@host` and a malformed `https:/user:password@host` †;
- a token alone cut by a raw `/`, `?` or `#` (`https://tok/en@host` — in a log line it cannot
  be told from an `@` in a path) †, a password with a `"`, `<`, `>` or whitespace in it — the
  output channels close only the apostrophe; errors about the configuration close all but
  whitespace †.

A `logging.config.dictConfig` that configures the `httpx` logger drops partest's filter until
the next client is built. Treat a CI log as carrying whatever the service sent under any other
name.

The same masking covers what is not an HTTP call: the plugin's `failure_summary` attachment,
`TokenManager` errors, and the UI failure context (`partest.ui.allure_ui`: the page URL,
network, console and page errors).

`redact_text` is for text that is no longer a mapping — a model's `repr`, a body kept as a
string, a log line: it masks the values of the same keys in `"key": "value"`, `key='value'`,
`key=value` and `('key', 'value')` shapes (a quoted value keeps its quotes), an object or
array to its balancing bracket or else to the end of the indented block it opens, a whole
`Cookie:` / `Set-Cookie:` line, `Bearer <token>` / `Basic <credentials>` anywhere (a
`Bearer realm="…"` challenge keeps its parameters), a PEM private key whole, `;jsessionid=`,
and the credentials of an address: `postgresql://app:S3cr3t@db.internal/prod` loses
`app:S3cr3t@`, and the bare DSN a database driver quotes in its exception,
`app:S3cr3t@db.internal/prod`, becomes `***@db.internal/prod` — whatever the host looks like
(`db_internal`, `[::1]`, an IDN, `db.internal: refused`). Only a colon before the `@` makes a
credential: `a@b.example`, `mailto:a@b.example` and `git@host:org/repo.git` stay;
`email:alice@example.com` reads `***@example.com`. An address whose password was cut by a raw
`?`, `#` or an apostrophe is `https://<redacted>`. It is pattern-based and best effort; mask
the mapping while you still have it. Poll messages (`partest.polling`, `sideeffects.wait_for`)
go through it.

`redact_url(url)` is for one address kept on its own — an artifact's `source`, a log line
about where a document came from: no credentials, no query string, no fragment
(`https://user:pw@h:8443/v3/api-docs?token=…#x` → `https://h:8443/v3/api-docs`), the rest
through `redact_text`, `;jsessionid=` masked. It is **closed on doubt** and gives
`scheme://` + `REDACTED` (`partest.redact.REDACTED == "<redacted>"`; compare with the
constant) for:

- any `@` after `scheme://` other than in the userinfo — a raw `/`, `?` or `#` in a password
  (`https://user:pa/ss@h/x`), but also `/@me` in a path, `?email=a@b.example`, a working
  `http://[::1]:8080/@scope/openapi.json`; `＠` (U+FF20) counts as `@`;
- a "port" that is not a number (`https://admin:hunter2/api`, a password without its `@`);
- anything after the address: whitespace, a quote, `<` or `>` and what follows
  (`https://h/My Specs/openapi.yaml` — write `My%20Specs`).

The userinfo cannot be told from the rest there, and a guess could show part of a password.
Percent-encode such a password (`%2F`, `%3F`, `%23`, `%40`); a client needs that anyway.
`redact_url(redact_url(x)) == redact_url(x)`. Text without `scheme://` (a path) loses its
query and fragment and goes through `redact_text`. The output channels share its core; they
show request URLs, so there an `@` in a path or a query value stays.

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
