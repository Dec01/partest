---
title: Package map — what lives where
status: current
verified: 2026-09-24
sources: [partest/methodology/__init__.py, partest/__init__.py, partest/client.py, partest/coverage.py, partest/reports/__init__.py, partest/reporting/__init__.py, partest/ui/__init__.py, partest/security/__init__.py, partest/auth/__init__.py, partest/tls.py, partest/http/client.py, partest/call_storage.py, partest/reports/payload.py, partest/pytest_plugin.py]
audience: agent
ships_in_wheel: true
---

# Package map

Orientation before reading code. Module docstrings and `__all__` are the real contract; this page
only says where to look.

```text
partest/
  client.py            ApiClient — async HTTP + coverage tracking + rich status errors
  coverage.py          track_api_calls, endpoint classification entry point
  call_storage.py      per-process counters; dump/merge for xdist
  test_types.py        TypesTestCases, canonicalize_type, TYPE_LABELS
  conf.py              load/validate confpartest
  openapi.py           spec loading and path matching
  tracking.py          TrackingApiClient, CreatedRegistry, id extractors
  payloads.py          BaseRequestBody
  validation/          BaseResponseValidator, ProblemDetail*, raw IncorrectBody cases
  data_marker.py       TEST_MARKER, marked_name/code/short — test-data naming
  env/                 project root, .env loading, require_env
  http/                Config, HeadersBind, httpx_client/httpx_async_client factory
  auth/                TokenManager, JWT decode
  reporting/           check_* helpers, «not measured» third outcome, steps, attaches, instrumented requests
  reports/             coverage analyzer, JSON payload, HTML, compare/badge/stubs/history
  methodology/         methodology SoT, two areas:
    api/               subtypes, matrix, classifier, inference, steps (derived from OpenAPI)
    ui/                surfaces, checks, matrix, steps (surface type declared by the consumer)
    <name>.py          deprecated aliases for the pre-2.0.0 paths, same objects, gone in 3.0.0
  security/            RiskProfile model, SecHttp raw transport, JWT tampering
  collections/         BaseCollection, CollectionsManager
  ui/                  partest[ui]: BasePage, PageMonitor, Storage, visual, capture_baselines
  project_gen/         deprecated bridge to the separate partest-gen distribution
  redact.py            secret redaction for attaches
  http_retry.py        transport retries
  flags.py             coerce_bool/env_bool — one reading of every on/off switch
  tls.py               one place deciding verify= for every client (see below)
  zorro_report.py      zorro() — Allure + simple coverage HTML
  docs/                generated user docs shipped in the wheel (do not hand-edit)
```

## Roles

| Module | Role |
|---|---|
| `ApiClient` | the only sanctioned way to make suite HTTP calls — raw httpx calls are invisible to coverage |
| `tls` | `default_verify()` / `resolve_verify()`: certificates are verified unless the project says otherwise |
| `TrackingApiClient` / `CreatedRegistry` | record created ids, clean up in LIFO with 409 retry |
| `TokenManager` | OIDC multi-role token cache; credentials come from an injected provider |
| `Config` / `HeadersBind` | header and param builders, `apply_token` binding |
| `httpx_client` / `httpx_async_client` | a client of your own **inside** the TLS policy — no retries, no coverage |
| `reporting` (`import partest.reporting as ah`) | `ah.check_*`, Allure steps and attaches; `check_measured` adds a third outcome, «not measured»; Allure is a soft dependency |
| `reports` | `zorro_enhanced`, `coverage.json`, interactive HTML, `python -m partest.reports` CLI |
| `methodology.api` | subtypes × matrix × inference, all derived from the specification — see [[concepts/methodology]] |
| `methodology.ui` | surfaces × checks × depth; no classifier — the surface type is declared, not inferred |
| `security` | `RiskProfile` model, `SecHttp`, `build_tampered_set`; entity PROFILES stay in the consumer |
| `ui` | shared UI harness only; page objects stay in the consumer — see [[howto/ui]] |
| `project_gen` | deprecated bridge to `partest_gen`; the scaffold is its own distribution, `pip install partest-gen` |

## Public surface

Everything re-exported from `partest/__init__.py` is public and covered by the alias policy
(legacy names kept at least one minor). Submodule internals are not.

```python
from partest import (
    ApiClient, TrackingApiClient, CreatedRegistry, TokenManager,
    BaseRequestBody, Config, HeadersBind, SecHttp, build_tampered_set,
    TypesTestCases, canonicalize_type, marked_name, TEST_MARKER,
    RiskProfile, BaseCollection, CollectionsManager, reset_storage,
)
import partest.reporting as ah
from partest.validation import BaseResponseValidator, ProblemDetailValidation
from partest.reports import zorro_enhanced
from partest.zorro_report import zorro
from partest.ui import BasePage, PageMonitor, Storage          # partest[ui]
```

## Consumer side

Never in this package: `confpartest.py` values, project tests, entity paths/DTO, RBAC roles,
page objects, SQL cleanup, baselines. Those belong to the suite that uses partest — the library
stays project-agnostic so a second project can adopt it without stripping anything out.

