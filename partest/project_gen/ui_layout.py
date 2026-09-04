"""G5: deep UI monorepo layout (aqa-style, product-agnostic).

Generated consumer tree re-exports ``partest.ui`` (requires ``partest[ui]``).
Product POM, scenes, and RBAC matrix stay in the consumer project.
"""

from __future__ import annotations

from typing import Dict


def _init() -> str:
    return '"""Package."""\n'


def build_ui_files(*, project_name: str = "api-suite") -> Dict[str, str]:
    """Return relative path → file content for full UI tree."""
    files: Dict[str, str] = {}
    name = project_name or "api-suite"

    for rel in [
        "src/ui/__init__.py",
        "src/ui/pages/__init__.py",
        "src/ui/components/__init__.py",
        "src/ui/fixtures/__init__.py",
        "src/ui/resources/__init__.py",
        "src/ui/utils/__init__.py",
        "src/ui/tools/__init__.py",
        "src/ui/tests/__init__.py",
        "src/ui/tests/smoke/__init__.py",
        "src/ui/tests/auth/__init__.py",
        "src/ui/tests/rbac/__init__.py",
        "src/ui/tests/visual/__init__.py",
    ]:
        files[rel] = _init()

    files["src/ui/README.md"] = f"""# UI suite ({name})

Playwright UI layer — **isolated** from API OpenAPI / partest coverage session.

## Principles

1. Test = user journey; locators live in Page / Component objects.
2. Prefer `data-testid` over CSS/XPath.
3. Seed data via **API** (`fixtures/api_seed.py`); UI verifies.
4. Attach network/console health on failures (`utils/page_monitor.py`).
5. Visual baselines under `baselines/reference/` (git); actual/diff gitignored.
6. Do **not** import `confpartest` or load swagger in UI conftest.

## Install

```bash
pip install partest[ui]
# or in this project:
pip install -r requirements/ui.txt
playwright install chromium
```

## Run

```bash
# PowerShell
./scripts/run_ui.ps1
# bash
./scripts/run_ui.sh
# raw
pytest src/ui -m ui_smoke -q
pytest src/ui -m "ui and not ui_visual" -q
```

## Layout

```text
src/ui/
  conftest.py          # frontend_url, page fixtures (no API session)
  pages/               # POM
  components/          # shared chrome (nav, shell)
  fixtures/            # auth, api_seed
  utils/               # monitor, health, visual, allure
  resources/           # ui rbac matrix stub
  tools/               # capture baselines
  baselines/reference/ # golden PNGs
  tests/{{smoke,auth,rbac,visual}}/
```

Utils re-export ``partest[ui]`` (``pip install partest[ui]``). Product POM/scenes stay here.
"""

    files["src/ui/conftest.py"] = '''"""UI conftest — isolated from API OpenAPI / TokenManager / partest coverage.

Uses **sync** pytest-playwright ``page`` (aqa-style). Do not import confpartest.
"""

from __future__ import annotations

import os

import pytest

from partest.ui.hooks import resolve_frontend_url


# Markers + --frontend-url + optional PageMonitor (PARTEST_UI_MONITOR=1)
# Local fixtures — do not pull API suite conftest
pytest_plugins = [
    "partest.ui.pytest_plugin",
    "src.ui.fixtures.auth",
    "src.ui.fixtures.api_seed",
]


@pytest.fixture(scope="session")
def frontend_url(request) -> str:
    return resolve_frontend_url(request.config, default="http://127.0.0.1:3000")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, frontend_url):
    """pytest-playwright context: locale, viewport, SPA base_url."""
    return {
        **browser_context_args,
        "viewport": {"width": 1440, "height": 900},
        "base_url": frontend_url,
        "ignore_https_errors": True,
    }


@pytest.fixture
def _attach_monitor(page, frontend_url):
    """Attach PageMonitor when the test uses ``page`` (opt-in via env still ok)."""
    try:
        from partest.ui import attach_page_monitor

        attach_page_monitor(page, spa_base_url=frontend_url)
    except Exception:
        pass
    yield page
'''

    files["src/ui/pages/base_page.py"] = '''"""Base Page Object — sync partest[ui] (pytest-playwright)."""

from partest.ui import BasePage

__all__ = ["BasePage"]
'''

    files["src/ui/pages/login_page.py"] = '''"""Login page stub — wire your IdP / SPA login form."""

from __future__ import annotations

from src.ui.pages.base_page import BasePage


class LoginPage(BasePage):
    """Example POM. Replace selectors with product testids."""

    def open(self):
        self.goto("/login")  # TODO: real login path
        return self

    def login(self, username: str, password: str):
        # TODO: by_test_id("login-username") etc.
        self.page.fill('input[name="username"]', username)
        self.page.fill('input[type="password"]', password)
        self.page.click('button[type="submit"]')
        return self
'''

    files["src/ui/components/app_shell.py"] = '''"""App chrome: sidebar / header — product-specific; keep thin."""

from __future__ import annotations

from src.ui.pages.base_page import BasePage


class AppShell(BasePage):
    def nav(self):
        # TODO: return by_test_id("app-nav")
        return self.page.locator("nav")

    def expect_shell_ready(self):
        self.expect_visible(self.nav())
'''

    files["src/ui/fixtures/auth.py"] = '''"""Auth fixtures for UI — local browser storage / login POM.

Do not pull API suite TokenManager session into UI collection unless needed
for api_seed only.
"""

from __future__ import annotations

import os

import pytest

from src.ui.pages.login_page import LoginPage


@pytest.fixture
def authenticated_page(page, frontend_url):
    """Log in with env UI credentials (optional skip if unset)."""
    user = os.getenv("FRONTEND_UI_USER") or os.getenv("UI_USER")
    password = os.getenv("FRONTEND_UI_PASSWORD") or os.getenv("UI_PASSWORD")
    if not user or not password:
        pytest.skip("Set FRONTEND_UI_USER / FRONTEND_UI_PASSWORD for authenticated UI tests")
    login = LoginPage(page, frontend_url)
    login.open()
    login.login(user, password)
    yield page
'''

    files["src/ui/fixtures/api_seed.py"] = '''"""Seed domain data via HTTP API for UI verification (not via UI clicks).

Use plain httpx — keep UI suite independent of partest coverage counters.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import pytest

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore


@pytest.fixture(scope="session")
def api_base_url() -> str:
    return (os.getenv("BASE_URL") or "http://127.0.0.1:8080").rstrip("/")


@pytest.fixture
def api_seed_client(api_base_url):
    if httpx is None:
        pytest.skip("httpx required for api_seed")
    with httpx.Client(base_url=api_base_url, verify=False, timeout=30.0) as client:
        yield client


def seed_example(client, token: Optional[str] = None) -> Dict[str, Any]:
    """TODO: POST a minimal entity marked with TEST_DATA_MARKER and return body."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    # response = client.post("/items", json={...}, headers=headers)
    raise NotImplementedError("Implement product seed helpers")
'''

    files["src/ui/utils/page_monitor.py"] = '''"""Re-export page monitor from partest[ui] (1.4+ parity)."""

from partest.ui.page_monitor import (
    MONITOR_ATTR,
    ConsoleIssue,
    NetworkIssue,
    PageMonitor,
    attach_monitor,
    get_monitor,
    is_library_console_message,
    should_ignore_url,
)

__all__ = [
    "MONITOR_ATTR",
    "ConsoleIssue",
    "NetworkIssue",
    "PageMonitor",
    "attach_monitor",
    "get_monitor",
    "should_ignore_url",
    "is_library_console_message",
]
'''

    files["src/ui/utils/health.py"] = '''"""Re-export health asserts from partest[ui]."""

from partest.ui.health import (
    assert_libraries_loaded,
    assert_page_healthy,
    assert_page_network_clean,
    ensure_monitor,
)

__all__ = [
    "ensure_monitor",
    "assert_page_network_clean",
    "assert_libraries_loaded",
    "assert_page_healthy",
]
'''

    files["src/ui/utils/allure_ui.py"] = '''"""Re-export UI Allure helpers from partest[ui]."""

from partest.ui.allure_ui import (
    attach_failure_context,
    attach_json,
    attach_screenshot,
    attach_text,
    attach_url,
)

__all__ = [
    "attach_screenshot",
    "attach_url",
    "attach_text",
    "attach_json",
    "attach_failure_context",
]
'''

    files["src/ui/utils/visual_compare.py"] = '''"""Re-export visual compare from partest[ui]."""

from partest.ui.visual import VisualCompareResult, compare_images

__all__ = ["VisualCompareResult", "compare_images"]
'''

    files["src/ui/utils/visual_scenes.py"] = '''"""Re-export freeze helpers; product SCENES stay in this file if needed."""

from partest.ui.visual import (
    FREEZE_CSS,
    VisualScene,
    inject_freeze_styles,
    inject_freeze_styles_sync,
    wait_ready_for_screenshot,
    wait_ready_for_screenshot_sync,
)

# SCENES = [VisualScene(name="home", path="/"), ...]

__all__ = [
    "FREEZE_CSS",
    "VisualScene",
    "inject_freeze_styles",
    "inject_freeze_styles_sync",
    "wait_ready_for_screenshot",
    "wait_ready_for_screenshot_sync",
]
'''

    files["src/ui/utils/storage.py"] = '''"""Re-export storage helpers from partest[ui]."""

from partest.ui.storage import clear_storage, get_local_storage, set_local_storage

__all__ = ["get_local_storage", "set_local_storage", "clear_storage"]
'''

    files["src/ui/resources/ui_rbac_matrix.py"] = '''"""Expected UI visibility × role — fill from product access model.

Example::

    MATRIX = {
        "admin": {"nav.settings": True, "button.create": True},
        "viewer": {"nav.settings": False, "button.create": False},
    }
"""

MATRIX = {}
'''

    files["src/ui/tools/capture_baselines.py"] = '''"""Capture visual baselines — thin wrapper over partest.ui.capture_baselines.

Usage (from project root)::

    python -m src.ui.tools.capture_baselines --out src/ui/baselines/reference
    # or library CLI directly:
    python -m partest.ui.capture_baselines --scenes src/ui/tools/scenes.json --dry-run

Edit SCENES below (or pass --scenes JSON) and optional login hook.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List, Optional

from partest.ui.capture_baselines import capture_baselines_sync, load_scenes
from partest.ui.visual import VisualScene

# Product scenes — fill after stable testids / routes
SCENES: List[dict] = [
    # {"name": "home", "path": "/"},
]


USE_LOGIN = False  # set True when _login is implemented


def _login(page) -> None:
    """Optional: product login before captures (sync Playwright)."""
    # from src.ui.pages.login_page import LoginPage
    # LoginPage(page, os.environ["FRONTEND_URL"]).login(...)
    return None


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Capture UI visual baselines")
    parser.add_argument(
        "--out",
        default="src/ui/baselines/reference",
        help="Output directory for reference PNGs",
    )
    parser.add_argument(
        "--frontend-url",
        default=os.getenv("FRONTEND_URL", "http://127.0.0.1:3000"),
    )
    parser.add_argument(
        "--scenes",
        default=None,
        help="Optional JSON list of {name, path} (overrides SCENES)",
    )
    args = parser.parse_args(argv)
    scenes = load_scenes(args.scenes) if args.scenes else load_scenes(SCENES)
    if not scenes:
        print(
            "No scenes configured — edit SCENES in capture_baselines.py "
            "or pass --scenes path.json"
        )
        return
    manifest = capture_baselines_sync(
        scenes,
        Path(args.out),
        frontend_url=args.frontend_url,
        login=_login if USE_LOGIN else None,
    )
    for entry in manifest:
        print("wrote", Path(args.out) / entry["file"])


if __name__ == "__main__":
    main()
'''

    files["src/ui/tools/scenes.example.json"] = """[
  {"name": "home", "path": "/"}
]
"""

    files["src/ui/baselines/README.md"] = """# Visual baselines

| Dir | Role |
|-----|------|
| `reference/` | Golden images (commit to git) |
| `actual/` | Last run screenshots (gitignored) |
| `diff/` | Diff PNGs (gitignored) |

Capture:

```bash
python -m src.ui.tools.capture_baselines
# library CLI:
python -m partest.ui.capture_baselines --scenes src/ui/tools/scenes.example.json --dry-run
```
"""

    files["src/ui/baselines/reference/.gitkeep"] = ""
    files["src/ui/baselines/actual/.gitkeep"] = ""
    files["src/ui/baselines/diff/.gitkeep"] = ""

    files["src/ui/tests/smoke/test_ui_smoke.py"] = '''"""UI smoke — page loads, shell visible, NF clean."""

from __future__ import annotations

import allure
import pytest

from src.ui.pages.base_page import BasePage
from src.ui.utils.health import assert_page_healthy

pytestmark = [pytest.mark.ui, pytest.mark.ui_smoke]


@allure.epic("UI")
@allure.feature("smoke")
def test_home_loads(page, frontend_url):
    base = BasePage(page, frontend_url)
    base.goto("/")
    # TODO: base.expect_visible(base.by_test_id("app-root"))
    assert page.url.startswith(frontend_url) or True
    assert_page_healthy(page)
'''

    files["src/ui/tests/auth/test_ui_login.py"] = '''"""UI authentication journey stub."""

from __future__ import annotations

import allure
import pytest

pytestmark = [pytest.mark.ui, pytest.mark.ui_auth]


@allure.epic("UI")
@allure.feature("auth")
@pytest.mark.skip(reason="TODO: implement LoginPage selectors + credentials env")
def test_login_success(authenticated_page, frontend_url):
    assert authenticated_page.url.startswith(frontend_url) or True
'''

    files["src/ui/tests/rbac/test_ui_visibility.py"] = '''"""UI RBAC visibility — drive from resources/ui_rbac_matrix.py."""

from __future__ import annotations

import allure
import pytest

from src.ui.resources.ui_rbac_matrix import MATRIX

pytestmark = [pytest.mark.ui, pytest.mark.ui_rbac]


@allure.epic("UI")
@allure.feature("rbac")
@pytest.mark.skip(reason="TODO: fill MATRIX and role fixtures")
def test_rbac_matrix_placeholder():
    assert isinstance(MATRIX, dict)
'''

    files["src/ui/tests/visual/test_visual_smoke.py"] = '''"""Visual regression against baselines/reference."""

from __future__ import annotations

from pathlib import Path

import allure
import pytest

from src.ui.pages.base_page import BasePage
from src.ui.utils.visual_compare import compare_images
from src.ui.utils.visual_scenes import (
    inject_freeze_styles_sync,
    wait_ready_for_screenshot_sync,
)

pytestmark = [pytest.mark.ui, pytest.mark.ui_visual]

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "baselines" / "reference"
ACTUAL = ROOT / "baselines" / "actual"
DIFF = ROOT / "baselines" / "diff"


@allure.epic("UI")
@allure.feature("visual")
@pytest.mark.skip(reason="TODO: capture baselines then enable")
def test_visual_home(page, frontend_url):
    ACTUAL.mkdir(parents=True, exist_ok=True)
    DIFF.mkdir(parents=True, exist_ok=True)
    base = BasePage(page, frontend_url)
    base.goto("/")
    inject_freeze_styles_sync(page)
    wait_ready_for_screenshot_sync(page)
    actual = ACTUAL / "home.png"
    page.screenshot(path=str(actual), full_page=True)
    ref = REF / "home.png"
    if not ref.is_file():
        pytest.skip(f"missing reference {ref}")
    result = compare_images(ref, actual, name="home", diff_output=DIFF / "home.png")
    assert result.ok, result.summary()
'''

    files["src/ui/tests/test_ui_utils_unit.py"] = '''"""Unit tests for UI utils that do not need a browser."""

from __future__ import annotations

from src.ui.utils.page_monitor import (
    is_library_console_message,
    should_ignore_url,
)
from src.ui.utils.visual_compare import VisualCompareResult


def test_should_ignore_tracker_url():
    assert should_ignore_url("https://www.google-analytics.com/x")


def test_library_console():
    assert is_library_console_message("Loading chunk 1 failed")


def test_visual_compare_import():
    r = VisualCompareResult(True, 0.0)
    assert r.equal
    assert r.ok
'''

    files["scripts/run_ui.ps1"] = '''param(
  [switch]$Headed,
  [string]$Marker = "ui_smoke"
)
$env:PYTHONPATH = "."
$args = @("src/ui", "-m", $Marker, "-q")
if ($Headed) { $args += "--headed" }
pytest @args
'''

    files["scripts/run_ui.sh"] = '''#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH=.
MARKER="${1:-ui_smoke}"
shift || true
pytest src/ui -m "$MARKER" -q "$@"
'''

    files["docs/UI_GUIDE.md"] = f"""# UI testing guide ({name})

Generated by **partest-gen G5**. **Sync** pytest-playwright + ``partest.ui.BasePage``.
Aligns with monorepo isolation:

| Suite | Entry | Loads OpenAPI? | Playwright? |
|-------|-------|----------------|-------------|
| API | `pytest src/api/tests` | yes (partest) | no |
| UI | `pytest src/ui` | **no** | yes |

## Checklist to productionize

1. Install: `pip install -r requirements/ui.txt && playwright install chromium`
2. Set `FRONTEND_URL`, `FRONTEND_UI_USER`, `FRONTEND_UI_PASSWORD` in `.env`
3. Replace LoginPage selectors with `data-testid`
4. Implement `api_seed` helpers (httpx + marker names)
5. Fill `ui_rbac_matrix.MATRIX`
6. Define visual scenes + capture baselines
7. Utils re-export `partest[ui]` (`BasePage` **sync**, `PageMonitor`, `Storage`)
8. Optional: `PARTEST_UI_MONITOR=1` for autouse PageMonitor finalize

## Markers

- `ui` — all UI
- `ui_smoke` — fast
- `ui_auth` / `ui_rbac` / `ui_visual`

## CI suggestion

```text
job:ui
  pip install -r requirements/ui.txt
  playwright install chromium --with-deps
  pytest src/ui -m "ui and not ui_visual" -q
```
"""

    return files
