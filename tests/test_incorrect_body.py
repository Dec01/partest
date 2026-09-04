"""LIB-REC-IB: raw IncorrectBody helper (no live HTTP)."""

from partest.validation import RAW_INCORRECT_BODY_CASES, assert_raw_incorrect_body
from partest.test_types import TypesTestCases as T


def test_raw_cases_have_ids_and_multi_status():
    assert len(RAW_INCORRECT_BODY_CASES) >= 2
    ids = [p.id for p in RAW_INCORRECT_BODY_CASES]
    assert "broken_json" in ids
    assert "ct_text_plain" in ids
    for param in RAW_INCORRECT_BODY_CASES:
        content, content_type, expected = param.values
        assert isinstance(content, (bytes, bytearray))
        assert "/" in content_type
        assert expected == (400, 415)


def test_assert_raw_incorrect_body_forwards_kwargs():
    import asyncio

    seen = {}

    class FakeClient:
        async def make_request(self, method, url, **kwargs):
            seen["method"] = method
            seen["url"] = url
            seen.update(kwargs)
            return {"ok": True}

    result = asyncio.run(
        assert_raw_incorrect_body(
            FakeClient(),
            "POST",
            "/items",
            {"Accept": "application/json"},
            content=b'{"a":',
            content_type="application/json",
            defining_url="/items",
        )
    )
    assert result == {"ok": True}
    assert seen["method"] == "POST"
    assert seen["content"] == b'{"a":'
    assert seen["type"] == T.request_incorrect_body
    assert seen["defining_url"] == "/items"
    assert seen["expected_status_code"] == (400, 415)
