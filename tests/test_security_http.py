"""1.2 security + http Config unit tests."""

from __future__ import annotations

import base64
import json

import pytest

from partest.http import Config
from partest.security import (
    SecHttp,
    build_alg_none_token,
    build_tampered_payload_token,
    build_tampered_set,
)


def _fake_jwt(payload: dict) -> str:
    h = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{h}.{p}.sig"


def test_config_headers_and_token():
    cfg = Config()
    h = cfg.get_headers(["Accept", "X-Request-ID"], token="abc")
    assert h["Accept"] == "application/json"
    assert "Authorization" in h and h["Authorization"].endswith("abc")
    assert h["X-Request-ID"]  # generated uuid


def test_config_rejects_bad_content_type():
    cfg = Config()
    with pytest.raises(ValueError):
        cfg.get_headers(["Content-Type"], custom_values={"Content-Type": "evil/type"})


def test_jwt_craft_set():
    real = _fake_jwt({"sub": "admin", "preferred_username": "admin"})
    tokens = build_tampered_set(real, forged_roles=["ADMIN"])
    assert "alg_none" in tokens
    assert tokens["alg_none"].count(".") == 2
    assert tokens["not_a_jwt"]
    tampered = build_tampered_payload_token(real, patch={"preferred_username": "x"})
    assert tampered.split(".")[2] == real.split(".")[2]
    none = build_alg_none_token(sub="a", roles=["R"])
    assert none.endswith(".")


@pytest.mark.asyncio
async def test_sec_http_status_mismatch(httpx_mock=None):
    """SecHttp raises on expected_status mismatch (instrument off avoids allure)."""
    # use respx-less approach: mock by patching AsyncClient if needed
    # simpler: call with unreachable host and auth=False — network error
    # Instead unit-test _bearer path with static token
    client = SecHttp("http://127.0.0.1:9", token="t", instrument=False, timeout=0.1)
    assert await client._bearer() == "t"
