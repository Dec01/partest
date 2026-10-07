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
        ("not slow_db and not flaky", ["slow"], False),  # the workaround: no pull-in
        ("not slow_db and not flaky", ["slow", "slow_web"], False),
        ("not flaky", ["slow"], False),
        ("not slow", ["slow"], False),
        ("", ["slow"], False),
        (None, ["slow"], False),
    ],
)
def test_selected_only_through_a_positive_dependence(expr, item_marks, expected):
    assert selected_through(expr, marks(*item_marks), SLOW) is expected


def test_an_or_with_another_marker_does_not_count_as_asking_for_the_set():
    """``-m "slow or api"`` on a test marked both: still true without ``slow``.

    The api half alone selects it; the set was not what selected it. Running it would
    mean a filter written for api tests drags the slow set along.
    """
    assert selected_through("slow or api", marks("slow", "api"), SLOW) is False
    assert selected_through("slow or api", marks("slow"), SLOW) is True


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
    OptInPlugin(sets).pytest_collection_modifyitems(config, items)
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


def _session(tmp_path, *args, optin="optin_markers = slow:RUN_SLOW", env=None, quiet=True):
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


def test_session_workaround_expression_does_not_pull_the_set_in(tmp_path):
    _, selected, out = _session(tmp_path, "-m", "not slow_db and not flaky_net")
    assert selected == ["test_plain"], out


def test_session_variable_selects_the_set(tmp_path):
    _, selected, out = _session(tmp_path, env={"RUN_SLOW": "1"}, quiet=False)
    assert selected == ["test_flaky", "test_plain", "test_slow", "test_slow_db"], out
    assert "partest opt-in markers: slow (or RUN_SLOW=1)" in out


def test_session_empty_ini_changes_nothing_and_says_nothing(tmp_path):
    _, selected, out = _session(tmp_path, optin="", quiet=False)
    assert selected == ["test_flaky", "test_plain", "test_slow", "test_slow_db"], out
    assert "opt-in" not in out


def test_session_malformed_ini_is_a_usage_error(tmp_path):
    code, _, out = _session(tmp_path, optin="optin_markers = slow:1BAD")
    assert code == 4, out  # pytest's exit code for a usage error
    assert "optin_markers" in out
