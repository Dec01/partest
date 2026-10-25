# Changelog

## 2.7.0 — 2026-10-25

### Added

- **`partest.rounding`: precision by significant digits.** `Rounded(value, significant=N)`
  (instead of `scale`) — a float the service computed and did not round is good to `N`
  significant digits; the unit follows its magnitude (`effective_scale`), the digits beyond it
  are not a `RoundingNoteWarning` note, zero is exact. `Rounded(value, None, significant=N)`
  is accepted (`None` is what `scale` becomes under `significant=`); any other `scale` with it
  is a `TypeError`; `Rounded(value)` without either is still a `TypeError`, with a message. A
  value so small or large that its unit leaves ±10000 decimals is a `ValueError` naming the
  value and `N`.
- **`partest.rounding`: direction of rounding.** `Rounded(..., rounding="half" | "floor" |
  "ceiling" | "toward_zero")` (`ROUNDING_MODES`; the `decimal` constants are accepted, and
  `ROUND_DOWN` is `"toward_zero"`, as in `decimal`; `ROUND_UP` — away from zero — and
  `ROUND_05UP` are not modelled and raise `ValueError`). `"floor"` is toward −∞: amounts whose
  extra digits are dropped — "rounded down" in most specifications, refunds and corrections
  included — are `"toward_zero"`; the two differ for negative values. The interval of a value rounded one way is
  a whole unit on one side of the record — `Rounded(12.34, 2, rounding="floor")` is
  `[12.34, 12.35]` — and an output is accepted when some value the formula allows rounds to it
  in that direction; truncation is sign-dependent. Default `"half"`: every existing check
  computes the same intervals and prints the same protocol. `as_dict()` gains
  `significant` / `rounding` keys (`output_significant` / `output_rounding` for the output)
  only for values that use them.
- **`partest.rounding.assert_all_agree(checks, *, name="rounding checks")`** — one verdict on
  many `Agreement`s: the protocol of all of them attached to Allure when it is available
  (`<name>` JSON of every `as_dict()`, `<name>.txt` of every `str()`), on a pass too; one
  `AssertionError` naming every check that disagrees with its full protocol. Works without
  Allure. Returns the checks; an empty set is a `ValueError`.
- **`partest.optin.would_select(marks, optin_markers, markexpr="", environ=None)`** — whether a
  test with these marks stays in the run under this `-m` and environment, given the
  `partest_optin_markers` value as written (one string, or the `config.getini` list); pytest's
  own `-m` filter included, `-k` and other plugins not. `is_selected` and `selected_through`
  are now public (`__all__`, with `MAX_CONTEXT_NAMES`), unchanged.
- **`partest.reports.optin_comparable(old, new)`** → `(verdict, changes)`: `True` when both
  `coverage.json` payloads record the same opt-in states, `False` with `["slow: off → env", …]`
  when they differ, `None` when either has no record — or is not a payload at all (`None`, a
  list) — rather than an `AttributeError`. `compare_payloads` derives its opt-in
  warning from it; its output is unchanged except in one malformed case: a set recorded
  without a `state` on one side and absent on the other used to give an empty list in the
  warning's parentheses and now names the set (`slow: recorded without a state → absent`).
- **`@pytest.mark.known_defect("BUG-123", reason=...)`** — a strict xfail that only an
  `AssertionError` from the test body satisfies (XFAIL, reason `BUG-123: …`). Not a
  reproduction: a `StatusMismatchError` with status 502, 503 or 504 — a gateway did not let
  the request through (500 is a reproduction, and so is 429: throttling and quotas are the
  service's own behaviour; a defect that *is* a 502 is asserted explicitly, for that status
  only, see the module docstring) —, any other exception in the body (failed), an error in setup or
  teardown (error) — each with a `known_defect` report section saying so in the terminal
  and a `known_defect_note` property in JUnit XML (Allure shows the failure, not the
  section); a passing body fails as `[XPASS(strict)]`. The line is the exception's type: an `AssertionError` about
  the environment raised in the body — `PollTimeout`, Playwright's `expect` timing out —
  counts as a reproduction. `pytest.xfail()` in the body is left to pytest. The verdict is set
  inside the report wrappers of other plugins, so allure-pytest records a reproduction as
  skipped (XFAIL) and a fixed defect as failed, and pytest-rerunfailures does not re-run a
  reproduction or hold back its module fixtures' finalizers. The id goes to
  `item.user_properties` (`("known_defect", id)`, JUnit XML) and, with allure-pytest, to an
  Allure issue link. Registered by the plugin in every session (`partest/known_defect.py`);
  `--runxfail` turns it off; a marker without an id, or together with `xfail` on one test, is
  a setup error — and an `xfail` added at run time (`request.applymarker` in a fixture, also
  with `run=False`) fails the test at the call instead of turning it into an XFAIL; on a rerun
  (pytest-rerunfailures) the marker is already on the test, and setup reports it as an error.
  With `-p no:skipping` a reproduction is reported as a skip, `XFAIL BUG-123` (`-ra`). The module exports nothing: the
  marker is used through pytest. See [[components/overview]].
- **`partest.StatusMismatchError`** — what `make_request` raises when the status is not one
  it expected. A subclass of `AssertionError`, so nothing that caught `AssertionError` changes;
  `str()` is the masked message as before, and `status_code` (the status that came) and
  `expected` (the allowed statuses, a tuple) can be read instead of parsed out of the text. It
  pickles. `instrumented_make_request` re-raises it with its own message and the same two
  attributes. `make_request`'s HTTP-error branch (an injected client whose hook calls
  `raise_for_status`) raises it too: `Server returned 502: …`, `expected` from
  `expected_status_code` (empty when none was given).
- **`validation_errors` on a schema failure.** The `AssertionError` raised when
  `validate_model` rejects a body carries `validation_errors`: one `{"loc", "type", "msg"}` per
  error — pydantic's list without `input` and `url`, the message masked. It replaces reading
  `err.__cause__`, which is no longer chained (see Changed).
- **Assertion depth (axis C) in `coverage.json`, beside the percentage.** Every endpoint row
  carries `depth`: `{"cells", "status", "schema", "values"}` — of the required cells this run
  filled, in how many some call of that type **asked for** a status check
  (`expected_status_code` passed) and in how many for a schema check as well (`validate_model`
  passed too: `make_request` validates the body only after the status check, so a model without
  a status asks for nothing). The flags are the call's arguments, recorded before the request is
  sent — what was asked, not what passed; a call is recorded whether or not its check then
  fails. A cell counts at its deepest call. `values` is `null`: value asserts live in the suite's
  code and are not measured. `depth` is `null` where nothing was measured — no filled required
  cell, an `exception` row, calls recorded without the flags. The flags are read through the
  tracked function's signature, so a status passed positionally counts and a default status of
  the client counts too; a wrapper without that parameter but with `**kwargs`
  (`make_request(self, method, endpoint, *args, **kwargs)`) is read from its keyword arguments,
  as before; a function with neither records no flags — its depth is "not measured", not a
  measured zero. The signature is read with annotations as forward references (Python 3.14+),
  and a signature that cannot be read at all also means "not measured": decorating never
  fails. `summary.depth` pools the counts over
  the run and adds `statusPct` / `schemaPct` (share of measured cells, 0..100), `null` when no
  cell was measured. **The percentage does not change** — the cell, P1/P2/P3 and `coverage` are
  computed as before. Shown in both HTML reports (header tiles "Cells: status asked" / "Cells:
  schema asked", a Depth column), in the text summary of `zorro()`, and in `compare_payloads` as
  `depth_delta` (`{"statusPct", "schemaPct"}` in points, `null` when either side has no
  `summary.depth`). `validate_coverage_payload` checks the new keys when present (`cells` ≥
  `status` ≥ `schema` ≥ 0, a zero-cell object instead of `null`, depth on an `exception` row or
  on a row with no calls, `summary.depth` against the rows and its shares); a missing
  `summary.depth` is `DATED` in a file without row depth and an error in a file whose rows carry
  it. `EndpointCoverage.depth` carries the same per endpoint. Proposals F1, option 2.
- **`partest.methodology.api.steps.call_depth(has_status, has_validate_model)`** — the level a
  call asked for: 0, 1 (status) or 2 (schema); a model without a status is 0. The report's
  depth uses it, and so does `depth_score` (see Changed). Declared in the module's new
  `__all__` (`TestStep`, `STEPS_BY_GROUP`, `call_depth`, `depth_score`) and re-exported, with
  `depth_score`, from `partest.methodology.api` and `partest.methodology`.
- **`CoverageReport.scored_count`** — a read-only property: the rows `average_pct` is taken
  from (all but `exception`), counted from `endpoints` each time it is read, so it follows a
  `dataclasses.replace` or an edit of `endpoints`; `0` means `average_pct`'s `0.0` is "not
  measured". The constructor is unchanged.
- **`Severity.NEWER`** in `partest.reports.validate`: the document follows a rule newer than
  this package (`meta.avgRule` above 2) — not an error; the checks that depend on the rule are
  skipped.

### Security

- **`Pillow>=13.0.0` on Python 3.11+, in the core dependencies.** The advisories `pip-audit`
  knew on 2026-10-25 as open in Pillow 12.3.0, the previous floor — CVE-2026-112405,
  CVE-2026-96636 to -96644 and GHSA-78g4-xqwv-q3g8 among them; OSV lists more since — are
  fixed in 13.0.0. Reachable from partest: PIL decodes foreign input only in
  `partest.ui.visual.compare_images` (`Image.open` on the baseline and the screenshot —
  reachable when those files are not trusted); `allure_graph` only encodes a PNG matplotlib
  drew. The floor
  goes into `install_requires` with the marker `python_version >= "3.11"`, not only into the
  `ui` extra: matplotlib, a core dependency, pulls Pillow into every install, so a consumer
  without `ui` would otherwise keep whatever matplotlib accepts. Run on 3.14 with Pillow
  13.0.0: `compare_images` and the `allure_graph` chart unchanged.
- **Python 3.10 stays on Pillow 12.3.0 with those advisories open.** Pillow 13.0.0 declares
  `Requires-Python >=3.11` and no 12.x release fixes them, so on 3.10 there is nothing to raise
  the floor to beyond 12.3.0. That floor now sits in `install_requires` too
  (`python_version < "3.11"`), so a 3.10 install without `ui` no longer takes an older Pillow
  from matplotlib. The same reachability applies (`compare_images` on files that are not
  trusted); the fix on 3.10 is to upgrade to Python 3.11+. `requirements.txt` lists both lines, so `pip-audit -r` reports against the
  floor of the interpreter it runs on.

### Changed

- **`exception` endpoints are left out of every average** (proposals F1, option 3). A row on
  which a call recorded an exception type (`health`, `test_types_exception`) keeps its 100 % and
  its `exception` status, and is still counted in `summary.exception` and `totalEndpoints`; it no
  longer enters `summary.avg` / `avgAll`, `avgCoverage` of a service, subtype or method row, the
  heatmap average, or a service's `covered` (now `full + partial`). Before, one health probe
  lifted the average as much as a fully tested endpoint — so **averages move down (never up)** on
  any run with such rows; on a run without them nothing changes. The rows the averages and
  `covered` are taken from are counted in a new `scored` (`totalEndpoints − exception` for a
  service; in `summary`, `subtypes` and `methods` too, which also gain `exception`). A set of
  `exception` rows only has no average: `summary.avg` / `avgAll`, `avgCoverage` and a heatmap
  cell are `null` (a service of health probes only sorts last). The payload says which rule it
  follows: `meta.avgRule: 2`; a file without the key was written under rule 1.
  `compare_payloads`: when one side has no `meta.avgRule` and has `exception` rows, its average
  is **recomputed from its rows without them**, the pair stays comparable, a `notes` line says
  so and the new key `avg_recomputed` gives `{"side", "recorded", "recomputed"}`; only when its
  rows are not all in the file (a trimmed list) does a warning make the pair not `comparable`.
  Without `exception` rows both rules give the same number and nothing is added. A rule this
  package does not know (an integer above 2, or not an integer) is not read as rule 1: a warning,
  not `comparable`, the averages as recorded. A run whose endpoints are all `exception` gets the
  "no scored endpoints" warning and a `null` delta. `validate_coverage_payload`: `meta.avgRule`
  is an integer, 1 or 2 (absent — `DATED`; above 2 — `NEWER`; anything else — an error); under
  rule 2 `null` is required exactly when no row outside `exception` exists; a file without the
  key is checked as before. `summary.full` / `partial` / `empty` / `exception` are now checked
  against the rows' statuses (`empty` takes every status that is not one of the other three),
  the same rule by which `compare` decides an older file can be recomputed. `CoverageReport.average_pct` and the `by_subtype` / `by_swagger`
  buckets of `analyze_coverage` follow the same rule; their types do not change (`0.0` when
  nothing is scored; a bucket now carries `scored`), and the simple HTML and the `zorro()` text
  summary print `n/a` where `scored` is zero. The interactive page follows the file's
  `meta.avgRule` and, for a rule it does not know, shows the file's own `summary.avg` instead of
  recomputing.
- **`partest.methodology.api.steps.depth_score`**: a `validate_model` without a status check no
  longer adds a point (`depth_score(False, True)` is `0`, was `1`) — the same rule as
  `make_request`, which does not validate such a body, and as the report's depth.

- **`summary.avg` and `summary.avgAll` in `coverage.json` are `null` when the run collected no
  endpoints.** An average over no endpoints is not a measurement, and `0.0` read as "nothing is
  covered" — the number a run that called everything and covered nothing would give. Same
  contract as `meta.unseenRatio` (2.3.0): the type widens from `float` to `float | null`; a
  measured zero is still `0.0`; this does not make `avgCoverage` of a service, subtype or method
  row `null` (a row exists only because an endpoint is in it — it is `null` only when every
  endpoint in it is `exception`, see the entry above); nothing else in the format changes.
  **Readers that do arithmetic on it must check for `null` first.** Inside the package:
  `badge` draws a grey `n/a` instead of a red `0.0%` (`badge_svg(None)`); `compare_payloads`
  gives `null` for that side's `old_avg` / `new_avg` and for `avg_delta` / `coverage_delta`
  instead of the other run's whole average, and adds a warning that makes the pair not
  `comparable`; the HTML page shows `—`; `validate_coverage_payload` accepts `null` only with
  zero endpoints, reports `null` with endpoints as an error, `0.0` with zero endpoints as
  `DATED` (that is how every earlier release wrote it) and any other number there as an error;
  with endpoints, an average that is not a number or lies outside 0..100 is now an error too.
  An older snapshot's `0.0` for a run with no endpoints (`summary.endpoints == 0` or
  `endpoints: []`) is read the way the validator reads it — not measured: `compare` gives
  `null` and a warning, `badge` `n/a` — so a 2.6 baseline of an empty run no longer turns the
  next run's whole average into a delta of a "comparable" pair. A `0.0` with endpoints stays
  a measured zero, and a missing key reads as `0.0`; a numeric `summary.endpoints` decides
  over the list (a payload trimmed to `endpoints: []` with `summary.endpoints: 12` is a
  measured `0.0`). `python -m partest.reports compare --strict` exits with code 2 on a pair
  where either side measured nothing. **The return type of `compare_payloads` widens with
  it:** `old_avg`, `new_avg`, `avg_delta` and `coverage_delta` are `float | None` — a
  deliberate change under the `coverage-payload` contract (decided 2026-09-24: a missing
  measurement is `null`, not zero; precedent `meta.unseenRatio`, 2.3.0). See
  [[howto/coverage-html]].
