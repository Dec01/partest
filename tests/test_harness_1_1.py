"""Unit tests for 1.1 harness modules (no live Keycloak/HTTP)."""

import pytest

from partest import (
    BaseRequestBody,
    BaseResponseValidator,
    BaseModelWithConfig,
    CreatedRegistry,
    ProblemDetailBody,
    TrackingApiClient,
    marked_name,
    prefix_marker,
    TEST_MARKER,
)
from partest.auth import decode_jwt_payload, jwt_claim
from partest.reporting import check_eq, ErrorTemplates, format_http_status_failure
from partest.security import RiskProfile
from partest.collections import BaseCollection
from partest.data_marker import fill_with_marker


def test_created_registry_track_and_count():
    reg = CreatedRegistry()
    reg.track("/items", 1)
    reg.track("/items", 2)
    assert reg.count == 2
    assert reg.items[0] == ("/items", 1)


def test_base_request_body():
    class Body(BaseRequestBody):
        _required = ["name", "code"]
        _json_main = {"name": lambda: "x", "code": "C1"}

    b = Body()
    assert b.json["name"] == "x"
    assert "code" in Body.get_json_required()
    miss = Body.get_json_miss_required("code")
    assert "code" not in miss


def test_problem_detail_model():
    m = ProblemDetailBody(
        detail="d", instance="/x", status=400, title="Bad Request"
    )
    assert m.status == 400


def test_base_validator_success():
    class M(BaseModelWithConfig):
        id: int

    class V(BaseResponseValidator):
        @property
        def ResponseSuccessBody(self):
            return M

    assert V().validate_success({"id": 1}).id == 1


def test_jwt_decode():
    # header.payload.sig — payload {"sub":"u1","exp":9999999999}
    import base64
    import json

    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": "u1", "exp": 9999999999}).encode()
    ).decode().rstrip("=")
    token = f"aaa.{payload}.bbb"
    assert decode_jwt_payload(token)["sub"] == "u1"
    assert jwt_claim(token, "sub") == "u1"


def test_data_marker():
    assert TEST_MARKER in marked_name("Client")
    assert prefix_marker("hello").startswith(TEST_MARKER)
    assert len(fill_with_marker(20)) == 20
    assert TEST_MARKER[:3] in fill_with_marker(20)


def test_risk_profile_level():
    # authz → critical; writes+fk → high; legacy kwargs still work
    critical = RiskProfile(name="users", has_writes=True, has_authz=True)
    assert critical.level == "critical"
    high = RiskProfile(name="pay", has_money=True, has_writes=True, has_authz=False)
    assert high.level == "high"
    low = RiskProfile(name="enum", has_authz=False)
    assert low.level == "low"


def test_error_templates_and_format():
    msg = format_http_status_failure(
        method="POST",
        path="/items",
        expected=201,
        actual=409,
        request_body={"name": "a"},
        response_body={"title": "Conflict", "status": 409, "detail": "x", "instance": "/i"},
    )
    assert "409" in msg
    assert "Conflict" in msg or "conflict" in msg.lower()


def test_check_eq_passes():
    check_eq(1, 1, field="id")


def test_check_eq_fails():
    with pytest.raises(AssertionError):
        check_eq(1, 2, field="id")


def test_base_collection_apply_token():
    class H:
        def __init__(self):
            self.token = None

        def apply_token(self, t):
            self.token = t

    c = BaseCollection()
    c.headers = H()
    c.apply_token("abc")
    assert c.headers.token == "abc"


def test_tracking_client_constructs():
    reg = CreatedRegistry()
    client = TrackingApiClient("http://example.invalid", reg, instrument=False)
    assert client.domain == "http://example.invalid"
    assert client.registry is reg


@pytest.mark.asyncio
async def test_cleanup_retries_on_409(monkeypatch):
    """LIB-15: CreatedRegistry.cleanup retries 409 then succeeds."""
    import httpx
    from partest.tracking import CreatedRegistry as Reg

    codes = [409, 204]

    class _Resp:
        def __init__(self, status_code):
            self.status_code = status_code

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def delete(self, url, headers=None):
            return _Resp(codes.pop(0))

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    reg = Reg()
    reg.track("/items", 7)
    await reg.cleanup("http://example.invalid", token="t")
    assert codes == []
    assert reg.count == 0
