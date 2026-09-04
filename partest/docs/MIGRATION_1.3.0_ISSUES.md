# partest — миграция aqa + roadmap library

**SoT** для: (1) что ещё нужно **в library**, (2) статус **внедрения в aqa**.  
Роадмап library: [`LIBRARY_ROADMAP.md`](LIBRARY_ROADMAP.md) (из aqa `docs/partest/`).  
Исторический extract-map: aqa `LIBRARY_EXTRACTION_BACKLOG.md`.

| | |
|---|---|
| **Дата актуализации** | 2026-08-14 |
| **Версия library** | **1.5.0** на **PyPI** |
| **aqa pin** | `partest==1.4.0` (**W3**); **W4 → 1.5.0** готов |
| **Волна aqa** | W1 1.3.0 → W2 1.3.3 → W3 1.4.0 → **W4 1.5.0** (pin pending in aqa) |
| **Дистрибуция** | **только PyPI**. Публичный GitHub **не планируется** |

---

## 1. Цели

| # | Цель | Где | Статус |
|---|---|---|---|
| **A** | Universal library | partest → PyPI | **1.5.0 shipped** |
| **B** | Drain aqa (domain only) | consumer | **W3 done**; residual AQA-6 |

**Не делать:** entity DTO, RBAC, SQL, page objects, baselines, stand URLs, public GitHub dump.

---

## 2. Сводка

### 2.1. Library

| Блок | Статус |
|---|---|
| API / auth / RiskProfile / plugin / collections / redact | ✅ ≤1.3.3 |
| Docs in wheel (`partest.docs`) | ✅ 1.4 |
| UI parity (sync BasePage, PageMonitor, Storage, `.ok`) | ✅ 1.4 |
| Isolation tests + harness `tests/` | ✅ in-repo (LIB-11 / LIB-15) |
| **LIB-CANON** `type_default` → `request_default` | ✅ 1.5.0 |
| **LIB-BPLUS** labels + P2 matrix | ✅ 1.5.0 |
| **LIB-COV-*** interactive HTML / CLI | ✅ 1.5.0 |
| LIB-UI-FREEZE / CAP / HOOKS | ✅ 1.5.0 |
| LIB-GEN + IB helper | ✅ 1.5.0 |
| Public GitHub | out of scope |

### 2.2. aqa consumer (из их SoT, 2026-08-13)

| Блок | Статус |
|---|---|
| Pin 1.4.0 + `pytest_plugin=False` | ✅ W3; **W4 pin 1.5.0** next |
| API harness re-exports / adapters | ✅ |
| Raw IncorrectBody ≥6 write entities | ✅ AQA-4 |
| `type=types.request_*` | ✅ AQA-5 |
| CollectionsManager + HeadersBind | ✅ AQA-7 |
| UI: BasePage / PageMonitor / health / Storage | ✅ W3 (AQA-1/2) |
| visual_scenes | ⬜ **domain STAY** |
| Shims allure/token/env | ⬜ STAY by design (AQA-3) |
| Full suite green | 🟡 AQA-6 sample only |

---

## 3. Issues tracker (through 1.5.0)

| ID | Status | Notes |
|---|---|---|
| LIB-01…07, 09, 10, 12–14, 16 | ✅ | 1.3.x |
| LIB-08 UI drain / parity | ✅ | 1.4 + aqa W3 |
| LIB-11 isolation tests | ✅ | `tests/test_ui_isolation.py` |
| LIB-15 harness tests | ✅ | `tests/` + Tracking 409 |
| LIB-UI-01…06 | ✅ | 1.4.0 |
| **LIB-CANON** | ✅ | 1.5.0 |
| **LIB-BPLUS** | ✅ | 1.5.0 |
| **LIB-COV-*** | ✅ | 1.5.0 |
| LIB-UI-FREEZE / CAP / HOOKS | ✅ | 1.5.0 |
| LIB-GEN + IB helper | ✅ | 1.5.0 |
| LIB-D7 Allure soft-dep docs | ✅ | REPORTING / ENTERPRISE |

---

## 4. aqa file map (W3)

| Path | Статус |
|---|---|
| `requirements/{api,ui}.txt` | ✅ `partest[ui]==1.4.0` |
| API utils (tracker, reporting, payloads, token adapter, RiskProfile) | ✅ library + domain STAY |
| UI jwt / visual_compare / allure_ui / page_monitor / health / base_page / storage | ✅ re-export 1.4 |
| `visual_scenes.py` | STAY domain |
| `db_cleanup` / entities | STAY |

### aqa backlog

| ID | Pri | Status |
|---|---|---|
| AQA-1 / AQA-2 | P0/P1 | ✅ W3 |
| AQA-3 shims | P2 | ✅ partial — keep domain adapters |
| AQA-4 / AQA-5 / AQA-7 | P2/P3 | ✅ |
| **AQA-6** full suite green | P2 | 🟡 |

---

## 5. Что дальше

### Library

```text
done   1.4.0 / 1.5.0 PyPI
never  public GitHub
next   only on request (roadmap empty)
```

### aqa

```text
W4     pin partest==1.5.0  →  drop local coverage_report / IB helper if desired
AQA-6  full API+UI suite green on stand
```

---

## 6. Scorecard

| Метрика | Сейчас |
|---|---|
| Greenfield API / UI docs in wheel | ✅ |
| aqa UI harness local? | ✅ drained |
| Second project needs aqa copy? | No (harness + extras on PyPI 1.5.0) |
| `import partest.ui` loads swagger? | No (LIB-11 tests) |
| Interactive coverage in library? | ✅ `zorro_enhanced` / `python -m partest.reports` |
| Public GitHub | out of scope |

---

## 7. История

| Дата | Событие |
|---|---|
| 2026-08-11 | W1/W2 aqa; LIB-01…16; LIB-UI |
| 2026-08-13 | **1.4.0 PyPI**; aqa **W3** UI drain; AQA-4/5/7; LIBRARY_ROADMAP |
| 2026-08-13 | partest: CANON + BPLUS + COV extract in tree; public GitHub out of scope |
| 2026-08-14 | **1.5.0 prepared** (COV + CANON/BPLUS + UI extras + GEN); checklist `RELEASE_1.5.0.md` |
| 2026-08-14 | **1.5.0 PyPI**; library roadmap empty; next = aqa W4 + AQA-6 |

*Не возвращать в backlog публикацию на GitHub.*
