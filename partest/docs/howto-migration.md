<!-- Part of the partest package: generated documentation, not hand-written.
     Read it with `python -m partest.docs`. Local edits are lost on upgrade. -->

# Migration guide

Version-by-version upgrade notes. Newest first. This is the library-side guide: what changed in
the public API and what a suite has to do about it.

```bash
pip install -U partest
pip install -U 'partest[ui]'   # UI suites
```

## 1.7.0 — coverage that tells the truth

No breaking API changes. **But your coverage figures will move**, because two things they
rested on were wrong. Read this section before you open the report and conclude something
broke.

| Change | What you will see | Action |
|---|---|---|
| **Coverage keys resolve to the real OpenAPI template** | endpoints that read as never called start recording; some calls move between keys | none — but expect the average to rise. `defining_url` still wins where you pass it |
| **Classifier fixed** | paths containing "me" (`/media-types`, `/departments`) are no longer GET BY SELF; `POST /{id}/<verb>` is now ACTION | the required P1 set changes for those endpoints, so `missing_p1` changes with it |
| **Worker results are merged under `-n`** | a parallel run no longer reports one worker's slice | nothing to configure; see the caveat below |
| **`kind` per endpoint** | `unseen / empty / partial / full / exception` alongside `status` | use it to tell "nobody called this in this run" from "this has no tests" |
| **Failures carry their diagnostics again** | `AssertionError` with the formatted status/schema message instead of `RuntimeError: generator didn't stop after throw()` | drop any handling written around that RuntimeError |
| **Created ids survive a failed validation** | a 201 rejected by `extra=forbid` no longer leaves an untracked row | remove a local track-before-validate overlay if you built one |
| **`aqa_*` helpers warn** | `DeprecationWarning` on the five legacy aliases | switch to `marked_name`, `marked_code`, `marked_short`, `fill_with_marker`, `prefix_marker` |
| **Wheel docs renamed** | `QUICKSTART.md` → `howto-quickstart.md`, and so on | only affects code calling `partest.docs.read_doc` |

**The caveat worth knowing:** a report written *by a test* still cannot see the merge — that
test runs on a worker, and merging happens on the controller after it. Either run the coverage
pass serially, or let the controller write the artifact:

```bash
PARTEST_COVERAGE_JSON=coverage.json PARTEST_COVERAGE_HTML=coverage_report.html pytest -n auto
```

Check `meta.workers` and `meta.merged` before trusting a number from a parallel run, and compare
runs with `python -m partest.reports compare --strict` rather than eyeballing the average.

New and optional: `partest.access` (four permission cells), `partest.files` (upload corpus),
`partest.sideeffects` (observing what a write left outside HTTP), `subtype_overrides` in
`confpartest.py`, `_cleanup_fields` on payloads, `CreatedRegistry.snapshot` / `cleanup_since`.
Each has a cookbook: `python -m partest.docs list`.

## 1.5.0 — coverage extras + UI freeze + IB helper

Backward compatible with 1.4.0. New opt-in APIs only.

| Change | Impact | Action |
|--------|--------|--------|
| **`zorro_enhanced()`** / `python -m partest.reports` | Interactive HTML + `coverage.json` | Replace local `coverage_report` if you had one; keep consumer `services.yaml` |
| **`ServiceMap`** | Path → service key (injected prefixes/tags) | `ServiceMap.load("…/services.yaml")` |
| **`canonicalize_type("type_default")`** | Attribute-name aliases score in coverage | New tests still write `type=types.request_default` |
| **`p2_test_cases()` / `TYPE_LABELS`** | Optional B+ cells; P1 unchanged | Ignore unless you track P2 |
| **`RAW_INCORRECT_BODY_CASES`** | Shared broken JSON / CT cases | `from partest.validation import …` |
| **Freeze / capture / UI hooks** | Generic CSS + CLI `--only` + optional plugin | Domain selectors stay consumer |
| **`compare_images(name=, diff_output=)`** | shim kwargs now in library | Drop local visual_compare extras |

```python
from partest.reports import ServiceMap, zorro_enhanced
from partest.validation import RAW_INCORRECT_BODY_CASES, assert_raw_incorrect_body
from partest.ui import inject_freeze_styles_sync, wait_ready_for_screenshot_sync

smap = ServiceMap.load("src/api/resources/coverage/services.yaml")
zorro_enhanced(service_map=smap)
```

## 1.4.0 — UI parity

| Change | Impact | Action |
|--------|--------|--------|
| **`BasePage` is sync** | Default POM methods have **no** `await` | Use `BasePage` with pytest-playwright; keep `AsyncBasePage` only for async suites |
| **PageMonitor** | `attach` / `finalize` / `library_issues` / `attach_report` | Drop local monitor after bump |
| **`Storage` class** | get/set local/session storage | `from partest.ui import Storage` |
| **`VisualCompareResult.ok`** | alias of `equal` | Drop consumer `.ok` shim |
| **Docs in wheel** | cookbooks install with the package | `from partest.docs import read_doc; read_doc("QUICKSTART.md")` |

```python
from partest.ui import (
    BasePage,
    AsyncBasePage,
    PageMonitor,
    Storage,
    should_ignore_url,
    is_library_console_message,
    attach_monitor,
    assert_page_healthy,
)
```

## Breaking / behavior notes (1.3.x still apply)

