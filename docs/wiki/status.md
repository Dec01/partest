---
title: Статус, версии и что дальше
status: current
verified: 2026-10-19
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
| **Дата актуализации** | 2026-10-19 |
| **Версия в коде** | **2.7.0** — кандидат, не выпущен (поднята 2026-10-18 по просьбе о выпуске-кандидате) |
| **Последний релиз на PyPI** | **2.6.0** (выпуск 2026-10-18; 2.5.0 — 2026-10-09). Минимальный Python — 3.10, pytest `>=9.0.3,<10` |
| **Дистрибуция** | PyPI — пакет, GitHub — исходники и история; см. [[decisions/distribution]] |
| **Соседний пакет** | `partest-gen` выделен из `partest.project_gen` 2026-09-07; см. §5 |
| **Consumer proof** | переезд `1.5.0 → 1.8.0` **состоялся** 2026-09-07: `8 failed, 2122 passed`, все падения предсуществующие; пять находок по пакету разобраны, см. §6 |
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
| Методология UI: поверхности × проверки × глубина, матрица применимости | 2.0.0 |
| `httpx_client` / `httpx_async_client` — свой клиент внутри политики TLS | 2.2.0 |
| `meta.tlsUnverifiedHosts` / `tlsUnknownHosts`, `check_measured` | 2.3.0 |
| `validate_coverage_payload` | 2.4.0 |
| `poll_until`, `partest.rounding`, opt-in наборы маркеров, владелец ресурса в `CreatedRegistry`, детерминированные zip/xlsx, расширения Problem Detail (`ProblemDetailWithErrors`, `ProblemDetailValidation(model)`) | 2.5.0 |

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
| G1–G6 | `partest-gen`: скелет → IR → ресурсы → P1 → UI → playbook | 1.4–1.5, вынесено §5 |
| 1.5.0 | CANON + BPLUS + COV-* + UI freeze/cap/hooks + GEN | 1.5.0 (PyPI) |

`LIB-11` (изоляция `import partest.ui`) и `LIB-15` (self-tests харнесса) во внешнем бэклоге помечены
«проверить в partest-repo» — **закрыты**: `tests/test_ui_isolation.py`, `tests/test_harness_1_1.py`.

## 3. Что дальше

### 2.6.0 — сверка вики сайта с колесом 2.5.0 · **выпущено** 2026-10-18

В коде: покрытие больше не пустеет молча, когда `confpartest` не виден на импорте —
спецификация и `subtype_overrides` читаются при первом использовании, `confpartest.py` из корня
pytest загружается по месту (кроме `--noconftest`, чужого корня и переключателей самого плагина),
отчёт без спецификации даёт раздел `partest: coverage NOT COUNTED` в сводке; все читатели
`confpartest` ищут его одинаково; `load_confpartest` оборачивает любую ошибку файла в
`ConfpartestError`. Импорт `partest` и `partest.ui` не ходит в сеть и не читает проект —
гарантировано, тест в чистом интерпретаторе. pytest-сессия с корнем на `sys.path` по-прежнему
читает `confpartest` ради переключателя `pytest_plugin`, UI-сессия тоже — как в 2.5.0; как
формулировать красную линию 8 для этого случая — вопрос мейнтейнеру ([[proposals]], спорное
2026-10-17 b). Сигнатуры и формат `coverage.json` не менялись; поведение отказа изменилось:
атрибуты `partest.coverage.*` пусты до первого вызова; `ConfpartestError` приходит из
учитываемых вызовов и `get_paths_info()` — и при спецификации, которая не грузится, и при
`confpartest`, который не импортируется; во втором случае ещё из `active_overrides()` и
`classify_endpoint` (они читают `subtype_overrides` из того же файла). Отчёт не падает ни в
одном случае: он строится пустым, причина — в разделе `NOT COUNTED` (`analyzer.py`,
`analyze_coverage`). Исправлено 2026-10-18 по коду: раньше здесь и в CHANGELOG 2.6.0 оба
отказа были описаны одним списком, а в [[howto/migration]] — ещё и «из отчёта». Список — в
[[howto/migration]] (2.6.0). В документах: шесть неработающих примеров, ось C и `exception` в
[[concepts/methodology]] (дефект методики — [[proposals]] F1), неполный Known issues 2.5.0,
«seventeen» в 2.3.0. Всё — в `CHANGELOG.md`, раздел 2.6.0.

