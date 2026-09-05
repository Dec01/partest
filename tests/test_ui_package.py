"""1.4 UI package unit tests (no browser required for most)."""

from __future__ import annotations

from pathlib import Path

import pytest

from partest.ui.page_monitor import (
    PageMonitor,
    is_library_console_message,
    should_ignore_url,
)
from partest.ui.visual import FREEZE_CSS, compare_images


def test_should_ignore_url_public():
    assert should_ignore_url("https://www.google-analytics.com/collect")
    assert should_ignore_url("https://x/favicon.ico")
    assert not should_ignore_url("https://api.example.com/v1/items")


def test_is_library_console_message_public():
    assert is_library_console_message("Loading chunk 5 failed")
    assert is_library_console_message("ChunkLoadError: Loading CSS chunk")
    assert not is_library_console_message("hello world")


def test_page_monitor_ignores_tracker():
    mon = PageMonitor()

    class Req:
        method = "GET"
        resource_type = "xhr"

    class Resp:
        status = 404
        url = "https://www.google-analytics.com/collect"
        request = Req()

    mon.on_response = mon._handlers.get("response")  # may be empty before start
    # call classification path directly
    mon.network_issues.clear()
    # simulate via public filter: ignore url should skip
    assert mon._ignore_url(Resp.url)


def test_page_monitor_records_api_5xx_not_4xx():
    """Critical filter: API 5xx yes, API 4xx no."""
    mon = PageMonitor(api_hosts=("api.example.com",))

    class Req:
        method = "GET"
        resource_type = "fetch"

    class Resp4:
        status = 404
        url = "https://api.example.com/v1/items"
        request = Req()

    class Resp5:
        status = 500
        url = "https://api.example.com/v1/items"
        request = Req()

    # use internal handlers without page
    mon.page = type("P", (), {"on": lambda *a, **k: None, "url": ""})()
    mon.start()
    mon._handlers["response"](Resp4())
    assert mon.network_issues == []
    mon._handlers["response"](Resp5())
    assert len(mon.network_issues) == 1
    assert mon.network_issues[0].status == 500
    assert mon.network_errors is mon.network_issues


def test_page_monitor_asset_4xx():
    mon = PageMonitor()
    mon.page = type("P", (), {"on": lambda *a, **k: None, "url": ""})()
    mon.start()

    class Req:
        method = "GET"
        resource_type = "script"

    class Resp:
        status = 404
        url = "https://cdn.example.com/app.js"
        request = Req()

    mon._handlers["response"](Resp())
    assert len(mon.network_issues) == 1


def test_compare_images_identical(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    p1 = tmp_path / "a.png"
    p2 = tmp_path / "b.png"
    img = Image.new("RGB", (10, 10), color=(20, 30, 40))
    img.save(p1)
    img.save(p2)
    r = compare_images(p1, p2)
    assert r.equal
    assert r.ok is True
    assert r.diff_ratio == 0.0


def test_compare_images_different(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    p1 = tmp_path / "a.png"
    p2 = tmp_path / "b.png"
    Image.new("RGB", (10, 10), color=(0, 0, 0)).save(p1)
    Image.new("RGB", (10, 10), color=(255, 255, 255)).save(p2)
    r = compare_images(
        p1, p2, max_diff_ratio=0.01, name="scene", diff_output=tmp_path / "d.png"
    )
    assert not r.equal
    assert r.ok is False
    assert r.diff_ratio > 0.5
    assert r.name == "scene"
    assert r.different_pixels > 0
    assert r.total_pixels == 100
    assert r.diff_path == tmp_path / "d.png"
    assert "DIFF" in r.summary()


def test_freeze_css_present():
    assert "animation" in FREEZE_CSS
    assert "scrollbar-width" in FREEZE_CSS
    assert "planning-task-row" not in FREEZE_CSS
    assert "q-loading" not in FREEZE_CSS


def test_inject_freeze_styles_sync_fallback():
    from partest.ui.visual import inject_freeze_styles_sync

    calls = []

    class Page:
        def add_style_tag(self, content=""):
            raise RuntimeError("no add_style_tag")

        def evaluate(self, js, payload=None):
            calls.append(payload)

    inject_freeze_styles_sync(Page())
    assert calls and calls[0]["id"] == "partest-visual-freeze"


def test_resolve_frontend_url(monkeypatch):
    from partest.ui.hooks import resolve_frontend_url, resolve_api_base_url

    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    assert resolve_frontend_url(default="http://x/") == "http://x"
    monkeypatch.setenv("FRONTEND_URL", "http://spa.test/")
    assert resolve_frontend_url() == "http://spa.test"
    monkeypatch.setenv("BASE_URL", "http://api.test/")
    assert resolve_api_base_url() == "http://api.test"


def test_finalize_page_monitor_idempotent():
    from partest.ui.hooks import finalize_page_monitor
    from partest.ui.page_monitor import PageMonitor

    mon = PageMonitor()
    mon.page = type("P", (), {"url": "about:blank", "screenshot": lambda **k: b""})()
    page = type("P", (), {"url": "about:blank"})()
    page._partest_monitor = mon
    finalize_page_monitor(page, test_failed=True)
    finalize_page_monitor(page, test_failed=True)
    assert mon._partest_finalized is True


def test_ui_package_exports():
    import partest.ui as ui

    assert ui.BasePage
    assert ui.AsyncBasePage
    assert ui.PageMonitor
    assert ui.PageMonitor.attach
    assert ui.should_ignore_url
    assert ui.is_library_console_message
    assert ui.Storage
    assert ui.compare_images
    assert ui.load_scenes
    import importlib

    cb = importlib.import_module("partest.ui.capture_baselines")
    assert callable(cb.capture_baselines)


def test_base_page_is_sync():
    import inspect
    from partest.ui import BasePage

    assert not inspect.iscoroutinefunction(BasePage.goto)
    assert not inspect.iscoroutinefunction(BasePage.expect_visible)


def test_shipped_docs():
    """The wheel carries user documentation and nothing internal."""
    from partest.docs import list_docs, read_doc

    names = list_docs()
    for expected in ("howto-quickstart.md", "howto-migration.md", "howto-ui.md",
                     "concepts-methodology.md", "components-overview.md"):
        assert expected in names, f"{expected} missing from the wheel"

    assert "partest" in read_doc("howto-ui.md").lower()
    assert "PyPI" in read_doc("howto-migration.md")

    # Internal pages must never ship: status, roadmaps, ADRs, consumer trackers.
    for internal in ("status.md", "howto-release.md", "howto-contribute.md"):
        assert internal not in names, f"{internal} must not ship in the wheel"
    import re

    for name in names:
        text = read_doc(name)
        # Structural check rather than a name list: this repository is public, so a
        # literal organisation name here would publish what it exists to catch.
        assert not re.search(r"[A-Za-z]:\\", text), f"{name} leaks a Windows path"
        assert "/home/" not in text and "/Users/" not in text, f"{name} leaks a home directory"
