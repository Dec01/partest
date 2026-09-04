"""Coverage analyzer + HTML report smoke tests."""

from partest.call_storage import reset_storage, record_call
from partest.methodology.subtypes import MethodSubtype
from partest.reports.analyzer import CoverageAnalyzer
from partest.reports.html_coverage import render_html, write_html_report
from partest.test_types import TypesTestCases as T


class FakePath:
    def __init__(self, method, path, description="", deprecated=False, request_body=None, parameters=None):
        self.method = method
        self.path = path
        self.description = description
        self.deprecated = deprecated
        self.request_body = request_body
        self.parameters = parameters or []
        self.source_type = "test-api"


def test_analyzer_missing_p1(tmp_path):
    reset_storage()
    paths = [
        FakePath("GET", "/items", "List"),
        FakePath("POST", "/items", "Create", request_body=object()),
    ]
    record_call(("GET", "/items", "List"), T.request_default, subtype=MethodSubtype.GET_LIST.value)
    # POST has no calls

    report = CoverageAnalyzer(paths, use_matrix=True).analyze()
    assert len(report.endpoints) == 2

    get_ep = next(e for e in report.endpoints if e.method == "GET")
    assert get_ep.calls == 1
    assert T.request_default in get_ep.executed_types
    # permissions still missing for list
    assert T.request_permissions in get_ep.missing_p1

    post_ep = next(e for e in report.endpoints if e.method == "POST")
    assert post_ep.calls == 0
    assert post_ep.status == "empty"
    assert T.request_new_object in post_ep.missing_p1

    html = render_html(report)
    assert "partest API coverage" in html
    assert "/items" in html

    out = write_html_report(report, tmp_path / "coverage_report.html")
    assert out.exists()
    assert "Average coverage" in out.read_text(encoding="utf-8")