### 2.7.0 — кандидат: маскировка во всех каналах, `summary.avg: null`, `exception` вне среднего и глубина (F1), находки перехода потребителя · **кандидат** (версия в коде 2.7.0, на PyPI не выпущен)

Записано в `CHANGELOG.md`, раздел «2.7.0 — unreleased» (дата — при выпуске); что меняется у
потребителя — [[howto/migration]]. Минор, а не патч: новые публичные имена
(`StatusMismatchError`, `validation_errors`, маркер `known_defect`, `would_select`,
`optin_comparable`, `assert_all_agree`, `significant=` / `rounding=`); тип `summary.avg`
расширен до `float | null`, и старый `0.0` пустого прогона читается как «не измерено» — вместе
с ним возвращаемые поля `compare_payloads` (`old_avg`, `new_avg`, `avg_delta`,
`coverage_delta`) стали `float | None`: осознанное решение по контракту `coverage-payload`
(решено 2026-09-24 — отсутствие измерения пишется `null`, прецедент `meta.unseenRatio` 2.3.0);
`AssertionError` провала схемы и HTTP-ветки больше не сцеплен с исходным исключением — чтение
`__cause__` заменено на `validation_errors` и `StatusMismatchError.status_code`; маскировка
меняет видимый текст логов, сообщений и вложений; строки `exception` вне среднего
(`meta.avgRule: 2`) — среднее сдвигается вниз у прогонов с такими строками, `covered` сервиса —
`full + partial`, `avgCoverage` может быть `null`; глубина (ось C) — новое поле рядом с процентом
([[proposals]] §F1, варианты 2 и 3; минор, в тот же кандидат). **Процент
клетки и состав P1/P2/P3 не менялись.** **Методология не менялась:** для каждого валидного пути подтип прежний; GET BY PARENT в 2.6.0 получал только некорректный шаблон с двумя и более `/` внутри `{}` (`/a/b/{x/y/z}`) — теперь такой путь читается по общим правилам: обычно GET DYNAMIC, с подсказками списка или статики — GET LIST / GET STATIC
(правило GET BY PARENT не выпускается, [[proposals]] §G4). Умолчание
`attach_response(redact_body=False)` **не менялось** (переворот — мажор, 3.0). Мажором ничто не
является: подклассы и новые атрибуты не ломают ловящий `AssertionError` код.

