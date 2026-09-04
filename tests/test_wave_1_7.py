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


# --- LIB-SUBTYPE-OVERRIDE -------------------------------------------------


@pytest.fixture
def no_overrides():
    from partest.methodology.overrides import clear_subtype_overrides

    clear_subtype_overrides()
    yield
    clear_subtype_overrides()


def test_override_beats_the_heuristic(no_overrides):
    from partest.methodology.classifier import classify_endpoint
    from partest.methodology.overrides import set_subtype_overrides
    from partest.methodology.subtypes import MethodSubtype

    assert classify_endpoint("POST", "/orders/{id}/lines", "") is (
        MethodSubtype.POST_CREATE_TO_OBJECT
    )
    set_subtype_overrides({"POST /orders/{id}/lines": "action"})
    assert classify_endpoint("POST", "/orders/{id}/lines", "") is MethodSubtype.ACTION


def test_override_matches_by_route_shape_not_parameter_name(no_overrides):
    """A project should not have to spell the spec's parameter names exactly."""
    from partest.methodology.classifier import classify_endpoint
    from partest.methodology.overrides import set_subtype_overrides
    from partest.methodology.subtypes import MethodSubtype

    set_subtype_overrides({"GET /orders/{id}/lines": "get_static_object"})
    assert classify_endpoint("GET", "/orders/{orderId}/lines", "") is (
        MethodSubtype.GET_STATIC
    )


def test_override_reaches_the_coverage_decorator(no_overrides):
    """The point of applying it inside the function rather than by rebinding.

    ``coverage.py`` imports ``classify_endpoint`` by value at import time, before any
    project configuration is read, so patching the module attribute would not be seen.
    """
    from partest.coverage import classify_endpoint as coverage_view
    from partest.methodology.overrides import set_subtype_overrides
    from partest.methodology.subtypes import MethodSubtype

    set_subtype_overrides({"GET /items": "get_by_self"})
    assert coverage_view("GET", "/items", "") is MethodSubtype.GET_BY_SELF


def test_bad_override_is_rejected_loudly(no_overrides):
    """A silently dropped override looks exactly like the bug it was meant to fix."""
    from partest.methodology.overrides import set_subtype_overrides

    with pytest.raises(ValueError, match="unknown subtype"):
        set_subtype_overrides({"GET /a": "not_a_subtype"})
    with pytest.raises(ValueError, match="must look like"):
        set_subtype_overrides({"GET-a": "action"})


def test_overrides_load_from_yaml(tmp_path, no_overrides):
    from partest.methodology.classifier import classify_endpoint
    from partest.methodology.overrides import load_subtype_overrides
    from partest.methodology.subtypes import MethodSubtype

    path = tmp_path / "subtypes.yaml"
    path.write_text('"POST /jobs/{id}/lines": action\n', encoding="utf-8")
    load_subtype_overrides(path)

    assert classify_endpoint("POST", "/jobs/{id}/lines", "") is MethodSubtype.ACTION


def test_missing_override_file_is_an_error(tmp_path, no_overrides):
    from partest.methodology.overrides import load_subtype_overrides

    with pytest.raises(FileNotFoundError):
        load_subtype_overrides(tmp_path / "nope.yaml")


# --- LIB-COV-CMP: kind-aware ----------------------------------------------


def _payload(endpoints, meta=None, avg=0.0):
    return {"meta": meta or {}, "summary": {"avg": avg}, "endpoints": endpoints}


def test_endpoint_not_called_this_run_is_not_a_regression():
    from partest.reports.compare import compare_payloads

    old = _payload([{"method": "GET", "path": "/a", "coverage": 100.0, "kind": "full", "missing": []}])
    new = _payload(
        [{"method": "GET", "path": "/a", "coverage": 0.0, "kind": "unseen", "missing": ["RequestDefault"]}]
    )

    diff = compare_payloads(old, new)

    assert diff["regressed"] == []
    assert [e["endpoint"] for e in diff["not_run"]] == ["GET /a"]
    assert diff["missing_new"] == [], "a missing list from a run that never fired is noise"


def test_a_real_loss_is_still_a_regression():
    from partest.reports.compare import compare_payloads

    old = _payload([{"method": "GET", "path": "/b", "coverage": 100.0, "kind": "full", "missing": []}])
    new = _payload(
        [{"method": "GET", "path": "/b", "coverage": 50.0, "kind": "partial", "missing": ["RequestNotFound"]}]
    )

    diff = compare_payloads(old, new)

    assert [e["endpoint"] for e in diff["regressed"]] == ["GET /b"]
    assert diff["missing_new"] == ["GET /b :: RequestNotFound"]


def test_unmerged_parallel_run_is_flagged_as_not_comparable():
    from partest.reports.compare import compare_payloads

    old = _payload([], avg=90.0)
    new = _payload([], meta={"workers": 3, "merged": False}, avg=25.0)

    diff = compare_payloads(old, new)

    assert diff["comparable"] is False
    assert any("without merging" in w for w in diff["warnings"])


