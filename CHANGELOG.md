# Changelog

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

- **A third outcome for checks: «not measured».** The seventeen `ah.check_*` helpers have two
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
  and `attach_not_measured`. The existing seventeen checks are untouched. See
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