- **What the package shows of a request or response is masked in every channel.** One rule
  for all of them: a structure is walked — a value under a secret key (`token`, `password`,
  `Authorization`, `Cookie`, `Set-Cookie` …) becomes `***` whole, no prefix kept, at any depth
  (beyond 32 levels the whole value is replaced); any other string gets only narrow patterns
  — URL credentials and secret query values, `Bearer` / `Basic` credentials, a JWT — so a body
  that merely *names* a field (`{"missing": ["password", "email"]}`, `{"field": "password"}`,
  `"token: expired"`) stays readable and stays valid JSON; a string holding JSON is walked too
  (a byte-order mark in front is ignored); pydantic models, dataclasses, bytes and sets are
  walked, and a container met again on its own path is `"<cycle>"`. A key is matched in any
  case and with `-`, `_` or a space alike (`client-secret`, `Access-Token`), an Enum key by its
  value, a bytes key decoded. A header is secret when it is one of the secret names
  (`Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key`, `X-Auth-Token`
  …) or when its name — lower case, without `-`, `_`, spaces and a numeric or `sha…` tail —
  ends with `token`, `key`, `apikey`, `secret`, `password`, `passwd`, `pwd`, `passphrase`,
  `signature`, `cookie`, `authorization`, `authentication`, `auth`, `session`, `sessionid`,
  `sid`, `jwt`, `ticket`, `otp`, `credential`, `credentials`, `pass`, `cred`, `assertion` or `hmac` (a
  `v2`-style tail is dropped as well): `CSRFPreventionToken`,
  `X-Authtoken`, `PVEAuthCookie`, `X-RestSvcSessionId`, `X-Session-Id`, `X-Hub-Signature-256`,
  `Ocp-Apim-Subscription-Key` are masked; `WWW-Authenticate`, `Proxy-Authenticate`,
  `Authentication-Info`, `Signature-Input`, `Access-Control-Allow-Credentials`,
  `X-Session-Expires`, `X-Api-Key-Id`,
  `X-OAuth-Scopes`, `X-RateLimit-Remaining-Tokens`, `X-Request-Id` are not. A message that quotes one element of a body (`in token = …` of a schema
  failure) masks it as the whole body would — `***` when a key on the path is secret. Text
  that is not JSON gets the full `redact_text`. Bodies are then shortened; a value that cannot
  be masked is shown as a placeholder, never raw. In a URL `user:password@` is removed (also
  with `@` or `/` in the password, and without a scheme); the values of secret query and
  fragment parameters become `***` — the secret keys plus names that mean one thing only:
  `X-Amz-Signature`, `X-Amz-Security-Token`, `X-Amz-Credential`, `X-Goog-Signature`,
  `signature`, `sig` (an Azure SAS signature is access), `auth_token`, `sessionid`,
  `session_id`, `jsessionid` — also as `;jsessionid=` in a path, and also as a pair in text
  outside a URL (`sv=1&sig=…`) — with `&` or
  `;` between them, and `#access_token=…`. **A JSON body in a message or the log is
  re-serialised**: duplicate keys collapse, numbers and spacing are normalised (`10.50` reads
  `10.5`); for a defect of the format itself look at the raw response —
  `attach_response(redact_body=False)` in your own call. Public `redact_mapping` and
  `redact_headers` are unchanged. This closes the 2.5.0 Known issues.
  What you will see differently:
  - the INFO request / response log (`Logger.log_request` / `log_response`): `Data:` and
    `Params:` are **JSON instead of a Python `repr`**, masked, the body shortened to 8000
    characters (it was whole); the URL masked; headers masked (a secret one `***` whole, a
    `Location` / `Referer` URL through the URL rule); cookies by name with `***`; `Files:` is
    field, file name, size and content type — never the content. Nothing is computed when INFO
    is off. `Logger.error`, `warning` and `log_str` mask their text;
  - httpx's own INFO line `HTTP Request: GET <url> …`: a filter on the `httpx` logger removes
    URL credentials and secret query values. It is added once per process when the package
    builds a client (`ApiClient`, `httpx_client`, `httpx_async_client`), not on import; no
    record is dropped;
  - the status mismatch message (`format_status_mismatch`, its `status_mismatch` attachment):
    URL, request headers and both bodies masked — a dict body is shown as JSON rather than its
    `repr`; the ERROR line `ErrorDesc.status` and `ErrorDesc.element` mask and shorten (2000
    characters), and a body that cannot be read is a placeholder instead of an
    `UnboundLocalError`; `response hook failed: …` is masked;
  - a schema failure's `AssertionError` is raised without `__cause__` and `__context__` (as
    `ConfpartestError` is since 2.6.0): pydantic's `ValidationError` printed `input_value=…`
    in the traceback. The message lists every failing path, type and message, and the same
    list is on the error (see Added). The same for `make_request`'s HTTP-error branch
    (`Server returned …`); its ERROR line and `Network/request error: …` are masked;
  - `PydanticResponseError.print_error` (stdout of `BaseResponseValidator.validate_*`) shows
    the rejected value by type only (`<str, значение не показывается>`) and the error list
    without `input` / `url`;
  - Allure: every attachment the package makes is masked — `attach_request` (headers,
    `params`, the query in `path`, the body unless `redact_body=False`), `attach_check` and
    the `list_lookup` of `check_in_list` (a value under a secret field name is `***`, the step
    title too), `attach_failure` (text through the free-text rule), `format_http_status_failure`
    and the `ErrorTemplates` messages (path, bodies, Problem Detail summary,
    `Original error: …`, `Entity context:`), and in `instrumented_make_request`
    (`TrackingApiClient` with instrumentation) the step title, the response attachments, the
    `status_mismatch` JSON with its `entity_hint`, and `failure_details`. The package's own
    calls of `attach_response` pass `redact_body=True`; **the public default of
    `attach_response(redact_body=False)` is unchanged** — flipping it is a major change,
    planned for 3.0;
  - `check_in` / `check_not_in` step titles and expectations, and the values quoted by
    `sideeffects.assert_locator`, `assert_status_enum` and `Observation.require`, are masked;
  - outside the HTTP client: the plugin's `failure_summary` attachment, `TokenManager`'s
    errors (the token response and the OIDC error body), and `partest.ui`'s failure context
    (the page URL, network, console and page errors);
  - when `instrumented_make_request` meets a schema failure under a status set
    (`expected_status_code=(200, 201)`, `201` came), it re-raises the schema failure with its
    `validation_errors` — it no longer turns it into a status mismatch;
  - `redact_text`: `Basic <credentials>` and a whole `Cookie:` / `Set-Cookie:` header line are
    masked. Where the value of a secret key ends is decided towards masking more — in free
    text a quote cannot be told apart from an apostrophe, a lone quote in an error message or
    an SQL literal, and a lost piece of text is cheaper than a shown secret. A quoted value
    (`"…"`, `'…'`, `b'…'`, `\"…\"`) runs to the same quote that is not followed by a letter or
    a digit (`'it''s'` included), else to the end of the line; an object or an array to its
    balancing bracket — a bracket inside a string in either quotes does not count, and when
    an apostrophe leaves the pair unfound the value falls back to the end of the indented
    block it opens (deeper-indented lines and a closing line at the key's indent) — never past
    the package's `... [truncated, N chars total]` marker, which counts only at the very end
    of the text (a marker in the middle is data); a bare value to whitespace, `&`, `;`, `,` or a closing bracket — a quote is part
    of it, so `password=abc"def` is masked whole and `"q": "token=abc"` loses its closing
    quote too. A quoted value keeps its quotes (`"token": "***"`); `('key', 'value')` is
    masked only as a tuple — `["password", "email"]` and `"field": "password", "message": …`
    are untouched. A quoted value may carry a `b`, `r`, `u`, `f` or `N` prefix. A PEM
    private key (`-----BEGIN … PRIVATE KEY-----` … `-----END …-----`) is masked whole,
    whatever key it sits under. Time grows linearly with the text;
  - text the package already masked is not masked a second time: the ERROR lines of
    `ErrorDesc`, the `failure_summary` and `failure_details` of a status mismatch, a schema
    failure, a `check_*` failure or a `PollTimeout`, `Original error:` of
    `format_http_status_failure` from `instrumented_make_request` — a second pass read their
    JSON as free text (`"detail": "token: expired"` lost its value and closing quote,
    `"password": ""` became `"***"`). What counts is a private mark the package sets on the
    exception it raises; a suite's own `StatusMismatchError` with raw text, or any exception
    carrying `validation_errors`, is masked like other text. In `failure_details` only the
    exception's own last line is kept as is — the traceback's frames (source lines) and its
    chained exceptions are masked;
  - `PollTimeout` and `sideeffects.wait_for` messages follow the same rule (key spellings,
    URLs, signed query values, JWTs), their description (`what=`) included;
  - `check_*`: the `context`, the `detail` of a precondition, the default context of
    `check_status_in` (method and path) and the value `check_ne` must not equal (in its step,
    its `check:` attachment and its message) are masked;
  - `Bearer realm="api", error="…"` — a `WWW-Authenticate` challenge — keeps its parameters;
  - `print_error` masks the values in its error list (`msg`, `ctx`) and leaves the path
    (`loc`) as it is: a path is field names, not values.
  What counts as a secret: for a body key — the exact name, as before (in any case, `-` / `_`
  / space alike); a key that only contains one (`accessToken`, `clientSecret`,
  `new_password`) is not masked. For a header in the output channels — the secret names or
  the end of the name, as above. For a query or fragment parameter — the secret keys and the
  names above. For a value of a `check_*` or of `sideeffects` (its message, step title,
  `context=` and `check:` attachment) — free text at every level: each string, `bytes` value
  and text key, at the top, in a dict, a list, a tuple or a set, gets the whole text rule
  (`password: …` included), the structure and valid JSON staying up to the attachment's cut
  at 8000 characters, and a value is shortened only after it is masked; a status is shown as a
  number (an `HTTPStatus` as its code), anything else in its place is masked — in the
  `ErrorTemplates` messages and the `StepTemplates.http` title too. `check_not_startswith`
  masks its text as free text without reading it as JSON, so a leading BOM, space or line
  break stays visible. One walk opens at most 100 000 containers — for HTTP bodies and check
  values alike — so shared references (a DAG, YAML anchors) no longer take exponential time;
  past that a container is `<too large>` — kept apart from `***` (a secret, or the depth limit). HTTP bodies keep
  the body rule. A test that matched a raw body or value in a log, a message or an attachment has to
  match the masked text. See [[howto/enterprise]].

### Fixed

- **The interactive report put numbers from `coverage.json` into the page as markup.** `calls`,
  `coverage`, `timing.msAvg` / `msP95` and the depth counts were inserted into `innerHTML`
  without escaping, so a string in a numeric field of a file rendered with
  `python -m partest.reports render` ran as HTML. Every number is now converted before it is
  shown (a non-number reads as `0` or `—`), and the one data string newly shown — an unknown
  `meta.avgRule` — is escaped.
- **`validate_coverage_payload` and `compare_payloads` raised on numbers JSON allows and a float
  does not hold.** An integer of 400 digits, `Infinity` or `NaN` in
  `summary.avg`, `unseenRatio` or `summary.depth` raised `OverflowError` (or compared as a
  value); the validator now reports it as an error and `compare` reads it as "not a
  measurement". `compare` no longer raises on a `summary`, `meta` or `selection` that is not an
  object, and reads a value of the wrong type in a row or in `meta` (a number where a text
  belongs, a text where a count belongs, a `missing` that is not a list, an integer of
  thousands of digits) as absent instead of raising; an older file whose rows carry such
  values is not recomputed (a warning instead).
- **The simple HTML report (`zorro()`) put endpoint paths into its chart as markup**, and a
  path containing `</script>` closed the chart's script block. The chart data is escaped for
  a script block and the labels are inserted as text.
- **The interactive report broke on some files**: `NaN` / `Infinity` (which `json.loads`
  accepts) made the page's `JSON.parse` fail and the page empty — they are rendered as "no
  value" now; a service, subtype, method or status named `constructor`, `__proto__` or another
  inherited property name raised in the page's grouping; a `meta` that is not an object
  stopped the page. A `meta.avgRule` written as `2.0` is an unknown rule on the page, as in
  Python.
- **`python -m partest.reports` on a file that is not a JSON object** (a list, broken JSON, a
  missing file, JSON nested too deep to read) printed a traceback; it prints
  `error: <file>: …` and exits **1**. `stubs` and `history-append` also refuse a document of
  the wrong shape (`endpoints` not a list of objects; for the history, `meta` or `summary` not
  an object) instead of writing stubs or a snapshot from it, and a file that cannot be written
  (`--out`, `--html`, `--dir`) is `error: …`, exit 1 too. Exit code 2 is `compare --strict` on
  a pair that is not comparable, or a command-line argument error (argparse); 1 is an input or
  output file that cannot be used. `history-append` writes `NaN` / `Infinity` from its input
  as `null`. The `--strict` help lists the reasons as
  examples of `warnings`.
- **`python -m partest.reports stubs` wrote strings from `coverage.json` into Python source as
  they were.** A `path` such as `/x", __import__("os").getcwd(), "` became an expression in the
  generated module, and a line break in it closed the docstring — code that ran when pytest
  collected the stubs. Method and path are written as `repr()` literals, the docstring keeps
  only letters, digits and path punctuation, and a missing type that is not a plain name
  (`[A-Za-z0-9_]`) is skipped with a comment; a row of the wrong type is skipped, and
  `endpoints` that is not a list is a `ValueError` from `generate_stubs`. Two stubs that would
  get the same name get a numeric suffix instead of replacing each other.
- **A payload method (`_json_main`, `_required` on a `partest.payloads` body) annotated with a
  name imported under `TYPE_CHECKING`** was called without `self` on Python 3.14 (its signature
  could not be read);
  the signature is read with annotations as forward references.
- **A parametrized test with an integer of thousands of digits among its parameters** made
  the plugin's Allure title raise an INTERNALERROR on collection (Python 3.11+); the value is
  shown by its type.
- **An expected status was retried.** With `max_retries` set, a call that expects `429` (a
  test of throttling) — or `502` / `503` — was repeated until something else came back, and
  failed on a status it never asked for. A status in `expected_status_code` is the answer now,
  never retried; other statuses retry as before.
- **A hook that rejects the expected status is not reported as the service's fault.** An
  injected httpx client whose `event_hooks` call `raise_for_status` turned an expected `404`
  into an `AssertionError` ("Server returned 404") — and `instrumented_make_request` into
  "expected 404, got 404". That is a `RuntimeError` now, naming the hook; a status outside the
  expected set is still a `StatusMismatchError`.
- **The ERROR line of a schema failure was the `repr` of a tuple**: `ErrorDesc.validate`
  returned a tuple, which went to the log as one line with literal `\n`, and masking a
  `token = …` in it ran on into the text after it. It returns one string now, line by line.
- **`make_request(data={...})` without `json_data`, and a GraphQL query sent with a method
  other than POST, raised `AttributeError: 'Logger' object has no attribute 'warning'`** before
  the request was sent: `ApiClient` logged a warning through `partest.utils.Logger`, which had
  no such method. `Logger.warning(message)` exists now and masks its text like the request log
  (`redact_text`, `user:password@` in a URL); both calls send the request with a WARNING line.

### Documentation

- Installing right after a release: pip may answer from its cache and not see the new version
  — `pip install --no-cache-dir "partest==X.Y.Z"` ([[howto/quickstart]], [[howto/migration]]).
- The `partest-cover-api` skill said GET `.../{parent}/{id}/children` is classified
  `get_by_parent`; the classifier never did that — no path is read as GET BY PARENT, it comes
  from `subtype_overrides` only, and the table says so. "An explicit subtype override is not
  available yet" (it is, since 1.7) is gone. [[concepts/methodology]] says which shape the
  classifier does not try to read and why. (A GET BY PARENT branch and an unused pattern
  were removed from `classifier.py`: for every valid path the subtype is the one 2.6.0 gave; in 2.6.0 GET BY PARENT went only to a malformed template with two or more `/` inside braces (`/a/b/{x/y/z}`), and such a path is now read by the general rules — usually GET DYNAMIC, GET LIST or GET STATIC with list or static hints.)
- 2.6.0: `load_confpartest` does not chain the original exception (`raise … from None`, by
  design); [[howto/migration]] said "with it chained". Which calls raise `ConfpartestError`
  for which failure is corrected in 2.6.0 Changed, in [[howto/migration]] and in the status
  page, by the code: the report never raises, it reports `NOT COUNTED`.
- `partest.tools.generate_init` (docstring, `--directory` help) and [[howto/recipes]] gave
  `src/api/resources` as the example — in a partest-gen tree that takes the generator's
  `__init__.py` files from it. The example is now a hand-written package, with the warning
  partest-gen 1.2.1 gives.
- `reset_storage`: once, before the `yield` of a session fixture. After it, the
  `PARTEST_COVERAGE_JSON` report and the xdist shards, written in `pytest_sessionfinish`, see
  an empty run (docstring, [[howto/quickstart]], the `partest-cover-api` skill).

### Known issues

- A key that only *contains* a secret name (`accessToken`, `clientSecret`, `sessionId`) is
  still not masked: widening what counts as a secret changes `redact_mapping`'s defaults —
  a major version, the owner's decision (`docs/wiki/proposals.md` §E2). The same class, and
  the most likely to carry a real password: `new_password`, `current_password`,
  `password_confirmation`, `DB_PASSWORD=` in text, and Keycloak's
  `{"type": "password", "value": …}` (the secret is under `value`).
- The text rule does not know these shapes: `key => value`, a value on the next line, a value
  escaped more than once, a URL-encoded pair outside a URL, a full-width colon `：`, a tuple of
  bytes `(b'token', b'…')`, a bare value with a space or a separator inside; nor a secret in a
  path segment (`/reset/<token>`).
- `key` and `code` in a URL are not masked: as bare names they also mean a sort key or a
  country code (`?code=RU`). So a Google API key in a URL (`?key=…`) and an OAuth
  authorization code in a redirect's `Location` (`?code=…&state=…`) are shown as sent.
- A header whose name ends like a secret but carries none is masked too — a cursor
  (`X-Next-Page-Token`), `X-Idempotency-Key`: the header rule errs towards masking. A project
  cannot add its own header names to the output channels (a setting is an open question,
  `proposals.md` §E2).
- A secret in a quoted value that spans lines with a real line break is masked only to the
  end of its first line.
- The text rule also misses: a value in triple quotes (`'''…'''`, `"""…"""`) or one that starts
  with a quote of its own; a value whose own quote is followed by a non-letter
  (`password="ab"-…"` ends at the first quote); headers `X-Auth-Code`, `X-2FA-Code`,
  `X-Csrf`, `X-Xsrf`, `Remember-Me`, and a Kubernetes token in `Sec-WebSocket-Protocol`.
- A map of validation errors under a secret field name (`{"errors": {"password": ["is too
  short"]}}`) is masked whole: the message about the password is lost with it.
- Two apostrophes in hand-written text can hide brackets between them and close a secret
  value early: in `token: {a: it's {b: c'}, d: …}` the part after `c'}` is shown.
- Not recognised as a private key: `-----BEGIN PGP PRIVATE KEY BLOCK-----`, and a BEGIN label
  longer than 40 characters. Not secret header names: `X-Sig`, `Passcode`.
- `user:password@` without a scheme is looked for in every text; on a body of megabytes this
  costs about 0.8 µs a character.
- Keys in a body that name a secret without being one of the exact names — `auth`,
  `credentials`, `pwd`, `pass`, `creds`, `secret_key`, `session`, `jwt`, `ticket`, `otp`,
  `signature`, `sig` — and text like `DB_PASSWORD=…`, `MY_TOKEN=…`,
  `AWS_SECRET_ACCESS_KEY=…`, `token …` are not masked: the same class as a key that only
  contains a secret name, the maintainer's decision. The shown size of a check value is not
  limited before the attachment's own cut.
- A value of a `check_*` is masked as free text at every level, so prose in it loses a value
  that merely follows a secret word: `{"detail": "token: expired"}` reads
  `{"detail": "token: ***"}` there (in HTTP bodies it stays readable). The value is the test
  author's, and anything may be in it — closed when in doubt.
- An unquoted challenge parameter (`Bearer error=…`, `Bearer realm=…`) is not masked. The
  mark that says "already masked" sits on the exception, not on its text: a subclass with
  its own `__str__`, or `args` rewritten after the fact, is shown as it then reads — that
  takes intent.
- `attach_response` still attaches the body as received by default when a suite calls it
  itself; the package's own calls mask. The default flips in 3.0 (`proposals.md` §E2).
- A secret inside an XML body (`<password>…</password>`) is not masked: the text rule knows
  `key: value` / `key=value` shapes, not tags.
- Also not masked: a multipart body sent through `content=`; `Authorization: Token …`,
  `Digest …` or `AWS4-HMAC-SHA256 …` in unquoted text (only `Bearer` and `Basic` are known
  schemes there; in a header dict the whole value is masked); a scheme-relative
  `//user:password@host`; a value without its key in the `msg` of a custom pydantic validator.
  A `logging.config.dictConfig` that configures the `httpx` logger replaces its filters,
  partest's included, until partest builds its next client.
- `-p no:partest` removes the `known_defect` marker with the rest of the plugin; under
  `--strict-markers` a suite using it then fails at collection.
- A suite with its own `known_defect` marker — its own hooks reading it, or another signature
  (no id as the first argument) — now meets the plugin's too: every such test is a setup error
  (`needs the defect id`) or is judged twice. Rename the suite's marker, or move it to the
  plugin's signature `known_defect("ID", reason=...)` and drop the suite's hooks.

## 2.6.0 — 2026-10-18

### Added

- **`confpartest.py` next to the ini file is found when that directory is not on `sys.path`.**
  A console `pytest` without `pythonpath = .` and without a `conftest.py` beside the ini file
  does not put it on `sys.path`, so a plain import does not see the project file. The plugin
  now reports the directory (`pytest_configure`: the ini file's, else pytest's rootdir — an
  IDE's `--rootdir` does not move it), and the coverage specification, subtype overrides,
  report settings, `conf_attr` (so `tls_verify`) and `load_confpartest` load
  `<dir>/confpartest.py` by location in that case. The summary names the file it loaded, in a
  `partest: confpartest` section. Limits: not with `--noconftest` or `-p no:conftest`; only
  when the directory contains the current directory or every test path (an ini named with
  `-c` elsewhere belongs to another project); never for the plugin's own switches
  (`pytest_plugin`, `run_metadata`) — they are read in every session, a UI-only one included,
  and do not see a module loaded this way even after something else loaded it. The module is
  unloaded when the session ends. A file there that fails to load is not an error: the summary
  says why — `pythonpath = .` is suggested only for an `ImportError` — and the run goes on
  without it. What a loaded file *says* is checked as anywhere else: a bad `subtype_overrides`
  in it raises. With `-p no:partest` no directory is reported, so none of this happens.
- **A coverage report that counts nothing says why.** When `analyze_coverage` — and so `zorro`,
  `zorro_enhanced`, the plugin's `PARTEST_COVERAGE_JSON` report — builds a report with no
  specification behind it (no `confpartest`, `swagger_files` empty, the spec failed to load,
  counting switched off by hand), the terminal summary gets a `partest: coverage NOT COUNTED`
  section with the reason and where the lookup looked. This holds when the report still has
  rows: under pytest-xdist the controller merges the workers' calls but loads the spec itself.
  Under pytest-xdist the workers' lines reach the controller's summary. Outside the plugin,
  where there is no such section, it is a `UserWarning`. The report and `coverage.json` are
  unchanged, and are still written under `filterwarnings = error`.

### Changed

- **The coverage specification and `subtype_overrides` are read on first use, not when
  `partest` is imported** — on the first tracked call, report, classification or
  `active_overrides()`. Importing `partest`, `partest.ui` or anything from them now reads no
  project file and does no network I/O; before, an unreachable spec URL broke
  `from partest import httpx_client` and every pytest session the plugin loaded into.
  Consequences for code that reached into `partest.coverage`: `SWAGGER_AVAILABLE` is `None`
  until something asks (`True`/`False` after), `swagger_files` is `None`, `paths_info` is an
  empty list that is filled in place — call `get_paths_info()` rather than reading the names
  right after import. Setting `SWAGGER_AVAILABLE = False` yourself still switches counting off;
  `True` alone is not taken as "set by hand". A pytest session starts from what was decided
  before it and puts that back when it ends: sequential sessions in one process each read their
  own project, and a nested in-process session (`pytester`) hands the outer one its state
  back. A `confpartest` imported from `sys.path` is not part of that state — it stays in
  `sys.modules`, and a later or nested session sees it.
- **Failures move to where coverage is used, and stay loud.** A `confpartest` that raises while
  importing — an `ImportError` from inside it included, which used to switch coverage off
  without a word — and a spec in `swagger_files` that cannot be loaded raise
  `ConfpartestError` from every tracked call and from `get_paths_info()`; a `confpartest` that
  fails to import raises it from `active_overrides()` and `classify_endpoint` as well, since
  they read `subtype_overrides` from the same file — a spec failure does not touch them. The
  report never raises: it is built empty and says why under `NOT COUNTED` (see Added).
  *Corrected in 2.7.0:* this entry and the migration table named `active_overrides()` and
  `classify_endpoint` for both failures, and the migration table said the report raised too.
  Either failure is raised again on every later call (it is kept; the fetch is not
  retried). The message names the source by its `swagger_files` key; URL credentials and
  query strings are removed from it, and the original exception is not chained, so a traceback,
  junit XML or Allure result does not print it either; the raw sources are not among the locals
  `pytest -l` shows. The same holds for `openapi.resolve_swagger` failing to fetch — not for a
  spec it fetched but cannot parse: that error quotes a piece of the document and keeps the
  parser's exception chained. `resolve_swagger` also moves `user:password@` from the URL into
  `auth=` and keeps the query string out of httpx's INFO `HTTP Request:` line (a filter on the
  `httpx` logger for that one request; the consumer's logging setup is not changed). Loading the
  spec for coverage goes through `requests`, whose INFO output is clean but whose `urllib3`
  DEBUG line shows the path with its query string. Exception: a `confpartest` found only by
  location turns a spec failure into a `NOT COUNTED` line instead — such a run was green
  before.
- **Relative paths in `confpartest` are also tried from its own directory.** A local spec in
  `swagger_files`, a `subtype_overrides` file and a `tls_verify` CA bundle path that do not
  exist from the current directory are taken relative to the directory of `confpartest.py`, so
  `cd tests && pytest` and IDE runs find them; `openapi.resolve_from_confpartest()` without
  `project_root` does the same. A path that exists from the current directory keeps its
  meaning. Source kinds are read as `validate_confpartest` accepts them — `local`, `file`,
  `path`, `url`, in any case — where the coverage loader took only `local` and `url`.
- **`load_confpartest` / `require_confpartest` raise `ConfpartestError` for any failure of the
  file**, not only `ImportError`; a `SyntaxError` or a failing statement came out raw. Every
  reader of `confpartest` in the package — `conf_attr`, `load_confpartest`,
  `openapi.resolve_from_confpartest`, the coverage loader, subtype overrides and the report's
  `test_types_coverage` / `test_types_exception` — now finds it the same way.

### Fixed

- **Coverage was silently empty when `confpartest` was not importable at plugin load.** The
  plugin is an entry point, so `partest` was imported — and `confpartest` read — before pytest
  had put the suite root on `sys.path`. See Added and Changed above.
- Loading the specification is serialised between threads: two threads making the first
  tracked call at once load it once. A thread that only reads a switch does not wait for it.
- Cleaning error text of URL credentials takes linear time; it was quadratic on text built to
  look like many half-URLs (a 64 KB response body quoted in a message took seconds). An object
  address (`<... at 0x...>`) is dropped from the text, so one failure seen by several xdist
  workers is one summary line.

### Not changed: the UI isolation rule in a pytest session

Importing `partest.ui` reads no project file and does no network I/O — guaranteed and tested
in a fresh interpreter. A pytest session whose root is on `sys.path` (`pythonpath = .`, a root
`conftest.py`) still imports `confpartest` to read the plugin's `pytest_plugin` switch, a UI-only
session included, exactly as in 2.5.0; the lookup by location above does not add to that. Whether the
rule should forbid it is open (`docs/wiki/proposals.md`).

### Documentation

- Examples that did not run, checked by calling them: `make_request(case.method, case.path,
  add_url1=…)` in [[howto/permissions]] and on the PyPI page sent `/items/{id}/5` — the concrete
  prefix goes in `endpoint`, the template in `defining_url`; the PyPI first test used an undefined
  `ItemValidation`, passed the class instead of an instance, and had neither the fixture nor the
  asyncio marker. The quickstart reset the coverage counters after every test, which left the
  report empty; it now resets once per session, adds `pytest.ini` with `pythonpath = .`, and
  shows how the report is written. `ah.check_status_in` has no `field=` ([[howto/reporting]]),
  `BasePage` has no `expect_text` and its helpers take a locator, not a selector ([[howto/ui]]),
  `TokenManager` has no `refresh_if_needed()` — `get_token()` already refreshes only an expired
  token ([[howto/layers]]).
- [[concepts/methodology]] keeps its definition of "covered" and now says what the report's
  number is: axes A and B only — depth (axis C) is not scored, and an `exception` endpoint
  counts as 100 % in the average instead of leaving it. That the code falls short of the
  methodology here is recorded as an open defect in `docs/wiki/proposals.md`; the code is
  unchanged. [[concepts/coverage-honesty]] said `exception` was excluded from scoring; fixed.
- 2.5.0 Known issues listed fewer unmasked channels than there are; completed below. 2.3.0 said
  "seventeen" `check_*` helpers; there were sixteen.

## 2.5.0 — 2026-10-09

### Known issues

- **A response body is masked only in the schema-failure message and its ERROR log line.**
  The text of the `AssertionError` raised when `validate_model` fails and the ERROR record
  that goes with it carry no input values and mask the body (see Fixed). These still show
  the body, or values from it, as received, as in earlier releases — not a change in
  2.5.0: the pytest traceback, through the chained
  pydantic `ValidationError` (`raise … from err`); the stdout of
  `PydanticResponseError.print_error`, which `BaseResponseValidator.validate_*` calls; the
  INFO request and response log (`Logger.log_request` / `log_response`); and the status
  mismatch message (`format_status_mismatch`, `ErrorDesc.status`). Treat a CI log of a
  failed run as carrying whatever the service sent. These channels are not masked by any
  released version.

  *Closed in 2.7.0:* every channel listed here and below is masked — see 2.7.0 →
  Changed. What remains — a key that only contains a secret name (`accessToken`,
  `new_password`), a secret in an XML body, `key` and `code` in a URL, the `httpx` logger's
  filter dropped by a `dictConfig` — is in 2.7.0 Known issues and `docs/wiki/proposals.md`
  §E2.

  *Completed after the release:* the list above is about the response body, and it is not the
  only thing shown as is. Also unmasked, as in earlier releases:

  - the **request** body — in the status mismatch message (`format_status_mismatch`: the
    `AssertionError` and its `status_mismatch` Allure attachment) and in the INFO request log
    (`Logger.log_request`; request headers are masked there, the body is not);
  - the **response** body in the ERROR log line of a status mismatch (`ErrorDesc.status`, from
    `ApiClient._check_status_code` and `_handle_http_error`);
  - the **response headers and cookies**, `Set-Cookie` included, in the INFO response log
    (`Logger.log_response`);
  - **Allure attachments** made by `reporting.attach_response` (its `redact_body` defaults to
    `False`) — and so by `reporting.instrumented_make_request`, which `TrackingApiClient` uses
    when instrumentation is on: the response body of every call, the `status_mismatch` JSON
    with request and response bodies, and `failure_details` with both;
  - `reporting.format_http_status_failure` (used by `instrumented_make_request` for the
    `AssertionError` and `failure_details`): request and response bodies and the original
    error text (`Original error: …`);
  - `reporting.attach_request` masks headers and the body, but not `params` or `path`;
  - the HTTP-error branch of `make_request`: `HTTP error <code>: <body>` in the ERROR log and
    `Server returned <code>: <body>` in the `AssertionError`, with the response body as is;
    and `Network/request error: …` with the transport exception's text, URL included;
  - the **URL with its query string**, and `params=`, in the INFO request log and the status
    mismatch message: a token passed as a query parameter is shown as is — and so is
    `user:password@` in the client's base URL, wherever the address is echoed.

### Added

- **`partest.polling.poll_until` / `poll_until_sync` — wait for a terminal state and keep the
  path.** A consumer had written the same loop three times, and the copies disagreed on the
  details: one ran on wall-clock time, one had earlier returned the last non-terminal value
  as if it were the answer, one reported only the last state and not the way there.
  `poll_until(fetch, is_terminal, *, timeout, interval, on_tick=None, state=None, what=...)`
  returns a `PollResult` (`value`, `history` — states seen, consecutive repeats collapsed —
  `attempts`, `elapsed`) or raises `PollTimeout` with `last`, `history`, `attempts`,
  `elapsed` and `timeout`. Its message shows the first and last five states with "… k more …"
  between them, redacted — plain dicts and lists by key, no deeper than six levels (`…`
  beyond), anything else (a model, a dataclass, a body kept as a string, a `Mapping`
  subclass, a namedtuple) as its own `repr` passed through `partest.redact.redact_text` — and
  shortened. **The attributes are not redacted**: `last`, `history` and `poll_history` hold
  what was fetched, whole bodies without `state=`; reporting them is the caller's call.
  `PollTimeout` is an `AssertionError` — a failed test, as with `sideeffects.wait_for` — and
  deliberately not a `TimeoutError`, which is an `OSError` that network `except OSError`
  blocks would swallow; it pickles. Monotonic clock; the last sleep is cut to the deadline
  and one more fetch is made there, so nothing waits beyond `interval` and a job finishing in
  the final sleep is not reported stuck. `fetch`, `is_terminal`, `state` and `on_tick` may be
  plain or async. An exception from any of them propagates unchanged, carrying
  `poll_history`, `poll_attempts` and `poll_elapsed` (and a note on Python 3.11+).
  `on_tick` runs after a successful fetch: whatever the next fetch needs — a fresh token —
  belongs inside `fetch`. Also public: `PollTick`. See [[howto/layers]].

- **`partest.redact.redact_text(text)` — secrets inside text whose structure is gone.** Masks
  the values of the keys `redact_mapping` and `redact_headers` know, in the shapes a JSON
  body, a dict or model `repr` and a query string give them (`"token": "…"`,
  `access_token='…'`, `password=…`, `('client_secret', '…')`), and `Bearer <token>`
  anywhere. Best effort by pattern, linear in the input; prefer `redact_mapping` while the
  data is still a mapping. Used for every value a poll message shows.

- **`partest.rounding` — "this value is that formula of those values", with the tolerance
  derived from how each was rounded.** `agrees_with_formula(actual, formula, *inputs)` takes
  every input as `Rounded(value, scale, label)`, i.e. the interval `value ± ½·10^−scale`,
  evaluates the formula over those intervals (decimal interval arithmetic, rounded outward),
  widens the result by the output's own half unit and checks the recorded output is inside.
  `agrees_with_sum(total, parts)` is the sum case: the tolerance is the sum of the half units
  and nothing more. The `Agreement` it returns is truthy on agreement, prints the whole
  protocol, serialises with `as_dict()`, and reports **`resolution`** — the accepted
  interval's half-width relative to the computed value — so a pass at `±4 %` is visibly not
  the same claim as a pass at `±0.002 %`. Unlike `math.isclose`, no tolerance is chosen by
  eye: a fixed `rel_tol` passes a real defect where inputs are precise and fails a correct
  value where the formula amplifies rounding; both cases are in the tests. Comparisons,
  `==`/`!=` against a number, `round()` and `math.*` on an interval raise `TypeError` rather
  than picking an end or a branch; a divisor interval containing zero raises
  `ZeroDivisionError`; powers above 64 and scales beyond ±10000 are refused. A value with
  more decimals than its declared scale is noted in the protocol and emitted as a
  `RoundingNoteWarning`, so the note survives a green run. `scale=None` means an exact
  decimal — not a float the service computed. Also public: `Interval`, `half_unit`,
  `RoundingNoteWarning`. See [[howto/layers]].

- **Opt-in marker sets: `partest_optin_markers = marker[:ENV_VAR] ...` in the ini file.**
  Tests with such a marker, or any `marker_*`, are **deselected** — not skipped — unless
  `ENV_VAR` reads as true or the `-m` expression asks for the family — depends on it
  positively in at least one context: `expr(M)` holds and for some set `S` of the
  expression's other marker names `expr(S)` is false and `expr(S ∪ F)` true, `F` being the
  test's family markers; evaluated by pytest's own parser over every `S`, with a documented
  two-context fallback above 8 names. So `-m slow`, `-m "slow or api"` and
  `-m "slow or not flaky"` take the set, `-m "not slow_db and not flaky"` does not pull it
  in, and `-m smoke` on a test marked `smoke` and `slow` leaves it out. Sub-markers are taken by
  prefix; the session header names what each prefix captured. A test in two sets must be
  opted into both; deselected tests go through `pytest_deselected`. How each set was decided
  is recorded as `run_info["selection"]["optin"]` — **`coverage.json` `meta.selection.optin`**,
  `{"<marker>": {"state": "off" | "markexpr" | "env", "env": ..., "deselected": n}}` —
  merged across xdist shards; `partialRun` does not read it. `compare` reports two
  payloads that both carry it and disagree as not comparable; when only one carries it and
  a set there deselected tests or ran by its variable, the result gains a soft entry in a
  new `notes` list ("comparability cannot be confirmed"), which does not touch
  `comparable`. With the option empty the
  plugin registers nothing and prints nothing. `-p no:partest` turns it off together with
  the rest of the plugin, and the opt-in sets then run. Lives in `partest.optin` (public:
  `INI_NAME`, `OptInSet`, `parse_optin_markers`); not behind `PARTEST_PYTEST_PLUGIN`. See
  [[components/overview]].

- **A tracked resource can belong to a wider area than the test that created it.** A
  session-scoped cache filled lazily creates its object inside whichever test needs it
  first, and per-test `cleanup_since` used to delete it — every later test got a cached id
  that no longer existed. `CreatedRegistry.owned_by(owner)` (also on `TrackingApiClient`)
  claims everything tracked inside the block, including ids registered from responses;
  `adopt(resource_id, owner, endpoint=None)` claims after the fact and raises `LookupError`
  rather than claiming nothing; `cleanup_owned(owner, ...)` drains one area;
  `track(..., owner=)`, `owner_of()` and `owned()` complete it. `cleanup_since` skips claimed
  entries, `cleanup` still removes everything. Nothing changes without a claim: `items` still
  yields `(endpoint, id)` pairs, and a subclass that builds `_items` itself keeps working.
  Claim the parents with the resource — wrapping the whole chain of creates in `owned_by`
  is the form that cannot miss one; a claimed child under a test-owned parent is lost to the
  cascade or keeps the parent's delete failing with 409. Leaving `owned_by` in another
  context than it was entered in (held across an async fixture's `yield`) is a
  `RuntimeError` naming the cause. Also public: `TEST_OWNER`, importable from `partest`
  next to `CreatedRegistry`. See [[howto/recipes]].

- **`partest.files.deterministic_zip` / `deterministic_xlsx` — equal content, equal bytes.**
  A generated test file had a different checksum on every run: a zip records a time per
  entry, and a workbook writer stamps "now" into `docProps/core.xml`. The archive is repacked
  with fixed entry times, permissions and creating system, entries sorted (`mimetype` and
  `[Content_Types].xml` first), the comment dropped; `deterministic_xlsx` also fixes
  `dcterms:created`, `dcterms:modified` and `cp:lastPrinted`. Permissions are never taken
  from the source. **Entries are stored by default** (`compression=ZIP_STORED`): deflate
  output depends on the zlib build — Python 3.14 builds may use zlib-ng — so a deflated
  checksum holds for one interpreter build only; `ZIP_DEFLATED` is there on request. Meant for
  files the suite generated: inflation is bounded by `max_entry_size`, `max_total_size` and
  `max_entries` (counted on decompressed bytes), and the core-date pattern is bounded, so a
  hostile archive fails fast. Standard library only. Also public: `FIXED_ZIP_TIME`,
  `FIXED_CORE_TIMESTAMP`, `MAX_ENTRY_SIZE`, `MAX_TOTAL_SIZE`, `MAX_ENTRIES`.
  See [[howto/upload]].

- **Problem Detail extension members: declare them, and the rest are still refused.**
  `ProblemDetailBody` forbids every member it does not declare, and RFC 9457 lets an API add
  its own; a consumer whose service sends `code` and `errors[]` saw a correct refusal fail
  validation, twice, each time the error contract grew. `ProblemDetailValidation(model=None)`
  now takes the model to check against — any pydantic model class; a non-class raises
  `TypeError` — so an API declares its extensions in a subclass of `ProblemDetailBody` and
  passes `ProblemDetailValidation(MyProblem)`; members it did not declare still fail with
  `extra_forbidden`. The common shape is ready-made:
  `ProblemDetailWithErrors` adds an optional `code` (string or integer) and an optional
  `errors: list[ProblemDetailErrorItem]`; an element types the RFC 9457 §3 members `detail`
  and `pointer` and the common `field`, `code` and `message`, all optional, and **rejects
  any other key**, like every model here — with all its fields optional, an element that
  took anything would let `field` renamed to `fieldName` pass. Element shapes differ between
  APIs: declare yours in a subclass of the element (a `rejectedValue` field), or open it with
  `extra="allow"` there. Both extensions are optional, so
  their absence is not caught; an endpoint that must return `errors` declares it required in
  a subclass. A subclass of `ProblemDetailValidation` may set `_model` on the class; the
  constructor without an argument keeps it. Unchanged: a body without extension members
  validates against `ProblemDetailBody` and `ProblemDetailValidation()` as before — apart
  from the standard member `type`, accepted now (see Fixed). The 409 message's Problem Detail
  summary now shows `code` as well. Also public, from `partest` and
  `partest.validation`: `ProblemDetailWithErrors`, `ProblemDetailErrorItem`.
  See [[howto/recipes]].

### Changed

- **A one-element status set is inferred exactly like its status.** `(404,)`, `[404]` and
  `(404, 404)` are normalised to `404` before the rules run. In 2.4.0 such a set skipped the
  single-status rules, and when the call also carried a status-independent signal it did not
  raise but took that signal's type; it now takes the status's. This is the **only** change
  on calls that worked in 2.4.0, measured against the 2.4.0 module over 63 360 combinations
  (statuses × methods × params × body × content type × files × GraphQL): 10 080 used to
  raise and are now answered, 47 488 are identical, and the 5 792 that differ are all
  one-status sets —

  | Expectation | 2.4.0 | Now | Combinations |
  |---|---|---|---|
  | `(404,)` / `[404]` / `(404, 404)` + broken raw body | incorrect-body 0.99 | not-found 0.99 | 3 × 1 120 |
  | `(405,)` + broken raw body | incorrect-body 0.99 | not-allowed 0.99 | 1 120 |
  | `(404,)` / `[404]` / `(404, 404)` + files on a write | default 0.5 | not-found 0.99 | 3 × 240 |
  | `(405,)` + files on a write | default 0.5 | not-allowed 0.99 | 240 |
  | `(404,)` / `[404]` / `(404, 404)` + list params on a `GET` | params 0.85 | not-found 0.99 | 3 × 80 |
  | `(405,)` + list params on a `GET` | params 0.85 | not-allowed 0.99 | 80 |
  | `(400,)` + JSON body under a non-JSON content type, with files or list params | default 0.5 / params 0.85 | incorrect-body 0.99 | 24 + 8 |

  Pass `type=` where the recorded cell matters — which was always the rule.

### Fixed

- **`sideeffects.wait_for` could sleep past its deadline and never looked at it.** It slept a
  whole `interval` even when less remained, and gave up without a last look — a pipeline that
  finished during that final sleep was reported as not having happened. It now runs on
  `partest.polling.poll_until_sync`: the last sleep is cut to the deadline and the probe is
  called once more there. Signature, return value, the `AssertionError` and the shape of its
  message are unchanged, and a negative `timeout` still means one look (the message keeps
  the value given). Two things are new: an exception from `probe` propagates carrying
  `poll_history`, `poll_attempts` and `poll_elapsed` (and a note on Python 3.11+), and the
  last observation in the message is redacted and shortened — dicts and lists by key,
  anything else through `redact_text` on its `repr`.

- **The repository did not contain `partest.env`.** `.gitignore` had a bare `env/` rule meant
  for a virtual environment, and it matched the package `partest/env/` as well (with
  `core.ignorecase` so did `ENV/`). The package existed on every developer machine and in
  every wheel built from one — the 2.4.0 wheel is not affected — and in no clone of the
  repository, where `import partest.env` failed and the docs lint could not pass. The
  virtual-environment rules are now anchored at the root, the two files are tracked, and
  `tests/test_packaging.py` fails if anything under `partest/` other than bytecode is
  ignored by git.

- **`make_request(expected_status_code=(200, 400))` without `type=` raised `TypeError`.**
  `ApiClient` has accepted a set of allowed statuses for a long time; type inference, which
  runs inside the coverage decorator whenever `type=` is missing, compared the expectation
  with `200 <= status < 300` and failed on a tuple — before the request was sent, so the
  test died on the harness rather than on anything the API did. Where it used to raise, a
  set of several statuses (`tuple`, `list`, `set`, `range`) is now decided status by
  status: if every status infers the same type, that type stands at the **lowest**
  confidence among them (`(200, 201)` is default at 0.4, `(401, 403)` permissions at 0.75);
  if they disagree, the call is recorded as `unknown` at 0.2 with a reason naming the split
  (`{200} → request_default, {400} → unknown; pass type= explicitly`). "Same class" is not
  the rule on purpose: `404` and `405` are both 4xx and still two different cells. Calls
  that did **not** raise keep their 2.4.0 answer: the status-independent signals (broken raw
  body, a content type that does not match the body, list parameters on a `GET`, files)
  still decide before a set of several statuses is looked at — `(200, 404)` with a broken
  body is incorrect-body at 0.99, as it was. An empty set and a one-shot iterator count as
  no status given (an iterator is not read at all; the status check consumes it). A set
  that names nothing usable (`("abc",)`) or more than 1000 statuses is `unknown`, without
  expanding `range(0, 10**12)`. Parsing is `partest.client.normalize_expected_status`, the
  reading the status check uses. An expectation that cannot be compared with a number no
  longer raises at the 2xx rule. Explicit `type=` still wins and is still the rule. See
  [[concepts/methodology]].

- **A generator as `expected_status_code` failed every status check.** `ApiClient` read the
  expectation twice — once for the step title, once for the match — and the second reading
  of a one-shot iterator was empty: `ValueError: expected_status_code sequence must not be
  empty`, whatever the response was. A non-`Sized` iterable is now read once, at the start
  of `make_request`.

- **A JSON body that failed `validate_model` was reported as unparseable.** pydantic's
  `ValidationError` is a `ValueError`, so it fell into the handler for a body that is not
  JSON, and the test read `Failed to parse JSON response and model does not expect a string`
  — a contract drift reported as a broken body, with the real errors only on stdout. It now
  reads `Response data validation failed for <Model> (N errors):`, then one line per error —
  path as `errors.0.pointer`, type, message, without the value; for the first five errors
  below the top level, the object holding the failing member (`in errors.0 = {…}`, masked,
  200 characters at most), because that element often lies beyond the cut of the body —
  then `Response body: …`. Every body and parent shown is masked (`redact_mapping` over the
  parsed JSON and `redact_text` over the result, so a secret below the mapping depth is
  covered too) and shortened; the error list is bounded as well. The same rule holds for the
  empty-body and string-model failures (`… for <Model> on empty response (N errors):`), for
  the body in the `Failed to parse JSON` message, and for the ERROR log line of each, which
  now names the model rather than printing the validator object. **Only the exception text
  and that ERROR line are masked** — other channels still show the body as received; see
  Known issues. A model whose root is `str` still gets the raw text when the body happens to
  parse as JSON (`42`). A test that matched the old text has to be updated.
  The recipe passed the class `ProblemDetailValidation` as `validate_model=`, which raises
  `TypeError`; it passes an instance now.

- **`ProblemDetailBody` refused the standard member `type`.** RFC 9457 defines `type` next to
  `title`, `status`, `detail` and `instance`, and a body with `"type": "about:blank"` failed
  with `extra_forbidden`. It is now an optional string (`None` when absent). Members neither
  the RFC nor your model declares are still refused.

- **`CreatedRegistry.cleanup` quotes resource ids in the DELETE path and follows redirects
  only within the origin of the request.** The default URL puts the id in as one
  percent-encoded path segment. A blank id (`""`, whitespace) is not tracked, like `None`,
  and is never sent as a DELETE. A custom `delete_builder` gets the id exactly as the
  service sent it and encodes the segment itself — `urllib.parse.quote(str(rid), safe="")`;
  if it returns an absolute URL on another host, the auth header goes there.

## 2.4.0 — 2026-09-24

### Added

- **`validate_coverage_payload(doc)` — a consumer that writes `coverage.json` can now check
  itself against it.** The payload is an observable interface, and some consumers produce it
  as well as read it: a fixture generator, a demonstration set, an importer that synthesises
  a run. Such a producer imitates the format by hand, had nothing to verify itself with, and
  one of them drifted silently — it copied `status` into `kind`, so endpoints nobody had
  called were filed as `empty` and that run's `unseenRatio` came out `0.0`. Not a measured
  zero: a zero produced by the wrong label, in the one field that exists to report absence,
  and arriving from the opposite direction to the defect 2.3.0 had just fixed. Run against
  that artefact as it stood, the function names all seven endpoints and the share that
  disagrees with them.
  Beyond keys and types it checks the agreements a hand-written producer gets wrong:
  `unseenRatio` is `float | null` and `null` belongs to exactly one state, `kind` must agree
  with `calls` (no call in this run is `unseen`, never `empty`), `callsTotal` and
  `summary.endpoints` must agree with the rows beneath them, and a `bool` is refused where a
  count belongs — `True == 1` in Python, so a naive `isinstance(x, int)` would pass a flag
  written into a counter.
  **A key that is absent is reported apart from a key that is wrong.** `Severity.DATED` says
  the document predates a field — internally consistent, simply older; artefacts outlive
  releases, and a check that fails on last month's file is a check people switch off. Nothing
  is raised and nothing is printed: what a divergence costs is the caller's decision.
  Also public: `Problem`, `Severity`. See [[howto/coverage-html]].

## 2.3.0 — 2026-09-24

### Added

- **`meta.tlsUnverifiedHosts` and `meta.tlsUnknownHosts` — which hosts, not only whether.**
  `meta.tlsVerified` is one bit for a whole run and means "at least one connection went
  unchecked". One auxiliary service is enough to switch it off, and on a real consumer it did
  so on **every** run: a plugin of theirs sits in `addopts` and signs into an auxiliary
  service with a self-signed certificate while pytest is still configuring itself, so even a
  run that never calls the API reports `false`. The flag was honest and stopped being informative — "the suite ran
  unverified throughout" read the same as "one service host was accepted, the stand was
  verified from the first call to the last". Two sorted lists now stand next to the flag:
  `tlsUnverifiedHosts` names the hosts a request actually went to while verification was off,
  and `tlsUnknownHosts` names the hosts partest did not decide and cannot read — today
  `ApiClient(domain, client=hx)`, which sets `self.verify = None` because the injected client
  settled `verify=` out of sight and whose run used to be reported as verified. The two are
  kept apart on purpose: "not ours to check" is not "unchecked". The host is taken **per
  request**, through an event hook that a client carries only while its verification is off —
  `base_url` says what a client was pointed at, a redirect leaves it behind, and `ApiClient`
  passes no `base_url` at all. A default port is dropped, a non-default one is kept (two
  services on one machine are two certificates), and credentials in a URL never reach the
  artifact. Both lists are unioned across xdist workers and are present even when empty.
  `tlsVerified` keeps its type, its two values and its meaning — adding a key to `meta` is
  compatible for `partest-atlas`, `partest-load` and the map; changing the type of one would
  not be. Also public: `partest.tls.note_unverified_host`, `partest.tls.note_unknown_tls_host`,
  `partest.call_storage.record_unverified_host`, `record_unknown_tls_host`, `host_of`,
  `unverified_hosts`, `unknown_tls_hosts`. See [[components/overview]].

- **`env_only=` on `httpx_client()` / `httpx_async_client()`.** `resolve_verify` and
  `partest.ui.ignore_https_errors` had it, the factory did not — so a consumer who needed the
  environment-only answer wrote three functions whose whole job was to call
  `partest.tls.default_verify(env_only=True)` and hand the result back in as `verify=`. It is
  passed straight through to `resolve_verify`; the default is unchanged.

- **A third outcome for checks: «not measured».** The sixteen `ah.check_*` helpers have two
  outcomes, and two are enough only while there is something to measure. When the data an
  assertion reads was never collected, the comparison still runs and still passes: a
  dependency audit that read the wrong file reported «passed» over 24 vulnerabilities and
  over two dependencies it never saw at all; a check for outbound URLs searched a bundle that
  this environment had never built, and stayed green on an empty file for two months; a
  «dead-letter queues did not grow» assertion was a difference of two dictionaries that are
  both empty when the broker is unreachable — zero equals zero by construction. Four such
  cases in one day, all green. `partest/reporting/measured.py` adds
  `check_measured(premise, assertion, *, what, reason="")`, which makes the assertion
  **only** under a stated premise of measurability and otherwise records what was not
  measured and why. The premise is positional and required, so it cannot be left to the
  caller's judgement; a reason is required with it, because the third outcome without one
  reads like a pass. `measurable(sample, *, what, min_size=1)` builds the premise aggregates
  need — `None` («never collected») and an empty sample («an aggregate over it is fixed by
  construction») get different reasons, and premises combine with `&` for a difference of two
  samples. In the report the three outcomes are told apart without reading: the step is
  `Measured: …` or `NOT MEASURED: … — reason`, the attachment is `not_measured:<what>` with
  `passed: null` instead of `check:<field>` with `passed: true`, the test carries the
  `not-measured` tag, a `NotMeasuredWarning` is raised, and the pytest run ends with a
  `NOT MEASURED` section listing what never ran. It is not `pytest.skip`: the test continues
  and its other assertions are made as usual. It does not fail the run either — a missing
  sample is not a defect of the service under test — but a project that wants it strict sets
  `filterwarnings = error::partest.reporting.NotMeasuredWarning`. Also public:
  `mark_not_measured`, `not_measured_records`, `reset_not_measured`, `Premise`, `NotMeasured`
  and `attach_not_measured`. The existing sixteen checks are untouched. See
  [[howto/reporting]].

### Changed

- **`meta.unseenRatio` in `coverage.json` is `null` when the run collected no endpoints.**
  It is a share over the endpoints of the run, and a run that has none — a fixture that
  failed before the specification was read, a worker shard that was never merged, an empty
  specification — has no denominator. The field used to be `0.0` there, which reads as "not
  one endpoint went untouched": the most reassuring number in the artifact, produced by the
  least informative run, and indistinguishable from a full run that called everything. The
  type of the field widens from `float` to `float | null`; a measured zero is still `0.0`,
  and the key is always present, so "not measured" stays distinguishable from an artifact
  written before the field existed. **Readers that do arithmetic on it must check for `null`
  first** — inside the package both already did. `meta.partialRun` is unchanged: it stays a
  bool, it stays `false` for a run with no endpoints, and every phrasing built on it ("some
  endpoints were never called") remains true where it fires. The claim about a run that
  measured nothing belongs to `unseenRatio: null`, which cannot be mistaken for a count.
  See [[concepts/coverage-honesty]].

### Fixed

- **`tools/docs_lint.py` printed "clean" and exited 0 when it had read no page at all.** A
  linter that collects nothing finds nothing, and the loudest possible pass is the one made
  over an empty walk — the same shape as the three green checks this release adds
  `check_measured` for. It now fails if `index.md` or `status.md` is missing from what it
  collected: the wiki has both by its own conventions, so their absence is a broken walk, not
  a broken wiki. This is a repository gate; nothing in the installed package changes.

- **The comment over `run_info` said the opposite of what the code does.** It described
  `tlsVerified=False` as "no response in this run was authenticated by a certificate" — i.e.
  *none*, where the implementation means *at least one*. The two readings differ by the whole
  ordinary case: one service host accepted unverified in a run that checked everything else.

## 2.2.0 — 2026-09-24

### Added

- **`httpx_client()` / `httpx_async_client()` — a client of your own, still inside the TLS
  policy.** `partest/tls.py` decided `verify=` for the clients the package builds and for
  nothing else. The moment a suite needed a client of its own — a fixture pulling the live
  specification, a probe against a second service — it wrote `httpx.Client(verify=False)` and
  left the policy entirely: `PARTEST_TLS_VERIFY` and `confpartest.tls_verify` unread, no
  `TLSVerificationDisabled` warning, nothing recorded — and the report of that same run still
  said `meta.tlsVerified: true` while the specification had come over an unverified
  connection. One consumer suite carried thirty-odd such call sites. The two factories apply
  `resolve_verify()` and `verify_for_httpx()` and pass everything else — `base_url`,
  `timeout`, `headers`, `http2`, `auth`, a `transport` — to httpx untouched; an explicit
  `verify=False` travels through the same policy, so it warns and is recorded like any other.
  They are a **factory, not a second `ApiClient`**: no retries, no coverage tracking, no steps
  or attaches, and a call through such a client stays as invisible to coverage as any other
  raw httpx call. Exported from `partest` and from `partest.http`.

### Changed

- **The package now builds httpx clients in exactly one place.** `ApiClient` (per-request and
  shared), `SecHttp`, `TokenManager`, `CreatedRegistry.cleanup` and the OpenAPI URL loader
  repeated the same `httpx.*Client(verify=verify_for_httpx(...))` pair five times over. The
  duplication was not the cost — each copy was another place where the TLS decision could be
  forgotten, and in this package's history it twice had been. All five now call the factory,
  and `tests/test_tls_factory.py` fails if any module grows a raw `httpx.Client(` again.
  Observable behaviour is unchanged: each of them still settles `verify=` in its constructor,
  where the warning belongs, and hands the settled value to the factory.

- **`meta.tlsVerified` keeps its type and its two values, and now says what it means.** `true`
  means "no client partest built for this run skipped verification" — it never could mean more:
  a consumer may still construct a client by hand, and an injected `client=` decides its TLS
  before partest sees it. Making that gap visible in the artifact (a third value, or a strict
  mode that fails the run) changes either the artifact contract or the behaviour of suites that
  knowingly run with `verify=False`; both are written up in `docs/wiki/proposals.md` and neither
  is taken here.

## 2.1.0 — 2026-09-23

**Support for pytest 8 ends with this release.** `PYSEC-2026-1845` is fixed in pytest 9.0.3
and in no 8.x release — there is no version of pytest 8 without it, so there was nothing to
keep supporting. Consumers still on pytest 8 stay on `partest 2.0.1`; moving to 2.1.0 means
moving to pytest 9 in the same step.

### Security

- **The declared lower bounds allowed versions with known advisories.** The bounds, not the
  development environment, are what a consumer gets: `pip install partest` resolves the
  oldest version every line still permits. Audited as such — a file of `name==floor` fed to
  `pip-audit -r` — the floors carried **24 findings across 5 packages**:

  | package | was | now | why exactly this version |
  |---|---|---|---|
  | `pytest` | `>=8.0.0` | `>=9.0.3,<10` | PYSEC-2026-1845, fixed in 9.0.3; no 8.x fix exists |
  | `pydantic` | `>=2.0.0` | `>=2.4.0` | PYSEC-2026-1812, fixed in 2.4.0 |
  | `requests` | `>=2.31.0` | `>=2.33.0` | PYSEC-2026-1873 / -1872 / -2275; the last of them is fixed in 2.33.0 |
  | `python-dotenv` | `>=1.0.0` | `>=1.2.2` | PYSEC-2026-2270, fixed in 1.2.2 |
  | `Pillow` (extra `ui`) | `>=10.0.0` | `>=12.3.0` | 18 advisories; the last of them is fixed in 12.3.0 |
  | `pytest-asyncio` | `>=0.23.7` | `>=1.3.0` | not security: every earlier release declares `pytest<9` |
  | `pytest-xdist` (extra `dev`) | `>=3.0.0` | `>=3.0.2` | 3.0.0 was never released; the first 3.x on PyPI is 3.0.2 |

  Each floor is the release that *fixed* the advisory, not the newest available: a package
  must not demand more than it needs.

- **The audit had never looked at `python-dotenv` or `Pillow` at all.** `pip-audit` reads
  dependencies from `requirements.txt`, and neither was listed there — so the gate reported
  `pip-audit PASSED` while two of the seven bounds above were outside its scope entirely.

### Changed

- **`pytest` now has an upper bound, `<10`.** `partest` registers as a `pytest11` plugin on
  six hooks, so it loads in every session of a consumer — including runs that never touch
  partest — and a hook signature a future major drops fails at plugin registration, before
  collection, taking the whole session with it. `<10` states what was run rather than
  promising a compatibility nobody checked. It is a debt, not a wall: the cap is lifted by a
  patch release as soon as the suite passes on the next major. A cap left to rot is how the
  consumer's environment was held on pytest 8 by two other plugins.

- **`requirements.txt` is now the audit target and nothing else**, and it matches `setup.py`
  line for line: `install_requires` plus the consumer-facing extras `ui` and `gen`. It used
  to be a list of pins that described nothing — 21 names the package never declared
  (transitive dependencies plus `ruff` and `pytest-repeat`), the abandoned `py==1.11.0`, and
  pins that had drifted from the installed environment. The `dev` extra stays out on purpose:
  the audit answers "is what ships safe", not "what do we develop with". The one place that
  still installed from it — the `Dockerfile` — now installs `-e ".[dev]"`, which is what it
  needed all along: the old line brought in neither the package nor the plugins `pytest.ini`
  demands.

- **`tests/test_packaging.py` keeps the two files from drifting apart again.** Names *and*
  bounds are compared, so a floor raised in one file and not the other fails the suite; a new
  extra has to be classified as consumer-facing or as tooling before the suite passes; and
  the pytest the suite actually runs on has to fall inside the declared window, which is what
  stops the upper bound from being widened without a run behind it.

### Added

- **Python 3.14 is supported, and the claim comes from a run.** The suite was installed into
  a fresh 3.14 environment and executed there with the same result as on 3.10 — 390 passed,
  2 skipped as this release went out — before the classifier was written. Every dependency resolves: the compiled ones
  ship `cp314` wheels, the rest carry no ABI tag. `python_requires` stays `>=3.10`; this
  release adds a version, it drops none.

- **`tests/test_packaging.py` — the configuration may not demand what the installation does
  not provide.** A new guard reads `pytest.ini` and `setup.py` side by side, so a setting that
  needs a plugin fails the suite until an extra installs that plugin. It also compiles the
  whole package looking for invalid escape sequences, and checks that the interpreter the
  suite just passed on is among the declared classifiers.

### Fixed

- **`SyntaxWarning: invalid escape sequence '\>'` on every import.** `partest/utils/checking.py`
  wrote `<\>` inside a plain string twice. On Python 3.12+ it warns, in the consumer's own
  output, for a package they merely installed; in a coming version it becomes a `SyntaxError`.
  The backslash is now escaped and the printed text is byte-for-byte what it was — the report
  it appears in is read by people.

- **`pip install -e '.[dev]'` produced an environment that could not run a single test.**
  `pytest.ini` puts `--reruns=2` into `addopts`, but `pytest-rerunfailures` was declared
  nowhere, and pytest rejects an unknown option while parsing arguments — before collection.
  The failure named the argument and no plugin:

  ```
  error: unrecognized arguments: --reruns=2
  ```

  The plugin is now in the `dev` extra, and the new packaging guard keeps `pytest.ini` and
  `setup.py` from drifting apart again.

## 2.0.1 — 2026-09-23

### Fixed

- **The source distribution could not be built.** `MANIFEST.in` pruned `docs/`, and
  `setup.py` reads `docs/PYPI.md` unconditionally for its long description, so the file
  the build needs was the one the manifest removed. Installing from source —
  `pip install --no-binary :all:`, a mirror that carries no wheels, a closed network that
  builds everything itself — failed on the first line of the build:

  ```
  FileNotFoundError: [Errno 2] No such file or directory: '.../docs/PYPI.md'
  ```

  The wheel was fine, which is why ordinary installation never noticed and why the defect
  shipped. Nothing else changed in this release.

## 2.0.0 — 2026-09-23

Three breaking changes, any one of which alone would make this a major release. The scaffold
generator left this package — see `Removed`. The methodology submodules moved under
`partest/methodology/api/` to make room for a second area, UI — see `Breaking`, where the old and
new import paths sit side by side, and `Deprecated`, because the old paths keep working with a
warning until 3.0.0 rather than disappearing here. And **TLS certificates are now verified by
default**, which is
the one that will reach a running suite first: also `Breaking`. If you are here because a prior
green run started failing on certificates, that section is the answer.

### Removed

- **The `partest-gen` console script.** It is now declared by the
  [partest-gen](https://pypi.org/project/partest-gen/) distribution, the one that implements
  it. `pip install partest` alone no longer gives you the command — install `partest-gen`, or
  `pip install 'partest[gen]'`.

  Two distributions cannot both own one console script without the winner depending on
  installation order, which is why this could not be kept as a courtesy.

- **`partest/project_gen/**` source.** The generator moved to `partest_gen`. Its release
  cadence, dependencies and notion of a breaking change all differ from the harness — for a
  code generator the *names and locations of the files it writes* are the public API. The
  reasoning and the rejected alternatives are in `docs/wiki/decisions/separate-package.md`
  in that repository.

- **`setup_project.py` from the repository root.** It imported
  `partest.project_gen.new_parparser` — a module that does not exist anywhere in the family:
  during the extraction it became `openapi_load.py` in `partest-gen`. The script therefore
  could not run at all, and it sat at the root of a public repository looking like a
  supported entry point. The scaffold has its own command: `pip install partest-gen`, then
  `partest-gen`. Two reviewers found this independently, which is what a dead file in a
  visible place earns.

### Deprecated

- **The old methodology module paths — `partest.methodology.subtypes` and the five beside it.**
  They import, they resolve to the *same* module objects as `partest.methodology.api.*` rather
  than second copies, and each warns once with the path to use instead. They are removed in
  3.0.0. The table of old and new is in `Breaking`.

  **They were removed outright first; this reverses that before publication**, because the
  removal was tried on a live consumer and cost more than expected:

  - the upgrade stopped being divisible. New paths do not exist on 1.8.x and old ones did not
    exist here, so the consumer had to move its version and rewrite its import lines in one
    commit, with no green state in between and nothing to bisect if the run went red.
  - the failure surfaced nowhere near the import. `confpartest.py` is imported from inside the
    pytest plugin, so a stale `from partest.methodology.subtypes import …` came back as an
    `INTERNALERROR` with a pluggy traceback during collection of the **whole** tree — including
    tests that have nothing to do with the methodology — instead of as an `ImportError` on the
    line that was wrong.
  - and there was a silent shape of it. With the versions the other way round the consumer's
    `confpartest` failed to import, `active_overrides()` came back empty, and coverage went on
    counting subtypes against the wrong required sets **without a message**. A number that is
    quietly wrong is worse than a red run.

  A major release is still the moment a move is allowed to be visible; what it is not is a
  reason to make the move undiagnosable. `partest.project_gen` is deprecated the same way in
  this release, which is now one technique across the whole thing rather than two.

  A package that reads these functions — the scaffold generator does — should still raise its
  dependency floor to this release and use the new paths, rather than lean on the alias.

- **`partest.project_gen`** is now a bridge to `partest_gen`, kept until the major release
  after this one. Old imports work — including submodules, and resolving to the *same* module
  objects rather than second copies, so `isinstance` and module-level state behave as before.
  Importing it warns; importing it without `partest-gen` installed fails with the command to
  run.

### Added

- **A second methodology: `partest.methodology.ui`.** Three axes, like the API half —
  `SurfaceType` (axis A), `UiTestCases` (axis B, eleven check families), `UiStep` (axis C) and a
  surface × check matrix with `applicable_checks`, `priority_of`, `required_checks`, `p1_checks`,
  `p2_checks`. All of it is re-exported from `partest.methodology`.

  **It has no classifier, and it is not getting one.** The API half derives axis A from the OpenAPI
  specification; no project ships a machine-readable description of its screens, so the surface type
  is declared by the consumer on its own page object. Guessing it from markup has the same failure
  mode as a misclassified endpoint — the screen silently gets the required set of a different kind of
  screen — with none of the evidence. `tests/test_methodology_ui.py` asserts the absence, so a later
  "small helper" cannot drift back into guessing.

  Two parts of it are findings from practice rather than vocabulary:
  `UiTestCases.screen_state_persistence` and the `UiStep.SURVIVES_RELOAD` depth level. Every other
  family and level describes **one** load of a screen, so "the filter the user set is still set after
  a reload" had nowhere to live — and a suite that starts each test from a clean browser profile
  cannot fail that check no matter how many tests it has.

  The matrix is deliberately small: more than half its cells are `NA`, every cell that is not carries
  its justification on its line in the source, and a cell that could only be justified by "it seems
  likely" is left empty and marked as left empty. `priority_of` raises on an unknown check name
  instead of answering `NA`, because `NA` reads as "the methodology does not ask for this" and a typo
  must not be able to say that.

  `CoveragePriority` is re-exported from `partest.methodology.ui` as well: it is what
  `priority_of` returns and what `required_checks` takes, and a consumer of this area
  should not have to import from the `api` one to name a value this one handed it. It is
  the same object in both places, deliberately — P1 means "implement first" in both areas.

- **`active_overrides` is re-exported from `partest.methodology` and `partest.methodology.api`.**
  It reports the subtype overrides a run is actually using, which is what a suite asserts on to
  prove its `subtype_overrides` reached the library — and until now the only way to reach it was
  `from partest.methodology.api.overrides import active_overrides`, a deep import into a module
  that had just moved. A public function with no package-level spelling has no path that
  survives a reorganisation; this gives it one.

  The rest of `partest.methodology.api.overrides` stays where it is on purpose:
  `set_subtype_overrides`, `load_subtype_overrides`, `load_from_confpartest`,
  `clear_subtype_overrides` and `lookup` are called by the harness while it reads the project's
  configuration. A suite that calls them is overruling its own `confpartest.py` from inside a
  test, and that should read as the unusual thing it is.

- **`partest[gen]` extra**, so `pip install 'partest[gen]'` still gets you both packages.
- `tests/test_methodology_aliases.py`: that each old methodology path resolves to the same module
  object as the new one, that `isinstance` and the override registry survive the alias, that the
  warning fires once per module and names the replacement, and that `partest.methodology` itself
  stays quiet.
- `tests/test_project_gen_bridge.py`: that the bridge warns, that submodules resolve to the
  same objects, that the error names the fix when the distribution is missing, and that this
  `setup.py` does not declare the console script.
- **`SWAGGER_FETCH_TIMEOUT` in `partest.parparser`** (60 seconds, the same default as
  `partest.openapi.resolve_swagger`) and a `timeout=` keyword on
  `OpenAPIParser.load_swagger_yaml` and `SwaggerSettings`. Fetching a specification over
  HTTP had no timeout at all, so an unreachable stand could hold the import of every suite
  that loads a spec. The signature is unchanged and the keyword is optional — **but the
  behaviour is not the same**, and that is the point of the change: a fetch that used to
  wait forever now gives up after 60 seconds. A specification served by a stand that takes
  longer than that has to say so explicitly (`timeout=`), and a suite that hung during
  collection now fails there instead. It is a per-operation limit, not a deadline for the
  whole load: a redirect chain gets it again on each hop, and reading the body and parsing
  the YAML are outside it.
- **`partest.flags`, a public module for reading switches.** `coerce_bool` (a string to
  `True`/`False`/`None`), `env_bool` (the same for an environment variable) and the two
  word lists behind them, `TRUE_WORDS` and `FALSE_WORDS`. Every on/off setting
  in the package — `PARTEST_TLS_VERIFY`, `PARTEST_PYTEST_PLUGIN`, `PARTEST_RUN_METADATA` —
  is parsed here, so `off`, `no`, `disabled` and `0` mean the same thing wherever a
  consumer writes them. It is public because a suite reading its own flags should not have
  to invent a second spelling table.
- **`partest.conf.conf_attr`**, the single reader for a switch that may be written in the
  consumer's `confpartest.py`. Returns a default when there is no `confpartest` at all;
  see `Changed` for the case where there is one and it does not import.
- **`pytest-xdist` and `partest-gen` in `extras_require["dev"]`.** The package still treats
  xdist as an optional integration — the plugin detects a parallel run through
  `hasattr(config, "workerinput")` and never imports it — but the test suite runs a real
  `-n 2` session, and that case now skips instead of erroring when xdist is absent.
  `partest-gen` is there for the bridge cases below: without it installed they skip, and
  the deprecation bridge that is this release's compatibility promise would go through a
  green gate unexecuted.

### Changed

- **`INVALID_BEARER` is now `"invalid.invalid.invalid"`.** It was a base64url blob that
  looked like a real credential to a reader and to a secret scanner. The new value keeps the
  three dot-separated segments, so anything that splits on dots still sees a compact JWS, and
  carries nothing else.

  **This changes where a server rejects it.** The old value decoded into a valid JOSE header
  (`{"alg":"HS256"}`), so a server got as far as verifying the signature; the new one does not
  decode into JOSE JSON at all and is refused as unparsable. Both are rejections, but a gateway
  may answer them with different statuses or bodies. If your `unauth` cell asserts on anything
  narrower than "not authenticated", re-check it. `access_cases` is unaffected: its `unauth`
  cell sends no `Authorization` header at all.

- **A `confpartest.py` that exists but does not import is now an error, not silence.**
  Every module that read a switch used to do a bare `import confpartest` and swallow
  `ImportError`. That conflates two different situations: *there is no project file* —
  legitimate, and the library's defaults are the right answer — and *there is one, the
  consumer wrote it, and it is broken*. `partest.conf.conf_attr` now tells them apart: no
  `confpartest` on the path returns the default as before, while a `confpartest` that is
  found and raises while importing raises `ConfpartestError`, naming the switch that was
  being read and the original exception.

  *Correction:* through 2.5.0 this held for `conf_attr` only. `load_confpartest` /
  `require_confpartest` wrapped only `ImportError`; the coverage loader, subtype overrides and
  the report's settings did a bare import that swallowed an `ImportError` from inside the file.
  All of them raise `ConfpartestError` for a file that fails since 2.6.0
  (the report's settings fall back to defaults instead, so that a report is still written).

  **This is a deliberate trade and it is not a cheap one.** A project whose `confpartest.py`
  is broken now fails on every read of a switch, including the `ApiClient` constructor, and
  it fails at import time rather than in one test. Swallowing was worse: it is exactly how
  `tls_verify = False` ends up unread while the run warns that verification is *on*, and how
  a project with a non-standard layout gets the library's defaults back with no hint why. A
  configuration file that cannot be imported is not a configuration that means "use the
  defaults".

- **Dependency floors raised in `requirements.txt`** after `pip-audit` could finally resolve
  the file: `idna` 3.15, `requests` 2.33.0, `urllib3` 2.7.0, `pytest` 9.0.3 (11 advisories in
  4 packages). `install_requires` still declares `pytest>=8.0.0`; the suite was verified
  against 9.0.3 in a separate environment. `swagger-parser` was removed from
  `requirements.txt`: nothing in the repository imports it, it was never in `install_requires`,
  and it was the requirement that made the file unresolvable — which is why the audit had been
  answering "could not look" instead of reporting these.

- **The pytest plugin's run metadata no longer depends on the Allure switch.**
  `pytest_plugin = False` / `PARTEST_PYTEST_PLUGIN=0` turned off four hooks at once: two that
  write into Allure, and two that record which tests the run actually selected. The flag was
  introduced against double Allure titles and attachments — and the documentation only ever
  gave that reason — but consumers who followed the advice silently lost `meta.selection`.

  That loss is worst exactly where the signal matters: a marker-filtered run over a full
  suite still touches every endpoint, so the unseen ratio stays near zero and nothing in the
  numbers reveals that half the suite did not run. Comparing such a run against a full one
  then reports every dropped cell as a regression.

  Recording the selection attaches nothing and prints nothing, so it has nothing to collide
  with. It is now behind its own switch, on by default: `PARTEST_RUN_METADATA=0` or
  `run_metadata = False` in `confpartest`. `plugin_enabled()` keeps its meaning — the Allure
  half — and its documentation now says so.

  **The signal now survives `-n`, which is where it was needed most.** Under `pytest-xdist`
  the controller does not collect, so neither hook fires there, and the shard a worker wrote
  carried no run metadata at all: a filtered parallel run produced correct counts and no
  record that it was filtered. The selection now travels with the shard, and the deselected
  tests travel as node ids rather than as a number — workers deselect *the same* tests, so
  counts cannot be summed while sets can be merged. Separate deselection rounds still add up,
  and the state is cleared at session start, so a second `pytest.main()` in one process no
  longer inherits the first one's filter.

### Note for the methodology

`classify_endpoint` and `p1_test_cases` in `partest.methodology` now have a second consumer in
another repository. They are no longer internal: changing their signatures is a cross-package
change, and the release order is `partest` first, then the generator's dependency floor. The move
into `api/` is exactly that kind of change — the generator imports the deep paths, so its floor has
to be raised in the same wave, and it must not be published before this release is on PyPI.

### Breaking

- **The methodology submodules moved into `partest/methodology/api/`.** There are two areas now,
  `api` and `ui`, with the same shape; the existing modules are the `api` half and moved unchanged.

  | Was | Now |
  |---|---|
  | `partest.methodology.subtypes` | `partest.methodology.api.subtypes` |
  | `partest.methodology.matrix` | `partest.methodology.api.matrix` |
  | `partest.methodology.classifier` | `partest.methodology.api.classifier` |
  | `partest.methodology.inference` | `partest.methodology.api.inference` |
  | `partest.methodology.overrides` | `partest.methodology.api.overrides` |
  | `partest.methodology.steps` | `partest.methodology.api.steps` |

  **Nothing inside them was renamed.** Every class, function and enum member keeps its name and
  its meaning, so the fix at a consumer is a mechanical edit of the import line and nothing else.
  `from partest.methodology import …` is unaffected: the package re-exports every name it exported
  before, plus the new UI ones.

  **The old paths still import, and warn** — see `Deprecated`. They are removed in 3.0.0. The move
  is listed as breaking because that is the release in which the deep import has to be rewritten,
  not because the upgrade to this one breaks it.

- **TLS certificates are verified by default.** The HTTP clients — `ApiClient`, `SecHttp`,
  `TokenManager`, `TrackingApiClient` — `CreatedRegistry.cleanup`, which deletes tracked
  test data over its own client, and the browser context of `capture_baselines` used
  to default to `verify=False`. A consumer who wrote `ApiClient(domain)` ran the whole suite
  without certificate validation and had no way of knowing: nothing in the signature, the
  output or the report said so.

  **For the two specification loaders the change goes the other way, and that matters.**
  `partest.openapi.resolve_swagger` declared `verify: bool = True`, and
  `partest.parparser.OpenAPIParser.load_swagger_yaml` relied on the `requests` default —
  both verified, unconditionally, and neither could be told not to. They now follow the same
  switch as everything else, which makes them **weaker** by one step: a project that sets
  `tls_verify = False` for a self-signed stand now also stops verifying the host that serves
  the specification, and that is frequently a different host. If the two need different
  answers, pass `verify=` to `resolve_swagger` explicitly — the argument still wins.

  Its default changed from `True` to `None` ("not specified"), which is a behaviour change at
  an unchanged signature. A caller that relied on the documented `True` must now say so.

  The error a rejected certificate produces now names the switch, the release and the host
  instead of arriving as "Network/request error", and it is no longer retried: a certificate
  failure is not transient, and retrying multiplied one wrong setting across every test.
  That applies to a **rejected certificate** and nothing else — a TLS connection that drops
  mid-handshake (`ssl.SSLEOFError`, `ssl.SSLZeroReturnError`, `ssl.SSLSyscallError`) is an
  ordinary transient failure and is still retried, and it is not answered with advice to
  switch verification off.

  **This is breaking.** A stand with a self-signed certificate will now fail with a TLS error
  where it used to pass. That is deliberate — the point is that the choice becomes visible —
  and turning it back off is one line, not an edit of every call site:

  ```bash
  PARTEST_TLS_VERIFY=0                     # environment, wins over confpartest
  ```
  ```python
  tls_verify = False                       # confpartest.py
  tls_verify = "/etc/ssl/corp.pem"         # or keep verification on with a private CA
  ```

  The decision lives in one place, `partest.tls`. Disabling it warns once per process
  (`partest.tls.TLSVerificationDisabled`) — a project that means it can silence exactly that
  category. An explicit `verify=False` at a call site is honoured and warns too: the warning
  is about the run being unverified, not about how it got that way. A run that went out
  unverified also says so in the report, as `meta.tlsVerified`: a warning does not survive
  the session, an artefact does. `verify=False` is not the only way to get there — an
  `ssl.SSLContext` with `verify_mode = ssl.CERT_NONE` accepts any certificate just as
  thoroughly, and it warns and is recorded the same way. A context that only turns
  `check_hostname` off is weakened, not off, and is left alone: the field is worth having
  only while it means one thing.

  `verify=` now accepts a CA bundle path, so **`client.verify` is no longer always a `bool`**
  — an assertion like `client.verify is False` has to change. A path is converted to an
  `ssl.SSLContext` for the `httpx` clients, because `httpx` deprecated the string form; for
  the `requests` road the path is passed through. The browser context takes neither: Playwright
  offers only on/off and checks the OS trust store, so a bundle leaves verification on there
  and says that it was not applied.

### Fixed

- **`partest.ui.ignore_https_errors` is public now.** The browser half of the TLS decision
  was a private helper, and a generated suite could not reach it without importing a private
  name. The scaffold generator therefore kept emitting `ignore_https_errors=True` — the
  browser equivalent of the default this release just removed. Same function, same
  environment-only reading (a UI job must not load `confpartest`); only the name changed.

- **A valid specification no longer looks broken in the log.** `extract_paths_info` treated
  every key of a path item as an HTTP method, so OpenAPI's own path-level `parameters`
  produced `expected a mapping …, got list; skipping` on every load. The spec was correct and
  the operation was parsed correctly — only the message said otherwise, and every consumer
  saw it. Non-method keys (`parameters`, `summary`, `description`, `servers`, `$ref`) are now
  skipped silently, and the warning is reserved for a key that really is unknown.



- Three stale references left over from before this repository went public: `tools/check_all.py`
  and `MANIFEST.in` pointed at `docs/wiki/decisions/pypi-only.md`, which was renamed to
  `distribution.md`, and `check_all.py` still claimed there is no public CI. The docstring of
  `partest/docs/__init__.py` still said the package is distributed through PyPI only.

- **`str(Logger())` raised `NameError`.** `Logger.__str__` returned `logger.info()`, referring
  to a module-level name that does not exist. Any f-string interpolating a `Logger` died with
  it. It now returns `Logger(name=…, level=…)`. `repr()` was never affected — the class defines
  no `__repr__`, and `repr` does not fall back to `__str__`.

- **A note in the released 1.8.1 section was inaccurate and has been corrected in place.** It
  said that adding `__all__` to `partest.reports.history` makes `dir()` stop presenting `json`,
  `Path` and `datetime` as API; `__all__` does not affect `dir()` on a module — it governs
  `from … import *`. The fix itself was correct, only its description was not. Flagged here
  rather than changed silently: `v1.8.1` is tagged and published, so the wheel on PyPI still
  carries the old wording.

## 1.8.1

Five bug fixes, all reported from a suite that made the 1.5.0 → 1.8.0 move, all with the
numbers to reproduce them. No API removed, nothing to change in a suite — upgrade and the
report starts telling the truth about comparisons.

The first two shared the expensive failure mode: the comparison returned a confident wrong
answer rather than an error.

### Fixed

- **Comparing against a snapshot older than `kind` invented dropped endpoints.**
  `compare_payloads` read a missing `kind` as "not unseen", so an endpoint never called in
  *either* run came back under `not_run` — "covered before and not called at all now" — with
  `from: 0.0, to: 0.0` printed in the same record. That dragged `comparable` to false, so
  `compare --strict` exited 2 on two snapshots between which nothing had changed. A missing
  `kind` is now inferred from the call count. Comparing against an older snapshot is what an
  upgrade *is*, so this was wrong at the one moment it mattered.

- **A marker-filtered run was compared as though it were a full one.** Coverage is scored per
  test case, but `unseen` is a property of an endpoint: `pytest -m "not rbac"` still calls the
  endpoint, it just drops one cell. So `unseenRatio` stayed near zero, `partialRun` stayed
  false, and every dropped cell was presented as a regression with the comparison marked
  sound. Measured on the reporting suite: 46% of tests and 55% of calls gone, `unseenRatio`
  0.009 → 0.018, 14 fake regressions, `avg_delta -2.78`, `comparable: True`.

  Two guards, because the exact one cannot help an old snapshot:
  - the bundled pytest plugin records `meta.selection` — the `-m` / `-k` expression and how
    many tests were deselected — and `partialRun` now includes it;
  - `compare` warns when a run made less than half the calls of the one before it while the
    share of never-called endpoints barely moved. That is what a cell-level filter looks like
    from the endpoints alone, so it also works on payloads written before `meta` existed.

  The lost cells stay in `regressed`. Deselected and deleted are indistinguishable from two
  payloads, and reclassifying them on a heuristic could bury a real loss; saying "these are
  not the same experiment" is the honest answer.

- **`partest/parparser.py` printed to stdout on every import.** Twelve `print()` calls, no
  `logging`, messages mixed Russian and English — 33 lines per process on a large
  specification, which stops any `python -c` next to partest from being machine-readable. Now
  `logging.getLogger("partest.parparser")`: unresolvable references and malformed parameters
  at `warning`, reference tracing at `debug`.

- **`prune_snapshots`, `list_snapshots` and `previous_snapshot` were not importable from
  `partest.reports`.** The 1.7.0 notes called them public, but only the full module path
  worked. Re-exported along with `append_snapshot` and `latest_snapshot`; `history` now
  declares `__all__`, so the module states its public interface and `from … import *`
  stops pulling in `json`, `Path` and `datetime`.

- **The migration page in the wheel had no 1.8.0 section.** The release's only user-facing
  change — Python 3.10 as the floor — was documented solely in `CHANGELOG.md`, which
  `MANIFEST.in` excludes from the package. Anyone following the documented path
  (`python -m partest.docs show howto-migration`) learned nothing about it, and the checklist
  still said `pip install -U 'partest>=1.5.0'`. On Python 3.9 the upgrade is silent: pip
  leaves you on the last supporting release. Now written down, with the command to check.

### Added

- `meta.selection` in the coverage payload, present only when the run was filtered.

`run_info["selection"]` deliberately survives `reset_storage()`: it is known at collection
time, before the session fixture that calls it, and describes the invocation rather than the
counters. Clearing it there would silently disarm the flag.

## 1.8.0

Raises the minimum Python to 3.10. Nothing else about the public API changed; the rest
of this entry is tooling and tests.

### Removed

- **Python 3.9 is no longer supported**; `python_requires` is now `>=3.10`. The claim had
  never been verified, and it did not hold: `partest-gen` crashed on 3.9 because
  `Path.write_text(newline=...)` needs 3.10, so every generated file raised a `TypeError`.
  Dropping a claim that was false beats keeping it. Suites on 3.9 keep resolving to 1.7.1.

### Added

- `.github/workflows/release.yml`: publishing through PyPI trusted publishing. A tag starts
  it, every check re-runs with `--strict-docs`, the tag is refused if it disagrees with
  `__version__`, and the `pypi` environment holds a required review before anything is
  uploaded. No API token exists at any point. The run is idempotent: it asks PyPI whether
  the version is already there and skips publishing if so, so a tag pushed after a manual
  upload — or a re-run — is not an error.
- `.github/workflows/checks.yml`: `tools/check_all.py` on push and pull request across the
  supported Python versions, plus a job that builds the artifacts and asserts nothing
  internal reached them. Publishing stays manual — a release is a deliberate act, not a
  consequence of a green build.
- `tests/test_coverage_keys.py`: a corpus for the function that decides which endpoint a
  call is counted against — nested templates, literal-versus-placeholder, verb suffixes,
  two parameters in one path, enum values, more than three segments, `after_url`,
  `defining_url` precedence, and the method as part of the key. It exercises the real entry
  point rather than the matcher underneath, because the wiring between them is where the
  previous heuristic went wrong.
- `tools/check_all.py --strict-docs` turns documentation warnings into failures. Without it
  a stale page is reported but does not reject a change; the release checklist uses it,
  because a release publishes those pages.

## 1.7.1

Metadata and documentation only; no code behaviour changed.

### Changed — distribution

- The source repository is public at `github.com/Dec01/partest`. PyPI carries the artifact,
  the repository carries how it was built and why — the decisions and their history do not
  ship in the wheel and were previously unreadable anywhere.
- `setup.py` gains `project_urls` for source, issues, changelog and documentation, and its
  `url` points at the repository rather than back at PyPI.
- Documentation still ships inside the wheel, now for the reason that it is convenient to
  read next to an installed package rather than because there was nowhere else to put it.
- `partest-gen` templates pin `partest>=1.7.0` instead of `>=1.5.0`. A suite generated today
  should not start on a version whose coverage keys and endpoint classification are known to
  be wrong.

## 1.7.0

Two releases' worth of work, published together: 1.6 fixed what the coverage number was
built on, 1.7 fixed the number itself. No breaking API changes — but coverage figures
will move, because path resolution and endpoint classification were wrong before. See
the consumer migration note for what to expect.


### Fixed

- **Coverage under pytest-xdist reported one worker's slice.** `call_storage` is per
  process, so a parallel run counted only the calls made by whichever worker rendered
  the report — a green suite measured 25.7% average with 58 endpoints marked as never
  called. Workers now write a shard when their session ends and the controller merges
  every shard before the run finishes; calls are summed and executed types unioned, so
  a later `RequestDefault` cannot overwrite an earlier `RequestElements`. On by
  default, `PARTEST_XDIST_MERGE=0` opts out, `PARTEST_CALL_STORAGE_DIR` moves the shard
  directory (LIB-XDIST).

  A report written *by a test* still cannot see the merge — that test runs on a worker.
  Run the coverage pass serially, or set `PARTEST_COVERAGE_JSON` /
  `PARTEST_COVERAGE_HTML` to have the controller write the artifact.

- **Allure step wrapper swallowed the real failure.** The guarded `_step` helper caught
  the exception raised by its own block and yielded a second time, so `contextlib`
  turned every failure inside a step into
  `RuntimeError: generator didn't stop after throw()`. Status-mismatch and schema
  diagnostics never reached the report. Present since the step helper was introduced;
  now `partest.allure_step.allure_step`, with a regression test.
- **Coverage keys for nested paths.** A concrete URL was mapped to a template by
  appending the first unused path parameter found anywhere in the specification, so
  `/orders/customer/5` became `/orders/customer/{id}` while the spec said
  `{customerId}` — the operation recorded zero calls and read as uncovered with green
  tests behind it. New `partest.path_match` matches per operation: equal segment count,
  literal segments must match, longest literal prefix wins. `defining_url` still
  overrides everything; the old heuristic remains as a fallback (LIB-PATH-RESOLVE).
- **Classifier matched substrings.** `/media-types`, `/departments` and `/mentions` all
  contain "me" and were classified as GET BY SELF, which changed their required P1 set.
  Self, upload and action detection now work on path segments and identifier tokens
  (LIB-CLASSIFY-TOKEN).
- **`POST /items/{id}/publish` was a create.** A verb in the last segment is now checked
  before "child under parent", so RequestNewObject no longer enters the P1 set of an
  operation that creates nothing (LIB-CLASSIFY-ACTION).
- **Created resources were lost when validation failed.** A 201 whose body failed
  `validate_model` (a new response field against `extra=forbid`) left the row on the
  stand: the id was extracted only after the call returned. `ApiClient` now emits a
  response hook after the status check and before schema validation, and
  `TrackingApiClient` registers the id there. The test still fails; the leftover does
  not happen. Opt out with `track_before_validate=False` (LIB-TRACK-VALIDATE).

### Added — licence

- `LICENSE` (MIT, `Copyright (c) 2024-2026 Parshin Ewgeniy`) ships in both the wheel and
  the sdist, and `license="MIT"` is declared in the metadata. The package had been
  claiming MIT in its classifiers and its description without carrying the text; every
  build warned about the missing file. The year range runs from the first PyPI release
  (`0.1.10`, 2 December 2024).

### Fixed — what gets published

- The sdist shipped `tests/` and the repo-facing `README.md`. The tests name the
  consumer project this library grew out of, reference an internal snapshot directory,
  and several of them depend on `tools/`, `docs/wiki/` and `.claude/`, which do not
  ship — so they could not pass from an sdist anyway. `MANIFEST.in` now prunes them
  along with `docs/`, `tools/`, `.claude/` and `.grok/`.
- Fifteen docstrings and one `--help` string described behaviour by naming the consumer
  project this library grew out of, in a published package. Reworded to say what they
  actually mean (sync pytest-playwright, page health, and so on).
- Historical changelog entries for 1.3–1.4 named the same project; the facts stay, the
  name is gone.
- The banner on generated documentation pointed at `docs/wiki/` and
  `tools/docs_build_wheel.py`, paths a user of the package does not have.

### Added — packaging and maintenance

- `partest/py.typed`: the package now ships its annotations, so a consuming project's
  type checker sees them. Coverage is partial and says so — `TrackingApiClient`
  delegates unknown attributes to the wrapped client and types as `Any` there.
- The `aqa_*` helpers in `partest.data_marker` emit a `DeprecationWarning` and will be
  removed in the next major version. They are older names for the same five functions,
  and one thing with two public names is a surface nobody benefits from. A deprecation
  that never warns never expires, hence the warning; `marked_name`, `marked_code` and
  the rest stay silent.
- `tools/check_all.py` runs tests, the documentation lint, the index check and the wheel
  drift check in one command; `--package` adds the build and `twine check`. There is no
  public CI here, so a single command is the only thing standing between a stale
  `partest/docs` and PyPI.
- UI cookbook gains "Covering a ticket item": Happy / Negative / Boundary / Side-effect /
  Close, and why asserting a value beats asserting that an element is visible
  (LIB-REC-UI-TICKET).

### Added — observing side effects

- `partest.sideeffects`: probe contracts for an object store, a broker and a database,
  plus `assert_locator` / `assert_status_enum` for the part of an async create that
  needs no credentials at all, and `wait_for` whose timeout message reports the last
  observation instead of just "timed out" (LIB-REC-SIDEEFFECT).
- Read-only by construction. The database probe rejects anything that is not a single
  SELECT — including `WITH x AS (DELETE ... RETURNING *) SELECT * FROM x`, which
  PostgreSQL would otherwise run. It errs towards refusing: blocking a legitimate read
  costs a rephrasing, letting a write through costs data.
- `observe_or_hold` records an unreachable surface instead of skipping the test, so the
  HTTP assertions keep their value and the gap stays visible in the report.
- `InMemoryObjectStore` and `InMemoryBus` let a suite be built before credentials
  exist, and mark everything they report as simulated. `Observation.require()` refuses
  a simulated observation outright — a fake proves the test wiring, never the system,
  and a green test backed by one is the false coverage this methodology exists to
  prevent.

### Added — cookbooks and the upload corpus

- `partest.files`: generated byte factories (`minimal_xlsx_bytes`,
  `minimal_ole_xls_bytes`, truncated and manifest-less packages, PNG/PDF stubs) and a
  mutation corpus — formats, content-versus-name spoofing, filename traversal and
  length, empty and modest sizes. Cases carry `gate_expect` with three values: a
  content-spoofed file is `fact`, because a gate that checks only the extension is a
  legitimate design rather than a bug. No zip bombs, no exploit payloads, nothing large
  enough to hurt a stand (LIB-REC-UPLOAD).
- Upload cookbook: the gate loop against the pipeline loop, the required cells for a
  `post_upload_file` subtype, multipart specifics, and why an over-limit case needs a
  documented limit first.
- Layers cookbook: L0–L4, the scenario classes, and the integration surfaces I0–I6.
  2xx is not persistence; journeys, invariants and integrations are checklist items, not
  extra cells in the coverage matrix (LIB-REC-PATH, LIB-REC-INTEGRATION, LIB-REC-E2E).
- A `type=` table in the recipes: which cell a call belongs to, including the classic
  hole where a fixture's setup POST records as the create endpoint's Default and the
  matrix looks covered while nothing tested creation (LIB-REC-TYPE).

### Added — coverage honesty

- Explicit subtype overrides: `subtype_overrides` in `confpartest.py` (a mapping or a
  path to YAML) pins the subtype for endpoints the classifier reads wrong. Routes match
  by shape, so `{id}` and `{orderId}` are the same route, and a malformed key or unknown
  subtype raises at load time instead of being ignored. Applied inside
  `classify_endpoint` rather than by rebinding it, because `coverage.py` imports that
  function by value before any project configuration is read (LIB-SUBTYPE-OVERRIDE).
- `compare_payloads` understands `kind`: an endpoint that was covered before and simply
  was not called this run is reported under `not_run`, never as a regression, and its
  `missing` list is ignored. The result carries `comparable` and `warnings`; an unmerged
  parallel run or a run with a fifth of the endpoints untouched is flagged.
  `python -m partest.reports compare --strict` exits 2 in that case (LIB-COV-CMP).

- `kind` per endpoint: `unseen / empty / partial / full / exception`, separate from the
  legacy `status`. "Nothing called this in this run" is not the same claim as "this has
  no tests", and a filtered or unmerged run produces the first in bulk (LIB-COV-KIND).
- `meta.workers`, `meta.merged`, `meta.partialRun`, `meta.callsTotal`,
  `meta.unseenRatio` in `coverage.json`, so a reader can tell what a number describes.
  `PARTEST_COVERAGE_REQUIRE_MERGE=1` fails the session instead of publishing a quiet
  wrong number (LIB-COV-META).
- Latency: every tracked call records `elapsed_ms`, including on the failure path.
  `timing` blocks with `n / msAvg / msP50 / msP95 / msMax` and a per-type breakdown are
  emitted per endpoint and for the run (LIB-COV-TIMING).
- Coverage history is pruned to the last two runs by default; `prune_snapshots`,
  `list_snapshots` and `previous_snapshot` are public. `keep=None` restores unbounded
  growth (LIB-COV-HIST-2).
- `partest.call_storage`: `write_shard`, `merge_shards`, `read_shards`, `clear_shards`,
  `worker_id`, `run_info`, `update_last_meta`.

- The interactive report opens with a banner when the run behind it does not describe the
  suite: parallel workers that were never merged, or a large share of endpoints never
  called. A **Not called this run** counter sits beside Full/Partial/Empty and filters the
  matrix when clicked, and `Reset filters` is now a visible control. Latency average and
  p95 appear once calls carry timings (LIB-COV-HTML, partly — drawer, hash-URL filters,
  CSV export and the command palette are still open).

### Added — report vitrine

- A **p95 ms** column in the matrix, coloured by the methodology thresholds (under 100
  fine, under 300 worth a look, above that bad). Endpoints with no measurement sort to
  the bottom whichever way the column is sorted: "unknown" is neither the fastest nor
  the slowest thing in the list.
- The active filter now lives in the URL, so a filtered view is a link you can send.
  A link wins over whatever the browser remembered locally.
- **Markdown** export of the current view, ready to paste into a ticket, carrying the
  partial-run or unmerged-workers caveat when there is one — the table travels, so the
  warning travels with it.

### Fixed — report template

- The shipped template hardcoded a consumer's service names in its filter presets and
  named that project in the footer. Presets are now generic (not called / partial /
  called-with-no-cells / write queue / writes only).
- Opening the report from a sandboxed or `data:` context blanked the whole page: the
  first `localStorage` access threw and no rendering ran at all. Every access is guarded,
  so persistence degrades instead of taking the report with it.
- The template mixed Russian and English in a page that ships to every user. It is now
  English throughout.

### Added — access, hooks and cleanup

- `partest.access`: `access_cases`, `AccessCase`, `anonymous_headers`,
  `invalid_bearer_headers`, `UserActivity` protocol — the four permission cells
  (allow / no_access / inactive / unauth) instead of a single 401. Cookbook:
  `python -m partest.docs show howto-permissions` (LIB-REC-ACCESS).
- `PERMISSION_CELLS`, `PERMISSION_CELL_EXPECTATIONS`, `permission_cell_label` — cell
  labels without adding a new required `request_*` type (LIB-PERM-QUAD).
- `ApiClient.add_response_hook(hook)` — `hook(method, endpoint, body, response)` runs
  after the status check, before schema validation. Hook exceptions are logged, never
  raised, so they cannot mask the real assertion.
- `CreatedRegistry.snapshot()` / `since(mark)` / `cleanup_since(mark, ...)` — drain what
  one test created without every project writing the same autouse fixture.
- `BaseRequestBody._cleanup_fields` and `get_json_required_marked()` — keep the marker
  in a required-only create so delete-by-marker cleanup can still find the row
  (LIB-BODY-MARK).
- `partest.path_match` — `build_concrete_url`, `match_template`,
  `resolve_endpoint_template`. Pure functions, testable without a stand.

### Changed — documentation

- Documentation reorganized into four layers: `AGENTS.md` (boundaries, ≤60 lines),
  `.claude/skills/` (procedures, loaded on demand), `docs/wiki/` (knowledge),
  a local, git-ignored layer of immutable source snapshots. Rationale:
  ``docs/wiki/decisions/docs-architecture.md``.
- `docs/wiki/status.md` is now the only source of versions, waves and planned work; the
  duplicated status tables in `AGENTS.md`, `IMPLEMENTATION_PLAN.md`, `LIBRARY_ROADMAP.md`,
  `DEVELOPMENT.md` and `MIGRATION_1.3.0_ISSUES.md` were merged into it and archived.
- `partest/docs/` is **generated** from wiki pages marked `ships_in_wheel: true`
  (`tools/docs_build_wheel.py`) instead of being copied by hand. File names are now flat
  (`howto-quickstart.md`, `concepts-methodology.md`, …).
- Internal material no longer ships in the wheel: consumer migration tracker, status board and
  release checklist were removed from the published package.
- `setup.py` reads `__version__` from `partest/__init__.py` instead of duplicating the number,
  and `long_description` comes from the self-contained `docs/PYPI.md`.

### Added — documentation tooling

- `python -m partest.docs list | show <page> | path` — read the bundled documentation.
- `tools/docs_lint.py`, `tools/docs_index.py`, `tools/docs_build_wheel.py` and
  `tests/test_docs.py`: broken links, stale pages (page `verified` older than its `sources`),
  version literals, private data in shipped pages, and wheel drift now fail the test suite.

## 1.5.0

Bundles the previously unreleased 1.4.x / 1.5 / 1.6 / 1.7 waves from
the consumer backlog snapshot. Backward compatible with 1.4.0.

### Added — coverage extras (LIB-COV-*)

- ``ServiceMap`` — consumer prefix/tag injection; fallback = first segment after API prefix
- Interactive HTML vitrine (filters, heatmap, CSV/JSON export)
- ``coverage.json`` writer + ``zorro_enhanced()``
- ``compare_payloads`` / SVG badge / missing-P1 pytest stubs / history snapshots
- CLI: ``python -m partest.reports`` (render / compare / badge / stubs / history-append)

### Added — methodology (LIB-CANON / LIB-BPLUS)

- ``canonicalize_type("type_default")`` → ``request_default`` (attribute-name aliases)
- ``TYPE_LABELS`` + optional P2 matrix cells (P1 set unchanged); ``p2_test_cases()``

### Added — UI extras (LIB-UI-FREEZE / CAP / HOOKS)

- Generic freeze CSS (scrollbars / scroll-behavior); sync
  ``inject_freeze_styles_sync`` / ``wait_ready_for_screenshot_sync``;
  optional ``hide_selectors`` (consumer), no product CSS
- ``capture_baselines_sync``, CLI ``--only``, scene ``id`` / ``full_page``,
  richer manifest; default CLI is sync Playwright
- ``partest.ui.hooks`` + optional plugin
  (``--frontend-url``, ``PARTEST_UI_MONITOR=1`` / ``--partest-ui-monitor``)
- ``compare_images(..., name=, diff_output=)`` + ``summary()`` / pixel counts
  (a local ``visual_compare`` shim can be dropped after the bump)

### Added — generator + IncorrectBody helper (LIB-GEN / LIB-REC-IB)

- ``partest.validation.incorrect_body``: ``RAW_INCORRECT_BODY_CASES`` +
  ``assert_raw_incorrect_body``
- ``partest-gen`` P1 IncorrectBody stubs parametrize the library cases
- Generated collections: ``HeadersBind`` + inherit ``partest.CollectionsManager``
- Generated UI: **sync** pytest-playwright + ``BasePage`` (not AsyncBasePage);
  ``pytest-playwright`` in ``requirements/ui.txt``; capture wrapper sync

### Docs / policy

- Recipes: Collections/HeadersBind, IncorrectBody param set, types (``docs/RECIPES.md``)
- ``docs/COVERAGE_REPORT.md``, ``docs/RELEASE_1.5.0.md``
- Distribution remains **PyPI only**; public GitHub is out of scope

## 1.4.0

### Added — UI parity (LIB-UI-01…06)

- **LIB-UI-01** Sync ``BasePage``; ``AsyncBasePage`` for async suites
- **LIB-UI-02** ``PageMonitor`` parity: ``attach``, ``finalize``, ``library_issues``,
  ``collect_loaded_assets``, ``attach_report``, critical network filter (assets 4xx + API 5xx)
- **LIB-UI-03** Public ``should_ignore_url`` / ``is_library_console_message``
- **LIB-UI-04** ``VisualCompareResult.ok`` alias for ``equal``
- **LIB-UI-05** ``Storage`` class (get_local/set_local/…)
- **LIB-12** Installable docs: ``partest.docs.read_doc("QUICKSTART.md")`` + package_data
- SoT copied in-repo: ``docs/MIGRATION_1.3.0_ISSUES.md``
- Health: ``require_app_shell``, ``assert_libraries_loaded``

### Breaking (UI)

- Default ``BasePage`` methods are **sync** (no ``await``). Use ``AsyncBasePage`` if you relied on async POMs from 1.3.x.

## 1.3.3

### Added — L5 enterprise polish
- **L5.1** `ApiClient(shared_client=True)` / inject `client=`; `aclose` / async context
- **L5.2** `RetryPolicy`: `max_retries`, `retry_statuses` (default 429/502/503), backoff
- **L5.3** `partest.redact` — header/body secret masking; used in attaches + status errors
- **L5.4** `set_status_hints_locale("en"|"ru")` for ErrorTemplates status hints
- **L5.5** `ApiClient.graphql(...)` convenience
- **L5.6** thread-safe `call_storage` + `dump_storage` / `merge_storage_files` for xdist
- Soft Allure: client steps/attaches no-op without allure package
- Docs: `docs/ENTERPRISE.md`

## 1.3.2

### Added — L1 tools & L3 UI isolation
- `partest.openapi.resolve_swagger` / `resolve_from_confpartest` (L1.10)
- `partest.tools.generate_init` + `partest-gen init-package-exports` (L1.11)
- `partest.env.profiles` — Keycloak/frontend helpers (L1.5)
- Tracking: `nested_id_extractor`, `field_id_extractor`, `chain_extractors` (L1.2)
- Docs: `REPORTING.md`, `SECURITY.md`, `UI_QUICKSTART.md`, `RECIPES.md` (L1.1/L2/L3/L4 recipes)
- UI PageMonitor: pageerror, console ignore, detach/reset, stricter mode, aliases
- `assert_page_console_clean`, storage session helpers, `set_auth_token_storage`
- BasePage: `expect_hidden`, `expect_url_contains`, screenshot `name=`
- Isolation tests: `import partest.ui` never loads project conf modules

### Fixed
- `get_local_storage` JS (was broken ellipsis)

## 1.3.1

### Fixed / multi-project safety (L0 from MIGRATION_1.3.0_ISSUES)

- **LIB-01** `RiskProfile` fields: `entity/writes/authz/pii/fk_traversal`,
  levels `critical|high|medium|low`; legacy `name`/`has_*` + `from_legacy()` kept
- **LIB-02** pytest plugin soft-disable: `PARTEST_PYTEST_PLUGIN=0`,
  `confpartest.pytest_plugin = False`, or `-p no:partest`
- **LIB-03** `expected_status_code` accepts `int | Sequence[int]` (ApiClient + SecHttp)
- **LIB-04** `PARTEST_FAKER_LOCALE` for data_marker Faker
- **LIB-05** TokenManager `verbose=False` + logging; optional `client_secret`
- **LIB-06** BaseRequestBody resolves `@property` / callable `_json_main`
- **LIB-07** confpartest + docs: matrix vs flat coverage

### Added (L1 starters)

- `CollectionsManager` + improved `BaseCollection.apply_token`
- `Config.apply_token`, `HeadersBind` / `Config.headers_bind`
- `partest.conf`: `load_confpartest`, `require_confpartest`, `validate_confpartest`
- Docs: `docs/QUICKSTART.md`, `docs/MIGRATION.md`
- Tests: `tests/test_migration_l0.py`

## 1.3.0

### Added — 1.2 security / http / plugin
- `partest.security.SecHttp` — raw httpx + optional Allure instrumentation
- `partest.security.jwt_craft` — `build_tampered_set`, alg=none, tampered payload
- `partest.http.Config` — headers/params builder (uuid Request-ID, Bearer)
- `partest.pytest_plugin` — Allure titles from docstring + failure_summary  
  (entry point `pytest11`)

### Added — 1.3 UI extra
- `partest.ui`: `BasePage`, `PageMonitor`, health, visual compare, freeze CSS,
  storage, Allure UI attaches
- `partest.ui.capture_baselines` — CLI + API for visual baseline PNGs  
  (`python -m partest.ui.capture_baselines --scenes scenes.json [--dry-run]`)
- Install: `pip install partest[ui]` (playwright, Pillow)
- Generator G5 re-exports library UI modules (thin consumer wrappers)

### Generator (G1–G6)
- `partest-gen`: init, from-openapi, sync-openapi, dump-ir, init-ui
- Depth: resources | default | p1
- G6 post-gen agent playbook (skill + `references/post-gen-playbook.md`)
- Golden e2e: `tests/test_project_gen_golden.py` (gen → import → collect-only)

## 1.0.0

### Added — coverage core & harness 1.1
- Methodology package, TypesTestCases, HTML/Allure zorro, raw body/CT
- TrackingApiClient, TokenManager, reporting, payloads, validation, env, data_marker
- Project skill, AGENTS.md, DEVELOPMENT.md

### Notes
- Explicit `type=` still recommended for ambiguous TC
- No product domain / private paths in public package
