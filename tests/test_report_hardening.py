"""The report readers on documents someone else wrote, and the tracker on functions someone
else declared.

`coverage.json` is read by `compare`, the validator, the badge and both HTML pages, and it is
not always ours: a demonstration set, a hand-written fixture, a file from another stand. Each
reader here must answer — a finding, a warning, a dash — and never raise or turn a value into
markup. The tracker decorates the consumer's client at import time, so nothing it reads may
stop that module from importing.
"""

from __future__ import annotations

import copy
import json
import re
import sys

import pytest
from test_depth_and_exception_avg import _called, _ep, _page_text, _report, _stat
from test_html_script_node import NODE

from partest import coverage
from partest.call_storage import reset_storage
from partest.methodology import call_depth as facade_call_depth
from partest.methodology.api import steps
from partest.reports import validate_coverage_payload
from partest.reports.__main__ import main as reports_cli
from partest.reports.compare import compare_payloads
from partest.reports.html_coverage import render_html as render_static_html
from partest.reports.payload import build_payload

needs_node = pytest.mark.skipif(NODE is None, reason="node is not in PATH")
HUGE = 10**5000  # `str()` of it raises from Python 3.11 on


@pytest.fixture(autouse=True)
def _clean_storage():
    reset_storage()
    yield
    reset_storage()


def _as_rule_1(payload: dict, *, explicit: bool = False) -> dict:
    old = copy.deepcopy(payload)
    if explicit:
        old["meta"]["avgRule"] = 1
    else:
        old["meta"].pop("avgRule")
    pcts = [ep["coverage"] for ep in old["endpoints"]]
    old["summary"]["avg"] = old["summary"]["avgAll"] = round(sum(pcts) / len(pcts), 2)
    return old


# --- the tracker ----------------------------------------------------------------------------


@pytest.mark.skipif(sys.version_info < (3, 14), reason="annotations are lazy from Python 3.14")
def test_an_unresolvable_annotation_does_not_stop_the_decoration():
    """Python 3.14 evaluates annotations on `inspect.signature`; a name imported under
    `TYPE_CHECKING` would raise `NameError` at the consumer's import."""
    namespace: dict = {"track_api_calls": coverage.track_api_calls}
    exec(
        "@track_api_calls\n"
        "async def make_request(self, method, endpoint, expected_status_code: NotDefinedHere = None,\n"
        "                       validate_model: AlsoMissing = None, type=None):\n"
        "    return None\n",
        namespace,
    )
    assert coverage._depth_reader(namespace["make_request"].__wrapped__) is not None


def test_a_broken_signature_means_not_measured():
    class Odd:
        @property
        def __signature__(self):
            raise RuntimeError("broken")

        async def __call__(self, *args, **kwargs):
            return None

    assert coverage._depth_reader(Odd()) is None
    coverage.track_api_calls(Odd())  # decorating does not raise


def test_call_depth_is_declared_and_reexported():
    assert {"TestStep", "STEPS_BY_GROUP", "call_depth", "depth_score"} <= set(steps.__all__)
    assert facade_call_depth is steps.call_depth


# --- CoverageReport.scored_count -------------------------------------------------------------


def test_the_report_counts_what_it_averaged():
    import dataclasses

    report = _report(_called())
    assert report.scored_count == 2
    only_health = _report([_ep("/health", status="exception", pct=100.0)])
    assert (only_health.scored_count, only_health.average_pct) == (0, 0.0)
    # Read from `endpoints` each time: it follows `replace` and in-place edits.
    assert dataclasses.replace(report, endpoints=report.endpoints[:1]).scored_count == 1
    report.endpoints.append(_ep("/x", status="full", pct=100.0))
    assert report.scored_count == 3
    assert dataclasses.replace(report, endpoints=None).scored_count == 0


@pytest.mark.skipif(sys.version_info < (3, 14), reason="annotations are lazy from Python 3.14")
def test_a_payload_method_with_an_unresolvable_annotation_still_gets_self():
    from partest.payloads import _needs_self

    namespace: dict = {}
    exec("def make(self) -> NotDefinedHere:\n    return 1\n", namespace)
    assert _needs_self(namespace["make"]) is True


