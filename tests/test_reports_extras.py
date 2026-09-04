"""LIB-COV-* extras: service map, payload, compare, badge, stubs, CLI."""

from __future__ import annotations

import json
from pathlib import Path

from partest.methodology.subtypes import MethodSubtype
from partest.reports.analyzer import CoverageReport, EndpointCoverage
from partest.reports.badge import badge_from_payload
from partest.reports.compare import compare_payloads
from partest.reports.history import append_snapshot
from partest.reports.interactive_html import render_html
from partest.reports.payload import build_payload, filter_endpoints
from partest.reports.services import ServiceMap, resolve_service
from partest.reports.stubs import generate_stubs
from partest.reports.writer import write_enhanced_report
from partest.test_types import TypesTestCases as T


def _ep(method, path, *, coverage, status, calls=1, missing=None):
    return EndpointCoverage(
        method=method,
        path=path,
        description="demo",
        subtype=MethodSubtype.GET_DYNAMIC,
        subtype_label="GET DYNAMIC OBJECT",
        calls=calls,
        executed_types={T.request_default},
        required_p1=[T.request_default, T.request_not_found],
        required_all=[T.request_default, T.request_not_found],
        missing_p1=missing if missing is not None else [T.request_not_found],
        missing_all=[T.request_not_found],
        present_required=[T.request_default],
        coverage_pct=coverage,
        status=status,
    )


def _report():
    rows = [
        _ep("GET", "/api/v1/tasks/{id}", coverage=33.33, status="partial", calls=6),
        _ep("PUT", "/api/v1/tasks/{id}", coverage=0.0, status="empty", calls=0),
        _ep("GET", "/api/v1/clients", coverage=100.0, status="full", calls=10, missing=[]),
    ]
    return CoverageReport(
        endpoints=rows,
        average_pct=44.44,
        total_calls=16,
        full_count=1,
        partial_count=1,
        empty_count=1,
        exception_count=0,
        by_subtype={},
        by_swagger={},
    )


def test_service_map_longest_prefix_and_fallback():
    smap = ServiceMap.from_dict(
        {
            "api_prefixes": ["/api/v1/"],
            "services": {
                "tasks": {"label": "Tasks", "prefixes": ["/api/v1/tasks"]},
                "order-batches": {
                    "label": "Split packages",
                    "prefixes": ["/api/v1/order-batches"],
                },
            },
            "tags": {"Task Controller": "tasks"},
        }
    )
    assert resolve_service("/api/v1/tasks/{id}", service_map=smap).key == "tasks"
    assert resolve_service("/api/v1/order-batches/{id}", service_map=smap).key == "order-batches"
    assert resolve_service("/api/v1/widgets/{id}", service_map=smap).key == "widgets"
    assert (
        resolve_service("/api/v1/unknown", swagger_tags=["Task Controller"], service_map=smap).key
        == "tasks"
    )


def test_build_payload_and_interactive_html(tmp_path):
    payload = build_payload(_report(), title="demo")
    assert payload["summary"]["endpoints"] == 3
    assert "tasks" in {s["key"] for s in payload["services"]}
    html = render_html(payload, title="demo")
    assert "demo" in html
    assert "/api/v1/clients" in html
    paths = write_enhanced_report(_report(), html_path=tmp_path / "c.html", json_path=tmp_path / "c.json")
    assert paths.html.exists()
    assert json.loads(paths.json.read_text(encoding="utf-8"))["summary"]["endpoints"] == 3


def test_compare_badge_stubs_history(tmp_path):
    old = build_payload(_report())
    new_eps = list(old["endpoints"])
    new_eps[0] = {**new_eps[0], "coverage": 80.0, "missing": []}
    new = {**old, "endpoints": new_eps, "summary": {**old["summary"], "avg": 60.0}}
    diff = compare_payloads(old, new)
    assert diff["added"] == []
    assert any("RequestNotFound" in x or "request_not_found" in x for x in diff["missing_fixed"]) or diff[
        "missing_fixed"
    ]
    svg = badge_from_payload(new)
    assert "svg" in svg and "%" in svg
    stubs = generate_stubs(old)
    assert "types.request_" in stubs
    assert "type=types." in stubs
    snap = append_snapshot(new, tmp_path / "hist")
    assert snap.exists()


def test_filter_endpoints_search():
    payload = build_payload(_report())
    only = filter_endpoints(payload["endpoints"], search="clients")
    assert len(only) == 1
    assert only[0]["path"].endswith("/clients")


def test_cli_compare_and_badge(tmp_path):
    from partest.reports.__main__ import main

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    payload = build_payload(_report())
    a.write_text(json.dumps(payload), encoding="utf-8")
    b.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "diff.json"
    assert main(["compare", "--a", str(a), "--b", str(b), "--out", str(out)]) == 0
    assert out.exists()
    svg = tmp_path / "c.svg"
    assert main(["badge", "--json", str(a), "--out", str(svg)]) == 0
    assert "svg" in svg.read_text(encoding="utf-8")
    stubs = tmp_path / "stubs.py"
    assert main(["stubs", "--json", str(a), "--out", str(stubs)]) == 0
    assert "TypesTestCases" in stubs.read_text(encoding="utf-8")
