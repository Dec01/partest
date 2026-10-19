"""Axis C as its own field, and `exception` rows outside every average (2.7.0, proposals F1).

Two things the report did not say. Depth: a status-only call of the right `type=` filled its
cell exactly like a call that validated the body, and the report had nowhere to show the
difference — it now writes `depth` per endpoint and `summary.depth`, apart from the
percentage, which does not move. `exception`: a `health` call gave the row 100 % inside the
average, so one probe lifted the number as much as a fully tested endpoint — such rows are now
counted and left out (`meta.avgRule: 2`), and `compare` refuses to call a trend across the rule.
"""

from __future__ import annotations

import copy
import re
import subprocess

import httpx
import pytest
from test_html_script_node import HARNESS, NODE

from partest import BaseModelWithConfig, BaseResponseValidator, call_storage, coverage
from partest.call_storage import record_call, reset_storage
from partest.client import ApiClient
from partest.methodology.api import MethodSubtype
from partest.methodology.api.steps import call_depth, depth_score
from partest.reports import Severity, validate_coverage_payload
from partest.reports._rules import AVG_RULE
from partest.reports.analyzer import CoverageAnalyzer, CoverageReport, EndpointCoverage
from partest.reports.compare import compare_payloads
from partest.reports.html_coverage import _depth_text
from partest.reports.html_coverage import render_html as render_static_html
from partest.reports.interactive_html import render_html
from partest.reports.payload import build_payload, summarize
from partest.test_types import TypesTestCases as T
from partest.zorro_report import _text_summary


class _Path:
    def __init__(self, method, path, description=""):
        self.method = method
        self.path = path
        self.description = description
        self.deprecated = False
        self.request_body = None
        self.parameters = []
        self.source_type = "API"


def _meta(tc, *, status, model):
    """What `track_api_calls` records for one call."""
    return {"type": tc, "has_status_check": status, "has_validate_model": model}


@pytest.fixture(autouse=True)
def _clean_storage():
    reset_storage()
    yield
    reset_storage()


def _analyze(paths):
    return CoverageAnalyzer(paths, use_matrix=True).analyze()


def _row(report, path):
    return next(e for e in report.endpoints if e.path == path)


# --- depth: what is measured ------------------------------------------------------------


def test_depth_takes_the_deepest_call_of_each_filled_cell():
    key = ("GET", "/items", "")
    record_call(key, T.request_default, meta=_meta(T.request_default, status=True, model=True))
    # A helper call of the same type with no checks does not make the cell shallower.
    record_call(key, T.request_default, meta=_meta(T.request_default, status=False, model=False))
    record_call(key, T.request_permissions, meta=_meta(T.request_permissions, status=True, model=False))

    depth = _row(_analyze([_Path("GET", "/items")]), "/items").depth

    assert depth == {"cells": 2, "status": 2, "schema": 1, "values": None}


def test_a_model_without_a_status_check_is_no_schema_check():
    """`make_request` validates the body only after checking the status."""
    key = ("GET", "/items", "")
    record_call(key, T.request_default, meta=_meta(T.request_default, status=False, model=True))

    depth = _row(_analyze([_Path("GET", "/items")]), "/items").depth

    assert depth == {"cells": 1, "status": 0, "schema": 0, "values": None}


def test_a_type_outside_the_required_set_is_not_a_cell():
    key = ("GET", "/items", "")
    record_call(key, T.request_default, meta=_meta(T.request_default, status=True, model=False))
    record_call(key, T.request_extra_data, meta=_meta(T.request_extra_data, status=True, model=True))

    depth = _row(_analyze([_Path("GET", "/items")]), "/items").depth

    assert depth == {"cells": 1, "status": 1, "schema": 0, "values": None}


def test_the_cell_percentage_does_not_move_with_depth():
    key = ("GET", "/items", "")
    record_call(key, T.request_default, meta=_meta(T.request_default, status=False, model=False))
    shallow = _row(_analyze([_Path("GET", "/items")]), "/items")
    reset_storage()
    record_call(key, T.request_default, meta=_meta(T.request_default, status=True, model=True))
    deep = _row(_analyze([_Path("GET", "/items")]), "/items")

    assert shallow.coverage_pct == deep.coverage_pct == 50.0
    assert shallow.status == deep.status == "partial"
    assert (shallow.depth["schema"], deep.depth["schema"]) == (0, 1)


