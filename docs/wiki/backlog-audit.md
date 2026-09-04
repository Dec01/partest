---
title: Аудит бэклога aqa и готовность к переезду
status: current
verified: 2026-09-04
sources: [partest/tracking.py, partest/coverage.py, partest/methodology/classifier.py, partest/payloads.py, partest/call_storage.py, partest/reports/payload.py, partest/reports/analyzer.py, partest/pytest_plugin.py]
audience: maintainer
ships_in_wheel: false
allow_version_literals: true
---

# Аудит бэклога и готовность к переезду

Сверка 10 документов из `docs/raw/aqa/2026-09-04/` с фактическим кодом библиотеки.
Каждый вердикт проверен запуском или чтением кода — ссылки на строки приведены.

## Вывод

| | |
|---|---|
| **Документационные требования бэклога** | применены — снапшот принят, план разнесён по [[status]] |
| **Кодовые требования бэклога (1.6 и 1.7)** | **не применены** — ни один пункт |
| **Можно ли переезжать aqa на новую версию** | **нет смысла**: кодовых изменений нет, `1.5.0` остаётся функционально актуальным |
| **Что реально изменилось** | документация, упаковка колеса, `python -m partest.docs`, линтер доков |

Если выпустить версию сейчас — это патч-релиз про документацию и упаковку.
Переезд aqa он не разблокирует: overlay `resource_tracker.py`, ручная нарезка
Permissions и запрет `-n` на прогоне покрытия остаются нужны.

---

## 1. Что применено в этой сессии

| Требование бэклога | Где выполнено |
|---|---|
| «не гонять `zorro` под xdist» — написать красным в доках 1.6 (`LIBRARY_UPDATE_COVERAGE` §5) | [[concepts/coverage-honesty]] §1, скилл `partest-cover-api`, [[howto/enterprise]] |
| unseen ≠ empty ≠ «нет тестов» — зафиксировать как канон (§2.1) | [[concepts/coverage-honesty]] §2 |
| дисциплина `type=`, инференс не заменяет явный тип (§2.2) | [[decisions/explicit-type]], [[concepts/methodology]] |
| объём = OpenAPI op × P1 клетки подтипа, не 12 TC на path (§2.4) | [[concepts/methodology]] |
| «после реализации в partest — короткая шапка и ссылка на `partest.docs`» | снапшот в `docs/raw/`, план в [[status]] |
| ACCESS / CLEANUP / UPLOAD / PATH → в `partest.docs` | **не сделано**: cookbook-страниц нет, см. §3 |

Дополнительно, вне бэклога: из колеса убраны внутренние документы (трекер миграции
консьюмера, доска статусов, релизный чек-лист), которые уезжали к пользователям PyPI.

## 2. Кодовые пункты — проверка построчно

### 1.6

| ID | Требование | Статус | Доказательство |
|---|---|---|---|
| **LIB-TRACK-VALIDATE** | регистрировать create-id при 2xx **до** `validate_model` | ❌ нет | [tracking.py:196](partest/tracking.py:196) — экстракторы вызываются после `await call(...)`; исключение из валидации до них не доходит |
| **LIB-CLASSIFY-TOKEN** | `me`/`self`/`my` по границе слова | ❌ нет, баг воспроизводится | [classifier.py:21](partest/methodology/classifier.py:21) — `(me\|self\|current\|my\|mine\|…)` без `\b`. Проверено: `/media-types` → self-hint `True`, `/mentions` → `True` |
| | `media` не «крадёт» `media-*` | ❌ нет | [classifier.py:24](partest/methodology/classifier.py:24) — `_UPLOAD_HINTS` тоже ловит `/media-types` |
| **LIB-CLASSIFY-ACTION** | ACTION раньше POST TO OBJECT для глагола в конце | ⚠️ частично | [classifier.py:179](partest/methodology/classifier.py:179) и `:184` — проверки есть, но под условиями `not create_like` / `not ends_with_param`; кейс `POST /items/{id}/publish` требует теста |
| **LIB-PATH-RESOLVE** | конкретный URL → шаблон OpenAPI, вложенные `/{parent}/{id}` | ❌ нет | [coverage.py:50-89](partest/coverage.py:50) — эвристика по `add_url1..3` поверх **глобального** словаря path-параметров всех путей, а не сопоставление с шаблоном конкретной операции |
| **LIB-REC-ACCESS** | cookbook 4 клеток: allow / no_access / inactive / unauth | ❌ нет | страницы нет; `request_permissions` в [[concepts/methodology]] описан как одна клетка |
| **LIB-BODY-MARK** | `_cleanup_fields` + `get_json_required_marked()` | ❌ нет | [payloads.py:117](partest/payloads.py:117) — есть `get_json_required` / `get_json_miss_required`, полей очистки нет |
| **LIB-PERM-QUAD** | labels для четырёх клеток | ❌ нет | `TYPE_LABELS` в `test_types.py` без разбивки permissions |
| — | `CreatedRegistry.snapshot()` / `cleanup_since(n)` | ❌ нет | [tracking.py:94](partest/tracking.py:94) — только `track`, `count`, `items`, `clear`, `cleanup` |

### 1.7

