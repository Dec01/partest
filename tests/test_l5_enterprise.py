"""L5 enterprise: redaction, storage merge, retry policy, status locale."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from partest.call_storage import (
    dump_storage,
    dump_storage_file,
    load_storage,
    merge_storage_files,
    record_call,
    reset_storage,
)
from partest.client import ApiClient, _mask_headers
from partest.http_retry import RetryPolicy
from partest.redact import mask_secret, redact_headers, redact_mapping
from partest.reporting.templates import (
    http_status_hint,
    set_status_hints_locale,
    status_hints_locale,
)


def test_mask_and_redact_headers():
    assert "masked" in mask_secret("Bearer supersecrettokenvalue").lower() or "…" in mask_secret(
        "Bearer supersecrettokenvalue"
    )
    h = redact_headers(
        {"Authorization": "Bearer abcdefghijklmnop", "Accept": "application/json"}
    )
    assert h["Accept"] == "application/json"
    assert "abcdefghijklmnop" not in str(h["Authorization"])
    assert _mask_headers({"Cookie": "sid=xyz12345678"})["Cookie"] != "sid=xyz12345678"


def test_redact_mapping_body():
    data = {"user": "a", "password": "secret12345", "nested": {"token": "ttttttttt"}}
    out = redact_mapping(data)
    assert out["user"] == "a"
    assert "secret12345" not in str(out["password"])
    assert "ttttttttt" not in str(out["nested"]["token"])


def test_storage_dump_merge(tmp_path: Path):
    reset_storage()
    record_call(("GET", "/a", "t"), "request_default")
    d1 = dump_storage()
    f1 = dump_storage_file(tmp_path / "w1.json")
    reset_storage()
    record_call(("GET", "/a", "t"), "request_default")
    record_call(("POST", "/b", "t"), "request_default")
    f2 = dump_storage_file(tmp_path / "w2.json")
    reset_storage()
    merge_storage_files([f1, f2])
    from partest.call_storage import call_count, call_type

    assert call_count[("GET", "/a", "t")] == 2
    assert "request_default" in call_type[("POST", "/b", "t")]
    load_storage(d1, merge=False)
    assert call_count[("GET", "/a", "t")] == 1


def test_retry_policy_status():
    p = RetryPolicy(max_retries=2, retry_statuses=(429, 503))
    assert p.should_retry_status(429, 0)
    assert p.should_retry_status(429, 1)
    assert not p.should_retry_status(429, 2)
    assert not p.should_retry_status(400, 0)


@pytest.mark.asyncio
async def test_api_client_retries_status(monkeypatch):
    """Simulated 503 then 200 with max_retries=2."""
    calls = {"n": 0}

    class FakeResp:
        def __init__(self, status, text="ok"):
            self.status_code = status
            self.text = text
            self.request = None
            self.cookies = {}
            self.headers = {}

        def json(self):
            return {"ok": True}

    async def fake_send(self, method, url, **kwargs):
        calls["n"] += 1
        if calls["n"] < 2:
            return FakeResp(503, "busy")
        return FakeResp(200, '{"ok":true}')

    monkeypatch.setattr(ApiClient, "_send_once", fake_send)
    # disable coverage decorator side-effects issues by calling internal path
    client = ApiClient("http://example.invalid", max_retries=2, retry_backoff=0.01)
    # make_request uses track_api_calls — fine
    result = await client.make_request(
        "GET", "/x", expected_status_code=200, type="request_default"
    )
    assert calls["n"] == 2
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_api_client_graphql_builds_body(monkeypatch):
    captured = {}

    async def fake_send(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json_data")
        captured["headers"] = kwargs.get("headers")
        class R:
            status_code = 200
            text = '{"data":{}}'
            request = None
            cookies = {}
            headers = {}
            def json(self):
                return {"data": {}}
        return R()

    monkeypatch.setattr(ApiClient, "_send_once", fake_send)
    client = ApiClient("http://example.invalid")
    await client.graphql("{ me { id } }", variables={"a": 1}, endpoint="/gql")
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/gql")
    assert "me" in captured["json"]["query"]
    assert captured["json"]["variables"] == {"a": 1}


def test_status_hints_locale_ru():
    set_status_hints_locale("en")
    en = http_status_hint(409)
    set_status_hints_locale("ru")
    ru = http_status_hint(409)
    assert status_hints_locale() == "ru"
    assert en != ru
    assert "Конфликт" in ru or "конфликт" in ru.lower()
    set_status_hints_locale("en")
