# partest 1.5.0 — release + consumer checklist

**Date:** 2026-08-14  
**Version:** `1.5.0`  
**Channel:** PyPI only (`pip install partest` / `partest[ui]`). No public GitHub.

This file is the operational checklist. Product notes: [`CHANGELOG.md`](../CHANGELOG.md),
[`MIGRATION.md`](MIGRATION.md).

---

## 1. What ships

1.4.0 + previously unreleased waves, one backward-compatible minor:

| Wave | IDs | What consumers get |
|------|-----|--------------------|
| 1.4.x | LIB-CANON, LIB-BPLUS, LIB-REC-* | `type_default` aliases, B+ labels, recipes |
| 1.5 | LIB-COV-* | `zorro_enhanced()`, `python -m partest.reports` |
| 1.6 | LIB-UI-FREEZE / CAP / HOOKS | freeze CSS, capture CLI, optional UI plugin |
| 1.7 | LIB-GEN, LIB-REC-IB | IB helper, gen HeadersBind + sync UI |

**Not breaking** vs 1.4.0: `zorro()`, `BasePage` sync, `TypesTestCases.request_*`,
legacy TC aliases, RiskProfile dual API, plugin opt-out — all unchanged.

**Stay in consumer:** entity DTO/paths, RBAC, SQL, page objects, `visual_scenes`,
baselines PNG, stand URLs, domain 409 provider.

---

## 2. Library — before upload

- [x] Version `1.5.0` in `setup.py` and `partest.__version__`
- [x] `CHANGELOG.md` — Unreleased folded into `## 1.5.0`
- [x] User docs + `partest/docs/` (wheel) updated
- [x] `partest-gen` pins `partest>=1.5.0` / `partest[ui]>=1.5.0`
- [x] `python -m pytest tests/ -q` green (137+ tests)

Re-verify locally:

```bash
python -m pytest tests/ -q
python -c "from partest import __version__; from partest.test_types import canonicalize_type; assert __version__=='1.5.0'; assert canonicalize_type('type_default')=='request_default'"
python -m partest.reports --help
python -m partest.ui.capture_baselines --dry-run
```

No secrets, stand URLs, or absolute local paths in files that ship in the wheel
(`partest/docs/*.md`, package source).

---

## 3. Library — publish to PyPI

From a clean tree (no leftover `dist/` from 1.4.0):

```bash
python -m pip install -U build twine
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

After upload:

```bash
pip index versions partest
python -m pip install -U 'partest==1.5.0' 'partest[ui]==1.5.0'
python -c "import partest; print(partest.__version__)"
```

- [x] `twine check` clean
- [x] `twine upload` succeeded
- [x] `partest==1.5.0` on PyPI
- [x] Docs flipped: **shipped on PyPI**

Do **not** push this tree to public GitHub.

---

## 4. aqa — W4 bump (1.5.0 is on PyPI)

aqa is still on **1.4.0** (W3). This is consumer work, not library.

### 4.1. Pin

```text
# requirements/api.txt
partest==1.5.0

# requirements/ui.txt
partest[ui]==1.5.0
```

```bash
pip install -r requirements/api.txt
pip install -r requirements/ui.txt
python -c "import partest; assert partest.__version__=='1.5.0'"
```

Keep `pytest_plugin = False` in `confpartest.py` (dual Allure hooks).

### 4.2. Smoke (no stand)

```bash
# AST / collect — same as W3 baseline
python -c "import ast, pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('src').rglob('*.py')]"
pytest --collect-only -q src/api/tests
pytest src/ui/tests/test_ui_utils_unit.py -v
```

### 4.3. Optional drain (safe after green collect)

| Local aqa path | After 1.5.0 |
|---|---|
| `src/api/utils/coverage_report/` | Replace `test_zorro` with `zorro_enhanced(service_map=…)` + `python -m partest.reports`. Keep `services.yaml` (consumer). |
| `src/api/resources/validations/common/raw_incorrect_body.py` | `from partest.validation import RAW_INCORRECT_BODY_CASES, assert_raw_incorrect_body` |
| `src/ui/utils/visual_compare.py` extra kwargs | Drop shim — library accepts `name=` / `diff_output=` |
| `src/ui/utils/visual_scenes.py` freeze CSS | Import `FREEZE_CSS` / `inject_freeze_styles_sync` from `partest.ui`; **SCENES stay** |
| `src/ui/tools/capture_baselines.py` | Thin wrapper over `capture_baselines_sync` (login/scenes stay) |

Do **not** delete: `visual_scenes.SCENES`, token/env/allure domain adapters (AQA-3),
`db_cleanup`, entities, page objects, baselines.

### 4.4. Coverage switch (when dropping local report)

```python
from partest.reports import ServiceMap, zorro_enhanced

smap = ServiceMap.load("src/api/resources/coverage/services.yaml")
zorro_enhanced(service_map=smap)  # coverage_report.html + coverage.json
```

```bash
python -m partest.reports render --json coverage.json --html coverage_report.html
python -m partest.reports compare --a old.json --b coverage.json
python -m partest.reports badge --json coverage.json --out coverage.svg
```

### 4.5. Stand / AQA-6 (not a library blocker)

```bash
pytest src/api/tests/brands/test_brands_validation.py::TestBrandsValidation::test_create_brand_raw_body_rejected -v
pytest src/ui/tests/test_ui_utils_unit.py -v
# then claim AQA-6 only after a full API+UI run on stand
```

### 4.6. Docs in aqa

Update `docs/partest/MIGRATION_1.3.0_ISSUES.md` / `README.md`:

- pin **1.5.0**, wave **W4**
- library remaining = none for this roadmap
- residual = **AQA-6** + domain STAY

---

## 5. Greenfield (new suite)

```bash
pip install 'partest[ui]>=1.5.0'
partest-gen from-openapi ./my-suite --file openapi.yaml --depth p1 --force --with-ui
```

Generated `requirements/{api,ui}.txt` already pin `>=1.5.0`.

---

## 6. Rollback

```bash
pip install 'partest==1.4.0' 'partest[ui]==1.4.0'
```

1.5.0 APIs (`zorro_enhanced`, `RAW_INCORRECT_BODY_CASES`, freeze sync helpers)
are absent on 1.4.0 — revert any W4 drain imports before rolling back.
