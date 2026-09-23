"""L3.6 / LIB-11: importing partest.ui must not load project conf / OpenAPI."""

from __future__ import annotations

import builtins
import sys
from pathlib import Path


def test_import_ui_does_not_need_confpartest(monkeypatch):
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "confpartest" or name.startswith("confpartest."):
            raise ImportError("confpartest must not be imported by partest.ui")
        return real_import(name, *args, **kwargs)

    for key in list(sys.modules):
        if key == "partest.ui" or key.startswith("partest.ui."):
            del sys.modules[key]

    monkeypatch.setattr(builtins, "__import__", guarded)
    import partest.ui as ui

    assert ui.BasePage
    assert ui.PageMonitor
    assert ui.attach_monitor
    assert ui.should_ignore_url


def test_import_ui_source_has_no_conf_or_swagger():
    import partest.ui as ui_pkg

    root = Path(ui_pkg.__file__).resolve().parent
    for py in root.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        # allow word only in comments if needed — require no import usage
        assert "import confpartest" not in text
        assert "swagger_files" not in text


def test_calling_the_ui_branch_does_not_reach_confpartest(monkeypatch):
    """Source-grepping is not enough: the reach can be one module away.

    This guard exists because the check above passed while isolation was broken.
    `capture_baselines` asked `partest.tls` for the TLS default, and that helper reads
    project configuration — so a UI job loaded it through a module whose name says nothing
    about it, and the grep above found no `import confpartest` to object to. The rule is
    about what a UI run *loads*, so this has to call, not read.

    It asserts on `sys.modules` rather than on a spy over ``builtins.__import__``: the
    loader goes through ``importlib.import_module``, which never touches the builtin. A
    spy there reports "clean" no matter what — the first version of this test did exactly
    that and passed against code that was provably broken.
    """
    from partest.ui.capture_baselines import ignore_https_errors

    monkeypatch.delitem(sys.modules, "confpartest", raising=False)

    for value in (None, True, False):
        ignore_https_errors(value)

    assert "confpartest" not in sys.modules, (
        "partest.ui loaded project configuration — red line 8"
    )


def test_importing_ui_does_not_load_confpartest_by_any_mechanism(monkeypatch):
    """The same blind spot as above, for the import of the package itself.

    `test_import_ui_does_not_need_confpartest` guards the import with a spy over
    ``builtins.__import__``; an `importlib.import_module` call walks past it untouched.
    """
    for key in list(sys.modules):
        if key == "partest.ui" or key.startswith("partest.ui."):
            monkeypatch.delitem(sys.modules, key, raising=False)
    monkeypatch.delitem(sys.modules, "confpartest", raising=False)

    import partest.ui  # noqa: F401

    assert "confpartest" not in sys.modules


def test_page_monitor_configurable_ignore():
    from partest.ui.page_monitor import PageMonitor

    mon = PageMonitor()
    mon.page = type("P", (), {"on": lambda *a, **k: None, "url": ""})()
    mon.start()
    mon.add_ignore_urls("my-cdn.example")

    class Req:
        method = "GET"
        resource_type = "script"

    class Resp:
        status = 500
        url = "https://my-cdn.example/app.js"
        request = Req()

    mon._handlers["response"](Resp())
    assert mon.network_issues == []

    class Resp2:
        status = 500
        url = "https://api.example.com/v1/x"
        request = type("R", (), {"method": "GET", "resource_type": "fetch"})()

    mon.api_hosts = ("api.example.com",)
    mon._handlers["response"](Resp2())
    assert len(mon.network_issues) == 1
    mon.reset()
    assert mon.network_issues == []


def test_page_monitor_console_library_warning():
    from partest.ui.page_monitor import PageMonitor

    mon = PageMonitor()
    mon.page = type("P", (), {"on": lambda *a, **k: None, "url": ""})()
    mon.start()

    class Msg:
        type = "warning"
        text = "Loading chunk 5 failed"
        location = {}

    mon._handlers["console"](Msg())
    assert len(mon.console_errors) == 1


def test_page_monitor_attach_class_api():
    from partest.ui.page_monitor import PageMonitor, get_monitor

    events = []

    class FakePage:
        url = "http://127.0.0.1:3000/"

        def on(self, event, handler):
            events.append(event)

    page = FakePage()
    mon = PageMonitor.attach(page, spa_base_url="http://127.0.0.1:3000")
    assert get_monitor(page) is mon
    assert mon.spa_origin
    assert "response" in events
