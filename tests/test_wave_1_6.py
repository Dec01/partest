"""Acceptance tests for the 1.6 wave.

Every case here comes from a concrete failure reported by a consumer suite and
recorded in ``docs/raw/aqa/2026-09-04/``. Each one silently produced a wrong
coverage number or a leftover row on the stand rather than a red test, which is
why they are pinned here.
"""

from __future__ import annotations

import asyncio

import pytest

from partest.methodology.classifier import classify_endpoint
from partest.methodology.subtypes import MethodSubtype
from partest.path_match import build_concrete_url, match_template
from partest.payloads import BaseRequestBody
from partest.test_types import PERMISSION_CELLS, permission_cell_label
from partest.tracking import CreatedRegistry, TrackingApiClient


# --- LIB-CLASSIFY-TOKEN ---------------------------------------------------


@pytest.mark.parametrize(
    "path, description",
    [
        ("/media-types", "Media types dictionary"),
        ("/departments", "List departments"),
        ("/mentions", "List mentions"),
        ("/measurements", "List measurements"),
        ("/companies", "List companies"),
    ],
)
def test_substring_me_does_not_mean_self_scope(path, description):
    """"me" inside media/departments/mentions used to classify as GET BY SELF."""
    assert classify_endpoint("GET", path, description) is not MethodSubtype.GET_BY_SELF


@pytest.mark.parametrize("path", ["/users/me", "/me", "/profile", "/my/orders"])
def test_real_self_scope_still_detected(path):
    assert classify_endpoint("GET", path, "") is MethodSubtype.GET_BY_SELF


def test_self_scope_from_operation_id():
    assert (
        classify_endpoint("GET", "/accounts", "", operation_id="getCurrentUserAccount")
        is MethodSubtype.GET_BY_SELF
    )


def test_media_types_is_not_an_upload():
    """The upload hint "media" must not swallow the "media-types" dictionary."""
    assert classify_endpoint("POST", "/media-types", "Create media type") is (
        MethodSubtype.POST_CREATE
    )


def test_media_is_still_an_upload():
    assert classify_endpoint("POST", "/media", "Upload media") is MethodSubtype.POST_UPLOAD


# --- LIB-CLASSIFY-ACTION --------------------------------------------------


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/items/{id}/publish"),
        ("POST", "/orders/{orderId}/cancel"),
        ("POST", "/reports/{id}/calculate"),
        ("PATCH", "/items/{id}/activate"),
        ("PUT", "/items/{id}/approve"),
    ],
)
def test_verb_as_last_segment_is_an_action(method, path):
    """A verb segment creates nothing, so RequestNewObject must stay out of its P1."""
    assert classify_endpoint(method, path, "") is MethodSubtype.ACTION


def test_child_under_parent_is_still_a_create():
    assert classify_endpoint("POST", "/posts/{id}/comments", "Add comment") is (
        MethodSubtype.POST_CREATE_TO_OBJECT
    )


def test_action_wins_over_create_wording():
    """"Create a copy" is still an action: nothing new is addressable afterwards."""
    assert classify_endpoint("POST", "/orders/{id}/copy", "Create a copy") is (
        MethodSubtype.ACTION
    )


# --- LIB-PATH-RESOLVE -----------------------------------------------------


def test_nested_template_beats_generic_id():
    """Acceptance from the spec: /orders/customer/5 is not /orders/{id}."""
    url = build_concrete_url("/orders/customer", ["/5"])
    assert url == "/orders/customer/5"
    assert match_template(url, ["/orders/{id}", "/orders/customer/{customerId}"]) == (
        "/orders/customer/{customerId}"
    )


def test_literal_segment_beats_placeholder_at_equal_length():
    assert match_template("/orders/user", ["/orders/{id}", "/orders/user"]) == "/orders/user"


def test_action_suffix_resolves_to_its_own_template():
    url = build_concrete_url("/orders", ["/12", "/publish"])
    assert url == "/orders/12/publish"
    assert match_template(url, ["/orders/{id}", "/orders/{id}/publish"]) == (
        "/orders/{id}/publish"
    )


def test_segment_count_must_match():
    assert match_template("/orders/12", ["/orders/{id}/publish"]) is None


def test_no_candidate_returns_none():
    assert match_template("/unknown/1", ["/orders/{id}"]) is None


def test_query_string_and_trailing_slash_are_ignored():
    assert match_template("/orders/12/?page=1", ["/orders/{id}"]) == "/orders/{id}"


def test_build_concrete_url_skips_empty_parts():
    assert build_concrete_url("/items", ["", None, "/7"], "") == "/items/7"


# --- LIB-TRACK-VALIDATE ---------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code=201, payload=None):
        self.status_code = status_code
        self.payload = payload if payload is not None else {"id": 1, "extra": 1}


class _FakeClient:
    """Minimal ApiClient stand-in: fires hooks, then fails schema validation."""

    def __init__(self, status_code=201, payload=None):
        self._hooks = []
        self._response = _FakeResponse(status_code, payload)

    def add_response_hook(self, hook):
        self._hooks.append(hook)

    async def make_request(self, method, endpoint, *args, **kwargs):
        for hook in self._hooks:
            hook(method, endpoint, self._response.payload, self._response)
        if kwargs.get("validate_model") is not None:
            raise AssertionError("Response data validation failed: extra fields")
        return self._response.payload


def test_created_id_is_tracked_even_when_validation_fails():
    """201 + a new response field + extra=forbid used to leave an untracked row."""
    registry = CreatedRegistry()
    client = _FakeClient()
    api = TrackingApiClient("http://stand", registry, client=client, instrument=False)

    async def run():
        await api.make_request("POST", "/items", validate_model=object())

    with pytest.raises(AssertionError):
        asyncio.run(run())

    assert registry.items == (("/items", 1),)


