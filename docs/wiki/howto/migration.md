---
title: Migration between partest versions
status: current
verified: 2026-09-24
sources: [partest/test_types.py, partest/__init__.py, partest/conf.py, partest/tls.py, partest/http/client.py, partest/pytest_plugin.py, partest/methodology/__init__.py, partest/methodology/_moved.py, partest/methodology/api/__init__.py, partest/methodology/api/overrides.py, partest/methodology/ui/__init__.py]
audience: user
ships_in_wheel: true
allow_version_literals: true
---

# Migration guide

Version-by-version upgrade notes. Newest first. This is the library-side guide: what changed in
the public API and what a suite has to do about it.

```bash
pip install -U partest
pip install -U 'partest[ui]'   # UI suites
```

## Unreleased — your own httpx clients can stay inside the TLS policy

Nothing here breaks. This is the upgrade a suite makes on purpose, and it is worth making if
`grep -rn "httpx.Client(\|httpx.AsyncClient(" tests/` finds anything: every hit is a client
that ignores `PARTEST_TLS_VERIFY`, ignores `confpartest.tls_verify`, warns about nothing and
leaves `meta.tlsVerified: true` in the report even when it accepts any certificate.

```python
# before — outside the policy, whatever the project configured
async with httpx.AsyncClient(verify=False) as http:
    spec = (await http.get(swagger_url)).json()

# after — the project's decision, in one place, for this client too
from partest import httpx_async_client

async with httpx_async_client() as http:
    spec = (await http.get(swagger_url)).json()
```

Drop the `verify=False` while you are there: if the stand really needs it, `PARTEST_TLS_VERIFY=0`
(or a CA bundle path, which is better) says so once for the whole run, and the report then says
so too. Keeping `verify=False` in the call also works and is honestly recorded — the factory
routes an explicit value through the same policy.

The factory gives you TLS and nothing else: no retries, no coverage tracking, no steps. Calls
made through it are **not** counted as covered — anything that has to be counted still goes
through `ApiClient.make_request`. Details in [[howto/enterprise]].

## 2.0.0 — the methodology moved into `api/` and `ui/`, TLS is verified, and the plugin flag stopped hiding the run metadata

### The methodology submodules moved — a deep import has to be edited, but not today

The methodology is now two areas, `partest.methodology.api` and `partest.methodology.ui`, because
a second one arrived: UI. The existing modules moved into `api/` unchanged — **nothing inside them
was renamed**, so every class, function and enum member keeps its name and its meaning. The import
path is the only thing that changed.

| Was | Now |
|---|---|
| `partest.methodology.subtypes` | `partest.methodology.api.subtypes` |
| `partest.methodology.matrix` | `partest.methodology.api.matrix` |
| `partest.methodology.classifier` | `partest.methodology.api.classifier` |
| `partest.methodology.inference` | `partest.methodology.api.inference` |
| `partest.methodology.overrides` | `partest.methodology.api.overrides` |
| `partest.methodology.steps` | `partest.methodology.api.steps` |

**If you import from the package itself, nothing changes**: `partest.methodology` re-exports every
name it exported before — `MethodSubtype`, `SUBTYPE_LABELS`, `CoveragePriority`,
`applicable_test_cases`, `required_test_cases`, `p1_test_cases`, `p2_test_cases`,
`classify_endpoint`, `classify_path_object`, `InferResult`, `infer_test_type`, `TestStep`,
`STEPS_BY_GROUP` — plus `active_overrides`, new here, and the new UI names alongside them.

**The old paths keep working until 3.0.0.** `import partest.methodology.matrix` imports, warns
once with the path to use instead, and gives you the *same module object* as
`partest.methodology.api.matrix` — so `isinstance` holds across the two spellings, and an
override set through one is visible through the other. There is one registry, one enum, one of
everything, spelled two ways.

#### Upgrade in two steps, in this order

This is the point of the alias, and the order is not interchangeable:

1. **Raise the version first, change nothing else.** `pip install -U partest`, run the suite.
   Old imports still work; the run should be green except for whatever the TLS section below
   costs you.
2. **Then rewrite the imports, driven by the warnings.** Run once with deprecations visible and
   fix what it names:

   ```bash
   python -m pytest -W "always::DeprecationWarning" -q 2>&1 | grep "partest.methodology"
   grep -rn "partest\.methodology\.\(subtypes\|matrix\|classifier\|inference\|overrides\|steps\)" .
   ```

   Each line is a one-token edit: insert `api.` after `methodology.`.

