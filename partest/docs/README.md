# partest 1.5.0

Methodology-driven **API + UI autotest harness** for Python, plus **`partest-gen`**
scaffold for aqa-style monorepo suites.

**Start here:** [QUICKSTART.md](QUICKSTART.md) · [MIGRATION.md](MIGRATION.md)  
**Cookbooks:** [REPORTING](REPORTING.md) · [COVERAGE](COVERAGE_REPORT.md) · [SECURITY](SECURITY.md) · [UI](UI_QUICKSTART.md) · [RECIPES](RECIPES.md) · [ENTERPRISE](ENTERPRISE.md)

## Install

```bash
pip install partest
pip install partest[ui]    # Playwright + Pillow
# development:
pip install -e ".[ui]"
```

## Quick start — write tests

```python
from partest import ApiClient, TypesTestCases, TrackingApiClient, CreatedRegistry
import partest.reporting as ah
from partest.zorro_report import zorro

types = TypesTestCases

await api_client.make_request(
    "GET",
    "/items/{id}",
    add_url1="/1",
    defining_url="/items/{id}",
    expected_status_code=200,
    validate_model=MyValidator,
    type=types.request_default,
)
```

Coverage report:

```python
report = zorro()  # Allure + simple coverage_report.html
# interactive HTML + coverage.json:
from partest.reports import zorro_enhanced
zorro_enhanced()
```

### Harness modules

```python
from partest import TrackingApiClient, CreatedRegistry, TokenManager, BaseRequestBody, Config
from partest.security import SecHttp, build_tampered_set
from partest.validation import BaseResponseValidator, ProblemDetailValidation
import partest.reporting as ah
from partest.env import load_project_env, require_env
from partest.data_marker import marked_name
from partest.ui import BasePage, PageMonitor, Storage, attach_monitor, compare_images  # partest[ui]>=1.5.0
```

| Module | Role |
|--------|------|
| TrackingApiClient | POST track + cleanup |
| TokenManager | OIDC multi-role cache |
| SecHttp | raw httpx security transport |
| build_tampered_set | JWT tampering fixtures |
| Config | headers/params builders |
| reporting | `ah.check_*`, instrumented requests |
| ui | sync BasePage, PageMonitor, Storage, visual, capture_baselines (`partest[ui]>=1.5.0`) |

**pytest plugin** auto-loads (`partest.pytest_plugin`): Allure titles from docstring.  
Disable dual hooks: `PARTEST_PYTEST_PLUGIN=0`, `pytest_plugin = False` in confpartest,
or `pytest -p no:partest`.

**Raw body:** `content=` + `content_type=` on `ApiClient` for IncorrectBody.  
**Multi-status:** `expected_status_code=(400, 415)`.

**RiskProfile** (consumer keeps entity registry)::

```python
from partest import RiskProfile
RiskProfile("clients", writes=True, fk_traversal=True)  # level=high
```

**UI baselines:**

```bash
python -m partest.ui.capture_baselines --out src/ui/baselines/reference \
  --scenes scenes.json --dry-run
```

### Coverage: matrix vs flat (confpartest)

| Mode | When | Config |
|------|------|--------|
| **Matrix (default)** | methodology subtype × P1 | ignore flat list; `use_matrix=True` |
| **Flat (legacy)** | old projects | `test_types_coverage = [...]` + `use_matrix=False` |

See [MIGRATION.md](MIGRATION.md) § coverage.

### Test types

Canonical: `request_default`, `request_permissions`, `request_new_object`,
`request_incorrect_body`, `request_elements`, `request_not_found`,
`request_not_allowed`, …  

Legacy aliases still work: `default`, `405`, `elem`, …

`type=` is recommended; auto-inference is high-confidence only for 405/404/broken JSON.

## Scaffold — partest-gen

```bash
partest-gen from-openapi ./my-suite --file openapi.yaml --depth p1 --force
partest-gen init-ui ./my-suite --force
partest-gen sync-openapi ./my-suite --depth p1
partest-gen dump-ir openapi.yaml -o .partest/suite_ir.json
```

| `--depth` | Generates |
|-----------|-----------|
| `resources` | paths + collections (G2) |
| `default` | + payloads/validations + Default/405 tests (G3) |
| `p1` | + full P1 matrix stubs + checklist (G4) |

| UI | Command |
|----|---------|
| With new project | `partest-gen init … --with-ui` |
| Add to existing | `partest-gen init-ui ./my-suite` |

UI suite is **isolated**: no OpenAPI/partest coverage session under `src/ui/`.

See [PROJECT_GEN_ROADMAP.md](PROJECT_GEN_ROADMAP.md).

## Configuration

**confpartest.py**

```python
swagger_files = {
    "myservice": ["local", "docs/openapi.yaml"],
}
test_types_coverage = ["request_default", "request_not_allowed"]  # legacy flat mode
test_types_exception = ["health"]
```

**Fixtures:** domain / `api_client` / `reset_storage` — see generated `conftest.py`.

## Maintainers

- Continue development: [DEVELOPMENT.md](DEVELOPMENT.md)  
- Status board: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)  
- Release / aqa bump: [RELEASE_1.5.0.md](RELEASE_1.5.0.md)  
- Agent rules: repo root `AGENTS.md`  
- Skill: `.grok/skills/partest/`  

## Version

**1.5.0** (PyPI) — interactive coverage (`zorro_enhanced` / `python -m partest.reports`),
`canonicalize_type("type_default")`, IB helper, UI freeze/capture hooks, gen HeadersBind.
Built on **1.4.0** UI parity (sync `BasePage`, `PageMonitor`, `Storage`, docs in wheel).

Distributed via **PyPI only**. Public GitHub is not a source channel.
Checklist: [RELEASE_1.5.0.md](RELEASE_1.5.0.md).
