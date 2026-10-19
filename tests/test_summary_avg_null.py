"""`summary.avg` is `null` for a run with no endpoints (2.7.0), and every reader survives it.

Same contract as `meta.unseenRatio` (2.3.0): an average over an empty set is not a
measurement, and `0.0` read as "nothing is covered". Older snapshots wrote `0.0` there and
are read exactly as before — the file cannot tell that zero from a measured one.
"""

from __future__ import annotations

import copy

import pytest

from partest.methodology.api import MethodSubtype
from partest.reports import Severity, validate_coverage_payload
from partest.reports.analyzer import CoverageReport, EndpointCoverage
from partest.reports.badge import badge_from_payload, badge_svg
from partest.reports.compare import compare_payloads
from partest.reports.interactive_html import render_html
from partest.reports.payload import aggregate_services, build_payload, summarize


def _endpoint(path: str, *, calls: int, kind: str, status: str, pct: float) -> EndpointCoverage:
    return EndpointCoverage(
        method="GET",
        path=path,
        description="",
        subtype=MethodSubtype.GET_LIST,
        subtype_label="list",
        calls=calls,
        executed_types=set(),
        required_p1=[],
        required_all=[],
        missing_p1=[],
        missing_all=[],
        present_required=[],
        coverage_pct=pct,
        status=status,
        kind=kind,
    )


def _report(endpoints) -> CoverageReport:
    return CoverageReport(
        endpoints=list(endpoints),
        average_pct=0.0,
        total_calls=sum(e.calls for e in endpoints),
        full_count=0,
        partial_count=0,
        empty_count=0,
        exception_count=0,
        by_subtype={},
        by_swagger={},
    )


@pytest.fixture()
def empty() -> dict:
    return build_payload(_report([]))


@pytest.fixture()
def measured() -> dict:
    return build_payload(
        _report(
            [
                _endpoint("/a", calls=3, kind="full", status="full", pct=100.0),
                _endpoint("/b", calls=0, kind="unseen", status="empty", pct=0.0),
            ]
        )
    )


def _legacy_empty(doc: dict) -> dict:
    """An empty run as 2.6.0 and earlier wrote it."""
    old = copy.deepcopy(doc)
    old["summary"]["avg"] = 0.0
    old["summary"]["avgAll"] = 0.0
    return old


def _errors(doc) -> list[str]:
    return [str(p) for p in validate_coverage_payload(doc) if p.severity is Severity.ERROR]


# --- the producer ---------------------------------------------------------------------------


def test_a_run_with_no_endpoints_writes_null_averages(empty):
    assert empty["summary"]["avg"] is None
    assert empty["summary"]["avgAll"] is None
    assert empty["summary"]["endpoints"] == 0
    # The other counters stay numbers: zero endpoints, zero calls are counts, not averages.
    assert empty["summary"]["calls"] == 0
    assert empty["services"] == [] and empty["heatmap"]["cells"] == []


def test_a_measured_zero_is_still_zero():
    doc = build_payload(_report([_endpoint("/a", calls=1, kind="empty", status="empty", pct=0.0)]))
    assert doc["summary"]["avg"] == 0.0
    assert doc["services"][0]["avgCoverage"] == 0.0


def test_summarize_of_nothing_is_null():
    assert summarize([])["avg"] is None


def test_service_rows_without_an_average_sort_last():
    rows = aggregate_services(
        [{"service": "a", "coverage": 10.0}, {"service": "b", "coverage": 90.0}]
    )
    assert [r["key"] for r in rows] == ["b", "a"]
    # A row that reached the sort with no average does not break it.
    from partest.reports.payload import _by_avg_coverage

    mixed = [{"label": "x", "avgCoverage": None}, {"label": "y", "avgCoverage": 5.0}]
    assert [r["label"] for r in sorted(mixed, key=_by_avg_coverage)] == ["y", "x"]


# --- the validator --------------------------------------------------------------------------


def test_validator_accepts_null_for_an_empty_run(empty):
    assert validate_coverage_payload(empty) == []


def test_validator_accepts_the_owners_measured_document(measured):
    assert validate_coverage_payload(measured) == []


@pytest.mark.parametrize("key", ["avg", "avgAll"])
def test_null_where_there_was_something_to_measure_is_an_error(measured, key):
    broken = copy.deepcopy(measured)
    broken["summary"][key] = None
    assert any(f"summary.{key}" in e and "null при 2" in e for e in _errors(broken))