| Что | Где | Документация |
|---|---|---|
| маскировка во всех каналах вывода (закрывает Known issues 2.5.0 и [[proposals]] §E2) одним приватным обходчиком: секретный ключ — `***` целиком, прочие строки — узкие шаблоны, JSON остаётся JSON. INFO-лог (тела и `params=` — JSON, `Files:` — имена и размеры), строка `HTTP Request:` самого httpx (фильтр логгера), сообщение о несовпадении статуса, `ErrorDesc`, `print_error`, трейсбэк провала схемы (без цепочки), все вложения Allure, `ErrorTemplates`, `attach_check`, `sideeffects`. `attach_response` по умолчанию не маскирует (умолчание публичного экспорта — мажор, перевернуть в 3.0), внутренние вызовы передают `True` | `partest/redact.py`, `partest/utils/*`, `partest/client.py`, `partest/http/client.py`, `partest/reporting/*`, `partest/sideeffects.py`, `partest/conf.py` | [[howto/enterprise]] |
| `StatusMismatchError(AssertionError)` с `status_code`, `expected`; `validation_errors` у провала схемы | `partest/client.py`, `partest/reporting/instrument.py` | [[howto/migration]] |
| ожидаемый статус больше не повторяется при `max_retries` (ожидаемый 429 повторялся до 200); хук внедрённого клиента, отвергший ожидаемый статус, — `RuntimeError`, а не `StatusMismatchError` | `partest/client.py` | [[howto/migration]] |
| `summary.avg` / `avgAll` — `null` при нуле эндпоинтов (контракт `coverage-payload`, как `meta.unseenRatio`); бейдж `n/a`, `compare` без дельты, валидатор, HTML | `partest/reports/payload.py`, `badge.py`, `compare.py`, `validate.py`, `interactive_html.py` | [[howto/coverage-html]] |
| F1, вариант 3: строки `exception` вне `summary.avg` / `avgAll`, `avgCoverage`, тепловой карты и `covered`; `scored` в `summary` и строках сервисов, подтипов, методов; набор из одних `exception` — `null`; `meta.avgRule: 2`; `compare` пересчитывает среднее старого файла по строкам (`avg_recomputed`), неизвестное правило — предупреждение; валидатор (`Severity.NEWER`), оба HTML, текстовая сводка `zorro()`; правило — в одном месте | `partest/reports/_rules.py`, `payload.py`, `analyzer.py`, `compare.py`, `validate.py`, `interactive_html.py`, `html_coverage.py`, `partest/zorro_report.py` | [[howto/coverage-html]], [[howto/migration]], [[concepts/methodology]] |
| F1, вариант 2: `depth` у строки (`cells`, `status`, `schema`, `values: null`) и `summary.depth` с `statusPct` / `schemaPct` — заказанные проверки; процент не меняется; `depth_delta` в `compare`; показ в HTML и сводке; флаги — через сигнатуру отслеживаемой функции; `call_depth` — одно правило уровня, `depth_score` по нему | `partest/reports/analyzer.py`, `payload.py`, `compare.py`, `validate.py`, `partest/coverage.py`, `partest/methodology/api/steps.py` | [[howto/coverage-html]], [[concepts/methodology]] |
| чужие `coverage.json` и чужие клиенты: экранирование чисел и имён в интерактивном отчёте, путей в простом; `NaN`/`Infinity` и имена `constructor`/`__proto__` на странице; валидатор, `compare` и CLI не падают на мусоре (числа вне `float`, неверные типы, не-объект); `track_api_calls` не ломает импорт на Python 3.14 (ленивые аннотации) и читает `**kwargs`-обёртку; `CoverageReport.scored_count`; `call_depth`/`depth_score` в `__all__` и фасаде | `partest/reports/*`, `partest/coverage.py`, `partest/methodology/*`, `partest/pytest_plugin.py` | `CHANGELOG.md` (Added, Fixed), [[howto/migration]] |
| неверные строки 2.6.0: `load_confpartest` не сцепляет исходное исключение; какие вызовы поднимают `ConfpartestError`, а где отчёт пишет `NOT COUNTED` | документы | [[howto/migration]] |
| `Rounded(..., significant=N)`, `Rounded(..., rounding="floor" / "ceiling" / "toward_zero")`, `assert_all_agree` | `partest/rounding.py` | [[howto/layers]] |
| правило opt-in публично: `would_select`, `is_selected`, `selected_through` | `partest/optin.py` | [[components/overview]] |
| `optin_comparable` — вердикт сравнимости opt-in-состояний; `compare` выражен через него; запись без `state` отличается от отсутствующего набора | `partest/reports/compare.py` | [[components/overview]], [[howto/coverage-html]] |
| старый `0.0` при нуле эндпоинтов — «не измерено» в `compare` и `badge`, как в валидаторе; валидатор: `avg` не число или вне 0..100 при эндпоинтах — ошибка | `partest/reports/compare.py`, `badge.py`, `validate.py` | [[howto/coverage-html]] |
| маркер `known_defect`: строгий xfail, засчитывающий только `AssertionError` тела (кроме `StatusMismatchError` 502/503/504 — статусов шлюза; 429 — воспроизведение); вердикт виден allure-pytest и pytest-rerunfailures; `xfail`, добавленный во время прогона, — отказ | `partest/known_defect.py`, `partest/pytest_plugin.py` | [[components/overview]] |
| `Logger.warning` — `make_request(data={...})` и GraphQL не через POST падали `AttributeError` | `partest/utils/logger.py` | [[howto/enterprise]] |
| совет `pip install --no-cache-dir` сразу после выпуска | документы | [[howto/quickstart]] |

