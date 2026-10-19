"""``Logger.warning`` exists (2.7.0): two ``make_request`` paths called it and got ``AttributeError``.

``make_request(data={...})`` without ``json_data`` and a GraphQL query sent with a method
other than POST each log a warning through the client's ``Logger``; until 2.7.0 that class
had ``error`` and no ``warning``, and the request never left.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from partest import TypesTestCases
from partest.client import ApiClient
from partest.utils import Logger

MARKER = "S3CRET-MARKER-91c2"


async def _call(**kwargs):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
        api = ApiClient("http://stand", client=hx)
        await api.make_request(
            endpoint="/items", type=TypesTestCases.request_default,
            expected_status_code=200, **kwargs,
        )
    return seen


def _warnings(caplog) -> list:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


@pytest.mark.asyncio
async def test_data_dict_without_json_data_warns_and_sends(caplog):
    caplog.set_level(logging.INFO)
    seen = await _call(method="POST", data={"name": "x"})
    assert len(seen) == 1
    assert any("json_data=" in m for m in _warnings(caplog))


@pytest.mark.asyncio
async def test_graphql_not_through_post_warns_and_sends(caplog):
    caplog.set_level(logging.INFO)
    seen = await _call(method="GET", graphql_query="{ items { id } }")
    assert len(seen) == 1
    assert any("GraphQL requests are usually POST" in m for m in _warnings(caplog))


def test_warning_is_masked_like_the_request_log(caplog):
    caplog.set_level(logging.WARNING)
    Logger().warning(f"retrying http://user:{MARKER}@stand/items?token={MARKER}&page=2")
    text = "\n".join(_warnings(caplog))
    assert MARKER not in text
    assert "page=2" in text
