"""Optional pytest plugin: Allure title/description enrichment.

**Auto-loaded** via setuptools ``pytest11`` entry point ``partest``.

Disable when the consumer already has Allure hooks (avoids double attach)::

    # env
    PARTEST_PYTEST_PLUGIN=0

    # or confpartest.py
    pytest_plugin = False

    # or CLI
    pytest -p no:partest

Enable explicitly after disable::

    PARTEST_PYTEST_PLUGIN=1
    # or confpartest: pytest_plugin = True
    # or pytest_plugins = ["partest.pytest_plugin"]
"""

from __future__ import annotations

import os
from typing import Any, List, Optional


def _env_flag(name: str) -> Optional[bool]:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return None
    if raw in {"0", "false", "off", "no", "disable", "disabled"}:
        return False
    if raw in {"1", "true", "on", "yes", "enable", "enabled"}:
        return True
    return None


def plugin_enabled() -> bool:
    """Whether hooks should run (env wins over confpartest)."""
    env = _env_flag("PARTEST_PYTEST_PLUGIN")
    if env is not None:
        return env
    try:
        import confpartest  # type: ignore

        flag = getattr(confpartest, "pytest_plugin", None)
        if flag is None:
            pass
        elif isinstance(flag, str):
            low = flag.strip().lower()
            if low in {"0", "false", "off", "no"}:
                return False
            if low in {"1", "true", "on", "yes"}:
                return True
        else:
            return bool(flag)
    except ImportError:
        pass
    # Default ON so greenfield gets titles; consumers with dual hooks opt out.
    return True


def _humanize_test_name(name: str) -> str:
    if name.startswith("test_"):
        name = name[5:]
    return name.replace("_", " ").strip().capitalize()


def _format_param_value(value: Any) -> str:
    if callable(value):
        return "<callable>"
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = str(value)
    else:
        text = repr(value)
    if len(text) > 48:
        return text[:45] + "..."
    return text


def _base_title_from_item(item) -> str:
    func = getattr(item, "function", None)
    if func and func.__doc__:
        first = func.__doc__.strip().splitlines()[0].strip()
        if first:
            return first
    raw = getattr(item, "originalname", None) or item.name.split("[")[0]
    return _humanize_test_name(raw)


def _title_with_params(item) -> str:
    base = _base_title_from_item(item)
    callspec = getattr(item, "callspec", None)
    if not callspec or not callspec.params:
        return base
    priority = (
        "role",
        "code",
        "name",
        "kind",
        "field",
        "resource",
        "method",
        "matrix",
        "collection",
    )
    keys: List[str] = [
        k for k in priority if k in callspec.params and not callable(callspec.params[k])
    ]
    keys += [
        k for k, v in callspec.params.items() if k not in keys and not callable(v)
    ]
    if not keys:
        return base
    extras = ", ".join(
        f"{k}={_format_param_value(callspec.params[k])}" for k in keys[:4]
    )
    return f"{base} · {extras}"


def pytest_itemcollected(item) -> None:
    """Set Allure display name from docstring + key params."""
    if not plugin_enabled():
        return
    try:
        import allure  # noqa: F401
    except ImportError:
        return
    title = _title_with_params(item)
    for obj in (getattr(item, "obj", None), getattr(item, "function", None)):
        if obj is None:
            continue
        try:
            setattr(obj, "__allure_display_name__", title)
        except Exception:
            pass


def pytest_runtest_makereport(item, call):
    """Attach short failure summary on test call failure."""
    if not plugin_enabled():
        return
    if call.when != "call" or call.excinfo is None:
        return
    # Optional: skip failure_summary when consumer attaches its own
    fail_env = _env_flag("PARTEST_ALLURE_FAILURE_SUMMARY")
    if fail_env is False:
        return
    try:
        import allure
        from allure_commons.types import AttachmentType
    except ImportError:
        return
    try:
        exc = call.excinfo.value
        text = f"{type(exc).__name__}: {exc}"
        allure.attach(
            text[:8000],
            name="failure_summary",
            attachment_type=AttachmentType.TEXT,
        )
    except Exception:
        pass