Doing it the other way round — new imports first, version after — does not work, because
`partest.methodology.api` does not exist on 1.8.x. That was the whole problem: without the
alias the two edits had to land in one commit, with no green state in between.

**Where the failure shows up if you skip this.** A stale methodology import inside
`confpartest.py` is not reported at the import line. `confpartest` is loaded from inside the
pytest plugin, so on a version that lacks the path you get an `INTERNALERROR` with a pluggy
traceback while **the whole tree** is being collected, including tests that never touch the
methodology. And in the quiet shape of it — new paths on an old partest — `confpartest` simply
fails to load, `active_overrides()` returns empty, and coverage counts subtypes against the
wrong required sets with no message at all. If a coverage number moved after an upgrade and
nothing went red, check that first.

If a package of yours reads these functions — the scaffold generator does — raise its floor to
this release and move to the new paths rather than leaning on the alias: it is removed in 3.0.0.

#### `active_overrides` has a stable home now

```python
from partest.methodology import active_overrides    # 2.0.0 and later
```

A suite that asserts its `subtype_overrides` arrived had only the deep import
`from partest.methodology.api.overrides import active_overrides` to do it with — a public
function whose only spelling pointed into a module that moved. It is on the package now, and on
`partest.methodology.api`. The setters are not, deliberately: they are the harness's side of
reading your `confpartest.py`.

### A second methodology: UI

New, additive, and nothing to migrate — there was no UI methodology to migrate from.
`partest.methodology.ui` gives a surface-type vocabulary (axis A), eleven check families (axis B), a
priority matrix and four depth levels. **The surface type is declared by your page object**; there is
no classifier, because no project has a machine-readable description of its screens.

```python
from partest.methodology import SurfaceType, UiTestCases, required_checks

class ClientsPage(BasePage):
    surface = SurfaceType.LIST_TABLE

required_checks(ClientsPage.surface)      # includes UiTestCases.screen_state_persistence
```

The one family worth reading about before you write the list: `screen_state_persistence` — filters,
sorting, columns and page size still in effect **after a reload of the same screen**. A suite that
starts each test from a clean profile never reaches it. See [[concepts/methodology]].

### TLS certificate verification is on by default — this can break your suite

The HTTP clients used to default to `verify=False`. A suite that wrote `ApiClient(domain)` ran
without certificate validation and had no way of knowing. That is now reversed: `ApiClient`,
`SecHttp`, `TokenManager`, `CreatedRegistry.cleanup`, `TrackingApiClient` and the
`capture_baselines` browser context all verify unless told otherwise.

**The two specification loaders moved the other way, and the difference is worth a minute.**
`partest.openapi.resolve_swagger` declared `verify: bool = True`, and
`partest.parparser.OpenAPIParser.load_swagger_yaml` relied on the `requests` default — both
verified always, and neither could be told not to. They now read the same switch as everything
else, so the single line below **also** stops verifying the host that serves your
specification, which is often not the host under test. If you need them to differ, pass
`verify=` to `resolve_swagger` explicitly; the argument still wins. Its default changed from
`True` to `None` ("not specified") — a behaviour change at an unchanged signature, so a caller
that relied on the documented `True` has to say so now.

A failure here arrives **during collection**, not as a failing test: the specification is
loaded while the suite is being assembled.

**If your stand serves a self-signed or internally signed certificate, the upgrade turns green
runs into `SSLError` / `ConnectError`.** One line puts it back, for the whole suite:

```python
# confpartest.py
tls_verify = False
```

```bash
# or the environment, which wins over confpartest
PARTEST_TLS_VERIFY=0
```

Prefer trusting the CA over switching the check off — same one line, and the suite keeps
detecting a certificate that is genuinely wrong:

```bash
PARTEST_TLS_VERIFY=/etc/ssl/corp-ca.pem
```

`verify=` on a call still wins over both and still accepts what httpx accepts (`True`, `False`,
a CA bundle path, or a ready `ssl.SSLContext`); the only change is what happens when you pass
nothing. Whenever verification ends up off, the run emits one
`partest.tls.TLSVerificationDisabled` warning and the report says `meta.tlsVerified: false`.
A context you built yourself with `verify_mode = ssl.CERT_NONE` counts as off, because it is:
it accepts any certificate. Silence the warning deliberately if you mean it:

```ini
# pytest.ini
filterwarnings = ignore::partest.tls.TLSVerificationDisabled
```

