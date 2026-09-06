"""A corpus for the one function that decides which endpoint a call is counted against.

`_resolve_endpoint` turns a call — endpoint plus `add_url*` plus `after_url` — into the
OpenAPI template used as the coverage key. When it is wrong nothing fails: the call is
recorded against another operation, or against none, and the report is confidently
incorrect. That failure mode is why this file is a table rather than a handful of cases.

It exercises the real entry point with a stubbed specification, not just the pure matcher
underneath, because the wiring between them is where the previous heuristic went wrong.
"""

from __future__ import annotations

import pytest

from partest import coverage


class _Param:
    def __init__(self, name, type_="path", schema=None):
        self.name = name
        self.type = type_
        self.schema = schema


class _Path:
    """Stand-in for a parsed OpenAPI operation."""

    def __init__(self, method, path, description="", parameters=None):
        self.method = method
        self.path = path
        self.description = description
        self.parameters = parameters or []
        self.request_body = None


SPEC = [
    _Path("GET", "/orders"),
    _Path("GET", "/orders/{id}", parameters=[_Param("id")]),
    _Path("GET", "/orders/user"),
    _Path("GET", "/orders/customer/{customerId}", parameters=[_Param("customerId")]),
    _Path("POST", "/orders/{id}/publish", parameters=[_Param("id")]),
    _Path("GET", "/orders/{id}/lines/{lineId}",
          parameters=[_Param("id"), _Param("lineId")]),
    _Path("GET", "/catalog/{kind}", parameters=[_Param("kind", schema={"enum": ["books", "toys"]})]),
    _Path("GET", "/a/{p1}/b/{p2}/c/{p3}/d/{p4}",
          parameters=[_Param(f"p{i}") for i in range(1, 5)]),
]


@pytest.fixture(autouse=True)
def spec(monkeypatch):
    monkeypatch.setattr(coverage, "paths_info", SPEC)


def resolve(method, endpoint, **kwargs):
    return coverage._resolve_endpoint(endpoint, kwargs, method)


# (label, method, endpoint, call kwargs, expected key)
CORPUS = [
    (
        "collection with no parameters",
        "GET", "/orders", {}, "/orders",
    ),
    (
        "single id becomes the template parameter",
        "GET", "/orders", {"add_url1": "/5"}, "/orders/{id}",
    ),
    (
        "nested template wins over the generic id",
        "GET", "/orders/customer", {"add_url1": "/5"}, "/orders/customer/{customerId}",
    ),
    (
        "a literal segment beats a placeholder of the same length",
        "GET", "/orders", {"add_url1": "/user"}, "/orders/user",
    ),
    (
        "a verb suffix resolves to its own operation",
        "POST", "/orders", {"add_url1": "/12", "add_url2": "/publish"},
        "/orders/{id}/publish",
    ),
    (
        "two parameters in one path",
        "GET", "/orders", {"add_url1": "/5", "add_url2": "/lines", "add_url3": "/9"},
        "/orders/{id}/lines/{lineId}",
    ),
    (
        "an enum value is still a path parameter",
        "GET", "/catalog", {"add_url1": "/books"}, "/catalog/{kind}",
    ),
    (
        "a value outside the enum resolves the same way",
        "GET", "/catalog", {"add_url1": "/anything"}, "/catalog/{kind}",
    ),
    (
        "more than three segments — the old heuristic stopped at three",
        "GET", "/a",
        {"add_url1": "/1", "add_url2": "/b", "add_url3": "/2", "add_url4": "/c",
         "add_url5": "/3", "after_url": "/d/4"},
        "/a/{p1}/b/{p2}/c/{p3}/d/{p4}",
    ),
    (
        "after_url participates in matching",
        "GET", "/orders", {"add_url1": "/5", "after_url": "/lines/9"},
        "/orders/{id}/lines/{lineId}",
    ),
    (
        "defining_url wins over everything",
        "GET", "/orders", {"add_url1": "/5", "defining_url": "/orders/customer/{customerId}"},
        "/orders/customer/{customerId}",
    ),
    (
        "method is part of the key: POST does not borrow a GET template",
        "POST", "/orders", {"add_url1": "/5", "add_url2": "/publish"},
        "/orders/{id}/publish",
    ),
]


@pytest.mark.parametrize(
    "label, method, endpoint, kwargs, expected",
    CORPUS,
    ids=[case[0] for case in CORPUS],
)
def test_coverage_key(label, method, endpoint, kwargs, expected):
    assert resolve(method, endpoint, **kwargs) == expected


def test_unknown_path_does_not_borrow_someone_elses_template():
    """A call the specification does not describe must not land on a real endpoint."""
    assert resolve("GET", "/unknown", add_url1="/5") not in {
        p.path for p in SPEC
    }


def test_resolution_is_stable_across_calls():
    """The same call must always produce the same key, whatever ran before it."""
    first = resolve("GET", "/orders", add_url1="/5")
    resolve("GET", "/orders/customer", add_url1="/7")
    resolve("GET", "/catalog", add_url1="/books")
    assert resolve("GET", "/orders", add_url1="/5") == first


def test_empty_specification_falls_back_without_raising(monkeypatch):
    """A suite with no loaded specification still records something rather than failing."""
    monkeypatch.setattr(coverage, "paths_info", [])
    assert resolve("GET", "/orders", add_url1="/5")