Отложено: признак секрета по подстроке ключа тела (`new_password`, Keycloak `value`) (мажор, решение мейнтейнера), умолчание
`attach_response` (перевернуть в 3.0), секрет в XML-теле — [[proposals]] §E2;
`Rounded(None)` как проваленная сверка и сверка модели с живой схемой — [[proposals]] §G1, §G2;
GET BY PARENT из формы пути (пункт про GET BY PARENT) — не выпускается, эвристика ненадёжна,
ответ — `subtype_overrides`, §G3–G4; спорное из ревью — §G5 (ручки отладки), §G6
(граница `known_defect`), §G7 (`null` в воротах); F1 вариант 1 (засчитывать клетку только при
нужной глубине) — открыт, мажор, [[proposals]] §F1. Потребителям формата (`partest-atlas`, veha) —
учесть `summary.avg: null` и старый `0.0` пустого прогона как «не измерено»; `meta.avgRule`
(тренд среднего сравнивать в пределах одного правила; `avgCoverage` — `float | null`; `covered`
без `exception`); новые необязательные `depth` / `summary.depth`. У veha своё правило серий для opt-in, и оно
намеренно расходится с `compare` там, где запись есть только у одной стороны;
`optin_comparable` может заменить у неё только ветку «записи у обоих»; `partest-gen`
(читает `classify_endpoint`) — без изменений. Спорное, ждущее
решения мейнтейнера: §E1 (предупреждение об открытой модели, индексатор), §E3 (обязательные члены
`ProblemDetailBody` против RFC 9457), §A15 (строковая модель).

### 2.5.0 — шесть возможностей, которые потребитель писал сам · **выпущено** (подготовлен 2026-10-09, на PyPI — по проверке 2026-10-16)

Один выпуск без отдельного патча 2.4.1: исправления выходят вместе с возможностями, а
`### Changed` (одноэлементный набор статусов выводится как сам статус, у существующих вызовов
меняется ячейка) — по правилам [[howto/release]] уже минор.

| Что | Где | Документация |
|---|---|---|
| набор статусов в выводе типа больше не роняет `make_request` | `partest/methodology/api/inference.py` | [[concepts/methodology]] |
| `poll_until` / `poll_until_sync`; `sideeffects.wait_for` на том же цикле | `partest/polling.py` | [[howto/layers]] |
| сверка «значение = формула от округлённых входов» | `partest/rounding.py` | [[howto/layers]] |
| opt-in наборы маркеров, `meta.selection.optin` | `partest/optin.py`, `partest/call_storage.py`, `partest/reports/compare.py` | [[components/overview]] |
| владелец ресурса шире теста | `partest/tracking.py` | [[howto/recipes]] |
| детерминированные байты zip/xlsx | `partest/files.py` | [[howto/upload]] |
| `partest/env/` снова в git; проверка от игнорируемых и забытых в `git add` файлов пакета | `.gitignore`, `tests/test_packaging.py` | [[howto/contribute]] |
| генератор в `expected_status_code` больше не валит проверку статуса | `partest/client.py` | — |
| `redact_text` — маскировка в тексте; ею закрыты сообщения опроса | `partest/redact.py` | [[howto/enterprise]] |
| члены-расширения Problem Detail (RFC 9457): объявленные проходят, прочие по-прежнему запрещены | `partest/validation/problem_detail.py` | [[howto/recipes]] |
| провал схемы на JSON-теле больше не выдаётся за «не удалось разобрать JSON»; сообщение и лог без значений из тела, тело маскировано и усечено | `partest/client.py` | [[howto/migration]] |