def test_a_legacy_zero_for_an_empty_run_is_dated_not_wrong(empty):
    problems = validate_coverage_payload(_legacy_empty(empty))
    assert _errors(_legacy_empty(empty)) == []
    dated = [p for p in problems if p.severity is Severity.DATED]
    assert {p.where for p in dated} == {"summary.avg", "summary.avgAll"}


def test_a_nonzero_average_over_no_endpoints_is_an_error(empty):
    broken = copy.deepcopy(empty)
    broken["summary"]["avg"] = 42.0
    assert any("summary.avg" in e and "42.0 при нуле" in e for e in _errors(broken))


@pytest.mark.parametrize("value", [True, "50", 150.0, -1])
def test_a_wrong_average_is_an_error(measured, value):
    broken = copy.deepcopy(measured)
    broken["summary"]["avg"] = value
    assert any("summary.avg" in e for e in _errors(broken))


# --- the badge ------------------------------------------------------------------------------


def test_badge_for_an_empty_run_says_not_measured(empty):
    svg = badge_from_payload(empty)
    assert "coverage: n/a" in svg
    assert "%" not in svg
    assert "#e05d44" not in svg  # not the red of a low number
    assert badge_svg(None) == svg


def test_badge_reads_an_old_empty_snapshot_as_not_measured(empty):
    """2.6 wrote 0.0 for a run with no endpoints; the validator reads it as "not measured",
    and so does the badge."""
    assert "coverage: n/a" in badge_from_payload(_legacy_empty(empty))
    only_count = {"summary": {"avg": 0.0, "endpoints": 0}}
    assert "coverage: n/a" in badge_from_payload(only_count)
    only_list = {"summary": {"avg": 0.0}, "endpoints": []}
    assert "coverage: n/a" in badge_from_payload(only_list)


def test_badge_keeps_a_measured_zero_and_an_unknown_payload(measured):
    zero = copy.deepcopy(measured)
    zero["summary"]["avg"] = 0.0
    assert "coverage: 0.0%" in badge_from_payload(zero)
    assert "coverage: 0.0%" in badge_from_payload({})  # no summary, no endpoints: as before
    assert "coverage: 0.0%" in badge_from_payload({"summary": {"avg": 0.0}})


# --- compare --------------------------------------------------------------------------------


def test_compare_with_an_empty_run_has_no_delta(empty, measured):
    diff = compare_payloads(measured, empty)
    assert diff["old_avg"] == 50.0
    assert diff["new_avg"] is None
    assert diff["avg_delta"] is None and diff["coverage_delta"] is None
    assert diff["comparable"] is False
    assert any("current run has no endpoints" in w for w in diff["warnings"])

    back = compare_payloads(empty, measured)
    assert back["old_avg"] is None and back["avg_delta"] is None
    assert any("previous run has no endpoints" in w for w in back["warnings"])


def test_compare_reads_an_old_empty_snapshot_as_not_measured(empty, measured):
    """A 2.6 baseline of an empty run (endpoints: [], avg: 0.0) is not a measured zero:
    no +50 delta, and the pair is not comparable."""
    diff = compare_payloads(_legacy_empty(empty), measured)
    assert diff["old_avg"] is None
    assert diff["avg_delta"] is None and diff["coverage_delta"] is None
    assert diff["comparable"] is False
    assert any(
        "previous run has no endpoints" in w and "releases before 2.7.0" in w
        for w in diff["warnings"]
    )


def test_compare_keeps_a_measured_zero(measured):
    zero = copy.deepcopy(measured)
    zero["summary"]["avg"] = 0.0
    diff = compare_payloads(zero, measured)
    assert diff["old_avg"] == 0.0 and diff["avg_delta"] == 50.0
    # a payload too old to say how many endpoints it had keeps reading as 0.0
    assert compare_payloads({"summary": {"avg": 0.0}}, measured)["old_avg"] == 0.0
    # a trimmed payload: no rows, but summary.endpoints says twelve were measured
    trimmed = {"summary": {"avg": 0.0, "endpoints": 12}, "endpoints": []}
    assert compare_payloads(trimmed, measured)["old_avg"] == 0.0
    assert "coverage: 0.0%" in badge_from_payload(trimmed)


def test_compare_of_two_empty_runs_has_no_delta(empty):
    diff = compare_payloads(empty, copy.deepcopy(empty))
    assert diff["avg_delta"] is None


# --- the HTML page --------------------------------------------------------------------------


def test_html_does_not_call_tofixed_on_an_average():
    html = render_html(build_payload(_report([])), title="t")
    assert ".avg.toFixed" not in html
    assert "function pct(v, digits)" in html
    assert "if (!list.length) return null;" in html
