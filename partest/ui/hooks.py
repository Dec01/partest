"""Optional UI pytest helpers (LIB-UI-HOOKS).

Does **not** import Playwright or project conf at module load (isolation).
Enable the plugin via UI conftest::

    pytest_plugins = ["partest.ui.pytest_plugin"]

Autouse PageMonitor is **off** unless ``PARTEST_UI_MONITOR=1`` or
``--partest-ui-monitor``. Consumer can still call helpers by hand.
"""

from __future__ import annotations

import os
from typing import Any, Optional


def env_truthy(name: str) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    return raw in ("1", "true", "yes", "on", "y")


def resolve_frontend_url(
    config: Any = None,
    *,
    default: str = "",
) -> str:
    """CLI ``--frontend-url`` → ``FRONTEND_URL`` → ``default``."""
    if config is not None:
        try:
            cli = config.getoption("--frontend-url", default=None)
        except (ValueError, AttributeError):
            cli = None
        if cli:
            return str(cli).rstrip("/")
    env_url = (os.getenv("FRONTEND_URL") or "").strip()
    if env_url:
        return env_url.rstrip("/")
    return (default or "").rstrip("/")


def resolve_api_base_url(*, default: str = "") -> str:
    """``BASE_URL`` / ``API_BASE_URL`` only — no product settings module."""
    for key in ("API_BASE_URL", "BASE_URL"):
        raw = (os.getenv(key) or "").strip()
        if raw:
            return raw.rstrip("/")
    return (default or "").rstrip("/")


def attach_page_monitor(
    page,
    *,
    spa_base_url: str,
    api_base_url: str = "",
):
    """Attach :class:`PageMonitor` if the page does not already have one."""
    from partest.ui.page_monitor import PageMonitor, get_monitor

    existing = get_monitor(page)
    if existing is not None:
        return existing
    return PageMonitor.attach(
        page,
        spa_base_url=spa_base_url,
        api_base_url=api_base_url or resolve_api_base_url(),
    )


def finalize_page_monitor(
    page,
    *,
    test_failed: bool = False,
    test_skipped: bool = False,
    require_app_shell: bool = True,
    stop: bool = True,
) -> None:
    """Call ``monitor.finalize`` once (idempotent)."""
    from partest.ui.page_monitor import get_monitor

    mon = get_monitor(page)
    if mon is None:
        return
    if getattr(mon, "_partest_finalized", False):
        return
    page_url = ""
    try:
        page_url = page.url or ""
    except Exception:
        page_url = ""
    never_opened = (not page_url) or str(page_url).startswith("about:blank")
    try:
        mon.finalize(
            test_failed=test_failed or test_skipped or never_opened,
            require_app_shell=require_app_shell,
            assert_healthy=not (test_skipped or never_opened),
        )
    finally:
        mon._partest_finalized = True
        if stop:
            try:
                mon.stop()
            except Exception:
                pass


def request_failed(request) -> bool:
    rep = getattr(request.node, "rep_call", None)
    return bool(rep is not None and getattr(rep, "failed", False))


def request_skipped(request) -> bool:
    rep = getattr(request.node, "rep_call", None)
    return bool(rep is not None and getattr(rep, "skipped", False))


def ui_monitor_enabled(config: Any = None) -> bool:
    if env_truthy("PARTEST_UI_MONITOR"):
        return True
    if config is None:
        return False
    try:
        return bool(config.getoption("--partest-ui-monitor", default=False))
    except (ValueError, AttributeError):
        return False
