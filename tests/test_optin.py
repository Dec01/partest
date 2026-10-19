"""Opt-in marker sets: deselected until asked for by -m or by an environment variable.

The rule is an evaluation, not a word search: a test in the set stays only when ``-m`` is
true on its markers and false on the same markers without the set. The workaround cases —
``-m "not slow_db and not flaky"`` — are the reason it is written that way, so they are
here twice: against the function, and through a real pytest session.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from partest.optin import (
    OptInPlugin,
    OptInSet,
    is_selected,
    parse_optin_markers,
    selected_through,
    would_select,
)

SLOW = OptInSet("slow", "RUN_SLOW")


class Mark:
    def __init__(self, name, **kwargs):
        self.name = name
        self.kwargs = kwargs


def marks(*names):
    return [Mark(n) for n in names]


# --- parsing --------------------------------------------------------------------


def test_entries_parse_with_and_without_a_variable():
    assert parse_optin_markers(["slow:RUN_SLOW", "nightly", "", "  "]) == (
        OptInSet("slow", "RUN_SLOW"),
        OptInSet("nightly", None),
    )


@pytest.mark.parametrize(
    "entry", ["slow:", "slow:1BAD", "not-a-name", "slow:RUN SLOW", ":RUN_SLOW"]
)
def test_malformed_entries_are_refused(entry):
    with pytest.raises(ValueError):
        parse_optin_markers([entry])


def test_a_marker_listed_twice_is_refused():
    with pytest.raises(ValueError, match="twice"):
        parse_optin_markers(["slow", "slow:RUN_SLOW"])


def test_sub_markers_are_taken_by_prefix_with_an_underscore():
    assert SLOW.covers("slow")
    assert SLOW.covers("slow_db")
    assert not SLOW.covers("slowish")
    assert not SLOW.covers("very_slow")


# --- the rule -------------------------------------------------------------------


@pytest.mark.parametrize(
    "expr, item_marks, expected",
    [
        ("slow", ["slow"], True),
        ("slow", ["slow", "slow_db"], True),
        ("slow_db", ["slow", "slow_db"], True),
        ("slow and not flaky", ["slow"], True),
        ("api", ["slow", "api"], False),  # selected by another marker, not by the set
        ("smoke", ["smoke", "slow"], False),  # about something else: the set stays out
        ("slow or api", ["slow", "api"], True),  # names the family; api does not cancel it
        ("slow or api", ["slow"], True),
        ("slow_db or api", ["slow", "api"], False),  # names a sub-marker this test lacks
        ("not slow_db and not flaky", ["slow"], False),  # the workaround: no pull-in
        ("not slow_db and not flaky", ["slow", "slow_web"], False),
        ("not flaky", ["slow"], False),
        ("not slow", ["slow"], False),
        ("", ["slow"], False),
        (None, ["slow"], False),
    ],
)
def test_selected_only_when_m_asks_for_the_family(expr, item_marks, expected):
    assert selected_through(expr, marks(*item_marks), SLOW) is expected


def test_an_expression_the_family_never_turns_true_does_not_ask_for_it():
    """No context in which adding the family flips false to true: not a request."""
    for expr in ("not slow_db and not flaky", "not flaky", "not slow_db"):
        assert selected_through(expr, marks("slow"), SLOW) is False, expr


@pytest.mark.parametrize("item", [["slow"], ["slow", "flaky"]], ids=["slow", "slow+flaky"])
@pytest.mark.parametrize("expr", ["slow or not flaky", "slow or not api", "not api or slow"])
def test_an_or_with_a_negation_still_asks_for_the_family(expr, item):
    """``slow or not flaky``: in the context {flaky} the family flips it — a request,
    for a test marked flaky and for one that is not."""
    assert selected_through(expr, marks(*item), SLOW) is True


def test_the_fallback_beyond_the_context_limit_is_the_two_context_rule(monkeypatch):
    from partest import optin

    monkeypatch.setattr(optin, "MAX_CONTEXT_NAMES", 0)
    # Two-context rule: "slow or not flaky" is true without the family and with no
    # markers at all, so the fallback does not take it — the documented, safer miss.
    assert selected_through("slow or not flaky", marks("slow"), SLOW) is False
    assert selected_through("slow or api", marks("slow", "api"), SLOW) is True
    assert selected_through("not slow_db and not flaky", marks("slow"), SLOW) is False


def test_two_sets_named_with_or_are_both_asked_for():
    nightly = OptInSet("nightly")
    both = marks("nightly", "slow")
    assert selected_through("nightly or slow", both, SLOW) is True
    assert selected_through("nightly or slow", both, nightly) is True
    assert selected_through("nightly", both, SLOW) is False


def test_keyword_matching_means_what_it_means_to_pytest():
    item = [Mark("slow", level=2)]
    assert selected_through("slow(level=2)", item, SLOW) is True
    assert selected_through("slow(level=3)", item, SLOW) is False


def test_the_variable_selects_the_whole_set_regardless_of_m():
    env = {"RUN_SLOW": "1"}
    assert is_selected(SLOW, "", marks("slow"), env)
    assert is_selected(SLOW, "not slow", marks("slow"), env)
    assert not is_selected(SLOW, "", marks("slow"), {"RUN_SLOW": "0"})
    assert not is_selected(SLOW, "", marks("slow"), {"RUN_SLOW": "maybe"})
    assert not is_selected(OptInSet("nightly"), "", marks("nightly"), {"RUN_SLOW": "1"})


# --- the hook, with stand-in items ----------------------------------------------


@pytest.fixture(autouse=True)
def _keep_run_selection():
    """The hook records into this process's run metadata; give it back afterwards."""
    from partest import call_storage

    saved = dict(call_storage.run_info.get("selection") or {})
    nodes = set(call_storage.deselected_nodes)
    yield
    call_storage.run_info["selection"] = saved
    call_storage.deselected_nodes.clear()
    call_storage.deselected_nodes.update(nodes)