| ID | Требование | Статус | Доказательство |
|---|---|---|---|
| **LIB-XDIST** (P0) | merge `call_storage` между воркерами | ⚠️ примитивы есть, автоматики нет | [call_storage.py:58](partest/call_storage.py:58) `dump_storage`, `:102` `merge_storage_files` — вызывать надо руками; в [pytest_plugin.py](partest/pytest_plugin.py) только `pytest_itemcollected` и `pytest_runtest_makereport`, хука `sessionfinish` / controller нет |
| **LIB-COV-KIND** (P0) | `unseen / empty / partial / full / exception` | ❌ нет | [payload.py:26](partest/reports/payload.py:26) — `_status_of` возвращает `ep.status or "empty"`, таксономии `kind` нет |
| **LIB-COV-META** | `meta.merged`, `meta.workers` в JSON | ❌ нет | [payload.py:274](partest/reports/payload.py:274) — `meta` = `generated / engine / title / defaultExcluded` |
| **LIB-COV-TIMING** | `elapsed_ms` → avg/p50/p95 по type × subtype | ❌ нет | `call_meta` в `call_storage` существует как контейнер, замеров и агрегации нет |
| **LIB-COV-HIST-2** | история прогонов, `keep=2`, Δ двух прогонов | ⚠️ частично | `partest/reports/history.py` есть; `keep=2` по умолчанию и timing в снапшоте — проверить отдельно |
| **LIB-COV-HTML** | целевая витрина (drawer, сброс фильтров, скролл матрицы) | ⚠️ частично | `interactive_html.py` из 1.5.0; целевой UX бэклога шире |
| **LIB-SUBTYPE-OVERRIDE** | YAML-map `(METHOD, path) → subtype` + rebind | ❌ нет | в `methodology/` и `conf.py` нет ни override, ни точки подмены |

### Cookbook-долг (docs, не код)

`LIB-REC-UPLOAD` (мутации файла, gate vs parse) · `LIB-REC-PATH` (слои L0–L4, оси F и I) ·
`LIB-REC-INTEGRATION` (201 ≠ persist) · `LIB-REC-E2E` · `LIB-REC-TYPE` · `LIB-REC-CLEANUP` ·
`LIB-REC-UI-TICKET` — ни одной страницы нет. Спеки лежат в `docs/raw/aqa/2026-09-04/`.

## 3. Что нужно сделать до релиза, который стоит переезда

Порядок бэклога сохранён; оценка — по объёму правок в коде этого репозитория.

**1.6 — точность и доступы**

1. `LIB-CLASSIFY-TOKEN` — границы слова в `_SELF_HINTS` и `_UPLOAD_HINTS` + тесты на
   `media-types`, `departments`, `mentions`. Малый объём, чистый баг-фикс.
2. `LIB-CLASSIFY-ACTION` — порядок проверок + тест `POST /items/{id}/publish` = ACTION.
3. `LIB-TRACK-VALIDATE` — разделить вызов и валидацию в `TrackingApiClient`: получить
   ответ, зарегистрировать id при 2xx, затем применить `validate_model`. Плюс
   `snapshot()` / `cleanup_since(n)` в `CreatedRegistry`. Средний объём, есть готовый
   overlay-образец в консьюмере.
4. `LIB-PATH-RESOLVE` — настоящий матчер: сегментное сопоставление конкретного URL с
   шаблонами операций вместо глобального словаря параметров. Самый крупный пункт 1.6.
5. `LIB-BODY-MARK` — `_cleanup_fields` + `get_json_required_marked()`. Малый объём.
6. `LIB-REC-ACCESS` — страница cookbook с таблицей 4 клеток и антипаттерном
   «есть 401 → Permissions закрыт». Docs.

**1.7 — честность покрытия**

`LIB-XDIST` (шардовый дамп + `pytest_sessionfinish` на контроллере), `LIB-COV-KIND`,
`meta.merged/workers`, timing, целевой HTML, `LIB-SUBTYPE-OVERRIDE`.

Замечание из спеки, которое стоит вынести отдельно: `LIB-XDIST` и `LIB-COV-KIND`
помечены **P0**, но стоят в 1.7. Пока они не сделаны, единственная защита — запрет
`-n` на прогоне покрытия, уже записанный в доках и скилле.

## 4. Что меняется для консьюмера уже сейчас

- **Имена документов в колесе стали плоскими**: `QUICKSTART.md` → `howto-quickstart.md`,
  `MIGRATION.md` → `howto-migration.md`, `UI_QUICKSTART.md` → `howto-ui.md` и т. д.
  Проверено: в aqa нет вызовов `partest.docs.read_doc` / `list_docs`, так что переезд
  ничего не ломает. Для любого другого потребителя это ломающее изменение имён.
- **Из колеса убраны** `MIGRATION_1.3.0_ISSUES.md`, `IMPLEMENTATION_PLAN.md`,
  `RELEASE_1.5.0.md`. Это внутренние документы; их место — этот репозиторий.
- Появилась команда `python -m partest.docs list | show <page> | path`.
- В `docs/partest/` консьюмера ссылки вида «скопировать в `partest.docs` (RECIPES /
  QUICKSTART)» указывают на имена, которых больше нет. Правки в том репозитории —
  отдельная задача, здесь они не делались.

## 5. Как обновлять этот аудит

Страница привязана к файлам в `sources:`. Как только тронут `tracking.py`,
`classifier.py`, `coverage.py`, `payload.py` — линтер пометит аудит протухшим,
и вердикты надо перепроверить прогоном, а не памятью.
