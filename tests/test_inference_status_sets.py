"""A set of allowed statuses used to crash type inference.

``make_request(expected_status_code=(200, 400))`` without ``type=`` reached
``200 <= status < 300`` with a tuple and raised ``TypeError`` — inside the coverage
decorator, before the request was sent, so the test died on a harness defect rather than
on anything the API did. The rule now: each status of the set is inferred on its own; one
shared type stands at the lowest confidence among them, a split is ``unknown`` with the
split named in the reason.
"""

from __future__ import annotations

import httpx
import pytest

from partest import call_storage, coverage
from partest.client import ApiClient
from partest.methodology.api.inference import infer_test_type
from partest.test_types import TypesTestCases as T


def infer(expected, **kwargs):
    kwargs.setdefault("method", "GET")
    kwargs.setdefault("endpoint", "/items")
    return infer_test_type(expected_status_code=expected, **kwargs)


@pytest.mark.parametrize(
    "expected",
    [(200, 400), [200, 400], {200, 400}, frozenset({200, 400}), range(200, 500, 200)],
    ids=["tuple", "list", "set", "frozenset", "range"],
)
def test_a_set_of_statuses_does_not_raise(expected):
    result = infer(expected)
    assert result.test_type == T.type_unknown
    assert result.confidence < 0.5
    assert result.inferred is True


def test_a_split_set_names_which_status_implies_what():
    result = infer((200, 400))
    assert "{200, 400}" in result.reason
    assert "200" in result.reason and T.request_default in result.reason
    assert "type=" in result.reason


def test_statuses_of_one_class_can_still_mean_two_cells():
    """404 and 405 are both 4xx and still two different test cases."""
    result = infer((404, 405))
    assert result.test_type == T.type_unknown
    assert T.request_not_found in result.reason and T.request_not_allowed in result.reason


def test_an_agreeing_set_keeps_the_type_at_its_weakest_confidence():
    assert infer((200, 201)).test_type == T.request_default
    assert infer((200, 201)).confidence == infer(200).confidence

    permissions = infer((401, 403))
    assert permissions.test_type == T.request_permissions
    assert permissions.confidence == min(infer(401).confidence, infer(403).confidence)
    assert "every expected status in {401, 403} agrees" in permissions.reason


def test_a_one_element_set_means_what_the_status_means():
    assert infer((404,)).test_type == infer(404).test_type == T.request_not_found
    assert infer((404,)).confidence == infer(404).confidence


def test_a_set_reaches_the_rules_that_depend_on_the_status():
    """CT abuse with a JSON body counts as incorrect-body only under 400/415."""
    result = infer(
        (400, 415),
        method="POST",
        json_data={"a": 1},
        content_type="text/plain",
    )
    assert result.test_type == T.request_incorrect_body
    assert result.confidence >= 0.99


@pytest.mark.parametrize(
    "kwargs",
    [
        {"method": "GET", "params": {"page": 1}},
        {"method": "POST", "files": {"file": ("a.txt", b"x", "text/plain")}},
        {"method": "POST", "content": b'{"a":', "content_type": "application/json"},
        {"method": "GET"},
    ],
    ids=["list-params", "files", "broken-body", "plain"],
)
@pytest.mark.parametrize("status", [404, 405, 200, 400, 401])
def test_a_one_element_set_is_the_status_whatever_else_the_call_carries(status, kwargs):
    single = infer(status, **kwargs)
    as_set = infer((status,), **kwargs)
    assert as_set.test_type == single.test_type
    assert as_set.confidence == single.confidence


BROKEN = {"method": "POST", "content": b'{"a":', "content_type": "application/json"}


@pytest.mark.parametrize("expected", [(200, 404), (200, 400), [404, 405], {401, 403}, range(200, 300)])
def test_status_independent_signals_still_decide_first(expected):
    """A set of several statuses never raised when such a signal was present, and its
    answer was the signal's. A call that worked in 2.4.0 keeps its cell."""
    broken = infer(expected, **BROKEN)
    assert broken.test_type == T.request_incorrect_body
    assert broken.confidence >= 0.99
    assert broken.reason == "raw content is not valid JSON"

    listing = infer(expected, params={"page": 1})
    assert listing.test_type == T.request_params

    upload = infer(expected, method="POST", files={"file": ("a.txt", b"x", "text/plain")})
    assert upload.test_type == T.request_default and upload.confidence == 0.5


