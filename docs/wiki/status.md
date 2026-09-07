---
title: Статус, версии и что дальше
status: current
verified: 2026-09-07
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
| **Дата актуализации** | 2026-09-07 |
| **Текущий релиз** | **1.8.1** — подготовлен, не опубликован; на PyPI пока `1.8.0`. Минимальный Python — 3.10 |
| **Дистрибуция** | PyPI — пакет, GitHub — исходники и история; см. [[decisions/distribution]] |
| **Consumer proof** | переезд `1.5.0 → 1.8.0` **состоялся** 2026-09-07: `8 failed, 2122 passed`, все падения предсуществующие; пять находок разобраны, см. §5 |
| **Источник бэклога** | снапшот консьюмера от 2026-09-04, хранится вне репозитория |
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

`LIB-11` (изоляция `import partest.ui`) и `LIB-15` (self-tests харнесса) во внешнем бэклоге помечены
«проверить в partest-repo» — **закрыты**: `tests/test_ui_isolation.py`, `tests/test_harness_1_1.py`.

## 3. Что дальше

### 1.6 — точность покрытия и доступы · **выпущено в 1.7.0**

Тесты в `tests/test_wave_1_6.py`. Выпущено вместе с 1.7 одним релизом.

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

### 1.7 — честность покрытия · **выпущено**

| ID | Задача | Статус |
|---|---|---|
| **LIB-XDIST** | воркеры пишут шарды, контроллер сливает до конца сессии; суммы вызовов, объединение типов | ✅ |
| **LIB-COV-KIND** | `unseen / empty / partial / full / exception` отдельно от legacy `status` | ✅ |
| **LIB-COV-META** | `meta.workers`, `merged`, `partialRun`, `callsTotal`, `unseenRatio` | ✅ |
| **LIB-COV-TIMING** | `elapsed_ms` на вызове, агрегаты avg/p50/p95/max и разбивка по типам | ✅ |
| **LIB-COV-HIST-2** | `keep=2` по умолчанию, обрезка старых снапшотов, `previous_snapshot` | ✅ |
| **LIB-COV-HTML** | баннер, KPI `unseen` с кликом в фильтр, видимый сброс, generic-пресеты, колонка p95 с порогами, фильтры в URL, экспорт CSV/JSON/markdown, весь текст английский | ✅ кроме палитры Ctrl+K и отдельного drawer (есть раскрывающаяся строка) |
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
библиотеки не запросит отдельно. Спека: снапшот бэклога, `LIBRARY_UPDATE_COVERAGE.md` §1.4.

### Cookbook-долг

| ID | Статус |
|---|---|
| `LIB-REC-UPLOAD` | ✅ [[howto/upload]] + корпус `partest.files` |
| `LIB-REC-PATH` / `LIB-REC-INTEGRATION` / `LIB-REC-E2E` | ✅ [[howto/layers]] — слои L0–L4, поверхности I0–I6 |
| `LIB-REC-TYPE` | ✅ таблица «какой `type=` для какого вызова» в [[howto/recipes]] |
| `LIB-REC-ACCESS` | ✅ [[howto/permissions]] |
| `LIB-REC-CLEANUP` | ✅ [[howto/recipes]] |
| `LIB-REC-UI-TICKET` | ✅ раздел «Covering a ticket item» в [[howto/ui]] |
| `LIB-REC-SIDEEFFECT` | ✅ `partest.sideeffects` — контракт наблюдения, read-only пробы, фейки для разработки, HOLD вместо skip |

## 4. На стороне consumer (не в этом репозитории)

- ✅ Полный прогон на стенде консьюмера — сделан 2026-09-07, см. §5.
- Overlay `resource_tracker.py` снимается — **не сделано**, и до тех пор `LIB-PATH-RESOLVE`
  у консьюмера не работает: overlay навязывает `defining_url`, который главнее (§5).
- Навсегда остаются у консьюмера: `visual_scenes`, PROFILES, roles/credentials, page objects, SQL cleanup,
  baselines PNG. См. [[decisions/no-domain]].

## 5. Отчёт о переезде консьюмера 1.5.0 → 1.8.0 (2026-09-07)

Переезд выполнен и задокументирован на стороне консьюмера. Полный прогон:
`8 failed, 2122 passed, 3 skipped`; все восемь падений проверены откатом на `1.5.0` и
падают идентично — к переезду отношения не имеют.

**Что подтвердилось на живой спеке, а не в юнит-тестах:**

| Заявление | Проверка консьюмера |
|---|---|
| `LIB-PATH-RESOLVE` | 8 из 8 вложенных путей, 0 расхождений |
| `LIB-CLASSIFY-*` | верный подтип по всем 12 путям **без** overrides |
| `LIB-SUBTYPE-OVERRIDE` | 12 активных, monkeypatch в `confpartest` снят |
| `LIB-ALLURE-STEP` | `RuntimeError: generator didn't stop after throw()` → настоящий `AssertionError` с телом ответа |

**Важное наблюдение.** Цифра покрытия не сдвинулась вообще (`95.74 → 95.74`, `regressed 0`) —
но не потому, что 1.7.0 ничего не дал. Консьюмерский overlay навязывает `defining_url`
каждому вызову, а `defining_url` главнее `path_match`, поэтому `LIB-PATH-RESOLVE` в том
прогоне не сработал ни разу. То есть **приоритет `defining_url` маскирует починку резолвера**
у всех, кто носит такой overlay. Выгода придёт со снятием overlay.

**Пять находок — все разобраны в 1.8.1:**

| # | Находка | Что сделано |
|---|---|---|
| F-1 | фильтр по маркерам режет клетки, а не эндпоинты → 14 ложных регрессий со штампом «сравнимо» | `meta.selection` из плагина + эвристика обвала вызовов в `compare`; [[concepts/coverage-honesty]] §2 |
| F-2 | в колесе 1.8.0 нет раздела про 1.8.0 и про Python 3.10 | раздел в [[howto/migration]], чек-лист исправлен |
| F-5 | сравнение со снимком старше `kind` всегда даёт ложный `not_run` | `kind` выводится из `calls`, когда ключа нет |
| F-3 | `parparser.py`: 12 `print()` в stdout при каждом импорте | переведено на `logging` |
| F-4 | хелперы истории не реэкспортированы | реэкспорт + `__all__` в `history` |

Тесты: `tests/test_report_comparability.py` (19 случаев), корпус построен на замерах отчёта.
Проверено на присланных снимках: `compare --strict` был `exit 0` с 14 регрессиями, стал
`exit 2` с названными причинами.

Отчёт и снимки — в репозитории консьюмера, `docs/partest/MIGRATION_1.8.0_REPORT.md`.

## 6. Как обновлять эту страницу

1. Новый снапшот бэклога → локальный `docs/raw/<источник>/<дата>/` (вне git), старый не трогаем.
2. Переписать §3 по свежему снапшоту; противоречия разрешать в пользу более поздней даты и
   **явно называть** их, как сделано с `LIB-XDIST`.
3. Обновить `verified:` и добавить строку в [[log]].