def test_successful_create_is_tracked_exactly_once():
    registry = CreatedRegistry()
    client = _FakeClient()
    api = TrackingApiClient("http://stand", registry, client=client, instrument=False)

    asyncio.run(api.make_request("POST", "/items"))

    assert registry.count == 1


def test_error_response_is_not_tracked():
    registry = CreatedRegistry()
    client = _FakeClient(status_code=400, payload={"id": 99})
    api = TrackingApiClient("http://stand", registry, client=client, instrument=False)

    asyncio.run(api.make_request("POST", "/items"))

    assert registry.count == 0


def test_response_without_id_is_not_tracked():
    registry = CreatedRegistry()
    client = _FakeClient(payload={"status": "ok"})
    api = TrackingApiClient("http://stand", registry, client=client, instrument=False)

    asyncio.run(api.make_request("POST", "/items"))

    assert registry.count == 0


def test_client_without_hook_support_still_tracks():
    class _Legacy:
        async def make_request(self, method, endpoint, *args, **kwargs):
            return {"id": 5}

    registry = CreatedRegistry()
    api = TrackingApiClient("http://stand", registry, client=_Legacy(), instrument=False)

    asyncio.run(api.make_request("POST", "/items"))

    assert registry.items == (("/items", 5),)


# --- CreatedRegistry.snapshot / since -------------------------------------


def test_snapshot_and_since_drain_only_the_tail():
    registry = CreatedRegistry()
    registry.track("/items", 1)
    mark = registry.snapshot()
    registry.track("/items", 2)
    registry.track("/items", 3)

    tail = registry.since(mark)

    assert tail.items == (("/items", 2), ("/items", 3))
    assert registry.count == 3, "since() must not mutate the source registry"


# --- LIB-BODY-MARK --------------------------------------------------------


class _Body(BaseRequestBody):
    _json_main = {"buyUnit": "PCS", "name": "AQA Item 42", "note": "ignored"}
    _required = ["buyUnit"]
    _cleanup_fields = ["name"]


def test_required_only_payload_stays_minimal():
    assert _Body.get_json_required() == {"buyUnit": "PCS"}


def test_marked_payload_adds_cleanup_fields():
    """Without the marked field a required-only create is invisible to cleanup."""
    assert _Body.get_json_required_marked() == {"buyUnit": "PCS", "name": "AQA Item 42"}


def test_cleanup_fields_default_to_empty():
    class _Plain(BaseRequestBody):
        _json_main = {"a": 1}
        _required = ["a"]

    assert _Plain.get_cleanup_fields() == []
    assert _Plain.get_json_required_marked() == {"a": 1}


# --- LIB-PERM-QUAD --------------------------------------------------------


def test_permission_cells_cover_four_distinct_layers():
    assert set(PERMISSION_CELLS) == {"allow", "no_access", "inactive", "unauth"}


def test_permission_cell_label_rejects_unknown_cell():
    assert permission_cell_label("unauth") == "Permissions/Unauthenticated"
    with pytest.raises(ValueError):
        permission_cell_label("forbidden")


# --- ApiClient hook ordering (end to end) ---------------------------------


@pytest.mark.asyncio
async def test_api_client_fires_hook_before_schema_validation():
    """The real client, not a stub: status → hook → validate_model."""
    import httpx

    from partest.client import ApiClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": 42, "unexpected": True})

    class _StrictModel:
        @staticmethod
        def validate_success(data):
            raise AssertionError("extra fields not permitted")

        @staticmethod
        def validate_error(data):  # pragma: no cover - not reached
            raise AssertionError("extra fields not permitted")

    seen = []
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hx:
        api = ApiClient("http://stand", client=hx)
        api.add_response_hook(lambda m, e, body, resp: seen.append((m, e, body, resp.status_code)))

        with pytest.raises(AssertionError):
            await api.make_request(
                "POST", "/items", expected_status_code=201, validate_model=_StrictModel
            )

    assert seen == [("POST", "/items", {"id": 42, "unexpected": True}, 201)]


@pytest.mark.asyncio
async def test_api_client_hook_does_not_fire_on_status_mismatch():
    """A failed status check means no resource was created — nothing to track."""
    import httpx

    from partest.client import ApiClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"id": 7})

    seen = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
        api = ApiClient("http://stand", client=hx)
        api.add_response_hook(lambda *a: seen.append(a))
        with pytest.raises(AssertionError):
            await api.make_request("POST", "/items", expected_status_code=201)

    assert seen == []


@pytest.mark.asyncio
async def test_api_client_hook_exception_does_not_mask_the_real_failure():
    import httpx

    from partest.client import ApiClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    def _broken_hook(*args):
        raise RuntimeError("hook is buggy")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
        api = ApiClient("http://stand", client=hx)
        api.add_response_hook(_broken_hook)
        result = await api.make_request("GET", "/items", expected_status_code=200)

    assert result == {"ok": True}


# --- Allure step must not swallow or mangle failures ----------------------


def test_allure_step_lets_the_original_exception_through():
    """Regression: the guarded step used to turn any failure into a RuntimeError.

    The old helper caught the body's exception and yielded a second time, so
    contextlib raised "generator didn't stop after throw()" and the formatted status
    or schema diagnostics never reached the report.
    """
    from partest.allure_step import allure_step

    with pytest.raises(AssertionError, match="expected 201, got 400"):
        with allure_step("probe"):
            raise AssertionError("HTTP status mismatch: expected 201, got 400")


def test_client_status_mismatch_reports_the_real_message():
    import httpx

    from partest.client import ApiClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
            api = ApiClient("http://stand", client=hx)
            await api.make_request("GET", "/items", expected_status_code=200)

    with pytest.raises(AssertionError, match="expected 200"):
        asyncio.run(run())