@pytest.mark.parametrize(
    "setup",
    ["unseen", "no-flags", "exception", "no-required-cell"],
)
def test_depth_is_null_where_nothing_was_measured(setup):
    key = ("GET", "/items", "")
    if setup == "no-flags":
        # Storage loaded from an older dump, or a call recorded by hand.
        record_call(key, T.request_default)
    elif setup == "exception":
        record_call(key, T.request_default, meta=_meta(T.request_default, status=True, model=True))
        record_call(key, "health", meta=_meta("health", status=True, model=True))
    elif setup == "no-required-cell":
        record_call(key, T.request_extra_data, meta=_meta(T.request_extra_data, status=True, model=True))

    row = _row(_analyze([_Path("GET", "/items")]), "/items")
    payload = build_payload(_analyze([_Path("GET", "/items")]))

    assert row.depth is None
    assert payload["endpoints"][0]["depth"] is None
    assert payload["summary"]["depth"] is None
    assert validate_coverage_payload(payload) == []


class _Item(BaseModelWithConfig):
    id: int


class _ItemValidation(BaseResponseValidator):
    @property
    def ResponseSuccessBody(self):
        return _Item


async def test_the_tracked_call_records_what_depth_reads(monkeypatch):
    """End to end through `make_request`: the flags come from its own arguments."""
    monkeypatch.setattr(coverage, "SWAGGER_AVAILABLE", True)
    monkeypatch.setattr(coverage, "swagger_files", ["stub"])
    monkeypatch.setattr(coverage, "paths_info", [_Path("GET", "/items")])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
        api = ApiClient("http://stand", client=hx)
        await api.make_request("GET", "/items", expected_status_code=200,
                               validate_model=_ItemValidation(), type=T.request_default)
        await api.make_request("GET", "/items", type=T.request_permissions)

    report = _analyze([_Path("GET", "/items")])
    assert _row(report, "/items").depth == {"cells": 2, "status": 1, "schema": 1, "values": None}
    assert call_storage.call_meta[("GET", "/items", "")][1]["has_status_check"] is False


# --- depth in the payload -----------------------------------------------------------------


def _ep(path, *, status, pct, calls=1, depth=None, kind=None, method="GET"):
    return EndpointCoverage(
        method=method, path=path, description="", subtype=MethodSubtype.GET_LIST,
        subtype_label="list", calls=calls, executed_types=set(), required_p1=[],
        required_all=[], missing_p1=[], missing_all=[], present_required=[],
        coverage_pct=pct, status=status, kind=kind or (status if calls else "unseen"),
        is_exception=status == "exception", depth=depth,
    )


def _report(endpoints):
    return CoverageReport(
        endpoints=list(endpoints), average_pct=0.0, total_calls=0, full_count=0,
        partial_count=0, empty_count=0, exception_count=0, by_subtype={}, by_swagger={},
    )


def _d(cells, status, schema):
    return {"cells": cells, "status": status, "schema": schema, "values": None}


def test_summary_depth_is_pooled_by_cell():
    payload = build_payload(_report([
        _ep("/a", status="full", pct=100.0, depth=_d(3, 3, 1)),
        _ep("/b", status="partial", pct=50.0, depth=_d(1, 0, 0)),
        _ep("/c", status="empty", pct=0.0, calls=0),
    ]))

    assert payload["endpoints"][0]["depth"] == _d(3, 3, 1)
    assert payload["endpoints"][2]["depth"] is None
    assert payload["summary"]["depth"] == {
        "cells": 4, "status": 3, "schema": 1, "values": None,
        "statusPct": 75.0, "schemaPct": 25.0,
    }
    assert validate_coverage_payload(payload) == []


# --- exception outside the average --------------------------------------------------------