A rejected certificate is not retried — nothing the next attempt does makes it valid. A TLS
connection that simply dropped (`SSLEOFError`, `SSLZeroReturnError`, `SSLSyscallError`) is a
different thing and is still retried as the transient failure it is.

### A broken `confpartest.py` is now an error instead of silence

Every switch that can live in the project file is read through one function,
`partest.conf.conf_attr`, and it separates two cases the library used to conflate:

- **no `confpartest` at all** — normal, and silent: you get the library default;
- **a `confpartest` that exists but raises while importing** — `ConfpartestError`, naming the
  switch that was being read and the original exception.

Previously the `ImportError` was swallowed, which is how `tls_verify = False` ends up unread
while the run warns that verification is *on*. The cost of the new behaviour is real and it is
deliberate: if your `confpartest.py` cannot be imported, you now find out on every read of a
switch — including in the `ApiClient` constructor — rather than in whichever test first depends
on a setting. Run `python -c "import confpartest"` from the suite root if this fires.

### `PARTEST_PYTEST_PLUGIN` no longer switches off the run metadata

The flag was documented as the way to avoid double Allure titles and attachments, and it did
that — but it also silenced the recording of *what the run selected*. Projects that followed the
advice lost `meta.selection` from the coverage payload without any sign, and a `-m`-filtered run
compared against a full one then reported every dropped cell as a regression.

The Allure half keeps the flag and its meaning. Recording the selection moved to its own switch,
on by default:

```bash
PARTEST_RUN_METADATA=0        # or confpartest: run_metadata = False
```

**What you will see** if you keep `pytest_plugin = False`: `meta.selection` and
`meta.partialRun` start appearing in `coverage.json` for filtered runs, and comparisons against
a full snapshot are marked unsound instead of reporting phantom regressions. Nothing is written
to Allure by this half — no attachment, no title, no file — so there is nothing new to collide
with your own hooks.

**Under `-n` this used to produce nothing at all.** The xdist controller does not collect, so
the hooks never fired there, and the shard a worker wrote carried no run metadata; a filtered
parallel run came out with correct counts and no record of being filtered. The selection now
travels with the shard. The deselected figure is a count of distinct node ids rather than a
running total, because every worker deselects the *same* tests — counts would add up, sets
merge. If you run filtered suites in parallel, this is the half that changes your reports.

## 1.8.0 — Python 3.10 is now the floor

One user-facing change, and it is an install-time one.

`python_requires` is `>=3.10`. Python 3.9 had been declared for releases without anyone
running the suite on it, and the claim did not hold — so it was dropped rather than patched.

**On Python 3.9 the upgrade is silent.** `pip install -U partest` does not fail; it resolves
to the last release that still supports 3.9 and leaves you there. Check what you actually got:

```bash
python -c "import partest, sys; print(partest.__version__, sys.version_info[:2])"
```

If the version did not move, the interpreter is the reason. Nothing else in this release
changes behaviour, so a suite already on 3.10 or newer needs no action beyond the bump.

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
| **pytest plugin** | Still auto entry point; can double-attach with local Allure hooks | Set `PARTEST_PYTEST_PLUGIN=0` or `pytest_plugin = False` — from 2.0.0 that flag covers the Allure hooks only, not the run metadata |
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

Releases go to **PyPI**; the source and its history live at `github.com/Dec01/partest`.

## Checklist after bump

- [ ] `pip install -U partest` (add `[ui]` for UI suites), then **confirm the version moved** —
      on Python 3.9 pip silently keeps you on the last release that supported it
- [ ] **After** the version moved, not before: run once with `-W "always::DeprecationWarning"`,
      then move the deep methodology imports it names (`partest.methodology.subtypes` and
      friends) under `api/`; imports from `partest.methodology` itself need nothing
- [ ] If POM used async `BasePage` from 1.3.x: switch to `AsyncBasePage` **or** drop `await`
- [ ] Replace local page_monitor / health / storage with `partest.ui`
- [ ] Optional: `zorro_enhanced()` instead of a local coverage HTML
- [ ] Optional: `RAW_INCORRECT_BODY_CASES` instead of a local IB helper
- [ ] Fix RiskProfile imports / levels if security suite asserts strings
- [ ] Disable plugin if dual Allure hooks
- [ ] Run `pytest --collect-only` then smoke TC
- [ ] Prefer `type=TypesTestCases.request_*` on ambiguous cases
- [ ] Re-run the coverage pass and confirm `missing_p1` did not grow