# --- What this run actually selected --------------------------------------


def _record_selection(config, deselected: int = 0) -> None:
    """Note that the run covered a subset, so the report can say so.

    Coverage is scored per test case, but "never called" is a property of an endpoint.
    A marker filter removes cases: the endpoint is still hit, it just loses one cell —
    so the unseen ratio stays near zero and nothing in the numbers reveals that half the
    suite did not run. Comparing such a run against a full one then presents every
    dropped cell as a regression. The selection expression is the one exact signal, and
    it is only available here.
    """
    try:
        from partest.call_storage import run_info
    except Exception:
        return
    option = getattr(config, "option", None)
    if option is None:
        return
    selection = run_info.setdefault("selection", {})
    for name, key in (("markexpr", "markexpr"), ("keyword", "keyword")):
        value = (getattr(option, name, None) or "").strip()
        if value:
            selection[key] = value
    if deselected:
        selection["deselected"] = int(selection.get("deselected", 0)) + int(deselected)


def pytest_collection_modifyitems(config, items) -> None:
    if not plugin_enabled():
        return
    _record_selection(config)


def pytest_deselected(items) -> None:
    """``-m`` and ``-k`` come through here; ``--deselect`` and plugins do too."""
    if not plugin_enabled() or not items:
        return
    config = getattr(items[0], "config", None)
    if config is not None:
        _record_selection(config, deselected=len(items))


# --- Coverage under pytest-xdist ------------------------------------------


def _xdist_merge_enabled() -> bool:
    """Merging is on by default; opt out with ``PARTEST_XDIST_MERGE=0``."""
    env = _env_flag("PARTEST_XDIST_MERGE")
    return True if env is None else env


def _is_xdist_worker(config) -> bool:
    return hasattr(config, "workerinput")


def pytest_sessionstart(session) -> None:
    """Drop shards from a previous run so stale workers cannot inflate this one."""
    if not _xdist_merge_enabled() or _is_xdist_worker(session.config):
        return
    try:
        from partest.call_storage import clear_shards

        clear_shards()
    except Exception:
        pass


def pytest_sessionfinish(session, exitstatus) -> None:
    """Workers write their counters; the controller merges them.

    Without this, ``pytest -n`` reports whichever worker happened to run the report
    test, and every endpoint exercised elsewhere reads as never called.
    """
    if not _xdist_merge_enabled():
        return
    try:
        from partest.call_storage import merge_shards, run_info, write_shard
    except Exception:
        return

    if _is_xdist_worker(session.config):
        try:
            write_shard()
        except OSError:
            pass
        return

    # Controller (or a plain serial run: then there are no shards and nothing changes).
    try:
        merge_shards()
    except Exception:
        return

    if run_info.get("workers", 1) > 1 and not run_info.get("merged"):
        if _env_flag("PARTEST_COVERAGE_REQUIRE_MERGE"):
            raise session.Failed(
                "partest: coverage was collected under xdist without a merge; "
                "the numbers are one worker's slice, not the suite"
            )

    _write_controller_report()


def _write_controller_report() -> None:
    """Optionally render the coverage report here, where the merged data lives.

    A report produced by a test cannot see the merge: that test runs on one worker,
    and merging happens on the controller after every worker has finished. Set
    ``PARTEST_COVERAGE_JSON`` (and optionally ``PARTEST_COVERAGE_HTML``) to have the
    artifact written from the controller instead.
    """
    json_path = (os.getenv("PARTEST_COVERAGE_JSON") or "").strip()
    html_path = (os.getenv("PARTEST_COVERAGE_HTML") or "").strip()
    if not json_path and not html_path:
        return
    try:
        from partest.reports import zorro_enhanced

        zorro_enhanced(
            html_path=html_path or "coverage_report.html",
            json_path=json_path or "coverage.json",
            attach_allure=False,
        )
    except Exception as exc:  # a broken report must not fail a green suite
        print(f"partest: could not write the coverage report: {exc}")