def _mixed():
    return [
        _ep("/api/items", status="full", pct=100.0, depth=_d(2, 2, 2)),
        _ep("/api/items/{id}", status="empty", pct=0.0, calls=0),
        _ep("/api/health", status="exception", pct=100.0),
    ]


def test_exception_rows_are_counted_but_not_averaged():
    payload = build_payload(_report(_mixed()))
    summary = payload["summary"]

    assert payload["meta"]["avgRule"] == AVG_RULE == 2
    # 2.6 would have said 66.67: the health probe as a fully covered endpoint.
    assert summary["avg"] == summary["avgAll"] == 50.0
    assert (summary["exception"], summary["endpoints"]) == (1, 3)
    assert validate_coverage_payload(payload) == []


def test_a_service_of_exception_rows_only_has_no_average():
    payload = build_payload(_report(_mixed()))
    services = {s["key"]: s for s in payload["services"]}

    health, items = services["health"], services["items"]
    # `covered` is out of `scored`, not out of `totalEndpoints`: nothing here contradicts.
    assert (health["totalEndpoints"], health["exception"], health["scored"]) == (1, 1, 0)
    assert (health["covered"], health["avgCoverage"]) == (0, None)
    assert (items["totalEndpoints"], items["scored"], items["covered"]) == (2, 2, 1)
    assert items["avgCoverage"] == 50.0
    assert payload["summary"]["scored"] == 2
    subtype = payload["subtypes"][0]
    assert (subtype["count"], subtype["scored"], subtype["exception"]) == (3, 2, 1)
    method = payload["methods"][0]
    assert (method["count"], method["scored"], method["exception"]) == (3, 2, 1)
    assert payload["services"][-1]["key"] == "health"  # no average sorts last
    cells = {(c["service"], c["subtype"]): c for c in payload["heatmap"]["cells"]}
    assert cells[("health", MethodSubtype.GET_LIST.value)]["avg"] is None
    assert cells[("health", MethodSubtype.GET_LIST.value)]["count"] == 1


def test_a_run_of_exception_rows_only_has_no_average():
    payload = build_payload(_report([
        _ep("/health", status="exception", pct=100.0),
        _ep("/ready", status="exception", pct=100.0),
    ]))

    assert payload["summary"]["avg"] is None
    assert payload["summary"]["avgAll"] is None
    assert payload["summary"]["exception"] == 2
    assert validate_coverage_payload(payload) == []


def test_summarize_on_dicts_follows_the_same_rule():
    rows = [{"coverage": 100.0, "status": "exception"}, {"coverage": 20.0, "status": "partial"}]
    assert summarize(rows)["avg"] == 20.0


def test_the_analyzer_average_and_its_buckets_leave_exception_out():
    record_call(("GET", "/items", ""), T.request_default,
                meta=_meta(T.request_default, status=True, model=False))
    record_call(("GET", "/health", ""), "health", meta=_meta("health", status=True, model=False))

    report = _analyze([_Path("GET", "/items"), _Path("GET", "/health")])

    assert report.exception_count == 1
    assert report.average_pct == 50.0
    # The type does not change: a float, and `scored` says that nothing was averaged.
    static = report.by_subtype[MethodSubtype.GET_STATIC.value]
    assert (static["avg_pct"], static["scored"], static["count"]) == (0.0, 0, 1)
    assert report.by_subtype[MethodSubtype.GET_LIST.value]["avg_pct"] == 50.0
    text = _text_summary(report)
    assert "50.00% — exception endpoints not averaged" in text
    assert ": n/a (1 ep)" in text  # the subtype of the health probe alone
    assert "status 1/1 (100%), schema 0/1 (0%), values not measured" in text
    page = render_static_html(report)
    assert "Cells: schema asked" in page
    assert "status 1/1 · schema 0/1" in page  # the Depth column
    assert page.count("<td class=\"muted\">—</td>") == 1  # the health row: not measured


