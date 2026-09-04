---
name: partest
description: >
  Build and grow API/UI autotest suites with the partest library: OpenAPI coverage,
  methodology (subtypes × test cases × steps), ApiClient, zorro reports.
  Use when writing API tests, coverage plans, IncorrectBody/transport cases,
  scaffold pytest+partest projects, or user runs /partest.
---

# partest — API & UI coverage skill

## When this skill applies

- Scaffold or extend Python API autotests with OpenAPI coverage
- Choose test-case types and method subtypes correctly
- Improve coverage % / fill missing P1 cases from `zorro` / HTML report
- Write transport IncorrectBody (raw body / Content-Type) via ApiClient
- Plan UI suite structure (`partest[ui]` for harness; keep domain POM in consumer)

## Hard rules

1. **Library is project-agnostic.** Never hardcode product entities, stand URLs, private paths, or RBAC role lists into `partest` itself.
2. **No private links** in package code/docs that ship in the **PyPI** wheel. Public GitHub is out of scope — do not plan a source dump.
3. Prefer **canonical TC names**: `request_default`, `request_not_allowed`, … Legacy `default` / `405` still work.
4. **Always pass `type=`** for ambiguous cases: permissions, new/update object, elements, extra_data, env, benchmark. Inference is only high-confidence for 405/404/broken raw body.
5. Coverage “100%” means **required P1 TC set for the method subtype is present**, not “a file exists”.
6. Create/update endpoints need **vertical** TC (`request_new_object` / `request_update_object`), not only default on seed data.
7. Assert depth: status → `validate_model` → value checks. Status-only is not enough for Default/Elements/Benchmark.

## Workflow: cover an API

### Step 1 — wire project

```text
confpartest.py          # swagger_files local|url
conftest.py             # domain, api_client, reset_storage()
src/tests/test_zorro.py # calls zorro() last
```

```python
from partest import ApiClient, TypesTestCases, reset_storage
from partest.zorro_report import zorro
```

### Step 2 — classify each operation

Use OpenAPI method+path. Library classifier (`classify_endpoint`) maps to subtypes:

| Pattern | Subtype |
|---------|---------|
| GET collection, no id | `get_list_objects` |
| GET `.../{id}` | `get_dynamic_object` |
| GET static catalog/enums | `get_static_object` |
| GET `.../parent/{id}` children | `get_by_parent` |
| POST create | `post_create_object` |
| POST + multipart/upload | `post_upload_file` |
| PUT/PATCH | `put_object` / `patch_*` |
| DELETE | `delete_object` (+ soft/physical when known) |
| non-CRUD verb | `action` |

### Step 3 — pick required P1 TC from matrix

Import mentally (or read `partest/methodology/matrix.py`):

- GET STATIC: Default + Benchmark
- GET DYNAMIC / LIST: Default + Permissions (+ NotFound for dynamic)
- POST CREATE: Default, Permissions, NewObject, IncorrectBody, Elements, ExtraData
- PUT: Default, Permissions, UpdateObject, IncorrectBody, Elements, ExtraData, NotFound
- DELETE: Default, Permissions, NotFound
- Always consider NotAllowed (405) at P3 unless suite uses flat required list

### Step 4 — implement with ApiClient

```python
types = TypesTestCases

await api_client.make_request(
    "GET",
    "/items/{id}",
    add_url1=f"/{item_id}",
    defining_url="/items/{id}",  # OpenAPI template path for coverage match
    expected_status_code=200,
    validate_model=ItemValidation,
    type=types.request_default,
)
```

**Path matching tips**

- Prefer `defining_url` equal to OpenAPI path template when path params are dynamic.
- Or use `add_url*` so tracker rewrites values to `{param}` via swagger enums.

### Step 5 — transport IncorrectBody

```python
await api_client.make_request(
    "POST",
    "/items",
    content=b'{"a":',
    content_type="application/json",
    expected_status_code=400,  # or 415 for CT abuse
    type=types.request_incorrect_body,
)
```

Do **not** bypass ApiClient with raw httpx for suite coverage — raw calls are invisible to partest counters.

### Step 6 — measure

```python
report = zorro()  # Allure + simple HTML
# interactive HTML + coverage.json (LIB-COV):
from partest.reports import zorro_enhanced
zorro_enhanced()
# report.endpoints[*].missing_p1  → backlog for next TC
```

CLI: `python -m partest.reports compare|badge|stubs|render`.  
Always `type=types.request_default` — not the string `"type_default"` (`canonicalize_type` maps it).

Prioritize **endpoint impact** first (auth/money/PII), then P1 TC depth. Do not polish P3 on low-risk catalogs before P1 on critical writes.

## UI guidance (consumer + `partest[ui]`)

