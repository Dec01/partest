# Changelog

## Unreleased

### Changed — documentation

- Documentation reorganized into four layers: `AGENTS.md` (boundaries, ≤60 lines),
  `.claude/skills/` (procedures, loaded on demand), `docs/wiki/` (knowledge),
  `docs/raw/` (immutable source snapshots). Rationale:
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

### Added

- `python -m partest.docs list | show <page> | path` — read the bundled documentation.
- `tools/docs_lint.py`, `tools/docs_index.py`, `tools/docs_build_wheel.py` and
  `tests/test_docs.py`: broken links, stale pages (page `verified` older than its `sources`),
  version literals, private data in shipped pages, and wheel drift now fail the test suite.

## 1.5.0

Bundles the previously unreleased 1.4.x / 1.5 / 1.6 / 1.7 waves from
the consumer backlog snapshot. Backward compatible with 1.4.0.

Release record: ``docs/archive/RELEASE_1.5.0.md``.

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
  (aqa ``visual_compare`` shim can drop after bump)

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

### Added — UI parity for aqa drain (LIB-UI-01…06)

- **LIB-UI-01** Sync ``BasePage`` (aqa-compatible); ``AsyncBasePage`` for async suites
- **LIB-UI-02** ``PageMonitor`` parity: ``attach``, ``finalize``, ``library_issues``,
  ``collect_loaded_assets``, ``attach_report``, critical network filter (assets 4xx + API 5xx)
- **LIB-UI-03** Public ``should_ignore_url`` / ``is_library_console_message``
- **LIB-UI-04** ``VisualCompareResult.ok`` alias for ``equal``
- **LIB-UI-05** ``Storage`` class (get_local/set_local/…)
- **LIB-12** Installable docs: ``partest.docs.read_doc("QUICKSTART.md")`` + package_data
- SoT copied in-repo: ``docs/MIGRATION_1.3.0_ISSUES.md``
- Health: ``require_app_shell``, ``assert_libraries_loaded`` aqa-style

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

- **LIB-01** `RiskProfile` aligned with aqa: `entity/writes/authz/pii/fk_traversal`,
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
