---
title: Package map — what lives where
status: current
verified: 2026-09-07
sources: [partest/__init__.py, partest/client.py, partest/coverage.py, partest/reports/__init__.py, partest/reporting/__init__.py, partest/ui/__init__.py, partest/security/__init__.py, partest/auth/__init__.py]
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
  http/                Config, HeadersBind
  auth/                TokenManager, JWT decode
  reporting/           check_* helpers, steps, attaches, instrumented requests
  reports/             coverage analyzer, JSON payload, HTML, compare/badge/stubs/history
  methodology/         subtypes, matrix, classifier, inference, steps  ← methodology SoT
  security/            RiskProfile model, SecHttp raw transport, JWT tampering
  collections/         BaseCollection, CollectionsManager
  ui/                  partest[ui]: BasePage, PageMonitor, Storage, visual, capture_baselines
  project_gen/         partest-gen: CLI, IR, emitters, skeleton, ui_layout
  redact.py            secret redaction for attaches
  http_retry.py        transport retries
  zorro_report.py      zorro() — Allure + simple coverage HTML
  docs/                generated user docs shipped in the wheel (do not hand-edit)
```

## Roles

| Module | Role |
|---|---|
| `ApiClient` | the only sanctioned way to make suite HTTP calls — raw httpx calls are invisible to coverage |
| `TrackingApiClient` / `CreatedRegistry` | record created ids, clean up in LIFO with 409 retry |
| `TokenManager` | OIDC multi-role token cache; credentials come from an injected provider |
| `Config` / `HeadersBind` | header and param builders, `apply_token` binding |
| `reporting` (`import partest.reporting as ah`) | `ah.check_*`, Allure steps and attaches; Allure is a soft dependency |
| `reports` | `zorro_enhanced`, `coverage.json`, interactive HTML, `python -m partest.reports` CLI |
| `methodology` | subtypes × matrix × inference — see [[concepts/methodology]] |
| `security` | `RiskProfile` model, `SecHttp`, `build_tampered_set`; entity PROFILES stay in the consumer |
| `ui` | shared UI harness only; page objects stay in the consumer — see [[howto/ui]] |
| `project_gen` | scaffold: `partest-gen` CLI, OpenAPI → IR → emitters |

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

Auto-loads via the `pytest11` entry point (`partest/pytest_plugin.py`) and enriches Allure titles
from docstrings. Opt out with `PARTEST_PYTEST_PLUGIN=0`, `pytest_plugin = False` in confpartest,
or `pytest -p no:partest` — needed when the project already owns Allure hooks.
