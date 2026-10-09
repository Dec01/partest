"""What ApiClient says when a JSON body fails its model.

pydantic's ``ValidationError`` subclasses ``ValueError``, so a schema failure used to fall into
the JSON-parse handler and read "Failed to parse JSON response" — a contract drift reported as
a broken body.
"""

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
    assert text.startswith("Response data validation failed:")
    assert "Extra inputs are not permitted" in text
    assert "Failed to parse JSON" not in text


@pytest.mark.asyncio
async def test_non_json_body_for_object_model_is_still_a_parse_failure():
    with pytest.raises(AssertionError, match="Failed to parse JSON response"):
        await _call(httpx.Response(200, text="not json"), _ItemValidation())


@pytest.mark.asyncio
async def test_string_model_still_falls_back_to_text_for_json_looking_bodies():
    # "42" parses as a JSON number; a str root model validates the raw text instead.
    await _call(httpx.Response(200, text="42"), _TextValidation())
    await _call(httpx.Response(200, text="plain"), _TextValidation())
