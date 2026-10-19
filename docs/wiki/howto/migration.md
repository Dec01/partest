---
title: Migration between partest versions
status: current
verified: 2026-10-19
sources: [partest/test_types.py, partest/__init__.py, partest/conf.py, partest/tls.py, partest/http/client.py, partest/pytest_plugin.py, partest/methodology/__init__.py, partest/methodology/_moved.py, partest/methodology/api/__init__.py, partest/methodology/api/overrides.py, partest/methodology/ui/__init__.py, partest/coverage.py, partest/reports/analyzer.py, partest/reports/payload.py, partest/reports/compare.py, partest/redact.py]
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
# right after a release pip may answer from its cache and not see the new version:
pip install --no-cache-dir "partest==X.Y.Z"
```

## 2.7.0 (candidate, not released) — `summary.avg: null`, `exception` outside the average, depth, masking in every channel

Nothing to change in a suite that neither reads `coverage.json` nor matches log or message
text. Subtypes do not change: every valid OpenAPI path keeps the cell 2.6.0 gave it. In 2.6.0 GET BY PARENT went only to a malformed template with two or more `/` inside braces (`/a/b/{x/y/z}`); such a path is now read by the general rules — usually GET DYNAMIC, GET LIST or GET STATIC with list or static hints (`GET /orders/status/{a/b/c}` "List statuses" is GET STATIC). Behaviours that change:

| What | Before | Now | Do |
|---|---|---|---|
| `summary.avg` / `summary.avgAll` in `coverage.json` of a run with no endpoints | `0.0` | `null` | a reader that does arithmetic on it checks for `null` first, **explicitly**: in JavaScript and `jq` `null < 60` is true, so a gate `avg < 60` decides an unmeasured run by accident — test `avg == null` first |
| `python -m partest.reports badge` for such a run, or for an older snapshot's `0.0` with no endpoints | red `0.0%` | grey `n/a` | nothing |
| `compare_payloads` with such a run on either side — including an older snapshot's `0.0` with `summary.endpoints == 0` or `endpoints: []` | `avg_delta` = the other run's average, `comparable: true` | `old_avg` / `new_avg` and `avg_delta` / `coverage_delta` `null`, a warning, `comparable: false`; `compare --strict` exits 2 | read `warnings` before the delta; a pipeline whose baseline is an empty run gets exit 2 until the baseline is replaced |
| `validate_coverage_payload` on `summary.avg` with endpoints present | a non-number or a value outside 0..100 passed | an error | fix the producer |
| `summary.avg` / `avgAll`, `avgCoverage`, the heatmap, a service's `covered` on a run with `exception` endpoints (`health`, `test_types_exception`) | the row counted as 100 % — one health probe lifted the average like a fully tested endpoint | left out; still counted in `exception`; the average **moves down, never up**; a set of `exception` rows only has `null`; `meta.avgRule: 2` | re-baseline a quality gate on the new number; read `covered` as out of `scored` (`full + partial`), not out of `totalEndpoints`; a reader that does arithmetic on `avgCoverage` checks for `null` too |
| `compare_payloads` / `compare` with a snapshot written before 2.7.0 (no `meta.avgRule`) that has `exception` rows | its average, with the `exception` rows inside, against the new one | the older average is recomputed from its rows without them: `old_avg` is the recomputed value, `avg_recomputed` gives both, a line in `notes`; still comparable. A snapshot whose row list was trimmed cannot be recomputed: a warning, `comparable: false`, `compare --strict` exits 2 | nothing; read `avg_recomputed` if you chart the recorded value |
| a reader of `meta.avgRule` | — | absent or `1` — the old rule, `2` — this one, above `2` — a newer rule: do not compare across it | compare a trend only within one rule |
| `coverage.json` endpoint rows and `summary` | no depth | `depth` per row (`cells`, `status`, `schema`, `values: null`) and `summary.depth` with `statusPct` / `schemaPct`, `null` where nothing was measured; `scored` in `summary` and in service, subtype and method rows, `exception` in subtype and method rows; the percentage is unchanged | nothing; to read it — `schemaPct` is the share of filled cells where some call asked for `validate_model` (with a status check): asked, not passed |
| `partest.methodology.api.steps.depth_score(has_status=False, has_validate_model=True)` | `1` | `0` — a model without a status check is not validated | nothing, unless you relied on the old score |
| `analyze_coverage(...)` / `zorro()` in Python: `report.average_pct`, `by_subtype[...]["avg_pct"]`, `by_swagger[...]["avg_pct"]` with `exception` rows | `exception` rows inside, as 100 | outside; types unchanged — `0.0` when nothing is scored, and then `report.scored_count == 0` / the bucket's `scored == 0` say "not measured" (`report.scored_count` is a new read-only property, counted from `endpoints`); `zorro()`'s text summary and the simple HTML print `n/a` there | check `scored_count` / `scored` before reading `0.0` as a measured zero |
| the depth flags of a tracked call (`has_status_check`, `has_validate_model` in `call_meta`) | written for every call from its keyword arguments, `False` when absent — also for a status passed positionally, and for a function that has no such parameters | read through the function's signature (positional arguments and defaults included); a `**kwargs` wrapper (`make_request(self, method, endpoint, *args, **kwargs)`) from its keyword arguments, as before; a function with neither an `expected_status_code` parameter nor `**kwargs` records no flags — depth `null` | nothing |
| `python -m partest.reports` on a file that is not a coverage.json object (a list, broken JSON, a missing file; for `stubs` / `history-append` also `endpoints` that is not a list of objects) | a traceback, exit 1 | `error: <file>: …`, exit 1; nothing is written | nothing; exit 2 is `compare --strict` on a pair that is not comparable, or a command-line argument error (argparse); 1 — an input or output file that cannot be used |
| a `validate_model=` passed without `expected_status_code=` | the body was not validated, silently | the same — and `depth` shows the cell at `status` 0, `schema` 0 | pass `expected_status_code=` |
| INFO request / response log | bodies, URL, `params=`, headers and cookies as received; `Data:` / `Params:` as a Python `repr` | masked; `Data:` and `Params:` are **JSON**, the body shortened to 8000 characters; a secret header or cookie value `***`; `Files:` lists field, file name, size and content type | a test that matched a raw body or a `repr` in `caplog` matches the masked JSON |
| httpx's own `HTTP Request: GET <url>` INFO line | the URL as sent | URL credentials and secret query values removed (a filter on the `httpx` logger, added when partest builds a client) | nothing |
| URL in a log or a message | as received | `user:password@` removed; `?token=…` → `?token=***`, also `X-Amz-Signature`, `X-Goog-Signature`, `sig`, `jsessionid` (and `;jsessionid=` in the path) and `#access_token=…`; `code` and `key` are shown | nothing |
| status mismatch message, its `status_mismatch` attachment, the ERROR line (`ErrorDesc.status`) | bodies and URL as received; the request body as `str()` of the object | masked; a dict body is shown as JSON | update a test that matched the old text |
| exception type of a status mismatch, and of `make_request`'s HTTP-error branch (`Server returned …`) | `AssertionError` | `StatusMismatchError`, a subclass — with `status_code` and `expected` | nothing; read the attributes instead of parsing the text |
| a JSON body in a message or the log | as received | **re-serialised** after masking: duplicate keys collapse, numbers and spacing are normalised (`10.50` reads `10.5`) | for a defect of the format itself look at the raw response: `attach_response(redact_body=False)` in your own call |
| `instrumented_make_request` (`TrackingApiClient`), a schema failure after a status that is in the expected set | could be reported as a status mismatch, `validation_errors` lost | re-raised as the schema failure, with `validation_errors` | nothing |
| `AssertionError` of a schema failure, and of `make_request`'s HTTP-error branch | chained to pydantic's `ValidationError` / httpx's `HTTPStatusError` (`__cause__`) | no `__cause__`, no `__context__`; the message still lists each failing path, type and message; a schema failure carries `validation_errors` (`loc`, `type`, `msg`) | read `err.validation_errors` instead of `err.__cause__.errors()` |
| `PydanticResponseError.print_error` stdout | the rejected value and `e.errors()` with inputs | the value's type only; `errors()` without `input` / `url` | nothing |
| `reporting.attach_response(...)` called by a suite | body as received unless `redact_body=True` | the same — the default is unchanged; the package's own attachments are masked | pass `redact_body=True` in your own calls |
| `attach_request` `params` / `path` / headers, `attach_check` under a secret field name, `attach_failure` text, `format_http_status_failure`, `ErrorTemplates` messages | as is; headers with an 8-character prefix | masked; a secret header or field value `***` whole | nothing |
| `redact_text` output | `"token": '***'`, `password='***'` | `"token": "***"` (the value's own quotes), `password=***`; `Basic` credentials and whole `Cookie:` lines masked | a test that compared exact masked text |
| `make_request(data={...})` without `json_data`, and a GraphQL query sent with a method other than POST | `AttributeError: 'Logger' object has no attribute 'warning'` — the request was never sent | a masked WARNING line, the request is sent | nothing |
| a header in the log, a message or an attachment | masked when it is one of the secret names (`Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key` …) | also masked when the name, without separators and a numeric or `sha…` tail, ends with `token`, `key`, `secret`, `password`, `pass`, `pwd`, `signature`, `hmac`, `assertion`, `cookie`, `auth`, `authorization`, `authentication`, `session`, `sessionid`, `sid`, `jwt`, `ticket`, `otp`, `cred`, `credential(s)` … (a `v2`-style tail is dropped too) (`CSRFPreventionToken`, `X-Authtoken`, `X-Session-Id`, `X-Hub-Signature-256`, `Ocp-Apim-Subscription-Key`; also cursors such as `X-Next-Page-Token`); `WWW-Authenticate`, `Proxy-Authenticate`, `Authentication-Info`, `Signature-Input`, `Access-Control-Allow-Credentials`, `X-Session-Expires`, `X-Api-Key-Id`, `X-RateLimit-Remaining-Tokens` stay visible | read a cursor header from the response object, not from the log |
| `make_request(..., max_retries=N)` and a status in `expected_status_code` that is also a retry status (`429`, `502`, `503`) | retried until another status came | the answer: not retried | nothing; a test of throttling now sees its `429` |
| an injected client whose `event_hooks` call `raise_for_status`, and an expected 4xx/5xx | `AssertionError` / `StatusMismatchError` "Server returned 404" | `RuntimeError` naming the hook | remove `raise_for_status` from the hook, or catch it |

What counts as a secret: for a body key, the exact name, as before (in any case, `-` / `_` / space alike); for a header in the output channels, the secret names or the end of the name (table above); for a query or fragment parameter, the secret keys plus `X-Amz-Signature`, `X-Amz-Security-Token`, `X-Amz-Credential`, `X-Goog-Signature`, `signature`, `sig`, `auth_token`, `sessionid`, `session_id`, `jsessionid` (`key` and `code` are shown). In free text the end of a secret value is decided towards masking more: a quote that may close it does not stop a bare value, and an object without its closing bracket is masked to the end of its indented block.

New and additive, nothing to change: `Rounded(..., significant=N)` and
`Rounded(..., rounding="floor" | "ceiling" | "toward_zero")`, `assert_all_agree` —
[[howto/layers]]; `partest.optin.would_select` (and `is_selected` / `selected_through` made
public), `partest.reports.optin_comparable`, `@pytest.mark.known_defect` —
[[components/overview]]. A suite that kept its own copy of any of them can switch:

| Your own helper | Use |
|---|---|
| an `unrounded()` wrapper, or a scale picked by hand for a computed float | `Rounded(value, significant=N)` |
| a sum or formula check over amounts rounded down, with a widened tolerance | `Rounded(value, scale, rounding="toward_zero")` when the digits are dropped (the usual meaning, and the only right one for amounts that can be negative — refunds, corrections); `"floor"` only when the specification says toward −∞ |
| a loop over `Agreement`s that attaches the protocol and asserts at the end | `assert_all_agree(checks, name=...)` |
| a pytest subprocess per `-m` / environment case to test `partest_optin_markers` | `would_select(marks, ini_value, markexpr, environ)` |
| a copy of `partest.reports.compare._optin_warning` | `optin_comparable(old, new)` |
| `xfail(strict=True)` on a defect reproduction | `known_defect("ID", reason=...)` — a failed setup, a network error or a gateway 502/503/504 is no longer an XFAIL (a 429 still is: throttling is the service's own behaviour); an `AssertionError` about the environment from the body (`PollTimeout`, Playwright's `expect`) still is. A suite marker of the same name has to be renamed or moved to this signature |

## 2.6.0 — coverage reads the project file when it is used, not on import

Nothing to change in a suite whose coverage report has numbers in it today and whose
`confpartest.py` imports cleanly. Behaviours that change:

| What | Before | Now | Do |
|---|---|---|---|
| `import partest` / `import partest.ui` next to a `confpartest` | read `confpartest` and fetched every spec in `swagger_files`; an unreachable URL broke the import | no project file read, no network | nothing |
| `partest.coverage.SWAGGER_AVAILABLE` / `swagger_files` / `paths_info` right after import | filled | `None` / `None` / empty until the first tracked call or report; `paths_info` is then filled in place | call `partest.coverage.get_paths_info()` |
| `monkeypatch.setattr(coverage, "SWAGGER_AVAILABLE", False)` | counting off | counting off | nothing |
| `SWAGGER_AVAILABLE = True` set by hand, nothing else | counted against what was loaded on import | not taken as "set by hand": the spec is loaded as usual | set `paths_info` / `swagger_files` too if you meant to replace the spec |
| a spec in `swagger_files` that cannot be loaded, `confpartest` on `sys.path` | the import raised, the whole session errored | `ConfpartestError` from every tracked call and from `get_paths_info()`; the message names the `swagger_files` key, without URL credentials or query. The report does not raise: it is built empty and the summary gets a `NOT COUNTED` line with the same reason (a `UserWarning` without the plugin). `active_overrides()` and `classify_endpoint` are not affected | fix the source, as before |
| an `ImportError` raised from inside `confpartest.py` | coverage silently off | `ConfpartestError` from every tracked call, `get_paths_info()`, `active_overrides()` and `classify_endpoint` (they read `subtype_overrides` from the same file); the report does not raise — `NOT COUNTED`, as above | fix the file; `python -c "import confpartest"` from the suite root |
| console `pytest`, `confpartest.py` next to the ini file, no `pythonpath = .`, no `conftest.py` beside it | coverage silently off, empty report | the file is loaded from the ini file's directory (not from an IDE's `--rootdir`); the summary names it; coverage counts. `tls_verify` from that file is read too, a relative CA path from its directory — `pytest_plugin` and `run_metadata` are not, even after the file was loaded | nothing; `pythonpath = .` is still the plain way to say it |
| the same, with `-p no:partest`, `--noconftest`, `-p no:conftest`, or an ini (`-c`) whose directory contains neither the current directory nor the test paths | as above | as before: not found. The coverage reason says where it looked | `pythonpath = .` |
| no ini file at all, and `--rootdir` pointing below the suite root (some IDEs) | as above | rootdir is searched, the file is not there: not found | keep a `pytest.ini` next to `confpartest.py`, or `pythonpath = .` |
| a bad `subtype_overrides` in a `confpartest` loaded that way | not read | `ValueError` from every classification, as for any other `confpartest` | fix the entry |
| a spec that cannot be loaded behind a `confpartest` found only in the pytest root | coverage silently off | a `NOT COUNTED` line naming the failure; the run is not failed | fix the source |
| `confpartest.py` in the root that fails to load by location | silently not read | a line in the `partest: confpartest` summary section: `pythonpath = .` for an `ImportError`, "failed while executing" for anything else | as the line says |
| a coverage report that counts nothing | zeros, nothing else | a `partest: coverage NOT COUNTED` summary section with the reason (workers' lines included under pytest-xdist); a `UserWarning` only when the partest plugin is not loaded | read the reason |
| a `swagger_files` kind written `file`, `path` or in upper case | the import failed (`Invalid source type`) | read as `local` / `url` | nothing |
| a relative `local` spec path or `subtype_overrides` file, run from a subdirectory | not found | also tried from the directory of `confpartest.py` | nothing |
| `subtype_overrides` in `confpartest` | read when `partest` was imported — dropped when the root was not on `sys.path` yet | read on the first classification; an explicit `set_subtype_overrides` / `clear_subtype_overrides` wins whichever came first; overrides from `confpartest` end with the pytest session | nothing |
| `load_confpartest()` on a file that raises something other than `ImportError` | that exception, raw | `ConfpartestError` whose message names it (`<type>: <text>`, URL credentials and query removed); the original is **not** chained, so a traceback does not print it | catch `ConfpartestError` |
| `filterwarnings = error` | — | nothing in the plugin's hooks warns; the report from `PARTEST_COVERAGE_JSON` is written either way | nothing |

## 2.5.0 — helpers a suite used to write for itself, and behaviour notes

Nothing here breaks a suite that does not use the new names. Behaviours that change:

| What | Before | Now | Do |
|---|---|---|---|
| `make_request(expected_status_code=(200, 400))` without `type=` | `TypeError` from type inference, before the request was sent | recorded; a set whose statuses imply different types is `unknown` | nothing — or pass `type=`, which was always the rule |
| a **one-element** status set (`(404,)`, `[404]`) together with a broken raw body, files or list parameters | the body/files/parameter signal decided | the set is its status: `(404,)` is exactly `404` | pass `type=` where the recorded cell matters |
| `expected_status_code=` a generator | every status check failed (`must not be empty`) | read once; works | nothing |
| `sideeffects.wait_for` | could sleep past its deadline and gave up without a last look | the last sleep is cut to the deadline and the probe is called once more there | nothing |
| a Problem Detail body with `"type": …` against `ProblemDetailBody` | `extra_forbidden` | accepted; `type` is a standard member, optional | drop a local workaround that stripped or allowed `type` |
| `ProblemDetailBody(...).model_dump()` | no `type` key | `'type': None` when the body had none | compare with `exclude_none=True`, or expect the key |
| a JSON body that fails `validate_model` | `Failed to parse JSON response and model does not expect a string` | `Response data validation failed for <Model> (N errors):`, one `path [type]: message` line per error, no values, the masked parent object for the first five nested errors; then `Response body: …`, masked and shortened — masked in this message and its ERROR log only (see Known issues in the changelog) | update a test that matched the old text; match on the `path [type]` line |
| the empty-body and string-model failures | `… for empty response: <pydantic text with input values>` | same format as above, `failed for <Model> on empty response (N errors):` | as above |

What a suite can now delete from its own code, if it carried a copy:

- a polling loop → `partest.polling.poll_until` / `poll_until_sync` ([[howto/layers]]). Put a
  token refresh inside `fetch`, not in `on_tick`.
- "value = formula of rounded inputs" with a hand-picked tolerance → `partest.rounding`
  ([[howto/layers]]).
- a `pytest_collection_modifyitems` that keeps a marker set out of plain runs → the ini option
  `partest_optin_markers` ([[components/overview]]). Behaviour to check against your copy:
  `-m "set or other"` selects a test marked with both, sub-markers are taken by prefix.
- per-test cleanup that deletes what a lazy session cache created → `CreatedRegistry.owned_by` /
  `adopt` / `cleanup_owned` ([[howto/recipes]]).
- re-zipping generated files for a stable checksum → `partest.files.deterministic_xlsx` /
  `deterministic_zip`, stored by default ([[howto/upload]]).
- a copy of `ProblemDetailBody` loosened to accept your API's extension members → subclass
  it, or use `ProblemDetailWithErrors` (`code`, `errors[]`), and pass
  `ProblemDetailValidation(model)`; undeclared members still fail, in an `errors[]` element
  too — declare the element's extra keys in a subclass ([[howto/recipes]]).

Working from a clone of the repository rather than from PyPI: `partest.env` was missing from
git until now (a `.gitignore` rule swallowed it). Wheels were not affected.

## 2.2.0 — your own httpx clients can stay inside the TLS policy

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

`-p no:partest` unloads everything, including the opt-in marker sets: if the project declares
`partest_optin_markers`, those tests then run in every plain `pytest`. Prefer the flag.

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