class _Hook:
    def __init__(self):
        self.deselected = []

    def pytest_deselected(self, items):
        self.deselected.extend(items)


class _Option:
    def __init__(self, markexpr):
        self.markexpr = markexpr


class _Config:
    def __init__(self, markexpr=""):
        self.option = _Option(markexpr)
        self.hook = _Hook()


class _Item:
    def __init__(self, name, *mark_names):
        self.nodeid = name
        self._marks = marks(*mark_names)

    def iter_markers(self):
        return iter(self._marks)


def run_hook(sets, markexpr, items, monkeypatch, env=None):
    for name in ("RUN_SLOW", "RUN_NIGHTLY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    config = _Config(markexpr)
    items = list(items)
    plugin = OptInPlugin(sets)
    plugin.pytest_collection_modifyitems(config, items)
    run_hook.plugin = plugin
    return [i.nodeid for i in items], [i.nodeid for i in config.hook.deselected]


ITEMS = [
    _Item("plain"),
    _Item("slow", "slow"),
    _Item("slow_db", "slow", "slow_db"),
    _Item("nightly", "nightly"),
    _Item("both", "slow", "nightly"),
]
SETS = (OptInSet("slow", "RUN_SLOW"), OptInSet("nightly", "RUN_NIGHTLY"))


def test_a_plain_run_deselects_every_set(monkeypatch):
    kept, gone = run_hook(SETS, "", ITEMS, monkeypatch)
    assert kept == ["plain"]
    assert gone == ["slow", "slow_db", "nightly", "both"]


def test_a_test_in_two_sets_must_be_opted_into_both(monkeypatch):
    """Only set members are this hook's business; ``plain`` is left to pytest's ``-m``."""
    kept, _ = run_hook(SETS, "slow", ITEMS, monkeypatch)
    assert kept == ["plain", "slow", "slow_db"]
    kept, _ = run_hook(SETS, "slow and nightly", ITEMS, monkeypatch)
    assert kept == ["plain", "both"]
    kept, _ = run_hook(SETS, "slow", ITEMS, monkeypatch, env={"RUN_NIGHTLY": "1"})
    assert kept == ["plain", "slow", "slow_db", "nightly", "both"]


def test_each_set_records_how_it_was_decided(monkeypatch):
    from partest.call_storage import run_info

    run_hook(SETS, "slow", ITEMS, monkeypatch, env={"RUN_NIGHTLY": "1"})
    assert run_info["selection"]["optin"] == {
        "slow": {"state": "markexpr", "env": "RUN_SLOW", "deselected": 0},
        "nightly": {"state": "env", "env": "RUN_NIGHTLY", "deselected": 0},
    }
    run_hook(SETS, "", ITEMS, monkeypatch)
    assert run_info["selection"]["optin"] == {
        "slow": {"state": "off", "env": "RUN_SLOW", "deselected": 3},
        "nightly": {"state": "off", "env": "RUN_NIGHTLY", "deselected": 2},
    }
    lines = run_hook.plugin.pytest_report_collectionfinish(None)
    assert "partest opt-in slow: off, 3 deselected (markers met: slow, slow_db)" in lines


def test_run_metadata_off_records_nothing(monkeypatch):
    from partest.call_storage import run_info

    monkeypatch.setenv("PARTEST_RUN_METADATA", "0")
    run_info["selection"] = {}
    run_hook(SETS, "", ITEMS, monkeypatch)
    assert "optin" not in run_info["selection"]


def test_the_header_names_what_each_prefix_captured():
    class Config:
        def getini(self, name):
            assert name == "markers"
            return ["slow: long", "slow_db: part of slow", "slowish: not ours", "nightly"]

    lines = OptInPlugin(SETS).pytest_report_header(Config())
    assert lines == [
        "partest opt-in markers: slow (or RUN_SLOW=1) covers: slow, slow_db",
        "partest opt-in markers: nightly (or RUN_NIGHTLY=1) covers: nightly",
    ]


def test_the_optin_record_crosses_an_xdist_shard():
    from partest import call_storage

    call_storage.record_optin({"slow": {"state": "off", "deselected": 2}})
    dumped = call_storage.dump_storage()
    assert dumped["selection"]["optin"] == {"slow": {"state": "off", "deselected": 2}}
    call_storage.run_info["selection"] = {}
    call_storage.load_storage({"selection": dumped["selection"]})
    assert call_storage.run_info["selection"]["optin"]["slow"]["state"] == "off"


def _payload(optin=None):
    selection = {}
    if optin is not None:
        selection["optin"] = {k: {"state": v, "deselected": 0} for k, v in optin.items()}
    return {"meta": {"selection": selection} if selection else {}, "endpoints": []}


def test_compare_calls_different_optin_states_incomparable():
    from partest.reports.compare import _run_warnings

    warnings = _run_warnings(_payload({"slow": "off"}), _payload({"slow": "env"}), [])
    assert any("different opt-in marker sets (slow: off → env)" in w for w in warnings)
    same = _run_warnings(_payload({"slow": "off"}), _payload({"slow": "off"}), [])
    assert not any("opt-in" in w for w in same)
    # An artifact without the key says nothing either way.
    older = _run_warnings(_payload(), _payload({"slow": "env"}), [])
    assert not any("opt-in" in w for w in older)


def test_optin_comparable_is_the_verdict_compare_uses():
    from partest.reports import optin_comparable
    from partest.reports.compare import _optin_warning

    off, env = _payload({"slow": "off"}), _payload({"slow": "env"})
    assert optin_comparable(off, off) == (True, [])
    assert optin_comparable(off, env) == (False, ["slow: off → env"])
    assert optin_comparable(_payload({"slow": "off"}), _payload({"slow": "off", "nightly": "env"})) == (
        False, ["nightly: absent → env"]
    )
    # a set recorded without a state is not the same as a set that is not there
    no_state = {"meta": {"selection": {"optin": {"slow": {"deselected": 0}}}}, "endpoints": []}
    none_declared = {"meta": {"selection": {"optin": {}}}, "endpoints": []}
    assert optin_comparable(no_state, none_declared) == (
        False, ["slow: recorded without a state → absent"]
    )
    assert optin_comparable(_payload(), env) == (None, [])
    assert optin_comparable(env, {"endpoints": []}) == (None, [])
    # the private warning is that verdict, worded
    assert _optin_warning(off, env) == [
        "the runs selected different opt-in marker sets (slow: off → env) — they did not run "
        "the same suite"
    ]
    assert _optin_warning(off, off) == [] and _optin_warning(_payload(), env) == []


def test_compare_notes_an_optin_record_on_one_side_only():
    from partest.reports.compare import compare_payloads

    acted = {"meta": {"selection": {"optin": {"slow": {"state": "off", "deselected": 4}}}},
             "endpoints": []}
    quiet = {"meta": {"selection": {"optin": {"slow": {"state": "off", "deselected": 0}}}},
             "endpoints": []}
    older = {"meta": {}, "endpoints": []}

    diff = compare_payloads(older, acted)
    assert diff["notes"] == [
        "previous run carries no opt-in record; current slow: deselected 4 — "
        "comparability cannot be confirmed"
    ]
    assert diff["comparable"] is True  # soft: one-sided evidence decides nothing
    env = {"meta": {"selection": {"optin": {"slow": {"state": "env", "deselected": 0}}}},
           "endpoints": []}
    assert "previous slow: enabled by env" in compare_payloads(env, older)["notes"][0]
    assert compare_payloads(older, quiet)["notes"] == []
    assert compare_payloads(acted, acted)["notes"] == []


def test_nothing_is_reported_when_nothing_is_deselected(monkeypatch):
    kept, gone = run_hook(SETS, "", [_Item("plain")], monkeypatch)
    assert kept == ["plain"] and gone == []


# --- a real session -------------------------------------------------------------

SUITE = '''
import pytest

def test_plain():
    pass

@pytest.mark.slow
def test_slow():
    pass

@pytest.mark.slow
@pytest.mark.slow_db
def test_slow_db():
    pass

@pytest.mark.flaky_net
def test_flaky():
    pass
'''

INI = """[pytest]
markers =
    slow: opt-in
    slow_db: part of slow
    flaky_net: unrelated
{optin}
"""


def _session(tmp_path, *args, optin="partest_optin_markers = slow:RUN_SLOW", env=None, quiet=True):
    (tmp_path / "test_suite.py").write_text(SUITE, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(INI.format(optin=optin), encoding="utf-8")
    environ = dict(os.environ)
    environ.pop("RUN_SLOW", None)
    environ.pop("PYTEST_ADDOPTS", None)
    environ.update(env or {})
    # The subprocess must exercise this working tree, not an installed partest.
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    environ["PYTHONPATH"] = str(repo_root) + os.pathsep + environ.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-p", "no:randomly", *args]
    if quiet:
        cmd.append("-q")
    result = subprocess.run(cmd, cwd=tmp_path, env=environ, capture_output=True, text=True)
    out = result.stdout + result.stderr
    lines = [line.strip() for line in result.stdout.splitlines()]
    selected = sorted(
        line.split("::", 1)[1] for line in lines if line.startswith("test_suite.py::")
    ) or sorted(
        line[len("<Function "):-1] for line in lines if line.startswith("<Function ")
    )
    return result.returncode, selected, out


def test_session_plain_run_keeps_the_set_out(tmp_path):
    code, selected, out = _session(tmp_path)
    assert code == 0, out
    assert selected == ["test_flaky", "test_plain"]
    assert "2 deselected" in out


def test_session_m_selects_the_set_and_its_sub_markers(tmp_path):
    _, selected, out = _session(tmp_path, "-m", "slow")
    assert selected == ["test_slow", "test_slow_db"], out
    _, selected, out = _session(tmp_path, "-m", "slow_db")
    assert selected == ["test_slow_db"], out


def test_session_or_with_another_marker_takes_the_set(tmp_path):
    _, selected, out = _session(tmp_path, "-m", "slow or flaky_net")
    assert selected == ["test_flaky", "test_slow", "test_slow_db"], out


def test_session_workaround_expression_does_not_pull_the_set_in(tmp_path):
    _, selected, out = _session(tmp_path, "-m", "not slow_db and not flaky_net")
    assert selected == ["test_plain"], out


def test_session_variable_selects_the_set(tmp_path):
    _, selected, out = _session(tmp_path, env={"RUN_SLOW": "1"}, quiet=False)
    assert selected == ["test_flaky", "test_plain", "test_slow", "test_slow_db"], out
    assert "partest opt-in markers: slow (or RUN_SLOW=1) covers: slow, slow_db" in out


def test_session_empty_ini_changes_nothing_and_says_nothing(tmp_path):
    _, selected, out = _session(tmp_path, optin="", quiet=False)
    assert selected == ["test_flaky", "test_plain", "test_slow", "test_slow_db"], out
    assert "opt-in" not in out


def test_session_malformed_ini_is_a_usage_error(tmp_path):
    code, _, out = _session(tmp_path, optin="partest_optin_markers = slow:1BAD")
    assert code == 4, out  # pytest's exit code for a usage error
    assert "partest_optin_markers" in out


SUITE_MARKS = {
    "test_plain": [],
    "test_slow": ["slow"],
    "test_slow_db": ["slow", "slow_db"],
    "test_flaky": ["flaky_net"],
}


@pytest.mark.parametrize(
    "expr, env",
    [
        ("", {}),
        ("slow", {}),
        ("slow_db", {}),
        ("slow or flaky_net", {}),
        ("not slow_db and not flaky_net", {}),
        ("", {"RUN_SLOW": "1"}),
        ("not slow", {"RUN_SLOW": "1"}),
    ],
)
def test_would_select_agrees_with_a_real_session(tmp_path, expr, env):
    """The call answers what the subprocess answers, for each test of the suite."""
    args = ("-m", expr) if expr else ()
    _, selected, out = _session(tmp_path, *args, env=env)
    predicted = sorted(
        name for name, names in SUITE_MARKS.items()
        if would_select(names, "slow:RUN_SLOW", expr, environ=env)
    )
    assert predicted == selected, out


def test_would_select_reads_the_ini_value_as_written():
    ini = """
        slow:RUN_SLOW
        nightly
    """
    assert would_select(["slow_db"], ini, "slow_db")
    assert not would_select(["slow_db"], ini, "slow")  # pytest's -m reads exact names
    assert not would_select(["slow_db"], ini, "not flaky")
    assert would_select(["slow_db"], ini, "", environ={"RUN_SLOW": "1"})
    assert not would_select(["slow_db"], ini, "", environ={})
    # a test in two sets must be opted into both
    assert not would_select(["slow", "nightly"], ini, "", environ={"RUN_SLOW": "1"})
    assert would_select(["slow", "nightly"], ini, "nightly", environ={"RUN_SLOW": "1"})
    # outside every set only pytest's own -m decides
    assert would_select(["api"], ini, "", environ={})
    assert not would_select(["api"], ini, "smoke", environ={})
    # the list config.getini() returns is accepted as well
    assert would_select(["slow"], ["slow:RUN_SLOW", "nightly"], "slow", environ={})


def _real_mark(name, **kwargs):
    """A real ``MarkDecorator`` for a marker this session does not register."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", pytest.PytestUnknownMarkWarning)
        return getattr(pytest.mark, name)(**kwargs)


def test_would_select_keeps_keyword_arguments_of_real_marks():
    slow = _real_mark("slow", level=2)
    assert would_select([slow], "slow", "slow(level=2)", environ={})
    assert not would_select([slow], "slow", "slow(level=3)", environ={})
    assert would_select([slow.mark], "slow", "slow", environ={})


def test_would_select_refuses_a_malformed_ini():
    with pytest.raises(ValueError):
        would_select(["slow"], "slow:1BAD", "slow")


def test_the_rule_is_public():
    from partest import optin

    for name in ("is_selected", "selected_through", "would_select", "OptInSet",
                 "parse_optin_markers"):
        assert name in optin.__all__


PROBE = '''
import json, os
import pytest
from partest.call_storage import run_info

@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if hasattr(session.config, "workerinput"):
        return
    with open(os.environ["OPTIN_PROBE"], "w", encoding="utf-8") as fh:
        json.dump(run_info.get("selection") or {}, fh)
'''


@pytest.mark.parametrize("parallel", [False, True], ids=["serial", "xdist"])
def test_session_runs_and_records_the_same_under_xdist(tmp_path, parallel):
    """Workers collect and deselect; the controller must still know what was decided."""
    import json
    import re

    if parallel:
        pytest.importorskip("xdist", reason="pytest-xdist not installed; see extras_require['dev']")
    (tmp_path / "test_suite.py").write_text(SUITE, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(
        INI.format(optin="partest_optin_markers = slow:RUN_SLOW"), encoding="utf-8"
    )
    (tmp_path / "conftest.py").write_text(PROBE, encoding="utf-8")
    probe = tmp_path / "probe.json"
    environ = dict(os.environ)
    for name in ("RUN_SLOW", "PYTEST_ADDOPTS", "PYTEST_XDIST_WORKER", "PYTEST_CURRENT_TEST"):
        environ.pop(name, None)
    environ["OPTIN_PROBE"] = str(probe)
    environ["PARTEST_CALL_STORAGE_DIR"] = str(tmp_path / "shards")
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    environ["PYTHONPATH"] = str(repo_root) + os.pathsep + environ.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:randomly"]
    if parallel:
        cmd += ["-n", "2"]
    result = subprocess.run(cmd, cwd=tmp_path, env=environ, capture_output=True, text=True)
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    passed = sorted(set(re.findall(r"PASSED test_suite\.py::(\w+)", out)))
    assert passed == ["test_flaky", "test_plain"], out
    selection = json.loads(probe.read_text(encoding="utf-8"))
    assert selection["optin"]["slow"] == {"state": "off", "env": "RUN_SLOW", "deselected": 2}
