# partest — implementation plan & status

**Version:** 1.5.0 (PyPI)  
**As of:** 2026-08-14  
**Roadmap:** [`LIBRARY_ROADMAP.md`](LIBRARY_ROADMAP.md)  
**Consumer SoT:** [`MIGRATION_1.3.0_ISSUES.md`](MIGRATION_1.3.0_ISSUES.md)

---

## Distribution (policy)

| Channel | Status |
|---------|--------|
| **PyPI** (`pip install partest` / `partest[ui]`) | **shipped** — 1.5.0 |
| Public GitHub | **out of scope** — not planned |

---

## Snapshot

| Area | Status |
|------|--------|
| L0–L5 / G1–G6 / UI parity 1.4.0 | **done** (PyPI 1.4.0) |
| aqa W3 UI drain (AQA-1/2) + AQA-4/5/7 | **done** (consumer, 2026-08-13) |
| **LIB-CANON** / **LIB-BPLUS** / recipes | **done** (1.5.0) |
| **LIB-COV-*** (HTML/CLI/compare/badge/stubs) | **done** (1.5.0) |
| **LIB-UI-FREEZE / CAP / HOOKS** | **done** (1.5.0) |
| **LIB-GEN** sync UI + HeadersBind + IB helper | **done** (1.5.0) |
| aqa AQA-6 full suite green | consumer |
| aqa W4 pin 1.5.0 | **next** (consumer) |

## Remaining

Library roadmap from aqa `docs/partest` is **empty**. Next work only on request.

Consumer (not this repo):

- aqa **W4**: pin `partest==1.5.0` / `partest[ui]==1.5.0` — [`RELEASE_1.5.0.md`](RELEASE_1.5.0.md) §4
- Optional drain: local `coverage_report/`, `raw_incorrect_body.py`, visual_compare shim
- **AQA-6** full stand regression

## Verify

```bash
python -m pytest tests/ -q
python -m partest.reports --help
python -c "from partest import __version__; from partest.test_types import canonicalize_type; assert __version__=='1.5.0'; assert canonicalize_type('type_default')=='request_default'"
```
