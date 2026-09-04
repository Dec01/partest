"""Allure attaches for UI failures."""

from __future__ import annotations

from typing import Optional

try:
    import allure
    from allure_commons.types import AttachmentType
except ImportError:  # pragma: no cover
    allure = None  # type: ignore
    AttachmentType = None  # type: ignore


def attach_screenshot(page, name: str = "screenshot", *, full_page: bool = True) -> None:
    if allure is None:
        return
    try:
        png = page.screenshot(full_page=full_page)
        # sync or already bytes
        if hasattr(png, "__await__"):
            return  # async page — caller should await screenshot separately
        allure.attach(png, name=name, attachment_type=AttachmentType.PNG)
    except Exception:
        pass


def attach_url(page, name: str = "url") -> None:
    if allure is None:
        return
    try:
        allure.attach(str(page.url), name=name, attachment_type=AttachmentType.TEXT)
    except Exception:
        pass


def attach_text(name: str, text: str) -> None:
    if allure is None:
        return
    allure.attach(str(text), name=name, attachment_type=AttachmentType.TEXT)


def attach_json(name: str, data) -> None:
    if allure is None:
        return
    import json

    allure.attach(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        name=name,
        attachment_type=AttachmentType.JSON,
    )


def attach_failure_context(page, label: str = "ui_failure") -> None:
    attach_url(page, name=f"{label}_url")
    attach_screenshot(page, name=f"{label}_screenshot")
    try:
        from partest.ui.page_monitor import get_monitor

        mon = get_monitor(page)
        if mon and allure:
            if mon.network_errors:
                attach_text(
                    f"{label}_network",
                    "\n".join(e.summary() for e in mon.network_errors[:30]),
                )
            if mon.console_errors:
                attach_text(
                    f"{label}_console",
                    "\n".join(e.summary() for e in mon.console_errors[:20]),
                )
            if getattr(mon, "page_errors", None):
                attach_text(
                    f"{label}_pageerror",
                    "\n".join(str(t) for t in mon.page_errors[:20]),
                )
    except Exception:
        pass