| Change | Impact | Action |
|--------|--------|--------|
| **RiskProfile fields** | Primary API is now `entity`, `writes`, `authz`, `pii`, `fk_traversal`; levels include **critical** | Prefer new fields; old `name=` / `has_*=` still work; use `RiskProfile.from_legacy(...)` |
| **pytest plugin** | Still auto entry point; can double-attach with local Allure hooks | Set `PARTEST_PYTEST_PLUGIN=0` or `pytest_plugin = False` |
| **Multi status** | `expected_status_code=(400, 415)` supported | Update TC that accept either 400 or 415 |
| **Faker locale** | `PARTEST_FAKER_LOCALE` (default `en_US`) | Set env for RU/DE data |
| **TokenManager** | `verbose=False` default; logs via `logging` not print | Optional `verbose=True`; optional `client_secret=` |

## From partest 0.3.x

1. Bump dependency to `partest>=1.5.0`.
2. Prefer canonical TC names: `request_default` instead of `default`, `request_not_allowed` instead of `405`.
3. Use `content=` + `content_type=` on `ApiClient` for transport IncorrectBody (do not raw-httpx bypass for suite coverage).
4. Import reporting: `import partest.reporting as ah`.
5. Tracking: `TrackingApiClient` + `CreatedRegistry` instead of local trackers.
6. Auth: inject `credentials_provider`; no product roles in library.

## From a local in-project harness

| Local module | Library |
|--------------|---------|
| allure_helper (generic) | `partest.reporting` |
| resource_tracker | `partest.tracking` |
| base_payload | `partest.payloads.BaseRequestBody` |
| base_validation | `partest.validation` |
| test_marker | `partest.data_marker` (`aqa_*` aliases kept) |
| configs headers | `partest.http.Config` / `HeadersBind` |
| token_manager | `partest.auth.TokenManager` + thin role adapter |
| risk_profiles dataclass | `partest.security.RiskProfile`; **PROFILES dict stays consumer** |
| SecHttp / jwt craft | `partest.security` |
| UI utils | `partest[ui]>=1.5.0` — `BasePage`, `PageMonitor`, `Storage` |

**Stay in consumer forever:** entity paths/DTO, RBAC matrix, SQL cleanup, page objects, baselines PNG, stand URLs, domain 409 explainers (pass as provider hooks).

### Plugin conflict with an existing root conftest

```python
# confpartest.py
pytest_plugin = False
```

```bash
export PARTEST_PYTEST_PLUGIN=0
# or
pytest -p no:partest
```

### RiskProfile rewrite

```python
# old 1.3.0
RiskProfile(name="clients", has_writes=True, has_fk=True)

# new (preferred)
RiskProfile("clients", writes=True, fk_traversal=True)

# dual
RiskProfile.from_legacy("clients", has_writes=True, has_fk=True)
```

Level mapping (new):

- critical ← authz or (pii ∧ writes)
- high ← writes ∧ fk_traversal (or money ∧ writes)
- medium ← writes
- low ← else

### Coverage matrix vs flat

Default analyzer uses **methodology matrix** (subtype → required P1 TC).  
`test_types_coverage` in confpartest is **legacy flat mode** only when
`use_matrix=False`. Prefer matrix for multi-project suites.

### BaseRequestBody property trap

Prefer class dict of callables:

```python
class Body(BaseRequestBody):
    _required = ["name"]
    _json_main = {"name": lambda: marked_name("X")}
```

`@property def _json_main` on the instance is supported in 1.3.1+; classmethod helpers that need a property instantiate a bare object.

### Collections apply_token

```python
from partest import CollectionsManager, Config
from partest.http import HeadersBind

mgr = CollectionsManager(items=ItemsCollection())
mgr.apply_token(token)

# or headers only
headers = Config.apply_token({"Accept": "application/json"}, token)
bind = Config().headers_bind(["Accept", "X-Request-ID"], token=token)
bind.apply_token(new_token)
```

## confpartest validation

```python
from partest import require_confpartest
conf = require_confpartest()  # clear errors if swagger_files missing
```

## Semver policy (D10)

- **Major** — remove aliases / change RiskProfile levels without dual API / drop entry points.
- **Minor** — new modules, new optional kwargs, docs.
- **Patch** — bugfixes, dual-API shims, docs only.

Aliases (`aqa_*`, legacy TC names, RiskProfile `has_*`) remain **≥ 1 minor**.

Releases go to **PyPI**. Public GitHub is not a distribution channel.

## Checklist after bump

- [ ] `pip install -U 'partest>=1.5.0'` (add `[ui]` for UI suites)
- [ ] If POM used async `BasePage` from 1.3.x: switch to `AsyncBasePage` **or** drop `await`
- [ ] Replace local page_monitor / health / storage with `partest.ui`
- [ ] Optional: `zorro_enhanced()` instead of a local coverage HTML
- [ ] Optional: `RAW_INCORRECT_BODY_CASES` instead of a local IB helper
- [ ] Fix RiskProfile imports / levels if security suite asserts strings
- [ ] Disable plugin if dual Allure hooks
- [ ] Run `pytest --collect-only` then smoke TC
- [ ] Prefer `type=TypesTestCases.request_*` on ambiguous cases
- [ ] Re-run the coverage pass and confirm `missing_p1` did not grow