def test_the_text_summary_says_n_a_when_nothing_is_scored():
    record_call(("GET", "/health", ""), "health", meta=_meta("health", status=True, model=False))
    report = _analyze([_Path("GET", "/health")])

    assert "Average coverage (methodology P1 set): n/a" in _text_summary(report)
    assert "Depth asked for, of filled cells: not measured" in _text_summary(report)
    assert ">n/a<" in render_static_html(report)


def test_depth_text_of_the_static_page():
    assert _depth_text(None) == "—"
    assert _depth_text({"cells": 0, "status": 0, "schema": 0}) == "—"
    assert _depth_text(_d(3, 2, 1)) == "status 2/3 · schema 1/3"


# --- one rule for the level of a call -------------------------------------------------------


@pytest.mark.parametrize(
    "status, model, level", [(False, False, 0), (False, True, 0), (True, False, 1), (True, True, 2)]
)
def test_call_depth_is_the_one_rule(status, model, level):
    assert call_depth(status, model) == level
    assert depth_score(status, model) == level
    assert depth_score(status, model, has_value_assert=True) == level + 1


# --- what the tracker can see ---------------------------------------------------------------


def _tracked(func, monkeypatch):
    monkeypatch.setattr(coverage, "SWAGGER_AVAILABLE", True)
    monkeypatch.setattr(coverage, "swagger_files", ["stub"])
    monkeypatch.setattr(coverage, "paths_info", [_Path("GET", "/items")])
    return coverage.track_api_calls(func)


async def test_a_positional_status_is_seen(monkeypatch):
    async def make_request(self, method, endpoint, expected_status_code=None,
                           validate_model=None, type=None):
        return None

    tracked = _tracked(make_request, monkeypatch)
    await tracked(None, "GET", "/items", 200, object(), type=T.request_default)

    meta = call_storage.call_meta[("GET", "/items", "")][0]
    assert (meta["has_status_check"], meta["has_validate_model"]) == (True, True)


async def test_a_default_status_of_the_client_counts(monkeypatch):
    async def make_request(self, method, endpoint, expected_status_code=200, type=None):
        return None

    tracked = _tracked(make_request, monkeypatch)
    await tracked(None, "GET", "/items", type=T.request_default)

    meta = call_storage.call_meta[("GET", "/items", "")][0]
    assert (meta["has_status_check"], meta["has_validate_model"]) == (True, False)


async def test_a_client_without_those_parameters_is_not_measured(monkeypatch):
    async def make_request(self, method, endpoint, type=None):
        return None

    tracked = _tracked(make_request, monkeypatch)
    await tracked(None, "GET", "/items", type=T.request_default)

    meta = call_storage.call_meta[("GET", "/items", "")][0]
    assert "has_status_check" not in meta and "has_validate_model" not in meta
    assert _row(_analyze([_Path("GET", "/items")]), "/items").depth is None


async def test_a_kwargs_wrapper_is_read_from_its_keyword_arguments(monkeypatch):
    """`make_request(self, method, endpoint, *args, **kwargs)` forwarding to `ApiClient`."""
    async def make_request(self, method, endpoint, *args, **kwargs):
        return None

    tracked = _tracked(make_request, monkeypatch)
    await tracked(None, "GET", "/items", type=T.request_default, expected_status_code=200)
    await tracked(None, "GET", "/items", type=T.request_permissions)

    first, second = call_storage.call_meta[("GET", "/items", "")]
    assert (first["has_status_check"], first["has_validate_model"]) == (True, False)
    assert (second["has_status_check"], second["has_validate_model"]) == (False, False)


# --- the validator ------------------------------------------------------------------------


def _as_2_6(payload: dict) -> dict:
    """The same run as 2.6.0 wrote it: no rule, no depth, `exception` inside the average."""
    old = copy.deepcopy(payload)
    old["meta"].pop("avgRule")
    old["summary"].pop("depth")
    old["summary"].pop("scored")
    for ep in old["endpoints"]:
        ep.pop("depth")
    pcts = [ep["coverage"] for ep in old["endpoints"]]
    old["summary"]["avg"] = old["summary"]["avgAll"] = round(sum(pcts) / len(pcts), 2)
    return old


