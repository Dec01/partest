---
title: Каталог документации partest
status: current
verified: 2026-09-04
sources: []
audience: agent
ships_in_wheel: false
---

# Каталог

Точка входа. Найди строку по задаче — открой одну страницу. Конвенции: `WIKI.md`.

## Первым делом

| Вопрос | Страница |
|---|---|
| Какая версия, что дальше, статус волн | [[status]] |
| Что вообще есть в пакете и где лежит | [[components/overview]] |
| Что значит «покрыто» в этой методологии | [[concepts/methodology]] |
| Почему цифра покрытия может врать | [[concepts/coverage-honesty]] |

## concepts — почему так

| Страница | О чём |
|---|---|
| [[concepts/methodology]] | три оси покрытия: подтип метода × тип TC × глубина проверки |
| [[concepts/coverage-honesty]] | xdist, unseen vs empty, unmatched пути — когда проценту нельзя верить |

## components — что есть

| Страница | О чём |
|---|---|
| [[components/overview]] | карта пакета, роли модулей, публичный экспорт, pytest-плагин |
| [[components/project-gen]] | `partest-gen`: команды, IR, эмиттеры, целевое дерево, UI-слой |

## howto — как сделать

| Страница | Кому | В колесе |
|---|---|---|
| [[howto/quickstart]] | новый проект с нуля, первый зелёный тест | да |
| [[howto/migration]] | переход между версиями, отказ от локального харнесса | да |
| [[howto/reporting]] | `ah.check_*`, шаги, вложения, Allure как мягкая зависимость | да |
| [[howto/coverage-html]] | интерактивный отчёт, `coverage.json`, CLI compare/badge/stubs | да |
| [[howto/security]] | `SecHttp`, JWT-подделки, `RiskProfile`, IncorrectBody | да |
| [[howto/ui]] | `partest[ui]`: BasePage, PageMonitor, визуальные эталоны, изоляция | да |
| [[howto/recipes]] | адаптеры на стороне проекта: OIDC-роли, коллекции, очистка | да |
| [[howto/enterprise]] | общий httpx-клиент, ретраи, редактирование секретов, xdist | да |
| [[howto/contribute]] | разработка самой библиотеки: инварианты, тесты, доки | нет |
| [[howto/release]] | чек-лист выпуска на PyPI | нет |

## decisions — почему именно так

| Страница | Решение |
|---|---|
| [[decisions/pypi-only]] | публикуемся только в PyPI, публичного GitHub не будет |
| [[decisions/no-domain]] | в библиотеке нет продуктового домена; где проходит граница |
| [[decisions/explicit-type]] | явный `type=` побеждает автоинференс |
| [[decisions/docs-in-wheel]] | `partest/docs` генерируется, `ships_in_wheel` решает состав |
| [[decisions/docs-architecture]] | четыре слоя документации и защита от гниения |

## Вне wiki

| Где | Что |
|---|---|
| `AGENTS.md` | границы работы агента в этом репозитории |
| `.claude/skills/` | процедуры: покрытие API, скаффолд, релиз, поддержка доков |
| `CHANGELOG.md` | что менялось по версиям |
| `docs/raw/aqa/<дата>/` | снапшоты бэклога консьюмера — источники, не редактируются |
| `docs/archive/` | вытесненные документы с пометкой преемника |
| `docs/PYPI.md` | текст страницы PyPI (`long_description`) |
| `docs/wiki/log.md` | журнал операций над документацией |