## pytest plugin

Auto-loads via the `pytest11` entry point (`partest/pytest_plugin.py`) and does two unrelated
things, each behind its own switch.

| Switch | Default | Governs |
|---|---|---|
| `PARTEST_PYTEST_PLUGIN=0` / `pytest_plugin = False` | on | Allure display names from docstrings, failure summary attachment |
| `PARTEST_RUN_METADATA=0` / `run_metadata = False` | on | `run_info["selection"]`: the `-m`/`-k` expression and how many tests were deselected |

`pytest -p no:partest` disables the plugin entirely, both halves.

Turning the Allure half off is normal — a project that owns its Allure hooks would otherwise get
double titles and double attachments. **It does not turn off the run metadata.** It used to, and
that was a defect: recording the selection attaches nothing and prints nothing, so it has nothing
to collide with, while losing it costs the report the only exact signal that a run covered a
subset of the suite ([[concepts/coverage-honesty]]). The deselected count is a set of node ids,
so a parallel run merges them: workers deselect the *same* tests, and sets merge where counts
would double. The same representation makes a second run in one process harmless.
When the change landed is in [[howto/migration]].

## TLS verification

Every client in the package — `ApiClient`, `SecHttp`, `TokenManager`, `CreatedRegistry.cleanup`,
`TrackingApiClient`, and the browser context of `capture_baselines` — takes its `verify=` from
`partest/tls.py` when the caller does not pass one. **Certificates are verified.** They used not
to be, and `ApiClient(domain)` said nothing about it — see [[howto/migration]] for the release
that changed it and for the one line that restores the old behaviour.

```bash
PARTEST_TLS_VERIFY=0                     # a self-signed stand: off for the whole run
PARTEST_TLS_VERIFY=/etc/ssl/corp-ca.pem  # better: trust the private CA, keep checking
```

```python
# confpartest.py — the same decision, in the project instead of the environment
tls_verify = False
```

The environment wins over `confpartest`; an explicit `verify=` on a call wins over both. Whenever
verification ends up off, the run emits one `partest.tls.TLSVerificationDisabled` warning —
once per process, so it is visible in the pytest summary without being noise per request — and
the report carries `meta.tlsVerified: false`, because a warning does not survive the session.
"Off" includes an `ssl.SSLContext` built with `verify_mode = ssl.CERT_NONE`: it accepts any
certificate, so it is recorded like `verify=False` rather than passing for verification.

Need a client of your own? `partest.http.httpx_client` / `httpx_async_client` build one with
the same decision applied, so a fixture fetching a live specification no longer has to leave
the policy to accept a self-signed stand — see [[howto/enterprise]]. Inside the package these
two are the **only** place that calls httpx's constructors; a test in `tests/test_tls_factory.py`
fails if a module grows a raw one again. Both take `env_only=True` to stop at the environment
and not read `confpartest`, the way `default_verify` and `partest.ui.ignore_https_errors` do.

`meta.tlsVerified: true` means "no client partest built for this run skipped verification". It
cannot mean more than that: a consumer may still construct an httpx client by hand, and an
injected `client=` decided its TLS before partest saw it.

### Which hosts, not only whether

`tlsVerified` is one bit for a whole run and says that **at least one** connection went
unchecked — not that every one did. One auxiliary service is enough to switch it off. Measured
on a consumer: a plugin of theirs sits in `addopts` and signs into an auxiliary service with a
self-signed certificate while pytest is still configuring itself, so every run of that project —
including runs that never call the API — went unverified by that one connection. The flag went `false` honestly and always, and "the suite ran
unverified throughout" stopped being distinguishable from "one service host was accepted, the
stand was verified from the first call to the last".

Two lists stand next to the flag and never instead of it:

```json
"meta": {
  "tlsVerified": false,
  "tlsUnverifiedHosts": ["admin.stand.invalid:9443"],
  "tlsUnknownHosts": []
}
```

- **`tlsUnverifiedHosts`** — hosts this run actually sent a request to while verification was
  off, `host` or `host:port` (a default port is dropped; credentials in a URL never reach the
  artifact). The host is taken **per request**, not from `base_url`: `base_url` says what a
  client was pointed at, a redirect leaves it behind, and `ApiClient` — the road the system
  under test travels — passes no `base_url` at all. A client built unverified and never used
  contributes nothing, because nothing was accepted.
- **`tlsUnknownHosts`** — hosts whose TLS partest did not decide and cannot read: today that is
  `ApiClient(domain, client=hx)`, which sets `self.verify = None` because the injected client
  settled `verify=` out of sight. That case used to be reported as a verified run. It is *not*
  the same claim as the first list and is kept apart from it: "not ours to check" is not
  "unchecked".

Both lists are sorted, deduplicated and unioned across xdist workers, and both are present even
when empty — so "nothing was accepted unverified" stays distinguishable from "an artifact
written by an older partest". Neither changes the type or the meaning of `tlsVerified`: adding a
key to `meta` is compatible for `partest-atlas`, `partest-load` and the map, changing the type
of one is not. The remaining option once considered here — a strict mode that fails the run
outright — is still untaken.