def test_a_2_6_file_is_valid_and_only_dated():
    old = _as_2_6(build_payload(_report(_mixed())))

    problems = validate_coverage_payload(old)

    assert [p for p in problems if p.severity is Severity.ERROR] == []
    assert {p.where for p in problems} == {"meta.avgRule", "summary.depth"}


def test_a_2_6_file_of_exception_rows_only_keeps_its_number():
    old = _as_2_6(build_payload(_report([_ep("/health", status="exception", pct=100.0)])))
    assert old["summary"]["avg"] == 100.0
    assert [p for p in validate_coverage_payload(old) if p.severity is Severity.ERROR] == []


def _errors(doc):
    return [str(p) for p in validate_coverage_payload(doc) if p.severity is Severity.ERROR]


def test_a_number_where_rule_2_has_nothing_to_average_is_an_error():
    doc = build_payload(_report([_ep("/health", status="exception", pct=100.0)]))
    doc["summary"]["avg"] = 100.0
    assert any("summary.avg" in e and "все — exception" in e for e in _errors(doc))


def test_null_under_rule_1_with_endpoints_is_still_an_error():
    doc = build_payload(_report([_ep("/health", status="exception", pct=100.0)]))
    doc["meta"].pop("avgRule")
    assert any("summary.avg" in e and "null при 1" in e for e in _errors(doc))


def test_a_newer_rule_is_noted_not_an_error():
    doc = build_payload(_report(_mixed()))
    doc["meta"]["avgRule"] = 3
    doc["summary"]["avg"] = 66.67  # whatever rule 3 means, it is not checked here

    problems = validate_coverage_payload(doc)

    assert _errors(doc) == []
    assert [(p.where, p.severity) for p in problems] == [("meta.avgRule", Severity.NEWER)]


@pytest.mark.parametrize("rule", [0, -1, "2", True, 2.0, None])
def test_a_rule_that_is_not_a_rule_is_an_error(rule):
    doc = build_payload(_report(_mixed()))
    doc["meta"]["avgRule"] = rule
    assert any("meta.avgRule" in e for e in _errors(doc)), _errors(doc)


def test_rows_with_depth_and_no_summary_depth_is_an_error():
    doc = build_payload(_report(_mixed()))
    del doc["summary"]["depth"]
    assert any("summary.depth" in e and "у строк depth есть" in e for e in _errors(doc))


@pytest.mark.parametrize(
    "patch",
    [
        lambda d: d["summary"].__setitem__("avg", 10**400),
        lambda d: d["summary"].__setitem__("avg", float("inf")),
        lambda d: d["summary"]["depth"].__setitem__("statusPct", 10**400),
        lambda d: d["summary"]["depth"].update(cells=10**400, status=10**400, schema=0),
        lambda d: d["meta"].__setitem__("unseenRatio", 10**400),
    ],
    ids=["avg", "avg-inf", "share", "counts", "ratio"],
)
def test_numbers_beyond_float_are_errors_not_exceptions(patch):
    doc = build_payload(_report(_mixed()))
    patch(doc)
    assert _errors(doc)  # reported, nothing raised


@pytest.mark.parametrize(
    "patch, needle",
    [
        (lambda d: d["endpoints"][2].__setitem__("depth", _d(1, 1, 0)), "строки exception"),
        (lambda d: d["endpoints"][0].__setitem__("depth", _d(0, 0, 0)), "0 клеток"),
        (lambda d: d["endpoints"][0].__setitem__("depth", _d(2, 1, 2)), "только после статуса"),
        (lambda d: d["endpoints"][0].__setitem__("depth", _d(2, 3, 0)), "со статусом из 2"),
        (lambda d: d["summary"]["depth"].__setitem__("schema", 0), "по сумме строк"),
        (lambda d: d["summary"]["depth"].__setitem__("statusPct", 12.0), "против 100.0"),
        (lambda d: d["summary"].__setitem__("depth", None), "null при 2 измеренных"),
        (lambda d: d["endpoints"][1].__setitem__("depth", _d(1, 1, 1)), "при нуле вызовов"),
    ],
    ids=["on-exception", "zero-cells", "schema-over-status", "status-over-cells",
         "summary-sum", "summary-share", "summary-null", "no-calls"],
)
def test_depth_that_contradicts_itself_is_found(patch, needle):
    doc = build_payload(_report(_mixed()))
    assert validate_coverage_payload(doc) == []
    patch(doc)
    assert any(needle in e for e in _errors(doc)), _errors(doc)


