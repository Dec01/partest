---
title: Статус, версии и что дальше
status: current
verified: 2026-09-04
sources: [partest/__init__.py, CHANGELOG.md]
audience: maintainer
ships_in_wheel: false
allow_version_literals: true
---

# Статус partest

**Единственный источник статусов.** Волны, версии, «что дальше» больше нигде не дублируются —
остальные страницы ссылаются сюда. Версия кода — `partest/__init__.py` (`__version__`).

| | |
|---|---|
| **Дата актуализации** | 2026-09-04 |
| **Текущий релиз** | **1.5.0** (PyPI) |
| **Дистрибуция** | только PyPI. Публичный GitHub не планируется — см. [[decisions/pypi-only]] |
| **Consumer proof** | aqa: `partest==1.5.0` / `partest[ui]==1.5.0`, волна W4 закрыта |
| **Источник бэклога** | снапшот `docs/raw/aqa/2026-09-04/` |
| **Сверка бэклога с кодом** | [[backlog-audit]] — волны 1.6 и 1.7 (P0-часть) реализованы |

---

## 1. Что уже универсально (не переизобретать)

| Блок | С какой версии |
|---|---|
| `ApiClient`: `content=` / `content_type=`, multi-status, rich errors | 1.3 |
| `TrackingApiClient` / `CreatedRegistry` | 1.3 |
| `reporting` / `check_*` / `conflict_hint_provider` | 1.3 |
| `TokenManager` + `credentials_provider` | 1.3 |
| `TypesTestCases` `request_*` + `canonicalize_type` | 1.3 |
| `RiskProfile` (модель без реестра сущностей) | 1.3.3 |
| `Config` + `HeadersBind.apply_token` | 1.3.3 |
| `BaseCollection` + `CollectionsManager` | 1.3.3 |
| UI: sync `BasePage`, `PageMonitor`, health, `Storage`, visual `.ok` | 1.4 |
| Доки внутри колеса (`partest.docs`) | 1.4 |
| Coverage extras: `zorro_enhanced`, CLI, `ServiceMap`, badge/stubs | 1.5.0 |
| IncorrectBody helper, freeze CSS sync, `compare_images(name=)` | 1.5.0 |

## 2. Волны — закрыты

| Волна | Фокус | Итог |
|---|---|---|
| 1.0–1.1 | методология, coverage, tracking, auth, reporting | 1.1 |
| 1.2 | `SecHttp`, JWT craft, `http.Config`, pytest-плагин | 1.2 |
| 1.3 | `partest[ui]`: BasePage / monitor / health / visual | 1.3 |
| L0 | multi-project safety | 1.3.1 |
| L1–L4 | drain API, cookbooks, UI isolation, recipes | 1.3.2 |
| L5 | enterprise: retry / redact / xdist-заготовки | 1.3.3 |
| 1.4 | UI parity: sync BasePage, PageMonitor, доки в колесе | 1.4.0 |
| G1–G6 | `partest-gen`: скелет → IR → ресурсы → P1 → UI → playbook | 1.4–1.5 |
| 1.5.0 | CANON + BPLUS + COV-* + UI freeze/cap/hooks + GEN | 1.5.0 (PyPI) |

`LIB-11` (изоляция `import partest.ui`) и `LIB-15` (self-tests харнесса) в бэклоге aqa помечены
«проверить в partest-repo» — **закрыты**: `tests/test_ui_isolation.py`, `tests/test_harness_1_1.py`.

## 3. Что дальше

### 1.6 — точность покрытия и доступы · **реализовано, не выпущено**

Код в ветке, тесты в `tests/test_wave_1_6.py`. Версия не бампалась — бамп делается
на релизе, см. [[howto/release]].

| ID | Задача | Где |
|---|---|---|
| **LIB-CLASSIFY-TOKEN** | `me`/`self`/`my` по границе слова и по сегментам; `media` не крадёт `media-types` | `partest/methodology/classifier.py` |
| **LIB-CLASSIFY-ACTION** | глагол в последнем сегменте → ACTION раньше POST TO OBJECT | там же |
| **LIB-PATH-RESOLVE** | конкретный URL → шаблон OpenAPI: сегментное сопоставление, самый длинный литеральный префикс | `partest/path_match.py`, `partest/coverage.py` |
| **LIB-TRACK-VALIDATE** | id регистрируется при 2xx **до** `validate_model` через хук ответа | `partest/client.py`, `partest/tracking.py` |
| **LIB-REC-CLEANUP** | `CreatedRegistry.snapshot()` / `since()` / `cleanup_since()` | `partest/tracking.py` |
| **LIB-BODY-MARK** | `_cleanup_fields` + `get_json_required_marked()` | `partest/payloads.py` |
| **LIB-REC-ACCESS** | 4 клетки доступа: хелперы + cookbook | `partest/access.py`, [[howto/permissions]] |
| **LIB-PERM-QUAD** | подписи клеток без нового обязательного `request_*` | `partest/test_types.py` |

