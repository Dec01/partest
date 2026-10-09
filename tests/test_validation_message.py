"""What ApiClient says when a JSON body fails its model.

pydantic's ``ValidationError`` subclasses ``ValueError``, so a schema failure used to fall into
the JSON-parse handler and read "Failed to parse JSON response" — a contract drift reported as
a broken body.
"""

import logging

import httpx
import pytest
from pydantic import RootModel

from partest import BaseModelWithConfig, BaseResponseValidator, TypesTestCases
from partest.client import ApiClient


class _Item(BaseModelWithConfig):
    id: int


class _ItemValidation(BaseResponseValidator):
    @property
    def ResponseSuccessBody(self):
        return _Item


class _Text(RootModel):
    root: str


class _TextValidation(BaseResponseValidator):
    @property
    def ResponseSuccessBody(self):
        return _Text


async def _call(response: httpx.Response, validate_model):
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
        api = ApiClient("http://stand", client=hx)
        return await api.make_request(
            "GET",
            "/items",
            expected_status_code=200,
            validate_model=validate_model,
            type=TypesTestCases.request_default,
        )


@pytest.mark.asyncio
async def test_schema_failure_on_json_body_is_reported_as_validation():
    with pytest.raises(AssertionError) as info:
        await _call(httpx.Response(200, json={"id": 1, "extra": True}), _ItemValidation())
    text = str(info.value)
    assert text.startswith("Response data validation failed for _Item (1 error):\n")
    assert "  extra [extra_forbidden]: Extra inputs are not permitted" in text
    assert "Failed to parse JSON" not in text
    assert text.splitlines()[-1] == 'Response body: {"id": 1, "extra": true}'


MARKER = "S3CRET-MARKER-7f3a9c"


def _error_logs(caplog) -> str:
    # The ERROR records this method writes. The INFO response log is a separate channel
    # that prints every body as received (see docs/wiki/proposals.md), not checked here.
    return "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"id": 1, "token": MARKER},
        {"id": 1, "detail": {"password": MARKER}},
        {"id": "x", "a": {"b": {"c": {"d": {"e": {"f": {"g": {"secret": MARKER}}}}}}}},
    ],
    ids=["top_level_token", "nested_password", "below_mapping_depth"],
)
async def test_failure_message_and_error_log_carry_no_secret(body, caplog):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(AssertionError) as info:
        await _call(httpx.Response(200, json=body), _ItemValidation())
    text = str(info.value)
    assert MARKER not in text
    assert MARKER[:8] not in text  # no prefix-keeping mask either
    assert "Response body: " in text  # the body is there, masked
    logged = _error_logs(caplog)
    assert logged  # the branch did log
    assert MARKER not in logged


@pytest.mark.asyncio
async def test_input_values_are_not_in_the_error_list():
    with pytest.raises(AssertionError) as info:
        await _call(httpx.Response(200, json={"id": "not-an-int-" + MARKER}), _ItemValidation())
    head, _, _body = str(info.value).rpartition("\nResponse body: ")
    assert MARKER not in head
    assert "  id [int_parsing]: " in head


@pytest.mark.asyncio
async def test_failure_message_is_bounded_and_counts_every_error():
    class Items(RootModel):
        root: list[_Item]

    class ItemsValidation(BaseResponseValidator):
        @property
        def ResponseSuccessBody(self):
            return Items

    body = [{"id": i, "extra": "x" * 50} for i in range(1000)]
    with pytest.raises(AssertionError) as info:
        await _call(httpx.Response(200, json=body), ItemsValidation())
    text = str(info.value)
    assert text.startswith(
        "Response data validation failed for Items (1000 errors):\n  0.extra [extra_forbidden]: "
    )
    assert "truncated" in text
    assert len(text) < 4000


class _Row(BaseModelWithConfig):
    id: int
    token: str


class _Rows(RootModel):
    root: list[_Row]


class _RowsValidation(BaseResponseValidator):
    @property
    def ResponseSuccessBody(self):
        return _Rows


@pytest.mark.asyncio
async def test_error_beyond_the_body_cut_shows_its_masked_parent(caplog):
    caplog.set_level(logging.DEBUG)
    body = [{"id": i, "token": MARKER} for i in range(500)]
    body[420] = {"id": "four-twenty", "token": MARKER}
    with pytest.raises(AssertionError) as info:
        await _call(httpx.Response(200, json=body), _RowsValidation())
    text = str(info.value)
    assert text.startswith("Response data validation failed for _Rows (1 error):\n")
    assert "  420.id [int_parsing]: " in text
    assert "    in 420 = {\"id\": \"four-twenty\", \"token\": '***'}" in text
    body_line = text.rpartition("\nResponse body: ")[2]
    assert "four-twenty" not in body_line  # element 420 lies beyond the cut
    assert MARKER not in text and MARKER[:8] not in text
    assert MARKER not in _error_logs(caplog)


@pytest.mark.asyncio
async def test_only_the_first_errors_get_a_parent():
    body = [{"id": "bad", "token": "t"} for _ in range(8)]
    with pytest.raises(AssertionError) as info:
        await _call(httpx.Response(200, json=body), _RowsValidation())
    assert str(info.value).count("\n    in ") == 5


@pytest.mark.asyncio
async def test_error_log_names_the_model_not_the_validator(caplog):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(AssertionError):
        await _call(httpx.Response(200, json={"id": 1, "extra": True}), _ItemValidation())
    logged = _error_logs(caplog)
    assert "'_Item'" in logged
    assert "object at 0x" not in logged


@pytest.mark.asyncio
async def test_non_json_body_for_object_model_is_still_a_parse_failure():
    with pytest.raises(AssertionError, match="Failed to parse JSON response"):
        await _call(httpx.Response(200, text="not json"), _ItemValidation())


@pytest.mark.asyncio
async def test_string_model_still_falls_back_to_text_for_json_looking_bodies():
    # "42" parses as a JSON number; a str root model validates the raw text instead.
    await _call(httpx.Response(200, text="42"), _TextValidation())
    await _call(httpx.Response(200, text="plain"), _TextValidation())