Для читателей формата: ключ `meta.selection.optin` в `coverage.json` — аддитивный, `partialRun` его не
читает; его видят `partest-atlas` и другие читатели формата, если читают `meta.selection`.
У `compare` новый мягкий список `notes`. Спорное из ревью —
[[proposals]] §D.

### 1.6 — точность покрытия и доступы · **выпущено в 1.7.0**

Тесты в `tests/test_wave_1_6.py`. Выпущено вместе с 1.7 одним релизом.

| ID | Задача | Где |
|---|---|---|
| **LIB-CLASSIFY-TOKEN** | `me`/`self`/`my` по границе слова и по сегментам; `media` не крадёт `media-types` | `partest/methodology/api/classifier.py` |
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

- ✅ Полный прогон на стенде консьюмера — сделан 2026-09-07, см. §6.
- Overlay `resource_tracker.py` снимается — **не сделано**, и до тех пор `LIB-PATH-RESOLVE`
  у консьюмера не работает: overlay навязывает `defining_url`, который главнее (§6).
- Навсегда остаются у консьюмера: `visual_scenes`, PROFILES, roles/credentials, page objects, SQL cleanup,
  baselines PNG. См. [[decisions/no-domain]].

## 5. Соседний пакет `partest-gen`

Генератор выделен в свой дистрибутив 2026-09-07. Здесь остались мост `partest.project_gen`,
экстра `partest[gen]` и методология, которую генератор читает. Подробности — [[components/project-gen]].

| | |
|---|---|
| Репозиторий | https://github.com/Dec01/partest-gen |
| Версия | 1.0.0, ещё не на PyPI |
| Требует | `partest>=1.8.0` |
| Что читает отсюда | `partest.methodology.api.{classifier,matrix,subtypes}`, `partest.test_types`, `partest.tools.generate_init` |

**Следствие для планирования релизов.** У `classify_endpoint` и `p1_test_cases` теперь второй
потребитель, и он в другом репозитории. Менять их сигнатуры как приватные нельзя; порядок —
сначала релиз `partest`, потом поднятие нижней границы в `partest-gen`.

**Переезд методологии в `api/` (2026-09-13) — ровно такой случай.** Генератор импортирует глубокие
пути: три строки в `partest_gen/ir.py` и нижняя граница в его `setup.py` правятся тем же прогоном.
Публиковать `partest-gen` можно **только после** выхода мажорной версии `partest`: до неё новых
путей не существует ни в одном установленном колесе. Потребительский проект прибит к текущему
патчу с PyPI и переключается уже после релиза, не раньше.

**Старые пути методологии оставлены алиасами (2026-09-23, решение владельца).** Проверка на
потребителе показала цену удаления: переезд становился неделимым (старые пути не работают
на 2.0.0, новые — на 1.8.x, значит код и версия одним коммитом), ошибка всплывала не на импорте,
а как `INTERNALERROR` с трейсбеком pluggy на сборе всего дерева — `confpartest.py` грузится изнутри
плагина, — и у неё была тихая форма: на старой версии `confpartest` не импортировался,
`active_overrides()` возвращал пусто, и покрытие молча считало подтипы по чужим обязательным
наборам. Шесть модулей (`classifier`, `inference`, `matrix`, `overrides`, `steps`, `subtypes`)
резолвятся в те же объекты, предупреждают по разу и снимаются в **следующей** мажорной версии.
Механика — `partest/methodology/_moved.py`, тесты — `tests/test_methodology_aliases.py`.
Версия при этом осталась 2.0.0: смягчается уже объявленное ломающее изменение до публикации.

