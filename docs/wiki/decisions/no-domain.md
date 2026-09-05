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

## Маркер тестовых данных — не домен

`TEST_MARKER` по умолчанию равен `AQA`: это общепринятое сокращение для автоматизации
тестирования, а не имя проекта. Маркер нужен, чтобы очистка delete-by-marker находила
строки, созданные прогоном, и не трогала остальное — поэтому пустым он не бывает.
Проект переопределяет его через `TEST_DATA_MARKER`, если на стенде принято иначе. Сам SQL
удаления в библиотеку не переносится — схема у каждого своя; библиотека только гарантирует,
что маркер попадёт в тело create (см. `_cleanup_fields` в [[howto/recipes]]).

Устаревшие имена `aqa_name`, `aqa_code`, `aqa_short`, `aqa_fill`, `aqa_prefixed` и
`MONITOR_ATTR_LEGACY = "_aqa_monitor"` — это дубли к `marked_*`, оставшиеся от прежнего
именования. Они предупреждают при вызове и снимаются мажорной версией: одна сущность с
двумя публичными именами — лишняя поверхность, вне зависимости от того, как её зовут.

## Как проверять

`tools/docs_lint.py` валит приватные маркеры в страницах с `ships_in_wheel: true`.
Для кода — ревью: любое имя сущности продукта в `partest/**` это баг.