def test_a_payload_method_without_parameters_needs_no_self():
    from partest.payloads import _needs_self

    assert _needs_self(lambda: 1) is False
    assert _needs_self(lambda self: 1) is True


# --- the static page ------------------------------------------------------------------------


def test_a_path_cannot_leave_the_static_pages_script():
    path = '/y</script><img src=x onerror="alert(1)">'
    page = render_static_html(_report([_ep(path, status="partial", pct=50.0)]))

    assert page.count("</script>") == 1
    assert "<img" not in page
    script = re.findall(r"<script>(.*?)</script>", page, re.S)[0]
    assert "innerHTML" not in script


# --- the validator --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "patch",
    [
        lambda d: d["endpoints"][0].__setitem__("calls", HUGE),
        lambda d: d["endpoints"][0].__setitem__("calls", -HUGE),
        lambda d: d["meta"].__setitem__("callsTotal", HUGE),
        lambda d: d["summary"].__setitem__("endpoints", HUGE),
        lambda d: d["meta"].__setitem__("avgRule", HUGE),
        lambda d: d["endpoints"][0].__setitem__("depth", {"cells": HUGE, "status": HUGE, "schema": 0, "values": None}),
        lambda d: d["summary"]["depth"].update(cells=HUGE, status=HUGE, schema=HUGE),
        lambda d: d["endpoints"][0].__setitem__("method", HUGE),
    ],
    ids=["calls", "negative-calls", "callsTotal", "summary-endpoints", "avgRule", "row-depth",
         "summary-depth", "method"],
)
def test_the_validator_never_prints_a_number_it_cannot(patch):
    doc = build_payload(_report(_called()))
    patch(doc)
    problems = validate_coverage_payload(doc)
    assert problems
    assert all(isinstance(str(p), str) for p in problems)


# --- compare on a malformed side ------------------------------------------------------------


@pytest.mark.parametrize(
    "patch",
    [
        lambda d: d["endpoints"][0].__setitem__("method", 5),
        lambda d: d["endpoints"][0].__setitem__("calls", "x"),
        lambda d: d["endpoints"][0].__setitem__("calls", HUGE),
        lambda d: d["endpoints"][0].__setitem__("coverage", "x"),
        lambda d: d["endpoints"][0].__setitem__("missing", 5),
        lambda d: d["endpoints"][0].__setitem__("missing", [{}, ["a"]]),
        lambda d: d["endpoints"][0].__setitem__("kind", 5),
        lambda d: d["endpoints"].append("not a row"),
        lambda d: d.__setitem__("endpoints", "not a list"),
        lambda d: d["meta"].__setitem__("workers", "x"),
        lambda d: d["meta"].__setitem__("selection", {"markexpr": HUGE, "deselected": HUGE}),
        lambda d: d["meta"].__setitem__("selection", {"keyword": "k", "deselected": "x"}),
        lambda d: d["meta"].__setitem__("selection", {"optin": {"slow": ["x"]}}),
        lambda d: d["meta"].__setitem__("selection", {"optin": {"slow": {"deselected": "x", "state": HUGE}}}),
        lambda d: d["meta"].__setitem__("unseenRatio", float("inf")),
        lambda d: d["summary"].__setitem__("exception", HUGE),
        lambda d: d["meta"].__setitem__("avgRule", HUGE),
    ],
)
def test_compare_survives_a_malformed_value(patch):
    good = build_payload(_report(_called()))
    for bad in (copy.deepcopy(good), _as_rule_1(good)):
        patch(bad)
        for pair in ((bad, good), (good, bad)):
            diff = compare_payloads(*pair)
            json.dumps(diff, default=str)  # every message can be printed
            assert all(isinstance(w, str) for w in diff["warnings"] + diff["notes"])


@pytest.mark.parametrize("depth", ["x", [1], {"cells": HUGE, "status": 0, "schema": 0},
                                   {"cells": 2, "status": 3, "schema": 0}],
                         ids=["text", "list", "huge", "status-over-cells"])