# --- compare ------------------------------------------------------------------------------


def _called():
    """Every endpoint called, so no partial-run warning muddies the verdict."""
    return [
        _ep("/api/items", status="full", pct=100.0, depth=_d(2, 2, 2)),
        _ep("/api/items/{id}", status="partial", pct=50.0, depth=_d(1, 1, 0)),
        _ep("/api/health", status="exception", pct=100.0),
    ]


def test_compare_recomputes_an_older_average_under_the_current_rule():
    new = build_payload(_report(_called()))
    old = _as_2_6(new)
    assert old["summary"]["avg"] == 83.33  # the health probe inside, as 2.6 wrote it

    diff = compare_payloads(old, new)

    assert diff["comparable"] is True, diff["warnings"]
    assert (diff["old_avg"], diff["new_avg"], diff["avg_delta"]) == (75.0, 75.0, 0.0)
    assert diff["avg_recomputed"] == {"side": "previous", "recorded": 83.33, "recomputed": 75.0}
    assert any("recomputed" in n and "1 exception endpoint(s)" in n for n in diff["notes"])
    assert diff["depth_delta"] is None  # the old run did not measure depth


def test_compare_cannot_recompute_a_trimmed_older_file():
    new = build_payload(_report(_called()))
    old = _as_2_6(new)
    old["endpoints"] = old["endpoints"][:2]  # summary.endpoints still says 3

    diff = compare_payloads(old, new)

    assert diff["comparable"] is False
    assert any("cannot be used to recompute" in w for w in diff["warnings"])
    assert diff["avg_recomputed"] is None


def test_compare_does_not_touch_a_rule_change_that_cannot_move_the_average():
    endpoints = [e for e in _called() if e.status != "exception"]
    new = build_payload(_report(endpoints))
    old = _as_2_6(new)

    diff = compare_payloads(old, new)

    assert diff["comparable"] is True, diff["warnings"]
    assert diff["avg_delta"] == 0.0 and diff["avg_recomputed"] is None and diff["notes"] == []


@pytest.mark.parametrize("rule", [3, "2", 2.5, None])
def test_compare_does_not_read_an_unknown_rule_as_rule_1(rule):
    old = build_payload(_report(_called()))
    new = copy.deepcopy(old)
    new["meta"]["avgRule"] = rule

    diff = compare_payloads(old, new)

    assert diff["comparable"] is False
    assert any("does not know" in w for w in diff["warnings"])


def test_compare_within_rule_2_is_comparable_and_reports_depth():
    old = build_payload(_report(_called()))
    new_rows = _called()
    new_rows[0].depth = _d(2, 2, 1)
    new = build_payload(_report(new_rows))

    diff = compare_payloads(old, new)

    assert diff["comparable"] is True, diff["warnings"]
    # schema 2/3 → 1/3 of the measured cells, each share rounded before the difference
    assert diff["depth_delta"] == {"statusPct": 0.0, "schemaPct": -33.34}


def test_compare_names_a_run_of_exception_rows_only():
    old = build_payload(_report(_called()))
    new = build_payload(_report([_ep("/api/health", status="exception", pct=100.0)]))

    diff = compare_payloads(old, new)

    assert diff["new_avg"] is None and diff["avg_delta"] is None
    assert any("no scored endpoints" in w for w in diff["warnings"])
    assert diff["comparable"] is False


