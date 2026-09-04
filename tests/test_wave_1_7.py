"""Acceptance tests for the 1.7 coverage-honesty wave.

The measured failure behind all of this: a green suite run with ``-n 3`` reported
25.7% average and 58 endpoints as never called, because each worker counts only its
own calls and the report test runs on one of them.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

from partest import call_storage as cs
from partest.reports.analyzer import _kind_for
from partest.reports.history import append_snapshot, list_snapshots, prune_snapshots
from partest.reports.payload import timing_of


@pytest.fixture(autouse=True)
def clean_storage():
    cs.reset_storage()
    yield
    cs.reset_storage()


# --- LIB-XDIST: merge contract --------------------------------------------


def _shard(tmp_path, name, payload):
    directory = tmp_path / "shards"
    directory.mkdir(exist_ok=True)
    (directory / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    return directory


def test_merge_sums_calls_and_unions_types(tmp_path):
    """Acceptance from the spec: two workers, one shared endpoint and one unique."""
    gw0 = {
        "call_count": {"GET\t/a\t": 2},
        "call_type": {"GET\t/a\t": ["request_default"]},
        "call_meta": {},
        "endpoint_subtype": {},
    }
    gw1 = {
        "call_count": {"GET\t/a\t": 3, "POST\t/b\t": 1},
        "call_type": {
            "GET\t/a\t": ["request_permissions"],
            "POST\t/b\t": ["request_default"],
        },
        "call_meta": {},
        "endpoint_subtype": {},
    }
    directory = _shard(tmp_path, "gw0", gw0)
    _shard(tmp_path, "gw1", gw1)

    cs.merge_shards(directory)

    assert cs.call_count[("GET", "/a", "")] == 5, "calls must be summed, not overwritten"
    assert set(cs.call_type[("GET", "/a", "")]) == {"request_default", "request_permissions"}
    assert cs.call_count[("POST", "/b", "")] == 1, "an endpoint only one worker hit must survive"
    assert cs.run_info["workers"] == 2
    assert cs.run_info["merged"] is True


def test_merge_does_not_reload_own_shard(tmp_path):
    """The controller already holds its own calls; loading them again would double."""
    cs.record_call(("GET", "/a", ""), "request_default")
    directory = tmp_path / "shards"
    directory.mkdir()
    cs.write_shard(directory)

    cs.merge_shards(directory)

    assert cs.call_count[("GET", "/a", "")] == 1


def test_merge_survives_a_corrupt_shard(tmp_path):
    directory = _shard(tmp_path, "gw0", {"call_count": {"GET\t/a\t": 1}, "call_type": {}})
    (directory / "gw1.json").write_text("{not json", encoding="utf-8")

    cs.merge_shards(directory)

    assert cs.call_count[("GET", "/a", "")] == 1


def test_shard_roundtrip_is_written_atomically(tmp_path):
    cs.record_call(("GET", "/a", "desc"), "request_default", subtype="get_list_objects")
    path = cs.write_shard(tmp_path / "shards")

    assert path.name.endswith(".json")
    assert not list((tmp_path / "shards").glob(".*tmp")), "no temp file left behind"

    cs.reset_storage()
    cs.load_storage_file(path)
    assert cs.call_count[("GET", "/a", "desc")] == 1


def test_serial_run_is_unchanged(tmp_path):
    """Regression: with no shards nothing is merged and nothing is claimed."""
    cs.record_call(("GET", "/a", ""), "request_default")
    cs.merge_shards(tmp_path / "empty")

    assert cs.call_count[("GET", "/a", "")] == 1
    assert cs.run_info["workers"] == 1
    assert cs.run_info["merged"] is False


def test_clear_shards_removes_previous_run(tmp_path):
    directory = _shard(tmp_path, "gw0", {"call_count": {}, "call_type": {}})
    assert cs.read_shards(directory)
    cs.clear_shards(directory)
    assert cs.read_shards(directory) == []


# --- LIB-COV-KIND ---------------------------------------------------------


@pytest.mark.parametrize(
    "count, present, required, expected",
    [
        (0, [], ["a", "b"], "unseen"),
        (3, [], ["a", "b"], "empty"),
        (3, ["a"], ["a", "b"], "partial"),
        (3, ["a", "b"], ["a", "b"], "full"),
        (0, [], [], "unseen"),
        (2, [], [], "full"),
    ],
)
def test_kind_separates_never_called_from_no_cells(count, present, required, expected):
    """"Nobody called it in this run" is a different claim from "it has no tests"."""
    assert _kind_for(count=count, present=present, required=required, is_exception=False) == expected


def test_exception_endpoints_keep_their_own_kind():
    assert _kind_for(count=0, present=[], required=["a"], is_exception=True) == "exception"


# --- LIB-COV-TIMING -------------------------------------------------------


def test_timing_aggregates_by_type():
    metas = [
        {"elapsed_ms": 10.0, "type": "request_default"},
        {"elapsed_ms": 30.0, "type": "request_default"},
        {"elapsed_ms": 200.0, "type": "request_permissions"},
    ]
    timing = timing_of(metas)

    assert timing["n"] == 3
    assert timing["msAvg"] == 80.0
    assert timing["msMax"] == 200.0
    assert timing["byType"]["RequestDefault"]["n"] == 2
    assert timing["byType"]["RequestDefault"]["msAvg"] == 20.0


def test_timing_is_absent_when_nothing_was_measured():
    assert timing_of([]) is None
    assert timing_of([{"type": "request_default"}]) is None


def test_timing_ignores_non_numeric_samples():
    assert timing_of([{"elapsed_ms": "slow"}, {"elapsed_ms": 5}])["n"] == 1


# --- LIB-COV-HIST-2 -------------------------------------------------------


def test_history_keeps_two_runs_by_default(tmp_path):
    import datetime as dt

    for minute in range(5):
        append_snapshot(
            {"run": minute},
            tmp_path,
            when=dt.datetime(2026, 9, 4, 10, minute, tzinfo=dt.timezone.utc),
        )

    kept = list_snapshots(tmp_path)
    assert len(kept) == 2
    assert json.loads(kept[-1].read_text(encoding="utf-8"))["run"] == 4


def test_history_can_keep_everything(tmp_path):
    import datetime as dt

    for minute in range(4):
        append_snapshot(
            {"run": minute},
            tmp_path,
            when=dt.datetime(2026, 9, 4, 11, minute, tzinfo=dt.timezone.utc),
            keep=None,
        )
    assert len(list_snapshots(tmp_path)) == 4


def test_prune_is_a_no_op_on_a_missing_directory(tmp_path):
    assert prune_snapshots(tmp_path / "nope") == 0


# --- End to end: a real parallel run --------------------------------------


XDIST_SUITE = '''
import pytest
from partest.call_storage import record_call

@pytest.mark.parametrize("n", list(range(6)))
def test_touch(n):
    """Each test records one call; xdist spreads them across workers."""
    record_call(("GET", f"/ep{n}", ""), "request_default")
'''

XDIST_CHECK = '''
import json, os
import pytest
from partest.call_storage import call_count, run_info

# trylast: conftest hooks run before plugin hooks by default, and we must observe
# the state *after* partest has merged the worker shards.
@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if hasattr(session.config, "workerinput"):
        return
    out = os.environ["MERGE_PROBE"]
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(
            {"endpoints": sorted(k[1] for k in call_count), "run": dict(run_info)},
            fh,
        )
'''


@pytest.mark.parametrize("parallel", [False, True], ids=["serial", "xdist"])
def test_parallel_run_sees_every_endpoint(tmp_path, parallel):
    """The whole point: -n must report the suite, not one worker's slice."""
    import subprocess
    import sys

    project = tmp_path / "suite"
    project.mkdir()
    (project / "test_suite.py").write_text(XDIST_SUITE, encoding="utf-8")
    # Our own hook must run after the plugin's merge, so it lives in a local plugin.
    (project / "conftest.py").write_text(XDIST_CHECK, encoding="utf-8")

    probe = tmp_path / "probe.json"
    env = dict(os.environ)
    env["MERGE_PROBE"] = str(probe)
    env["PARTEST_CALL_STORAGE_DIR"] = str(tmp_path / "shards")
    # The subprocess must exercise this working tree, not an installed partest.
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("PYTEST_XDIST_WORKER", None)
    env.pop("PYTEST_CURRENT_TEST", None)

    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", str(project)]
    if parallel:
        cmd += ["-n", "2"]

    result = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

    data = json.loads(probe.read_text(encoding="utf-8"))
    assert data["endpoints"] == [f"/ep{i}" for i in range(6)], (
        "every endpoint the suite touched must be visible to the controller"
    )
    if parallel:
        assert data["run"]["merged"] is True
        assert data["run"]["workers"] == 2
