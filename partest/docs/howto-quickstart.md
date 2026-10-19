<!-- Part of the partest package: generated documentation, not hand-written.
     Read it with `python -m partest.docs`. Local edits are lost on upgrade. -->

# Quickstart — first green API test

Time-to-first-green API test target: **&lt; 30 minutes**.

## 1. Install

```bash
pip install partest
# optional UI:
pip install partest[ui] && playwright install chromium
```

Right after a release pip may not see the new version yet: it answers from its cached copy
of the package index and reports "no matching distribution" or installs the previous one.
Ask for the version explicitly and skip the cache:

```bash
pip install --no-cache-dir "partest==X.Y.Z"
```

## 2. Minimal API project

```text
my-suite/
  pytest.ini
  confpartest.py
  conftest.py
  test_health.py
```

**pytest.ini**

```ini
[pytest]
pythonpath = .
asyncio_mode = auto
```

`pythonpath = .` puts the suite root on `sys.path`, so `confpartest` and your own modules import
the same way under a console `pytest` as under `python -m pytest`. Without it — and without a
`conftest.py` next to the ini file — partest still loads `confpartest.py` from the ini file's
directory for coverage and says so in a `partest: confpartest` summary section, but nothing
else of yours is importable from there, and the plugin's own switches (`pytest_plugin`,
`run_metadata`) are not read from it. If no `confpartest` is found at all, a coverage report
built in that run counts nothing and the pytest summary says why in a
`partest: coverage NOT COUNTED` section. Without any ini file pytest's rootdir is searched
instead, and an IDE that passes `--rootdir=<suite>/tests` then points it at the wrong
directory — keep a `pytest.ini`, or `pythonpath = .`.

**confpartest.py**

```python
swagger_files = {
    "api": ["local", "docs/openapi.yaml"],  # or ["url", "https://…/openapi.json"]
}
test_types_exception = ["health"]
# pytest_plugin = False   # if you already own Allure hooks — Allure only, see below
# tls_verify = False      # if the stand serves a self-signed certificate
```

Two switches worth knowing before the first run:

- `pytest_plugin = False` turns off what the plugin adds **to Allure** and nothing else. What
  the run selected (`-m`/`-k`, deselected count) is still recorded — that is `run_metadata`,
  on by default, and the report needs it to know a run was partial.
- TLS certificates are verified. A stand with a self-signed certificate fails until you say
  `tls_verify = False` (or `PARTEST_TLS_VERIFY=0`, or point `PARTEST_TLS_VERIFY` at the CA
  bundle, which is better). Disabling it warns once per run rather than passing quietly.

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

@pytest.fixture(scope="session", autouse=True)
def _coverage_session():
    reset_storage()   # once, at the start: the counters belong to the whole run
    yield
```

Reset the counters once per session, never per test. The report is built from what the whole
run recorded; a reset after each test leaves nothing for it to read.

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
PARTEST_COVERAGE_JSON=coverage.json PARTEST_COVERAGE_HTML=coverage_report.html pytest -q
```

The two variables make the plugin write `coverage.json` and the interactive HTML when the run
ends, from every test's calls (and from every worker's under `pytest -n`). Building the report
inside a test instead is in [Interactive coverage report and CLI](howto-coverage-html.md).

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
| `PARTEST_PYTEST_PLUGIN=0` | disable partest Allure hooks — **titles and attachments only** |
| `pytest_plugin = False` in confpartest | same |
| `PARTEST_RUN_METADATA=0` / `run_metadata = False` | stop recording what the run selected (`meta.selection`); rarely what you want |
| `pytest -p no:partest` | hard unload entry point — all of the above, **and** the opt-in marker sets (`partest_optin_markers`): their tests then run like any other; **and** everything the plugin does for coverage: no `confpartest.py` lookup in the pytest root, no `partest: coverage NOT COUNTED` section, no report from `PARTEST_COVERAGE_JSON`, no merge of counters under pytest-xdist |

The first two are for projects that own their Allure hooks — use `PARTEST_PYTEST_PLUGIN=0`
rather than `-p no:partest` for that. They do not take the run metadata or the coverage
machinery with them: see [Coverage honesty — when the number lies](concepts-coverage-honesty.md) for what those signals are worth.

## 9. TLS

Certificates are verified. For a stand with a self-signed certificate:

| Mechanism | Effect |
|-----------|--------|
| `PARTEST_TLS_VERIFY=0` | off for the run (wins over confpartest) |
| `tls_verify = False` in confpartest | off for the project |
| `PARTEST_TLS_VERIFY=/path/ca.pem` | keep verifying, trust a private CA |
| `ApiClient(domain, verify=False)` | off for this client only |

Whichever you use, the run says once that it is unverified.
A relative bundle path in `tls_verify` that does not exist from the current directory is
taken from the directory of `confpartest.py`.

## Next

- [Migration between partest versions](howto-migration.md) — upgrading from 0.3 / earlier 1.x
- [UI quickstart (partest[ui])](howto-ui.md) — `partest[ui]` sync BasePage
- [Package map — what lives where](components-overview.md) — full module map
- [Coverage methodology — two areas, three axes each](concepts-methodology.md) — what "covered" actually means
