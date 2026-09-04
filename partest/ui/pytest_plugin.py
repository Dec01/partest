"""Optional UI pytest hooks. Enable in UI conftest only::

    pytest_plugins = ["partest.ui.pytest_plugin"]

Does not load API coverage plugin, OpenAPI, or Playwright at import time.
Autouse PageMonitor: ``PARTEST_UI_MONITOR=1`` or ``--partest-ui-monitor``.
"""

from __future__ import annotations

import pytest

from partest.ui.hooks import (
    attach_page_monitor,
    finalize_page_monitor,
    request_failed,
    request_skipped,
    resolve_frontend_url,
    ui_monitor_enabled,
)


def pytest_addoption(parser):
    group = parser.getgroup("partest-ui")
    group.addoption(
        "--frontend-url",
        action="store",
        default=None,
        help="SPA base URL (else FRONTEND_URL env)",
    )
    group.addoption(
        "--partest-ui-monitor",
        action="store_true",
        default=False,
        help="Autouse PageMonitor attach/finalize on Playwright `page`",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "ui: UI suite")
    config.addinivalue_line("markers", "ui_smoke: fast UI smoke")
    config.addinivalue_line("markers", "ui_auth: UI authentication")
    config.addinivalue_line("markers", "ui_rbac: UI role visibility")
    config.addinivalue_line("markers", "ui_visual: visual baseline compare")


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture(autouse=True)
def _partest_ui_page_monitor(request):
    """Attach PageMonitor when enabled and the test uses the `page` fixture.

    Does not define ``frontend_url`` (consumer / generated conftest owns it).
    """
    if not ui_monitor_enabled(request.config):
        yield
        return
    if "page" not in request.fixturenames:
        yield
        return
    spa = ""
    if "frontend_url" in request.fixturenames:
        spa = str(request.getfixturevalue("frontend_url") or "")
    if not spa:
        spa = resolve_frontend_url(request.config)
    page = request.getfixturevalue("page")
    attach_page_monitor(page, spa_base_url=spa)
    yield
    markers = {m.name for m in request.node.iter_markers()}
    require_shell = "ui_auth" not in markers
    finalize_page_monitor(
        page,
        test_failed=request_failed(request),
        test_skipped=request_skipped(request),
        require_app_shell=require_shell,
    )