- Keep page objects domain-specific in the consumer project.
- Shared harness: `pip install partest[ui]` → BasePage, monitor, visual compare, health asserts.
- Sync freeze/wait: `inject_freeze_styles_sync` / `wait_ready_for_screenshot_sync`.
- Capture: `python -m partest.ui.capture_baselines --scenes …` (sync by default; `--only`).
- Optional plugin: `pytest_plugins = ["partest.ui.pytest_plugin"]`; autouse monitor via `PARTEST_UI_MONITOR=1`.
- API session/OpenAPI load must **not** be imported by pure UI suites (isolation).

## Checklist before claiming “endpoint covered”

- [ ] Subtype identified
- [ ] All P1 TC for subtype present with correct `type=`
- [ ] Vertical TC if create/update exists
- [ ] Status + schema validation on positive TC
- [ ] Value asserts for Default/Benchmark/Elements where data is deterministic
- [ ] Cleanup for created resources (consumer tracker)
- [ ] `zorro` missing_p1 empty for that endpoint

## Harness imports (1.1–1.4)

```python
from partest import (
    ApiClient, TrackingApiClient, CreatedRegistry,
    TokenManager, BaseRequestBody, Config, SecHttp, build_tampered_set,
    TypesTestCases, marked_name, RiskProfile, CollectionsManager,
)
# Plugin dual-hook opt-out: PARTEST_PYTEST_PLUGIN=0 or confpartest.pytest_plugin=False
# Multi-status: expected_status_code=(400, 415)
# RiskProfile("entity", writes=True, fk_traversal=True) — PROFILES dict stays consumer
from partest.validation import BaseResponseValidator, ProblemDetailValidation
import partest.reporting as ah
from partest.env import load_project_env, require_env
from partest.zorro_report import zorro
# UI (pip install 'partest[ui]>=1.5.0'):
from partest.ui import (
    BasePage, AsyncBasePage, PageMonitor, Storage,
    attach_monitor, assert_page_healthy, compare_images,
    should_ignore_url, is_library_console_message,
)
```

- `TokenManager`: inject `credentials_provider(role) -> (user, password)`
- `SecHttp` + `build_tampered_set` for security suite (raw httpx / JWT)
- `Config` for headers; pytest plugin enriches Allure titles automatically

## Scaffold / project_gen (G1–G6)

```bash
partest-gen from-openapi ./my-suite --file openapi.yaml --depth p1 --force --with-ui
partest-gen init-ui ./my-suite --force
partest-gen sync-openapi ./my-suite --depth p1
partest-gen dump-ir openapi.yaml -o .partest/suite_ir.json
```

| Wave | Output |
|------|--------|
| G1–G2 | skeleton, IR, paths, collections |
| G3 | payloads, validations, Default/405 |
| G4 | full P1 stubs + `P1_CHECKLIST.md` |
| G5 | deep `src/ui` (isolated conftest, POM, monitor, visual) |
| G6 | post-gen agent playbook (this section + references) |

**Prefer `--depth p1` + `--with-ui` / `init-ui` for greenfield.**

### After generation — agent loop (G6)

Full checklist: `references/post-gen-playbook.md`. Short form:

1. **Read maps** — `.partest/openapi_summary.md`, `src/api/tests/<tag>/P1_CHECKLIST.md`
2. **Wire** — `.env` (`BASE_URL`, Keycloak), `roles.py` → TokenManager in API conftest
3. **Impact order** — auth/money/PII writes before catalog GETs
4. **Per endpoint** — unskip stubs → seed / `add_url1` → `type=` → status + schema + values  
   Vertical TC for create/update; IncorrectBody via `content=` on ApiClient only
5. **Measure** — `pytest src/api/tests` → `test_zorro` → close `missing_p1`
6. **Sync** — `partest-gen sync-openapi … --depth p1` (banner files only unless `--force`)
7. **UI (separate job)** — login POM, api_seed, smoke → baselines:

```bash
python -m partest.ui.capture_baselines --out src/ui/baselines/reference \
  --scenes src/ui/tools/scenes.example.json --dry-run
python -m src.ui.tools.capture_baselines   # consumer wrapper
```

8. **Never** load OpenAPI / coverage session from `src/ui/conftest`

Use generated façades: `models.<tag>.paths.*`, `.payload.*()`, `.validate.*`, `.headers.read|write`.

### Definition of done (slice)

- [ ] P1 TC for chosen endpoints with correct `type=`
- [ ] Vertical TC where create/update exists
- [ ] `zorro` missing_p1 empty for those endpoints
- [ ] Cleanup via TrackingApiClient; no secrets in git
- [ ] UI isolation preserved; reference baselines committed only when selectors stable

## References in this skill

- `references/methodology-cheatsheet.md` — compact subtype × TC matrix
- `references/post-gen-playbook.md` — full G6 agent loop after scaffold
- Library SoT: `partest/methodology/`, `docs/README.md`, `AGENTS.md`
- Generator target: `docs/PROJECT_GEN_ROADMAP.md`
- Cookbooks: `docs/REPORTING.md`, `SECURITY.md`, `UI_QUICKSTART.md`, `RECIPES.md`
- UI isolation: never load OpenAPI from `src/ui`; `import partest.ui` is conf-free
