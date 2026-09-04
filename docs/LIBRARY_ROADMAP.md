# partest — универсальный роадмап library

**Аудитория:** владелец `partest` (не consumer aqa).  
**Инвариант:** всё ниже — **проект-независимо**. Никаких entity DTO, ролей Keycloak,
URL стендов, SQL-схем, page objects экранов.

Consumer SoT: [`MIGRATION_1.3.0_ISSUES.md`](MIGRATION_1.3.0_ISSUES.md).  
Источник предложений: aqa `docs/partest/LIBRARY_ROADMAP.md` (2026-08-13).

| | |
|---|---|
| **Дата** | 2026-08-14 |
| **Текущий релиз** | 1.5.0 (PyPI) |
| **Дистрибуция** | **только PyPI**. Публичный GitHub **не планируется** |
| **Принцип** | greenfield API/UI без копипасты consumer-utils |

---

## 0. Что уже универсально (не повторять)

| Блок | Где |
|---|---|
| ApiClient: `content=` / `content_type=`, multi-status, rich errors | 1.3+ |
| TrackingApiClient / CreatedRegistry | 1.3 |
| reporting / `check_*` / conflict_hint_provider | 1.3 |
| TokenManager + credentials_provider | 1.3 |
| RiskProfile model (без registry сущностей) | 1.3.3 |
| Config + **HeadersBind.apply_token** | 1.3.3 |
| **BaseCollection** + **CollectionsManager** | 1.3.3 |
| TypesTestCases `request_*` + `canonicalize_type` | 1.3 |
| UI: sync BasePage, PageMonitor, health, Storage, visual `.ok` | 1.4 |
| `partest.docs` в wheel | 1.4 |
| Isolation tests + harness `tests/` | 1.4 (локально; public CI нет) |
| Interactive coverage / CLI / IB helper / UI freeze | **1.5.0** |

Consumer proof (aqa 2026-08-13 / W3): pin 1.4.0, UI drain, HeadersBind +
CollectionsManager, `type=request_*`, raw IncorrectBody на ≥6 write-сущностях.
W4 (pin 1.5.0) — после upload, см. [`RELEASE_1.5.0.md`](RELEASE_1.5.0.md).

---

## 1. Must — качество library (P1) → **1.5.0**

| ID | Задача | Acceptance | Status |
|---|---|---|---|
| **LIB-15** | Harness self-tests | `python -m pytest tests/ -q`: raw body, multi-status, Tracking 409, canonicalize, plugin on/off, HeadersBind | **done** in-repo (`tests/`) |
| **LIB-11** | Isolation: `import partest.ui` без сети/OpenAPI | `tests/test_ui_isolation.py` | **done** |
| **LIB-CANON** | `canonicalize_type("type_default")` → `request_default` | alias имён атрибутов `type_*` + тест | **done** (1.5.0) |
| **LIB-BPLUS** | TYPE_LABELS / matrix P2 для B+ | labels + optional P2 set; P1 не менять | **done** (1.5.0) |
| **LIB-D7** | Allure soft-dep в docs | REPORTING + ENTERPRISE | **done** (docs) |

---

## 2. Product — coverage & DX (P2) → **1.5.0** ✅

EXTRACT из aqa `src/api/utils/coverage_report/` (без имён сервиса).

| ID | Задача | Универсальный контракт |
|---|---|---|
| **LIB-COV-HTML** | Интерактивный HTML | вход = `CoverageReport` / `coverage.json`; service map **инъекция** |
| **LIB-COV-CMP** | Compare двух `coverage.json` | `{added, removed, avg_delta, missing_fixed, missing_new}` |
| **LIB-COV-BADGE** | SVG badge из average | `coverage.svg` |
| **LIB-COV-STUB** | pytest stubs для missing P1 | `type=types.request_*` |
| **LIB-COV-HIST** | Append snapshot | каталог JSON, не БД |
| **LIB-COV-CLI** | `python -m partest.reports` | compare / badge / stubs / history-append / render |

Service map YAML — **consumer**. Library: `ServiceMap` + fallback «первый сегмент после api prefix».

---

## 3. Recipes (P2) → **1.5.0 docs**

| ID | Тема |
|---|---|
| **LIB-REC-CM** | HeadersBind + BaseCollection + CollectionsManager |
| **LIB-REC-IB** | IncorrectBody `(content, content_type, expected=(400,415))` |
| **LIB-REC-MONO** | API extras ≠ UI extras; `pytest_plugin=False` |
| **LIB-REC-TYPE** | `type=types.request_default`, не строка `"type_default"` |
| **LIB-GEN** | partest-gen: `request_*`, TrackingApiClient, HeadersBind, sync UI |

---

## 4. UI extras (P2 / optional) → **1.5.0** (was 1.6 plan)

| ID | Задача | Не тащить |
|---|---|---|
| **LIB-UI-FREEZE** | generic freeze CSS + sync/async `wait_ready` | domain / Quasar selectors |
| **LIB-UI-CAP** | `capture_baselines` + hooks `login` / `scenes` / `--only` | Keycloak admin walk |
| **LIB-UI-HOOKS** | optional plugin: attach PageMonitor / finalize | product `frontend_url` fixture |

**done in 1.5.0.** `hide_selectors` / `login` / `prepare` — consumer.

---

## 5. Enterprise (P3) → later

| ID | Задача | Notes |
|---|---|---|
| **LIB-XDIST** | xdist-safe `call_storage` | **done** 1.3.3 (`dump_storage` / `merge_storage_files`) |
| **LIB-REDACT** | redact в attaches по умолчанию | **done** 1.3.3 (`partest.redact` + reporting) |
| **LIB-I18N** | locale-neutral templates; RU/EN provider | **done** 1.3.3 (`set_status_hints_locale`) |
| **LIB-SEMVER** | major при снятии aliases `type_*` | documented in MIGRATION.md |

---

## 6. Чего **никогда** не класть в partest

- paths / DTO / validations конкретного API  
- RBAC matrix, список ролей, PROFILES сущностей  
- SQL cleanup, маркеры `AQA` как единственный API  
- page objects экранов, PNG baselines, URL стендов  
- the container platform / GitLab / SSH  
- публикация этого дерева в публичный GitHub  

---

## 7. Порядок релизов

```text
1.4.0  UI parity + docs-in-wheel                         shipped PyPI
1.5.0  CANON + BPLUS + COV + UI freeze/cap/hooks + GEN   shipped PyPI
later  (none from this roadmap — next library work on request)
```

Публичный GitHub не планируется. aqa W4: [`RELEASE_1.5.0.md`](RELEASE_1.5.0.md) §4.

aqa: bump pin → smoke collect → optional drain `coverage_report` / IB helper → AQA-6.
