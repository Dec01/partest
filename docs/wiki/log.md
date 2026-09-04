---
title: Журнал операций над документацией
status: current
verified: 2026-09-04
sources: []
audience: maintainer
ships_in_wheel: false
allow_version_literals: true
---

# Журнал

Хронология: что сделано с документацией и почему. Новые записи сверху.
Формат строки: дата · операция (ingest / update / lint / restructure) · что затронуто.

## 2026-09-04 · update · реализовано P0-ядро волны 1.7

Закрыты оба пункта, из-за которых цифра покрытия врала: слияние шардов между воркерами
xdist и таксономия `kind`. Плюс `meta.workers/merged/partialRun/unseenRatio`, замеры
`elapsed_ms` с агрегатами по типам и обрезка истории до двух прогонов.

Слияние проверено настоящим прогоном `-n 2` в подпроцессе — шесть эндпоинтов, два
воркера, контроллер видит все шесть. Мок здесь ничего бы не доказал.

Осознанное отклонение от спеки: вместо jsonl на каждый вызов воркер пишет один шард на
финише сессии. Контракт слияния тот же, зато нет поблочных локов и рваных строк на
Windows. Записано в [[backlog-audit]] §2.

Остаточное ограничение, которое честнее назвать, чем прятать: отчёт из теста слияния не
видит — `test_zorro` живёт на воркере, слияние на контроллере. Описано в
[[concepts/coverage-honesty]] §1 и [[howto/enterprise]], там же ключи
`PARTEST_COVERAGE_JSON` / `PARTEST_COVERAGE_HTML`.

Противоречие приоритетов из бэклога (P0, но стоят в 1.7) снято — сделано сразу после 1.6.

## 2026-09-04 · update · реализована волна 1.6

Кодовые пункты бэклога, которые аудит нашёл открытыми, закрыты: классификатор
(границы сегментов и порядок ACTION), резолвер путей `partest/path_match.py`,
трекинг до валидации через хук ответа, `_cleanup_fields`, хелперы четырёх клеток
доступа. Вердикты в [[backlog-audit]] перевёрнуты, план в [[status]] §3 переписан.

Новая страница в колесе: [[howto/permissions]]. Дополнены [[howto/recipes]]
(track-before-validate, `cleanup_since`, маркер в required-only) и
[[concepts/coverage-honesty]] §3 — эвристика ключей заменена описанием резолвера.

Попутно найден баг 1.5.0: обёртка Allure-шага превращала любое исключение внутри
блока в `RuntimeError: generator didn't stop after throw()`, из-за чего диагностика
несовпадения статуса и провала схемы не доходила до отчёта. Вынесено в
`partest/allure_step.py`.

Линтер сработал по назначению: поймал дефолтный маркер `AQA` в примере
[[howto/recipes]], уезжающем в колесо.

## 2026-09-04 · lint · сверка бэклога с кодом

Проверка каждого пункта `docs/raw/aqa/2026-09-04/` против фактического кода: [[backlog-audit]].
Результат — документационные требования бэклога применены, **кодовые (1.6 и 1.7) не начаты**.
Два бага классификатора воспроизведены запуском (`/media-types` и `/mentions` определяются как
BY SELF), порядок трекинга в `TrackingApiClient` подтверждён чтением.

Идеи развития сверх бэклога вынесены отдельно: [[proposals]] (статус `draft`, не согласовано).

## 2026-09-04 · restructure · полная реорганизация документации

Разделили документацию на четыре слоя: границы (`AGENTS.md`), процедуры (`.claude/skills/`),
знание (`docs/wiki/`), источники (`docs/raw/`). Обоснование и замеры «как было»:
[[decisions/docs-architecture]].

Перенос — все файлы через `git mv`, ни один не удалён:

| Было | Стало |
|---|---|
| `docs/QUICKSTART.md` | [[howto/quickstart]] |
| `docs/MIGRATION.md` | [[howto/migration]] |
| `docs/REPORTING.md` | [[howto/reporting]] |
| `docs/COVERAGE_REPORT.md` | [[howto/coverage-html]] |
| `docs/SECURITY.md` | [[howto/security]] |
| `docs/UI_QUICKSTART.md` | [[howto/ui]] |
| `docs/RECIPES.md` | [[howto/recipes]] |
| `docs/ENTERPRISE.md` | [[howto/enterprise]] |
| `docs/DEVELOPMENT.md` | [[howto/contribute]] (переписан: таблицы волн ушли в [[status]]) |
| `docs/RELEASE_1.5.0.md` | [[howto/release]] (обезличен) + `docs/archive/RELEASE_1.5.0.md` |
| `docs/PROJECT_GEN_ROADMAP.md` | [[components/project-gen]] |
| `docs/IMPLEMENTATION_PLAN.md` | `docs/archive/` → слито в [[status]] |
| `docs/LIBRARY_ROADMAP.md` | `docs/archive/` → слито в [[status]] |
| `docs/MIGRATION_1.3.0_ISSUES.md` | `docs/archive/` → слито в [[status]]; из колеса убран |
| `docs/README.md` | `docs/PYPI.md` (самодостаточный `long_description`) |
| `partest/docs/*.md` (12 ручных копий) | генерируются `tools/docs_build_wheel.py` |

Новые страницы: [[status]], [[index]], этот журнал, [[concepts/methodology]],
[[concepts/coverage-honesty]], [[components/overview]], пять ADR в `decisions/`.

Разрешённые противоречия:

- репозиторный `MIGRATION_1.3.0_ISSUES.md` (2026-08-14) утверждал «роадмап библиотеки пуст»;
  источник (2026-09-04) описывает релизы 1.6 и 1.7. Принят более поздний источник;
- `LIB-11` и `LIB-15` числились «проверить в partest-repo» — закрыты, тесты в репозитории есть;
- `LIB-XDIST` помечен P0 в бэклоге, но стоит в 1.7 по порядку релизов; противоречие оставлено
  явным в [[status]] §3 с временной мерой «не гонять zorro под xdist».

Вычищено из страниц, уезжающих в колесо: имя консьюмер-проекта в прозе, внутренние ID волн
(`L5.3`, `LIB-16`, `LIB-REC-*`), баннеры версий. Идентификаторы кода (`aqa_*`, `_aqa_monitor`)
оставлены — это реальный публичный API, переименование потребует мажорной версии.

## 2026-09-04 · ingest · снапшот бэклога консьюмера

`docs/raw/aqa/2026-09-04/` — 10 файлов. Проверено на приватные данные: абсолютных путей, URL
стендов и учёток нет. Источник не редактируется; следующий снапшот кладётся в каталог с новой
датой, старый остаётся.

Что из него вошло в [[status]]: состав релизов 1.6 / 1.7, HOLD по Testing Atlas, cookbook-долг,
консьюмерский остаток (AQA-6, overlay `resource_tracker`).