@pytest.mark.parametrize(
    "patch",
    [
        lambda d: d.__setitem__("summary", ["not", "a", "mapping"]),
        lambda d: d.__setitem__("summary", None),
        lambda d: d["summary"].__setitem__("depth", {"statusPct": 10**400, "schemaPct": 1.0}),
        lambda d: d["summary"].__setitem__("avg", 10**400),
        lambda d: d["summary"].__setitem__("exception", "many"),
        lambda d: d.__setitem__("meta", "not a mapping"),
    ],
    ids=["summary-list", "summary-null", "depth-overflow", "avg-overflow", "exception-text", "meta-text"],
)
def test_compare_survives_a_malformed_side(patch):
    good = build_payload(_report(_called()))
    bad = copy.deepcopy(good)
    patch(bad)

    for pair in ((bad, good), (good, bad)):
        diff = compare_payloads(*pair)
        assert isinstance(diff["warnings"], list)


# --- the interactive page, executed -------------------------------------------------------

_PRINTING = HARNESS.replace('console.log("ok " + assigned.length);', "console.log(text);")


def _page_text(tmp_path, payload: dict) -> str:
    page = render_html(payload, title="t")
    script = re.findall(r"<script>(.*?)</script>", page, re.S)[0]
    # The data as the page embeds it — what its own JSON.parse reads.
    data = re.findall(r'<script id="coverage-data" type="application/json">(.*?)</script>', page, re.S)[0]
    (tmp_path / "harness.js").write_text(_PRINTING, encoding="utf-8")
    (tmp_path / "data.json").write_text(data, encoding="utf-8")
    (tmp_path / "report.js").write_text(script, encoding="utf-8")
    result = subprocess.run(
        [NODE, str(tmp_path / "harness.js"), str(tmp_path / "data.json"), str(tmp_path / "report.js")],
        capture_output=True, text=True, timeout=60, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _stat(text: str, label: str) -> str:
    match = re.search(re.escape(label) + r'</div><div class="value">([^<]*)<', text)
    assert match, label
    return match.group(1)


needs_node = pytest.mark.skipif(NODE is None, reason="node is not in PATH")


@needs_node
def test_the_page_averages_without_exception_rows_and_shows_depth(tmp_path):
    text = _page_text(tmp_path, build_payload(_report(_called())))

    assert _stat(text, "Average coverage") == "75.0%"
    assert _stat(text, "Cells: status asked") == "100%"
    assert _stat(text, "Cells: schema asked") == "67%"
    assert "status 2/2 · schema 2/2" in text


@needs_node
def test_the_page_keeps_the_rule_of_an_older_file(tmp_path):
    text = _page_text(tmp_path, _as_2_6(build_payload(_report(_called()))))

    assert _stat(text, "Average coverage") == "83.3%"  # as its summary.avg says
    assert _stat(text, "Cells: schema asked") == "—"


@needs_node
def test_the_page_shows_the_files_own_average_under_an_unknown_rule(tmp_path):
    doc = build_payload(_report(_called()))
    doc["meta"]["avgRule"] = 3
    doc["summary"]["avg"] = 12.5

    text = _page_text(tmp_path, doc)

    assert _stat(text, "Average coverage (file, avgRule 3)") == "12.5%"
    assert _stat(text, "Coverage (selected)") == "—"


@needs_node
def test_the_page_runs_on_a_run_of_exception_rows_only(tmp_path):
    text = _page_text(tmp_path, build_payload(_report([_ep("/health", status="exception", pct=100.0)])))

    assert _stat(text, "Average coverage") == "—"


_MARKUP = '<img src=x onerror="alert(1)">'


@needs_node
def test_numbers_from_the_file_never_reach_the_page_as_markup(tmp_path):
    doc = build_payload(_report(_called()))
    for ep in doc["endpoints"]:
        ep["calls"] = _MARKUP
        ep["coverage"] = _MARKUP
        ep["timing"] = {"msP95": _MARKUP}
    doc["endpoints"][0]["depth"] = {"cells": _MARKUP, "status": _MARKUP, "schema": _MARKUP}
    doc["timing"] = {"msAvg": _MARKUP, "msP95": _MARKUP}
    doc["meta"]["avgRule"] = _MARKUP
    doc["meta"]["workers"] = _MARKUP

    text = _page_text(tmp_path, doc)

    assert "<img" not in text
    assert "&lt;img" in text  # the one place it is shown: the rule, escaped