**Незакрытый хвост.** Мост `partest.project_gen` снимается в **следующей** мажорной версии:
в 2.0.0 он живёт и проверяется — `tests/test_project_gen_bridge.py` прогоняется по-настоящему
с тех пор, как `partest-gen` объявлен в `extras_require["dev"]`. Алиасы методологии снимаются
тогда же и тем же приёмом — один приём на весь релиз, а не два разных.

**Версия поднята до 2.0.0 по запросу на релиз (2026-09-23).** Раздел `Unreleased` в
`CHANGELOG.md` закрыт этой датой. На PyPI выпуска ещё нет: публикация — отдельное решение
мейнтейнера, и до неё `pip install partest` по-прежнему ставит 1.8.1.

**2.1.0 — нижние границы зависимостей (2026-09-23).** Объявленные границы, а не закреплённое
окружение, — это то, что получает потребитель. Аудит именно границ (`имя==граница` →
`pip-audit -r`) нашёл 24 записи в пяти пакетах, включая `Pillow` из extra `ui`, которого
`requirements.txt` не содержал вовсе и аудит не видел никогда. Пол `pytest` поднят до 9.0.3 —
исправления в ветке 8.x не существует, поэтому **поддержка pytest 8 прекращена**, — и получил
потолок `<10`: партест грузится как плагин в каждой сессии потребителя, а мажорную версию,
на которой набор не гонялся, обещать нечем. Потолок снимается патч-релизом после прогона на
следующем мажоре. `requirements.txt` стал ровно целью аудита и сверяется с `setup.py`
по именам **и** границам — `tests/test_packaging.py`.

## 6. Отчёт о переезде консьюмера 1.5.0 → 1.8.0 (2026-09-07)

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

**Важное наблюдение, которое стоит помнить.** Цифра покрытия не сдвинулась вообще
(`95.74 → 95.74`, `regressed 0`) — но не потому, что 1.7.0 ничего не дал. Консьюмерский
overlay навязывает `defining_url` каждому вызову, а `defining_url` главнее `path_match`,
поэтому `LIB-PATH-RESOLVE` в том прогоне не сработал ни разу. Выгода придёт со снятием
overlay. То есть **приоритет `defining_url` маскирует починку резолвера** у всех, кто такой
overlay носит.

**Пять находок по пакету — все разобраны:**

| # | Находка | Что сделано (в `1.8.1`) |
|---|---|---|
| F-1 | фильтр по маркерам режет клетки, а не эндпоинты → 14 ложных регрессий со штампом «сравнимо» | `meta.selection` из плагина + эвристика обвала вызовов в `compare`; [[concepts/coverage-honesty]] §2 |
| F-2 | в колесе 1.8.0 нет раздела про 1.8.0 и про Python 3.10 | раздел в [[howto/migration]], чек-лист исправлен |
| F-5 | сравнение со снимком старше `kind` всегда даёт ложный `not_run` | `kind` выводится из `calls`, когда ключа нет |
| F-3 | `parparser.py`: 12 `print()` в stdout при каждом импорте | переведено на `logging` |
| F-4 | хелперы истории не реэкспортированы | реэкспорт + `__all__` в `history` |

Тесты: `tests/test_report_comparability.py` (19 случаев), корпус построен на замерах из отчёта.

Отчёт и снимки покрытия — в репозитории консьюмера, `docs/partest/MIGRATION_1.8.0_REPORT.md`.

## 7. Как обновлять эту страницу

1. Новый снапшот бэклога → локальный `docs/raw/<источник>/<дата>/` (вне git), старый не трогаем.
2. Переписать §3 по свежему снапшоту; противоречия разрешать в пользу более поздней даты и
   **явно называть** их, как сделано с `LIB-XDIST`.
3. Обновить `verified:` и добавить строку в [[log]].