@pytest.mark.parametrize("expected", [(), [], set()], ids=["tuple", "list", "set"])
def test_an_empty_set_means_no_status_was_given(expected):
    assert infer(expected) == infer(None)
    assert infer(expected, **BROKEN) == infer(None, **BROKEN)
    assert infer(expected, params={"page": 1}) == infer(None, params={"page": 1})


def test_a_huge_set_is_refused_without_being_expanded():
    result = infer(range(0, 10**12))
    assert result.test_type == T.type_unknown
    assert "no usable status" in result.reason


def test_a_one_shot_iterator_is_not_read_and_counts_as_no_status():
    import itertools

    statuses = iter([401, 403])
    assert infer(statuses) == infer(None)
    assert list(statuses) == [401, 403], "inference must leave the iterator to the status check"
    assert infer(itertools.count(200)) == infer(None)  # infinite, and not a hang


def test_a_long_run_of_statuses_is_named_compactly():
    result = infer(range(200, 300))
    assert result.test_type == T.request_default
    assert "{200-299}" in result.reason


@pytest.mark.parametrize("expected", [("abc",), [object()], ("abc", "def")], ids=["text", "object", "two"])
def test_a_set_with_no_usable_status_is_unknown_not_an_error(expected):
    result = infer(expected)
    assert result.test_type == T.type_unknown
    assert "no usable status" in result.reason


@pytest.mark.parametrize(
    "expected, expected_type",
    [(200, T.request_default), (404, T.request_not_found), (405, T.request_not_allowed),
     (401, T.request_permissions), (None, T.type_unknown)],
)
def test_single_statuses_are_inferred_as_before(expected, expected_type):
    assert infer(expected).test_type == expected_type


def test_explicit_type_still_wins_over_a_set():
    result = infer((200, 400), explicit_type=T.request_elements)
    assert result.test_type == T.request_elements
    assert result.inferred is False


class _Path:
    def __init__(self, method, path):
        self.method = method
        self.path = path
        self.description = ""
        self.parameters = []
        self.request_body = None


@pytest.mark.asyncio
async def test_make_request_with_a_status_set_and_no_type_records_the_call(monkeypatch):
    """The regression as a consumer met it: through the decorator, not the function."""
    monkeypatch.setattr(coverage, "SWAGGER_AVAILABLE", True)
    monkeypatch.setattr(coverage, "swagger_files", ["stub"])
    monkeypatch.setattr(coverage, "paths_info", [_Path("POST", "/items")])
    call_storage.reset_storage()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "nope"})

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
            api = ApiClient("http://stand", client=hx)
            body = await api.make_request(
                "POST", "/items", json_data={"a": 1}, expected_status_code=(200, 400)
            )
        assert body == {"error": "nope"}
        key = ("POST", "/items", "")
        assert call_storage.call_type[key] == [T.type_unknown]
        meta = call_storage.call_meta[key][0]
        assert meta["inferred"] is True and "{200, 400}" in meta["reason"]
    finally:
        call_storage.reset_storage()


@pytest.mark.asyncio
async def test_make_request_with_a_generator_of_statuses_is_left_intact(monkeypatch):
    """Inference reads nothing from a one-shot iterator: the status check still sees 404."""
    monkeypatch.setattr(coverage, "SWAGGER_AVAILABLE", True)
    monkeypatch.setattr(coverage, "swagger_files", ["stub"])
    monkeypatch.setattr(coverage, "paths_info", [_Path("GET", "/items")])
    call_storage.reset_storage()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "gone"})

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
            api = ApiClient("http://stand", client=hx)
            body = await api.make_request(
                "GET", "/items", expected_status_code=(s for s in (200, 404))
            )
        assert body == {"error": "gone"}
        assert call_storage.call_type[("GET", "/items", "")] == [T.type_unknown]
    finally:
        call_storage.reset_storage()
