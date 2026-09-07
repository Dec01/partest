---
title: Quickstart — first green API test
status: current
verified: 2026-09-07
sources: [partest/client.py, partest/conf.py, partest/env/__init__.py, partest/zorro_report.py]
audience: user
ships_in_wheel: true
---

# Quickstart — first green API test

Time-to-first-green API test target: **&lt; 30 minutes**.

## 1. Install

```bash
pip install partest
# optional UI:
pip install partest[ui] && playwright install chromium
```

## 2. Minimal API project

```text
my-suite/
  confpartest.py
  conftest.py
  test_health.py
```

**confpartest.py**

```python
swagger_files = {
    "api": ["local", "docs/openapi.yaml"],  # or ["url", "https://…/openapi.json"]
}
test_types_exception = ["health"]
# pytest_plugin = False   # if you already own Allure hooks
```

**conftest.py**

```python
from pathlib import Path
import pytest
from partest import ApiClient, reset_storage
from partest.env import set_project_root, load_project_env

ROOT = Path(__file__).resolve().parent
set_project_root(ROOT)
load_project_env(ROOT)

@pytest.fixture(scope="session")
def domain():
    return "http://127.0.0.1:8080"  # or env BASE_URL

@pytest.fixture(scope="session")
def api_client(domain):
    return ApiClient(domain)

@pytest.fixture(autouse=True)
def _coverage_reset():
    reset_storage()
    yield
    reset_storage()
```

**test_health.py**

```python
import pytest
from partest import TypesTestCases

types = TypesTestCases

@pytest.mark.asyncio
async def test_health(api_client):
    await api_client.make_request(
        "GET",
        "/health",
        expected_status_code=200,
        type=types.request_default,
    )
```

```bash
pytest test_health.py -q --asyncio-mode=auto
```

## 3. Scaffold monorepo (recommended)

The scaffold is a separate package — install it once, and it brings this one with it:

```bash
pip install partest-gen
partest-gen from-openapi ./my-suite --file openapi.yaml --depth p1 --force --with-ui
cd my-suite
pip install -r requirements/api.txt
cp env.example .env   # set BASE_URL, optional KEYCLOAK_*
pytest src/api/tests --collect-only -q
```

What to do next with the generated stubs: `python -m partest_gen.docs show howto-after-generation`.

## 4. Multi-status & raw IncorrectBody

```python
# accept either validation or media-type error
await api_client.make_request(
    "POST", "/items",
    content=b'{"a":',
    content_type="application/json",
    expected_status_code=(400, 415),
    type=types.request_incorrect_body,
)
```

## 5. Auth (Keycloak recipe)

```python
from partest import TokenManager
from partest.env import require_env

def credentials(role: str):
    # map roles → env; never hardcode passwords in git
    return require_env(f"USER_{role.upper()}"), require_env(f"PASS_{role.upper()}")

tm = TokenManager(
    keycloak_url=require_env("KEYCLOAK_URL"),
    realm=require_env("KEYCLOAK_REALM"),
    client_id=require_env("KEYCLOAK_CLIENT_ID"),
    credentials_provider=credentials,
    known_roles=("admin", "viewer"),
    verbose=False,  # default quiet; logger.debug on refresh
)
token = await tm.get_token(role="admin")
```

## 6. Risk profiles (consumer registry)

```python
from partest import RiskProfile
from partest.security import by_level, writable

PROFILES = {
    "items": RiskProfile("items", writes=True, fk_traversal=True),
    "users": RiskProfile("users", writes=True, authz=True, pii=True),
}
assert by_level(PROFILES, "critical")[0].entity == "users"
```

## 7. UI isolation (monorepo)

```bash
pip install partest[ui] partest-gen
partest-gen init-ui ./my-suite --force
pytest src/ui/tests -q   # must NOT load confpartest swagger session
```

Baselines:

```bash
python -m partest.ui.capture_baselines --scenes scenes.json --dry-run
```

## 8. Plugin dual-hook opt-out

| Mechanism | Effect |
|-----------|--------|
| `PARTEST_PYTEST_PLUGIN=0` | disable partest Allure hooks |
| `pytest_plugin = False` in confpartest | same |
| `pytest -p no:partest` | hard unload entry point |

## Next

- [[howto/migration]] — upgrading from 0.3 / earlier 1.x
- [[howto/ui]] — `partest[ui]` sync BasePage
- [[components/overview]] — full module map
- [[concepts/methodology]] — what "covered" actually means
