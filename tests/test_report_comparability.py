"""When two coverage snapshots may be compared, and when the answer is "they may not".

Every case here comes from a real 1.5.0 → 1.8.0 upgrade in a consuming suite. The failure
mode they share is the expensive one: the comparison returned a confident, wrong answer
instead of an error. A tool that says "regressed 14" when nothing regressed costs more than
one that says "I cannot tell".
"""

from __future__ import annotations

import subprocess
import sys
import types

import pytest

from partest.reports.compare import compare_payloads


def _payload(endpoints, meta=None, avg=0.0):
    return {"meta": meta or {}, "summary": {"avg": avg}, "endpoints": endpoints}


def _ep(path, *, calls, coverage, kind=None, missing=(), method="GET"):
    """An endpoint record. Omit ``kind`` to model a snapshot written before it existed."""
    record = {
        "method": method,
        "path": path,
        "calls": calls,
        "coverage": coverage,
        "missing": list(missing),
    }
    if kind is not None:
        record["kind"] = kind
    return record


# --- A snapshot older than `kind` -----------------------------------------


def test_never_called_endpoint_is_not_reported_as_newly_dropped():
    """The first thing anyone does when upgrading is compare against an old snapshot.

    Reading a missing `kind` as "not unseen" turned every endpoint that was never called
    into one that "was covered before and is not called now" — and dragged `comparable`
    to False on two runs between which nothing had changed.
    """
    old = _payload([_ep("/jobs/{jobId}", calls=0, coverage=0.0)])          # pre-1.7: no kind
    new = _payload([_ep("/jobs/{jobId}", calls=0, coverage=0.0, kind="unseen")])

    diff = compare_payloads(old, new)

    assert diff["not_run"] == [], "it was never called before either — nothing was dropped"
    assert diff["comparable"] is True
    assert diff["warnings"] == []


def test_a_genuinely_dropped_endpoint_is_still_reported_without_kind():
    """The inference must not go the other way and hide a real loss."""
    old = _payload([_ep("/users/{id}", calls=12, coverage=33.33)])          # pre-1.7: no kind
    new = _payload([_ep("/users/{id}", calls=0, coverage=0.0, kind="unseen")])

    diff = compare_payloads(old, new)

    assert [e["endpoint"] for e in diff["not_run"]] == ["GET /users/{id}"]
    assert diff["regressed"] == [], "not called is not the same as lost a test case"
    assert diff["comparable"] is False


# --- A run filtered by markers --------------------------------------------
#
# `-m "not rbac"` removes test *cases*. The endpoint is still called, it just loses one
# cell, so the share of never-called endpoints does not move and nothing in the numbers
# says half the suite was skipped.


def _filtered_pair():
    """Modelled on the measured run: calls 7015 → 3177, never-called 1 → 2 of 114."""
    old_eps, new_eps = [], []
    for i in range(113):
        old_eps.append(_ep(f"/e{i}", calls=62, coverage=100.0))
        new_eps.append(
            _ep(f"/e{i}", calls=28, coverage=75.0, kind="partial", missing=["RequestPermissions"])
        )
    old_eps.append(_ep("/never", calls=0, coverage=0.0))
    new_eps.append(_ep("/never", calls=0, coverage=0.0, kind="unseen"))
    return _payload(old_eps, avg=100.0), _payload(new_eps, avg=97.22)


def test_a_marker_filtered_run_is_not_silently_compared():
    old, new = _filtered_pair()

    diff = compare_payloads(old, new)

    assert diff["comparable"] is False, (
        "every lost cell was presented as a regression, with the comparison marked sound"
    )
    assert any("fewer" in w for w in diff["warnings"]), diff["warnings"]


def test_the_lost_cells_are_still_listed_rather_than_hidden():
    """The warning says the comparison is unsound; it must not also erase the evidence.

    Whether a cell was deselected or deleted is unknowable from the payloads alone, so
    quietly moving these out of `regressed` would risk burying a real loss.
    """
    old, new = _filtered_pair()

    diff = compare_payloads(old, new)

    assert len(diff["regressed"]) == 113
    assert len(diff["missing_new"]) == 113


def test_ordinary_run_to_run_variation_stays_comparable():
    """The signal is a collapse, not noise: two full runs of one suite must not trip it."""
    old = _payload([_ep(f"/e{i}", calls=60, coverage=100.0, kind="full") for i in range(20)])
    new = _payload([_ep(f"/e{i}", calls=57, coverage=100.0, kind="full") for i in range(20)])

    diff = compare_payloads(old, new)

    assert diff["comparable"] is True
    assert diff["warnings"] == []


