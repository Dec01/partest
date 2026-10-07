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


def test_status_independent_signals_still_decide_first():
    """These never raised for a set; their answer must not change."""
    broken = infer((200, 404), method="POST", content=b'{"a":', content_type="application/json")
    assert broken.test_type == T.request_incorrect_body
    assert broken.reason == "raw content is not valid JSON"

    listing = infer((200, 404), params={"page": 1})
    assert listing.test_type == T.request_params


def test_a_long_run_of_statuses_is_named_compactly():
    result = infer(range(200, 300))
    assert result.test_type == T.request_default
    assert "{200-299}" in result.reason


@pytest.mark.parametrize("expected", [(), [], ("abc",), [object()]], ids=["empty", "list", "text", "object"])
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
