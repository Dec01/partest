"""High-level page health checks (aqa parity, LIB-UI-02)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Optional, Sequence

from partest.ui.page_monitor import PageMonitor, get_monitor


@contextmanager
def _step(title: str):
    try:
        import allure

        with allure.step(title):
            yield
    except Exception:
        yield


def ensure_monitor(
    page: Any,
    *,
    spa_base_url: str = "",
    api_base_url: str = "",
    **kwargs: Any,
) -> PageMonitor:
    mon = get_monitor(page)
    if mon is None:
        mon = PageMonitor.attach(
            page, spa_base_url=spa_base_url, api_base_url=api_base_url, **kwargs
        )
    return mon


def assert_page_network_clean(
    page: Any,
    *,
    context: str = "",
    allow_statuses: Optional[Sequence[int]] = None,
) -> None:
    """Fail if monitor recorded critical network issues."""
    mon = get_monitor(page)
    if mon is None:
        return
    # allow_statuses kept for backward compat — critical filter already applied on collect
    _ = allow_statuses
    label = f"NF: network clean{(' — ' + context) if context else ''}"
    with _step(label):
        from partest.ui import allure_ui

        net = [n.summary() for n in mon.network_issues]
        if net:
            allure_ui.attach_json("network_issues_at_check", net)
            raise AssertionError(
                "Network errors on page"
                + (f" ({context})" if context else "")
                + ":\n  - "
                + "\n  - ".join(net)
            )
        allure_ui.attach_text(
            "network_check",
            f"OK — 0 critical network issues{(' @ ' + context) if context else ''}",
        )


def assert_libraries_loaded(
    page: Any,
    *,
    require_app_shell: bool = False,
    context: str = "",
) -> None:
    """Fail if SPA assets/bootstrap look broken."""
    mon = get_monitor(page)
    if mon is None:
        mon = ensure_monitor(page)
    label = f"NF: libraries/assets loaded{(' — ' + context) if context else ''}"
    with _step(label):
        from partest.ui import allure_ui

        assets = mon.collect_loaded_assets()
        allure_ui.attach_json("assets_snapshot", assets)
        issues = mon.library_issues(require_app_shell=require_app_shell)
        if issues:
            allure_ui.attach_json("library_issues", issues)
            raise AssertionError(
                "Libraries/assets not healthy"
                + (f" ({context})" if context else "")
                + ":\n  - "
                + "\n  - ".join(issues)
            )
        allure_ui.attach_text(
            "libraries_check",
            (
                f"OK — scripts={assets.get('scriptCount')} "
                f"styles={assets.get('styleCount')} "
                f"readyState={assets.get('readyState')} "
                f"appShell={assets.get('hasAppShell')}"
            ),
        )


def assert_page_console_clean(page: Any, *, context: str = "") -> None:
    mon = get_monitor(page)
    if mon is None:
        return
    bad = list(mon.console_errors)
    page_errs = list(mon.page_errors)
    if not bad and not page_errs:
        return
    lines = [e.summary() for e in bad[:20]] + [
        f"[pageerror] {t}" for t in page_errs[:10]
    ]
    prefix = f"{context}: " if context else ""
    raise AssertionError(prefix + "Console/page errors:\n" + "\n".join(lines))


def assert_page_healthy(
    page: Any,
    *,
    require_app_shell: bool = False,
    context: str = "",
    check_console: bool = True,
    check_libraries: bool = True,
    allow_statuses: Optional[Sequence[int]] = None,
) -> None:
    """Network + libraries + console/pageerror (Allure steps)."""
    label = f"NF: page health{(' — ' + context) if context else ''}"
    with _step(label):
        assert_page_network_clean(
            page, context=context, allow_statuses=allow_statuses
        )
        if check_libraries:
            assert_libraries_loaded(
                page, require_app_shell=require_app_shell, context=context
            )
        mon = get_monitor(page)
        if mon is None or not check_console:
            return
        from partest.ui import allure_ui

        extra = []
        for c in mon.console_errors:
            extra.append(f"Console: {c.summary()}")
        for pe in mon.page_errors:
            extra.append(f"PageError: {pe}")
        if extra:
            allure_ui.attach_json("runtime_errors", extra)
            raise AssertionError(
                "Runtime errors on page"
                + (f" ({context})" if context else "")
                + ":\n  - "
                + "\n  - ".join(extra)
            )
        allure_ui.attach_text("runtime_check", "OK — no console/page errors")