Попутно найден и починен баг 1.5.0: обёртка Allure-шага превращала любое исключение
внутри блока в `RuntimeError: generator didn't stop after throw()`. Диагностика
несовпадения статуса и провала схемы до отчёта не доходила. Теперь `partest/allure_step.py`.

### 1.7 — честность покрытия · **ядро реализовано, не выпущено**

| ID | Задача | Статус |
|---|---|---|
| **LIB-XDIST** | воркеры пишут шарды, контроллер сливает до конца сессии; суммы вызовов, объединение типов | ✅ |
| **LIB-COV-KIND** | `unseen / empty / partial / full / exception` отдельно от legacy `status` | ✅ |
| **LIB-COV-META** | `meta.workers`, `merged`, `partialRun`, `callsTotal`, `unseenRatio` | ✅ |
| **LIB-COV-TIMING** | `elapsed_ms` на вызове, агрегаты avg/p50/p95/max и разбивка по типам | ✅ |
| **LIB-COV-HIST-2** | `keep=2` по умолчанию, обрезка старых снапшотов, `previous_snapshot` | ✅ |
| **LIB-COV-HTML** | целевой UX витрины: drawer, сброс фильтров, скролл матрицы, ms на клетке | ⬜ открыто |
| **LIB-SUBTYPE-OVERRIDE** | YAML/dict `(METHOD, template) → subtype`; применяется внутри `classify_endpoint`, поэтому виден декоратору | ✅ |
| **LIB-COV-CMP kind-aware** | `not_run` отдельно от `regressed`, `comparable` + `warnings`, `compare --strict` | ✅ |

Слияние проверено настоящим прогоном `-n 2` в подпроцессе, не моком:
`tests/test_wave_1_7.py::test_parallel_run_sees_every_endpoint`.

**Противоречие приоритетов снято.** `LIB-XDIST` и `LIB-COV-KIND` были помечены P0, но
стояли в 1.7 по порядку релизов; сделаны сразу после 1.6.

**Остаточное ограничение, важное для консьюмера.** Отчёт, который пишет тест
(`test_zorro`), слияния не видит: тест исполняется на воркере, слияние происходит на
контроллере после него. Либо гонять покрытие последовательно, либо отдать запись
артефакта контроллеру через `PARTEST_COVERAGE_JSON` / `PARTEST_COVERAGE_HTML`.
Подробности — [[concepts/coverage-honesty]] и [[howto/enterprise]].

### Позже

i18n шаблонов reporting · `LIB-PERM-QUAD` labels · `LIB-REC-CLEANUP` helper ·
`LIB-REDACT-CREDS` (не светить `password=` в traceback при 401) · `LIB-SEMVER` политика
для переименования алиасов `type_*`.

### HOLD — не тащить в 1.6/1.7

**Testing Atlas** (`src.atlas` / `src.viz`, pytest-плагины эффектов UI · DB · bus). Это не харнесс
покрытия. Не смешивать с `LIB-COV-HTML`. Даже переносимое ядро не извлекать, пока владелец
библиотеки не запросит отдельно. Спека: `raw/aqa/2026-09-04/LIBRARY_UPDATE_COVERAGE.md` §1.4.

### Cookbook-долг (не новые `request_*`)

`LIB-REC-UPLOAD` (POST upload: mutations, gate vs parse) · `LIB-REC-PATH` (слои L0–L4, UJ ≠ e2e) ·
`LIB-REC-INTEGRATION` (поверхности I0–I7; 201 ≠ persist) · `LIB-REC-E2E` (UI↔API) ·
`LIB-REC-SIDEEFFECT` (HOLD, пока нет доступа к object store / шине).

## 4. На стороне consumer (не в этом репозитории)

- **AQA-6** — зелёный полный прогон на стенде.
- Overlay `resource_tracker.py` (track до validate) снимается после `LIB-TRACK-VALIDATE` в 1.6.
- Навсегда остаются в aqa: `visual_scenes`, PROFILES, roles/credentials, page objects, SQL cleanup,
  baselines PNG. См. [[decisions/no-domain]].

## 5. Как обновлять эту страницу

1. Новый снапшот бэклога → `docs/raw/aqa/<дата>/`, старый не трогаем.
2. Переписать §3 по свежему снапшоту; противоречия разрешать в пользу более поздней даты и
   **явно называть** их, как сделано с `LIB-XDIST`.
3. Обновить `verified:` и добавить строку в [[log]].
