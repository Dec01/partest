# partest — agent instructions

Public Python library for **methodology-driven API autotests** (optional UI scaffold)
with OpenAPI-aware coverage.

**Version:** 1.5.0 (PyPI)  
**Package:** `partest`  
**Continue developing:** `docs/DEVELOPMENT.md`  
**Consumer issues SoT:** `docs/MIGRATION_1.3.0_ISSUES.md` (copy in aqa)  
**Distribution:** PyPI only — **do not** publish this tree to public GitHub.

---

## Mission

1. Thin HTTP harness + OpenAPI coverage + methodology (subtype × TC × steps).
2. Extract shared harness only — never product domain.
3. Scaffold suites via `partest-gen` (aqa-like monorepo).
4. Skill enables agents to grow suites consistently.

---

## Non-goals (never in library)

Entity DTO/paths of a product · RBAC role lists · SQL cleanup · product page objects ·
visual baselines · private stand URLs · absolute local paths in public artifacts ·
public GitHub dump of this repo.

---

## Architecture (current)

```text
partest/
  client, coverage, call_storage, test_types, zorro_report
  methodology/     # SoT for subtypes × matrix × inference
  reports/         # analyzer + HTML
  tracking, auth, reporting, payloads, validation, env, data_marker
  collections, security
  project_gen/     # CLI + IR + emitters + ui_layout (G5)
  utils/
```

Consumer-only: `confpartest.py`, project tests, domain resources.

---

## Coverage methodology (encoded)

- **Axis A** — method subtype (`methodology/subtypes` + classifier)  
- **Axis B** — TC types (`TypesTestCases`, matrix)  
- **Axis C** — steps (status → schema → values)  

**Inference:** explicit `type=` wins; high confidence only for 405/404/broken raw body.
Do not remove `type=` for permissions/new/update/elements/extra/env.

---

## Generator

| Wave | Status |
|------|--------|
| G1–G4 API scaffold | done |
| G5 UI deep layout | done |
| G6 agent playbook | done (skill + post-gen-playbook) |

Commands: `init`, `from-openapi`, `sync-openapi`, `dump-ir`, `init-ui`.  
Depth: `resources` | `default` | `p1`.  
UI baselines: `python -m partest.ui.capture_baselines`.

---

## Implementation backlog

| Wave | Focus | Status |
|------|--------|--------|
| **1.2–1.3** | security, UI extra, gen G1–G6 | **done** |
| **L0** | multi-project safety | **done** (1.3.1) |
| **L1–L3** | drain API + cookbooks + UI isolation | **done** (1.3.2) |
| **L5** | enterprise | **done** (1.3.3) |
| **1.4 UI parity** | sync BasePage, PageMonitor finalize, docs-in-wheel | **done** |
| **P0 ops** | PyPI 1.4.0 | **done** (PyPI only; public GitHub out of scope) |
| **1.5.0** | CANON + BPLUS + COV + UI extras + GEN | **done** (PyPI) |

aqa: W3 pin 1.4.0. **Next = W4 pin 1.5.0** + AQA-6. Library roadmap empty.

Roadmap: `docs/LIBRARY_ROADMAP.md`  
SoT: `docs/MIGRATION_1.3.0_ISSUES.md`

See `docs/IMPLEMENTATION_PLAN.md` for full WP table.

---

## Agent workflow in this repo

1. Read this file + `docs/DEVELOPMENT.md`.  
2. Methodology SoT: `partest/methodology/*`.  
3. Generator SoT: `docs/PROJECT_GEN_ROADMAP.md` + `project_gen/`.  
4. No secrets/stand URLs in package.  
5. Tests: `python -m pytest tests/ -q`.  
6. Update `docs/README.md` + `CHANGELOG.md` + skill on public API/CLI changes.  
7. Bump version only on release request.

---

## Skill

`.grok/skills/partest/SKILL.md` — `/partest` for writing/extending suites.
