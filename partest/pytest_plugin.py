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