def test_a_collapse_that_does_show_up_as_unseen_is_left_to_not_run():
    """When endpoints go untouched wholesale, `not_run` already explains it."""
    old = _payload([_ep(f"/e{i}", calls=60, coverage=100.0, kind="full") for i in range(10)])
    new = _payload(
        [_ep(f"/e{i}", calls=0, coverage=0.0, kind="unseen") for i in range(10)]
    )

    diff = compare_payloads(old, new)

    assert diff["comparable"] is False
    assert not any("fewer" in w for w in diff["warnings"]), (
        "one explanation is enough; this is the case not_run was written for"
    )


# --- The exact signal: what the run selected ------------------------------


def test_a_declared_selection_makes_the_comparison_unsound():
    new = _payload([], meta={"selection": {"markexpr": "not rbac", "deselected": 992}})

    diff = compare_payloads(_payload([]), new)

    assert diff["comparable"] is False
    assert any("not rbac" in w and "992" in w for w in diff["warnings"]), diff["warnings"]


def test_the_plugin_records_the_selection_expression():
    from partest.call_storage import run_info
    from partest.pytest_plugin import _record_selection

    run_info["selection"] = {}
    try:
        config = types.SimpleNamespace(
            option=types.SimpleNamespace(markexpr="not rbac and not security", keyword="")
        )
        _record_selection(config, deselected=992)

        assert run_info["selection"] == {
            "markexpr": "not rbac and not security",
            "deselected": 992,
        }
    finally:
        run_info["selection"] = {}


def test_the_selection_survives_reset_storage():
    """`reset_storage` runs in a session fixture — after collection, where this is known."""
    from partest.call_storage import reset_storage, run_info

    run_info["selection"] = {"markexpr": "smoke"}
    try:
        reset_storage()
        assert run_info["selection"] == {"markexpr": "smoke"}, (
            "clearing it here would silently disarm the partial-run flag"
        )
    finally:
        run_info["selection"] = {}


def test_a_selected_run_is_marked_partial_in_the_payload():
    from partest.call_storage import run_info
    from partest.reports.payload import build_payload

    report = types.SimpleNamespace(endpoints=[])
    run_info["selection"] = {"markexpr": "not rbac"}
    try:
        payload = build_payload(report)
    finally:
        run_info["selection"] = {}

    assert payload["meta"]["partialRun"] is True
    assert payload["meta"]["selection"] == {"markexpr": "not rbac"}


def test_an_unfiltered_run_carries_no_selection_key():
    from partest.call_storage import run_info
    from partest.reports.payload import build_payload

    run_info["selection"] = {}
    payload = build_payload(types.SimpleNamespace(endpoints=[]))

    assert payload["meta"]["partialRun"] is False
    assert "selection" not in payload["meta"]


# --- Reachability of the public surface -----------------------------------


@pytest.mark.parametrize(
    "name",
    ["append_snapshot", "list_snapshots", "prune_snapshots", "previous_snapshot", "latest_snapshot"],
)
def test_history_helpers_are_importable_from_the_package(name):
    """The changelog called these public; only the full module path worked."""
    import partest.reports as reports

    assert hasattr(reports, name)
    assert name in reports.__all__


def test_history_declares_its_own_surface():
    from partest.reports import history

    assert "json" not in history.__all__, "dir() showed imported modules as if they were API"
    assert "prune_snapshots" in history.__all__


# --- Diagnostics must not land in stdout ----------------------------------


def test_parsing_a_specification_writes_nothing_to_stdout():
    """Any `python -c` next to partest has to stay machine-readable.

    The parser printed a line per resolved reference, so importing it in a process whose
    output someone parses meant piping through grep.
    """
    script = (
        "import io, contextlib, logging\n"
        "logging.disable(logging.CRITICAL)\n"
        "buf = io.StringIO()\n"
        "with contextlib.redirect_stdout(buf):\n"
        "    from partest.parparser import OpenAPIParser\n"
        "    p = OpenAPIParser({'components': {'schemas': {}}})\n"
        "    p.resolve_ref({'not': 'a string'})\n"
        "    p.resolve_ref('#/components/schemas/Missing')\n"
        "print(repr(buf.getvalue()))\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "''", f"parser wrote to stdout: {result.stdout}"


def test_the_parser_reports_through_logging():
    import logging

    from partest.parparser import OpenAPIParser

    parser = OpenAPIParser({"components": {"schemas": {}}})

    logger = logging.getLogger("partest.parparser")
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        parser.resolve_ref("#/components/schemas/Missing")
    finally:
        logger.removeHandler(handler)

    assert records, "a reference that cannot be resolved must still be reportable"
    assert any(r.levelno >= logging.WARNING for r in records)