def test_an_older_file_with_a_hostile_row_is_not_recomputed(depth):
    new = build_payload(_report(_called()))
    old = _as_rule_1(new)
    old["endpoints"][0]["depth"] = depth

    diff = compare_payloads(old, new)

    assert diff["comparable"] is False
    assert diff["avg_recomputed"] is None
    assert any("cannot be used to recompute" in w for w in diff["warnings"])


def test_an_older_file_whose_counts_disagree_with_its_rows_is_not_recomputed():
    new = build_payload(_report(_called()))
    old = _as_rule_1(new)
    old["endpoints"] = [e for e in old["endpoints"] if e["status"] != "partial"]
    old["summary"].pop("endpoints")  # the count that would have shown the trim

    diff = compare_payloads(old, new)

    assert diff["comparable"] is False and diff["avg_recomputed"] is None


def test_the_recompute_note_speaks_of_the_rule_not_of_the_release():
    new = build_payload(_report(_called()))
    diff = compare_payloads(_as_rule_1(new, explicit=True), new)

    assert diff["comparable"] is True, diff["warnings"]
    assert diff["notes"] and all("written before" not in n for n in diff["notes"])
    assert any("rule 1 (no meta.avgRule, or 1)" in n for n in diff["notes"])


def test_a_recorded_average_that_is_not_a_number_is_named_so():
    new = build_payload(_report(_called()))
    old = _as_rule_1(new)
    old["summary"]["avg"] = "x"

    diff = compare_payloads(old, new)

    assert any("(not a number)" in n for n in diff["notes"]), diff["notes"]
    assert all("None" not in n for n in diff["notes"])


def test_the_validator_checks_the_status_counters_against_the_rows():
    doc = build_payload(_report(_called()))
    assert validate_coverage_payload(doc) == []
    doc["summary"]["partial"] = 5
    problems = [str(p) for p in validate_coverage_payload(doc)]
    assert any("summary.partial" in p and "5 против 1" in p for p in problems), problems


def test_no_note_when_the_older_run_had_nothing_to_average():
    new = build_payload(_report(_called()))
    old = _as_rule_1(build_payload(_report([_ep("/api/health", status="exception", pct=100.0)])))

    diff = compare_payloads(old, new)

    assert diff["old_avg"] is None
    assert diff["avg_recomputed"]["recomputed"] is None
    assert diff["notes"] == []
    assert any("no scored endpoints" in w for w in diff["warnings"])


# --- the CLI --------------------------------------------------------------------------------


def _cli_args(command: str, bad, tmp_path) -> list:
    return {
        "render": ["render", "--json", str(bad), "--html", str(tmp_path / "o.html")],
        "badge": ["badge", "--json", str(bad), "--out", str(tmp_path / "o.svg")],
        "compare": ["compare", "--a", str(bad), "--b", str(bad)],
        "stubs": ["stubs", "--json", str(bad), "--out", str(tmp_path / "o.py")],
        "history-append": ["history-append", "--json", str(bad), "--dir", str(tmp_path / "h")],
    }[command]


_COMMANDS = ["render", "badge", "compare", "stubs", "history-append"]


@pytest.mark.parametrize("content", ["[1, 2]", "not json", '"text"', "[" * 200_000],
                         ids=["list", "not-json", "string", "deep"])
@pytest.mark.parametrize("command", _COMMANDS)
def test_the_cli_names_a_file_it_cannot_read(tmp_path, capsys, content, command):
    """Exit 1 — the input; 2 stays "not comparable" under `compare --strict`."""
    bad = tmp_path / "bad.json"
    bad.write_text(content, encoding="utf-8")

    assert reports_cli(_cli_args(command, bad, tmp_path)) == 1
    assert capsys.readouterr().err.startswith("error: ")