def test_two_clean_runs_are_comparable():
    from partest.reports.compare import compare_payloads

    meta = {"workers": 2, "merged": True, "partialRun": False}
    diff = compare_payloads(_payload([], meta=meta), _payload([], meta=meta))

    assert diff["comparable"] is True
    assert diff["warnings"] == []


# --- LIB-COV-HTML ---------------------------------------------------------


def _html_payload(meta=None, endpoints=None):
    return {
        "meta": {"generated": "now", "engine": "partest", "defaultExcluded": [], **(meta or {})},
        "summary": {"avg": 50.0, "avgAll": 50.0, "endpoints": 1, "calls": 1,
                    "full": 0, "partial": 1, "empty": 0, "exception": 0},
        "services": [{"key": "core", "label": "core", "avg": 50.0, "endpoints": 1}],
        "subtypes": [], "methods": [], "missingTop": [], "heatmap": {"rows": [], "cols": []},
        "endpoints": endpoints if endpoints is not None else [
            {"method": "GET", "path": "/items", "service": "core", "serviceLabel": "core",
             "subtype": "GET LIST OBJECTS", "subtypeKey": "get_list_objects", "calls": 1,
             "coverage": 50.0, "status": "partial", "kind": "partial",
             "executed": ["RequestDefault"], "missing": ["RequestPermissions"],
             "description": "list"}
        ],
    }


def test_report_shows_a_not_called_counter_and_banner_hook():
    from partest.reports.interactive_html import render_html

    html = render_html(_html_payload(), title="t")

    assert 'id="run-banner"' in html, "a partial or unmerged run must be announced at the top"
    assert "Not called this run" in html
    assert 'data-kind="unseen"' in html, "the counter must be clickable into a filter"
    assert "Reset filters" in html


def test_report_presets_carry_no_product_names():
    """The template ships to every user; a consumer's services must not be baked in."""
    from partest.reports.interactive_html import render_html

    html = render_html(_html_payload(), title="t")

    for leaked in (the service names):
        assert leaked not in html.lower(), f"{leaked!r} leaked into the shipped template"


def test_report_survives_without_local_storage():
    """Opened from a sandboxed context, persistence must degrade, not blank the page."""
    from partest.reports.interactive_html import render_html

    html = render_html(_html_payload(), title="t")

    assert html.count("localStorage.") == 2, (
        "every localStorage access belongs inside the guarded shim"
    )
    assert "try { return localStorage.getItem(key); }" in html


# --- LIB-REC-UPLOAD: the gate corpus --------------------------------------


def test_generated_xlsx_is_a_valid_package():
    """A stub that no zip reader accepts would test the reader, not the gate."""
    import io
    import zipfile

    from partest.files import minimal_xlsx_bytes

    with zipfile.ZipFile(io.BytesIO(minimal_xlsx_bytes())) as zf:
        assert zf.testzip() is None
        assert "[Content_Types].xml" in zf.namelist()


def test_broken_packages_are_actually_broken():
    import io
    import zipfile

    from partest.files import truncated_zip_bytes, zip_without_content_types

    with pytest.raises(zipfile.BadZipFile):
        zipfile.ZipFile(io.BytesIO(truncated_zip_bytes()))

    with zipfile.ZipFile(io.BytesIO(zip_without_content_types())) as zf:
        assert "[Content_Types].xml" not in zf.namelist()


def test_ole_stub_carries_the_compound_document_magic():
    from partest.files import minimal_ole_xls_bytes

    assert minimal_ole_xls_bytes()[:8] == bytes([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1])


def test_mutation_corpus_covers_every_class():
    from partest.files import mutation_cases

    ids = {c.id for c in mutation_cases()}

    assert {"neighbour-csv", "no-extension", "double-extension"} <= ids, "format handling"
    assert {"png-named-xlsx", "xlsx-named-txt", "truncated-zip"} <= ids, "content vs name"
    assert {"traversal-unix", "traversal-windows", "very-long"} <= ids, "filename"
    assert {"empty-file", "modest-size"} <= ids, "size"


def test_content_spoofing_is_a_fact_not_an_expectation():
    """A gate that only checks the extension is a legitimate design, not a bug."""
    from partest.files import spoof_cases

    assert {c.gate_expect for c in spoof_cases()} <= {"fact", "reject"}
    assert next(c for c in spoof_cases() if c.id == "png-named-xlsx").gate_expect == "fact"


def test_corpus_carries_no_oversized_payload():
    """No case may be big enough to hurt a stand; over-limit needs a documented limit."""
    from partest.files import mutation_cases

    assert max(len(c.content) for c in mutation_cases()) < 1_000_000


def test_upload_case_maps_onto_the_client_files_argument():
    from partest.files import mutation_cases

    case = mutation_cases()[0]
    name, content, mime = case.files_kwarg["file"]
    assert name == case.filename and content == case.content and mime == case.content_type


def test_filenames_never_contain_a_null_byte():
    """A NUL breaks the HTTP client before the server sees it — it tests nothing."""
    from partest.files import mutation_cases

    assert all("\x00" not in c.filename for c in mutation_cases())
