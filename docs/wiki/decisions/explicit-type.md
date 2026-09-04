---
title: ADR — явный type= вместо автоинференса
status: current
verified: 2026-09-04
sources: [partest/methodology/inference.py, partest/test_types.py, partest/client.py]
audience: maintainer
ships_in_wheel: false
allow_version_literals: true
---

# ADR: явный `type=` побеждает инференс

**Дата:** действует с 1.3, подтверждено в 1.5.0 (`LIB-CANON`).

## Решение

В `make_request` тип тест-кейса передаётся явно: `type=types.request_default`. Инференс
(`partest/methodology/inference.py`) остаётся страховкой и применяется только когда `type=` не
задан. Явное значение всегда выигрывает.

Инференс считается высокоуверенным лишь для трёх ситуаций: `405`, `404` и заведомо сломанное
сырое тело. Всё остальное — permissions, new/update object, elements, extra data, env, benchmark —
по проводу неотличимо: один и тот же `GET /items/1 → 200` может быть и Default, и Permissions,
и Benchmark.

## Следствия

1. Не убирать `type=` из существующих тестов «раз инференс есть».
2. Писать канонические имена (`request_default`), а не строку `"type_default"`;
   `canonicalize_type` разбирает легаси-алиасы, но новый код их не использует.
3. Алиасы (`default`, `405`, `elem`, `type_*`, `aqa_*`) живут минимум один минорный релиз;
   их удаление — мажорная версия (`LIB-SEMVER` в [[status]]).

## Когда пересмотреть

Если инференс дойдёт до уверенности ≥0.99 на неоднозначных классах — тогда `type=` станет
опциональным. Порог именно такой, потому что ошибка инференса не падает тестом: она молча
записывает не ту клетку матрицы, и покрытие врёт в плюс.

Связано: [[concepts/methodology]] · [[concepts/coverage-honesty]]
