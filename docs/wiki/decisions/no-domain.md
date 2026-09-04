---
title: ADR — в библиотеке нет продуктового домена
status: current
verified: 2026-09-04
sources: [partest/security/risk.py, partest/collections/base.py, partest/data_marker.py]
audience: maintainer
ships_in_wheel: false
---

# ADR: в библиотеке нет продуктового домена

**Дата:** действует с 1.0, ужесточено при drain консьюмера в 1.3–1.5.

## Решение

`partest` — харнесс, а не набор тестов конкретного продукта. Граница проходит так:

| В библиотеке | Всегда в consumer |
|---|---|
| `ApiClient`, coverage, `zorro`, `TypesTestCases` | пути и DTO сущностей, валидации полей |
| `TrackingApiClient`, `reporting`/`check_*`, `BaseRequestBody` | экземпляры коллекций, реестр сущностей |
| `TokenManager` + `credentials_provider` | `roles.py`, ключи учёток в env |
| `SecHttp`, JWT craft, **модель** `RiskProfile` | реестр `PROFILES`, RBAC-матрица |
| `env`, `data_marker`, `Config`, скелет `BaseCollection` | SQL-очистка, бизнес-данные |
| UI: `BasePage`, `PageMonitor`, health, visual, storage | page objects экранов, сцены, PNG baselines |
| `partest-gen`, хелперы conf/openapi | значения `confpartest`, секреты стендов |

Приём при переносе кода из консьюмера: **STRIP** — убрать имена сущностей, жёсткие роли,
обращения вида `parents[3]`, префикс проекта как единственный API, отладочный print-спам.

## Почему так

Первый же второй проект на библиотеке ломается о зашитый домен: чужие роли, чужие сущности,
чужая схема БД. Плюс всё это уезжает на PyPI посторонним людям.

## Тонкое место: `TEST_MARKER`

`partest/data_marker.py` по умолчанию использует маркер `AQA` — это наследие консьюмера, но
переопределяется переменной `TEST_DATA_MARKER`. Маркер остаётся в библиотеке потому, что
на нём держится безопасность очистки: **удалять можно только данные с маркером**. Сам SQL
удаления при этом в библиотеку не переносится — схема у каждого своя.

## Известное нарушение: алиасы `aqa_*`

В публичном API остались имена, взятые из консьюмера: `aqa_name`, `aqa_code`, `aqa_short`,
`aqa_fill`, `aqa_prefixed` (`partest/data_marker.py`) и `MONITOR_ATTR_LEGACY = "_aqa_monitor"`
(`partest/ui/page_monitor.py`). Это противоречит решению, но убрать их — ломающее изменение,
поэтому они живут до мажорной версии (`LIB-SEMVER` в [[status]]). Новый код их не использует:
`marked_name`, `marked_code`, `marked_short`, `fill_with_marker`, `prefix_marker`.

## Как проверять

`tools/docs_lint.py` валит приватные маркеры в страницах с `ships_in_wheel: true`.
Для кода — ревью: любое имя сущности продукта в `partest/**` это баг.
