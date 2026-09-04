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

Проверка проводилась дважды: первый проход (аудит) — до реализации, второй — после
волны 1.6. Ниже актуальное состояние.

| | |
|---|---|
| **Документационные требования бэклога** | применены |
| **Волна 1.6** | **реализована**, тесты в `tests/test_wave_1_6.py`; не выпущена |
| **Волна 1.7** | P0-ядро **реализовано** (xdist-merge, `kind`, meta, timing, history keep=2); открыты витрина HTML, override подтипов, kind-aware compare |
| **Можно ли переезжать aqa** | да, после публикации: снимается overlay `resource_tracker.py`, чинятся ключи покрытия и классификация |
| **Чего переезд не даст** | отчёта из теста под `-n`: слияние живёт на контроллере, `test_zorro` — на воркере. Нужен либо serial, либо `PARTEST_COVERAGE_JSON` |

---

## 1. Что применено в этой сессии

| Требование бэклога | Где выполнено |
|---|---|
| «не гонять `zorro` под xdist» — написать красным в доках 1.6 (`LIBRARY_UPDATE_COVERAGE` §5) | [[concepts/coverage-honesty]] §1, скилл `partest-cover-api`, [[howto/enterprise]] |
| unseen ≠ empty ≠ «нет тестов» — зафиксировать как канон (§2.1) | [[concepts/coverage-honesty]] §2 |
| дисциплина `type=`, инференс не заменяет явный тип (§2.2) | [[decisions/explicit-type]], [[concepts/methodology]] |
| объём = OpenAPI op × P1 клетки подтипа, не 12 TC на path (§2.4) | [[concepts/methodology]] |
| «после реализации в partest — короткая шапка и ссылка на `partest.docs`» | снапшот в `docs/raw/`, план в [[status]] |
| ACCESS → cookbook в `partest.docs` | [[howto/permissions]] |
| CLEANUP (track-before-validate, marked payload) → `partest.docs` | [[howto/recipes]] |
| UPLOAD / PATH / INTEGRATION / E2E cookbooks | **не сделано**, см. §2 «Cookbook-долг» |

Дополнительно, вне бэклога: из колеса убраны внутренние документы (трекер миграции
консьюмера, доска статусов, релизный чек-лист), которые уезжали к пользователям PyPI.

## 2. Кодовые пункты — проверка построчно

### 1.6 — закрыто

| ID | Требование | Статус | Где |
|---|---|---|---|
| **LIB-TRACK-VALIDATE** | регистрировать create-id при 2xx до `validate_model` | ✅ | хук ответа в `client.py`, `TrackingApiClient._on_response` |
| **LIB-CLASSIFY-TOKEN** | `me`/`self`/`my` по границе слова; `media` не крадёт `media-*` | ✅ | сегментное сопоставление в `classifier.py` |
| **LIB-CLASSIFY-ACTION** | ACTION раньше POST TO OBJECT для глагола в конце | ✅ | `_is_action_call`, проверка поднята выше |
| **LIB-PATH-RESOLVE** | конкретный URL → шаблон OpenAPI, вложенные пути | ✅ | `partest/path_match.py`, подключён в `_resolve_endpoint` |
| **LIB-REC-ACCESS** | cookbook 4 клеток | ✅ | `partest/access.py` + [[howto/permissions]] |
| **LIB-BODY-MARK** | `_cleanup_fields` + `get_json_required_marked()` | ✅ | `payloads.py` |
| **LIB-PERM-QUAD** | подписи четырёх клеток | ✅ | `PERMISSION_CELLS`, `permission_cell_label` |
| — | `CreatedRegistry.snapshot()` / `cleanup_since(n)` | ✅ | `tracking.py` |

Acceptance-кейсы из спеки закреплены тестами: `/media-types` и `/mentions` больше не
BY SELF, `POST /items/{id}/publish` — ACTION, `/orders/customer/5` резолвится в
`/orders/customer/{customerId}`, 201 с лишним полем оставляет id в реестре.

**Найдено попутно и починено:** обёртка Allure-шага (`_step`) в 1.5.0 ловила исключение
тела блока и делала второй `yield`, из-за чего `contextlib` поднимал
`RuntimeError: generator didn't stop after throw()` вместо `AssertionError`. Любое
несовпадение статуса и любой провал схемы теряли диагностику. Теперь
`partest/allure_step.py`, регрессия закреплена тестом.

### 1.7 — P0-ядро закрыто

| ID | Требование | Статус | Где |
|---|---|---|---|
| **LIB-XDIST** | merge `call_storage` между воркерами | ✅ | шард на воркере + слияние на контроллере в `pytest_sessionfinish`; проверено реальным `-n 2` |
| **LIB-COV-KIND** | `unseen / empty / partial / full / exception` | ✅ | `_kind_for` в `analyzer.py`, поле `kind` в JSON |
| **LIB-COV-META** | `meta.merged`, `meta.workers` | ✅ | плюс `partialRun`, `callsTotal`, `unseenRatio` |
| **LIB-COV-TIMING** | `elapsed_ms` → avg/p50/p95 по типам | ✅ | замер в `track_api_calls`, агрегат `timing_of` |
| **LIB-COV-HIST-2** | история, `keep=2` | ✅ | `append_snapshot(keep=2)`, `prune_snapshots`, `previous_snapshot` |
| **LIB-COV-HTML** | целевой UX витрины | ⬜ | `interactive_html.py` из 1.5.0 не переписан |
| **LIB-SUBTYPE-OVERRIDE** | YAML-map + rebind | ✅ | `partest/methodology/overrides.py`; проверка внутри `classify_endpoint`, а не подменой ссылки |
| **LIB-COV-CMP kind-aware** | дельта прогона vs дельта suite | ✅ | `not_run`, `comparable`, `warnings`, флаг `--strict` в CLI |

Контракт слияния из спеки соблюдён: `calls` суммируются, `types` объединяются — поздний
`request_default` не затирает ранний `request_elements`.

Отклонение от спеки, осознанное: вместо дописывания jsonl на каждый вызов воркер пишет
один шард на финише сессии. Контракт слияния тот же, но нет ни поблочных локов, ни
рваных строк на Windows. Цена — воркер, убитый посреди прогона, не отдаёт ничего;
это в любом случае сломанный прогон.

### Cookbook-долг (docs, не код)

`LIB-REC-UPLOAD` (мутации файла, gate vs parse) · `LIB-REC-PATH` (слои L0–L4, оси F и I) ·
`LIB-REC-INTEGRATION` (201 ≠ persist) · `LIB-REC-E2E` · `LIB-REC-TYPE` · `LIB-REC-CLEANUP` ·
`LIB-REC-UI-TICKET` — ни одной страницы нет. Спеки лежат в `docs/raw/aqa/2026-09-04/`.

## 3. Что осталось

1. **`LIB-COV-HTML`** — целевой UX витрины: drawer по эндпоинту, сброс фильтров, скролл
   матрицы в контейнере, ms на клетке, пресеты «unseen» и «≥300 ms», баннер частичного
   прогона. Данные для всего этого в JSON уже есть.
2. **Cookbook-долг**: upload, path/layers, integration, e2e, type-дисциплина, UI-ticket.
3. Из [[proposals]], если возьмётесь: `py.typed`, предупреждения об устаревании алиасов,
   единая команда проверок перед релизом.

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
