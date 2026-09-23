"""pytest plugin helpers, and which switch governs what.

The plugin does two unrelated jobs: it enriches Allure, and it records how the run was
selected. They used to share one flag, so every project that disabled the plugin to keep
its own Allure hooks also lost `meta.selection` — silently, and visibly only a month
later when a filtered run was compared against a full one.
"""

from __future__ import annotations

import sys
import types

import pytest

from partest import pytest_plugin as pp
from partest.pytest_plugin import (
    _format_param_value,
    _humanize_test_name,
    plugin_enabled,
    run_metadata_enabled,
)


def test_humanize():
    assert _humanize_test_name("test_get_client_by_id") == "Get client by id"


def test_format_param():
    assert _format_param_value("admin") == "admin"
    assert _format_param_value(lambda: 1) == "<callable>"


# --- fakes ----------------------------------------------------------------


def _config(markexpr: str = "", keyword: str = ""):
    return types.SimpleNamespace(
        option=types.SimpleNamespace(markexpr=markexpr, keyword=keyword)
    )


def _items(config, count: int, prefix: str = "tests/test_s.py::t"):
    return [
        types.SimpleNamespace(nodeid=f"{prefix}{i}", config=config) for i in range(count)
    ]


@pytest.fixture
def selection():
    """Isolate both halves of the selection state: run_info and the node id set."""
    from partest.call_storage import run_info

    saved = dict(run_info.get("selection") or {})
    run_info["selection"] = {}
    pp._reset_selection_state()
    yield run_info
    run_info["selection"] = saved
    pp._reset_selection_state()


@pytest.fixture
def no_confpartest(monkeypatch):
    """The suite of this repository has no confpartest; make that explicit and stable."""
    monkeypatch.delitem(sys.modules, "confpartest", raising=False)
    monkeypatch.setattr(pp, "_conf_flag", lambda name: None)


# --- the two switches -----------------------------------------------------


def test_the_switches_default_to_on(monkeypatch, no_confpartest):
    monkeypatch.delenv("PARTEST_PYTEST_PLUGIN", raising=False)
    monkeypatch.delenv("PARTEST_RUN_METADATA", raising=False)

    assert plugin_enabled() is True
    assert run_metadata_enabled() is True


def test_run_metadata_switch_reads_env_and_confpartest(monkeypatch):
    conf = types.ModuleType("confpartest")
    conf.run_metadata = False  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "confpartest", conf)
    monkeypatch.delenv("PARTEST_RUN_METADATA", raising=False)

    assert run_metadata_enabled() is False, "confpartest must be able to turn it off"

    monkeypatch.setenv("PARTEST_RUN_METADATA", "1")
    assert run_metadata_enabled() is True, "the environment wins over confpartest"

    monkeypatch.setenv("PARTEST_RUN_METADATA", "0")
    assert run_metadata_enabled() is False


def test_the_allure_switch_still_reads_confpartest(monkeypatch):
    """`plugin_enabled` keeps its meaning and its inputs — only its scope shrank."""
    conf = types.ModuleType("confpartest")
    conf.pytest_plugin = "no"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "confpartest", conf)
    monkeypatch.delenv("PARTEST_PYTEST_PLUGIN", raising=False)

    assert plugin_enabled() is False

    monkeypatch.setenv("PARTEST_PYTEST_PLUGIN", "on")
    assert plugin_enabled() is True


# --- the selection is recorded regardless of the Allure switch ------------


def test_selection_is_recorded_while_the_allure_hooks_are_off(
    monkeypatch, no_confpartest, selection
):
    """The reported defect: `pytest_plugin = False` used to erase `meta.selection`."""
    monkeypatch.setenv("PARTEST_PYTEST_PLUGIN", "0")
    monkeypatch.delenv("PARTEST_RUN_METADATA", raising=False)
    assert plugin_enabled() is False

    config = _config(markexpr="not rbac")
    items = _items(config, 3)
    pp.pytest_collection_modifyitems(config, items)
    pp.pytest_deselected(items)

    assert selection["selection"] == {"markexpr": "not rbac", "deselected": 3}


def test_run_metadata_off_records_nothing(monkeypatch, no_confpartest, selection):
    monkeypatch.setenv("PARTEST_RUN_METADATA", "0")

    config = _config(markexpr="not rbac", keyword="health")
    items = _items(config, 3)
    pp.pytest_collection_modifyitems(config, items)
    pp.pytest_deselected(items)

    assert selection["selection"] == {}


def test_the_same_items_reported_twice_are_counted_once(
    monkeypatch, no_confpartest, selection
):
    """The same tests can reach the hook more than once; the figure must not double.

    This is what merging a parallel run looks like from the recorder's side: every worker
    deselects the *same* tests, so their reports overlap completely. A running total would
    say 6 removed out of 3, and a wrong number is worse than the missing one we set out
    to fix.

    It is **not** about a plugin registered twice — the earlier name and docstring claimed
    that, and it cannot happen: pytest refuses to start when the entry point and a root
    `conftest` both register this module (`ValueError: Plugin already registered under a
    different name`). Verified before renaming.
    """
    monkeypatch.delenv("PARTEST_RUN_METADATA", raising=False)
    config = _config(markexpr="not rbac")
    items = _items(config, 3)

    for _ in range(2):
        pp.pytest_collection_modifyitems(config, items)
        pp.pytest_deselected(items)

    assert selection["selection"] == {"markexpr": "not rbac", "deselected": 3}


def test_separate_deselection_rounds_still_add_up(monkeypatch, no_confpartest, selection):
    """Idempotence is per node id, not per call: distinct rounds must accumulate."""
    monkeypatch.delenv("PARTEST_RUN_METADATA", raising=False)
    config = _config(keyword="health")

    pp.pytest_deselected(_items(config, 2, prefix="tests/test_a.py::t"))
    pp.pytest_deselected(_items(config, 3, prefix="tests/test_b.py::t"))

    assert selection["selection"]["deselected"] == 5


# --- the Allure hooks stay behind their own flag --------------------------


def _collected_item(monkeypatch, *, enabled: bool):
    monkeypatch.setenv("PARTEST_PYTEST_PLUGIN", "1" if enabled else "0")

    def sample():
        """A readable title."""

    item = types.SimpleNamespace(
        function=sample, obj=sample, name="test_sample", originalname="test_sample"
    )
    pp.pytest_itemcollected(item)
    return sample


def test_allure_display_name_is_set_when_the_flag_is_on(monkeypatch, no_confpartest):
    pytest.importorskip("allure")
    func = _collected_item(monkeypatch, enabled=True)

    assert func.__allure_display_name__ == "A readable title."


def test_allure_display_name_is_not_set_when_the_flag_is_off(monkeypatch, no_confpartest):
    func = _collected_item(monkeypatch, enabled=False)

    assert not hasattr(func, "__allure_display_name__")


class _ExplodingCall:
    """Any attribute read means the hook did not return where it should have."""

    when = "call"

    def __getattr__(self, name):
        raise AssertionError(f"the disabled hook looked at {name!r}")


def test_the_failure_summary_hook_is_silent_when_the_flag_is_off(
    monkeypatch, no_confpartest
):
    monkeypatch.setenv("PARTEST_PYTEST_PLUGIN", "0")

    assert pp.pytest_runtest_makereport(types.SimpleNamespace(), _ExplodingCall()) is None