@pytest.mark.parametrize(
    "content",
    ['{"endpoints": 5}', '{"endpoints": [null]}', '{"endpoints": [1, "x"]}', '{"missing": 5}'],
    ids=["endpoints-number", "null-row", "scalar-rows", "no-endpoints"],
)
@pytest.mark.parametrize("command", ["stubs", "history-append"])
def test_stubs_and_history_refuse_a_document_of_the_wrong_shape(tmp_path, capsys, content, command):
    bad = tmp_path / "bad.json"
    bad.write_text(content, encoding="utf-8")

    assert reports_cli(_cli_args(command, bad, tmp_path)) == 1
    assert capsys.readouterr().err.startswith("error: ")
    assert not (tmp_path / "h").exists() or not list((tmp_path / "h").iterdir())
    assert not (tmp_path / "o.py").exists()


def test_compare_strict_still_exits_2(tmp_path):
    new = build_payload(_report(_called()))
    old = copy.deepcopy(new)
    old["meta"]["avgRule"] = 3
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(old), encoding="utf-8")
    b.write_text(json.dumps(new), encoding="utf-8")
    assert reports_cli(["compare", "--a", str(a), "--b", str(b), "--strict"]) == 2


# --- stubs: strings from the file are not code ------------------------------------------------

_INJECTED = '/x", __import__("os").getcwd(), "'


def _hostile_stub_payload() -> dict:
    doc = build_payload(_report(_called()))
    doc["endpoints"] = [
        {"method": "GET", "path": _INJECTED, "missing": ["Default"]},
        {"method": 'GET"""\nimport os\n"""', "path": "/a\n\"\"\"\nprint(1)\n", "missing": ["Default"]},
        {"method": "GET", "path": "/b", "missing": ["request_default; import os", "x y", 5, None]},
        {"method": 5, "path": "/c", "missing": ["Default"]},
        {"method": "GET", "path": "/d", "missing": 5},
        "not a row",
    ]
    return doc


def test_stubs_write_strings_as_literals_and_skip_what_is_not_a_name():
    import ast

    from partest.reports.stubs import generate_stubs

    source = generate_stubs(_hostile_stub_payload())
    tree = ast.parse(source)

    module_level = [type(node).__name__ for node in tree.body]
    assert module_level == ["Expr", "Import", "ImportFrom", "ClassDef"]
    (cls,) = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    tests = [n for n in cls.body if isinstance(n, ast.AsyncFunctionDef)]
    assert len(tests) == 2  # the injected path and the multi-line one, as plain strings
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    called = {ast.unparse(c.func) for c in calls}
    assert called == {"pytest.mark.skip", "api_client.make_request"}
    literals = [c.args[1].value for c in calls if ast.unparse(c.func) == "api_client.make_request"]
    assert _INJECTED in literals
    assert source.count("# skipped: a missing type that is not a plain name") == 4


def test_running_the_generated_stubs_runs_nothing_injected(tmp_path):
    from partest.reports.stubs import generate_stubs

    marker = tmp_path / "ran"
    doc = build_payload(_report(_called()))
    doc["endpoints"] = [{"method": "GET", "missing": ["Default"],
                         "path": f'/x", open({str(marker)!r}, "w").close(), "'}]
    module = tmp_path / "stubs_mod.py"
    module.write_text(generate_stubs(doc), encoding="utf-8")

    namespace: dict = {}
    exec(compile(module.read_text(encoding="utf-8"), str(module), "exec"), namespace)

    assert not marker.exists()


# --- the interactive page -------------------------------------------------------------------


@needs_node
def test_not_a_number_in_the_file_does_not_blank_the_page(tmp_path):
    doc = build_payload(_report(_called()))
    doc["summary"]["avg"] = float("nan")
    doc["endpoints"][0]["coverage"] = float("inf")
    doc["timing"] = {"msAvg": float("nan"), "msP95": HUGE}

    text = _page_text(tmp_path, doc)

    assert _stat(text, "Latency avg") == "—"


@needs_node
@pytest.mark.parametrize("name", ["constructor", "__proto__", "toString", "hasOwnProperty"])
def test_names_that_objects_inherit_are_names(tmp_path, name):
    rows = _called()
    for ep in rows:
        ep.path = f"/api/{name}{ep.path[len('/api/items'):]}" if ep.path.startswith("/api/items") else ep.path
    doc = build_payload(_report(rows))
    for ep in doc["endpoints"]:
        ep["subtype"] = name
        ep["method"] = name
        ep["status"] = name if ep["status"] == "partial" else ep["status"]

    text = _page_text(tmp_path, doc)

    assert name in text




@needs_node
@pytest.mark.parametrize("meta", ["text", [1], None, 5], ids=["text", "list", "null", "number"])
def test_meta_that_is_not_an_object_does_not_stop_the_page(tmp_path, meta):
    doc = build_payload(_report(_called()))
    doc["meta"] = meta

    text = _page_text(tmp_path, doc)

    # No readable meta, no rule: the rule a file without the key follows (1).
    assert _stat(text, "Average coverage") == "83.3%"


@needs_node
def test_a_rule_written_as_a_float_is_an_unknown_rule_on_the_page(tmp_path):
    doc = build_payload(_report(_called()))
    doc["meta"]["avgRule"] = 2.0
    doc["summary"]["avg"] = 12.5

    text = _page_text(tmp_path, doc)

    assert _stat(text, "Average coverage (file, avgRule 2.0)") == "12.5%"


@needs_node
@pytest.mark.parametrize("excluded", ["items", {"items": 1}, 5], ids=["text", "object", "number"])
def test_default_excluded_that_is_not_a_list_does_not_stop_the_page(tmp_path, excluded):
    doc = build_payload(_report(_called()))
    doc["meta"]["defaultExcluded"] = excluded

    text = _page_text(tmp_path, doc)

    assert _stat(text, "Average coverage") == "75.0%"


@pytest.mark.parametrize("endpoints", [{}, 0, "", False], ids=["object", "zero", "empty-text", "false"])
def test_stubs_refuse_endpoints_that_are_falsy_but_not_a_list(endpoints):
    from partest.reports.stubs import generate_stubs

    with pytest.raises(ValueError):
        generate_stubs({"endpoints": endpoints})


def test_stubs_read_absent_or_null_endpoints_as_none():
    from partest.reports.stubs import generate_stubs

    assert "test_no_missing_p1" in generate_stubs({})
    assert "test_no_missing_p1" in generate_stubs({"endpoints": None})


def test_render_of_a_deeply_nested_file_is_an_input_error(tmp_path, capsys):
    deep = tmp_path / "deep.json"
    deep.write_text('{"meta": {}, "endpoints": [], "x": ' + "[" * 950 + "]" * 950 + "}", encoding="utf-8")

    code = reports_cli(["render", "--json", str(deep), "--html", str(tmp_path / "o.html")])

    assert code in (0, 1)  # rendered, or refused by name — never a traceback
    if code == 1:
        assert capsys.readouterr().err.startswith("error: ")


@pytest.mark.parametrize("command", ["stubs", "render", "badge"])
def test_an_output_that_cannot_be_written_is_an_error(tmp_path, capsys, command):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(build_payload(_report(_called()))), encoding="utf-8")
    out = tmp_path / "missing-dir" / "deeper" / "out"
    args = {
        "stubs": ["stubs", "--json", str(good), "--out", str(out)],
        "render": ["render", "--json", str(good), "--html", str(out)],
        "badge": ["badge", "--json", str(good), "--out", str(out)],
    }[command]

    assert reports_cli(args) == 1
    assert capsys.readouterr().err.startswith("error: ")


def test_history_does_not_store_bare_nan(tmp_path):
    doc = build_payload(_report(_called()))
    doc["summary"]["avg"] = float("nan")
    doc["meta"]["unseenRatio"] = float("inf")
    src = tmp_path / "in.json"
    src.write_text(json.dumps(doc), encoding="utf-8")

    assert reports_cli(["history-append", "--json", str(src), "--dir", str(tmp_path / "h")]) == 0

    (snapshot,) = list((tmp_path / "h").iterdir())

    def refuse(token):
        raise AssertionError(f"bare {token} in the snapshot")

    stored = json.loads(snapshot.read_text(encoding="utf-8"), parse_constant=refuse)
    assert stored["summary"]["avg"] is None and stored["meta"]["unseenRatio"] is None
