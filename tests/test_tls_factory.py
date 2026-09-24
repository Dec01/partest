"""A consumer can build their own httpx client without leaving the TLS policy.

``partest.tls`` decided ``verify=`` for the clients the package builds and for nothing
else. The moment a suite needed a client of its own — a fixture pulling the live swagger,
a probe against a second service — it wrote ``httpx.Client(verify=False)``: no
``resolve_verify``, no warning, no ``meta.tlsVerified`` record, and a report claiming the
run verified certificates while it did not. These cases pin the factory that removes the
reason to do that, its boundary (a client, not a second ``ApiClient``), and the fact that
the package no longer builds a raw httpx client anywhere else.
"""

from __future__ import annotations

import asyncio
import ssl
import sys
import types
from pathlib import Path

import certifi
import httpx
import pytest

from partest import tls
from partest.http import httpx_async_client, httpx_client


@pytest.fixture(autouse=True)
def clean_tls_state(monkeypatch):
    from partest.call_storage import run_info

    monkeypatch.delenv(tls.VERIFY_ENV, raising=False)
    monkeypatch.delitem(sys.modules, "confpartest", raising=False)
    tls._reset_warning_state()
    run_info["tlsVerified"] = True
    yield
    tls._reset_warning_state()
    run_info["tlsVerified"] = True


@pytest.fixture
def verify_seen(monkeypatch):
    """What the factory handed to httpx — a built client no longer exposes it."""
    seen: list = []

    for name in ("Client", "AsyncClient"):
        real = getattr(httpx, name)

        def spy(*, _real=real, **kwargs):
            seen.append(kwargs.get("verify", "<not passed>"))
            return _real(**kwargs)

        monkeypatch.setattr(httpx, name, spy)
    return seen


def _close(client) -> None:
    # By duck type, not by class: ``verify_seen`` replaces httpx's constructors, so
    # ``httpx.AsyncClient`` is a function while the spy is in place.
    if hasattr(client, "aclose"):
        asyncio.run(client.aclose())
    else:
        client.close()


#: Both roads out of the factory. Everything below is checked on each: a sync-only
#: property would leave half of the consumers' clients outside the policy.
BOTH = [
    pytest.param(httpx_client, id="sync"),
    pytest.param(httpx_async_client, id="async"),
]


# --- the policy applies ---------------------------------------------------


@pytest.mark.parametrize("factory", BOTH)
def test_a_client_from_the_factory_verifies_by_default(factory, verify_seen):
    _close(factory())

    assert verify_seen == [True]


@pytest.mark.parametrize("factory", BOTH)
def test_the_switch_reaches_a_client_the_consumer_built(factory, monkeypatch, verify_seen):
    """The whole point: one project-wide setting, not thirty call sites."""
    monkeypatch.setenv(tls.VERIFY_ENV, "0")

    with pytest.warns(tls.TLSVerificationDisabled):
        _close(factory())

    assert verify_seen == [False]


@pytest.mark.parametrize("factory", BOTH)
def test_such_a_client_cannot_leave_the_policy_silently(factory, monkeypatch):
    """A run that stopped verifying says so twice: in the output and in the artifact.

    This is the case the factory exists for. A consumer's own ``httpx.Client(verify=False)``
    produced neither, and ``meta.tlsVerified`` stayed ``true`` about a run in which a live
    specification had been fetched over an unverified connection.
    """
    from partest.call_storage import run_info

    monkeypatch.setenv(tls.VERIFY_ENV, "0")

    with pytest.warns(tls.TLSVerificationDisabled):
        _close(factory())

    assert run_info["tlsVerified"] is False


@pytest.mark.parametrize("factory", BOTH)
def test_an_explicit_opt_out_goes_through_the_same_policy(factory, verify_seen):
    """``verify=False`` written by the caller is not a way around the record."""
    from partest.call_storage import run_info

    with pytest.warns(tls.TLSVerificationDisabled):
        _close(factory(verify=False))

    assert verify_seen == [False]
    assert run_info["tlsVerified"] is False


@pytest.mark.parametrize("factory", BOTH)
def test_a_context_that_checks_nothing_is_caught_here_too(factory, verify_seen):
    """The other spelling of ``verify=False``; it is what slipped through in 2.0.0."""
    from partest.call_storage import run_info

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    with pytest.warns(tls.TLSVerificationDisabled):
        _close(factory(verify=context))

    assert verify_seen == [context]
    assert run_info["tlsVerified"] is False


@pytest.mark.parametrize("factory", BOTH)
def test_confpartest_reaches_the_factory_as_well(factory, monkeypatch, verify_seen):
    module = types.ModuleType("confpartest")
    module.tls_verify = False
    monkeypatch.setitem(sys.modules, "confpartest", module)

    with pytest.warns(tls.TLSVerificationDisabled):
        _close(factory())

    assert verify_seen == [False]


@pytest.mark.parametrize("factory", BOTH)
def test_a_ca_bundle_arrives_as_a_context_not_as_a_string(
    factory, monkeypatch, verify_seen, recwarn
):
    """httpx 0.28 deprecates ``verify=<str>``; under ``filterwarnings = error`` it fails.

    ``certifi`` ships with httpx, so this is a real bundle on every platform rather than a
    system path that may not exist.
    """
    monkeypatch.setenv(tls.VERIFY_ENV, certifi.where())

    _close(factory())

    assert isinstance(verify_seen[0], ssl.SSLContext)
    assert [w for w in recwarn if issubclass(w.category, DeprecationWarning)] == []


# --- what the caller asked for still arrives ------------------------------


def test_the_callers_own_arguments_are_not_touched():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    with httpx_client(
        base_url="https://stand.invalid/api",
        timeout=7.5,
        headers={"X-Suite": "partest"},
        follow_redirects=False,
        transport=httpx.MockTransport(handler),
    ) as http:
        response = http.get("/items", params={"page": 2})

    assert response.json() == {"ok": True}
    assert str(calls[0].url) == "https://stand.invalid/api/items?page=2"
    assert calls[0].headers["X-Suite"] == "partest"
    assert http.timeout == httpx.Timeout(7.5)
    assert http.follow_redirects is False


def test_the_async_road_carries_them_too():
    async def go() -> httpx.Response:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, json={"id": 1})

        async with httpx_async_client(
            base_url="https://stand.invalid",
            headers={"X-Suite": "partest"},
            transport=httpx.MockTransport(handler),
        ) as http:
            return await http.post("/items", json={"name": "x"})

    response = asyncio.run(go())

    assert response.status_code == 201
    assert response.json() == {"id": 1}


# --- the boundary: a client, not a harness --------------------------------


@pytest.mark.parametrize("factory", BOTH)
def test_the_factory_returns_a_plain_httpx_client(factory):
    """Not a subclass, not a wrapper: what the caller gets is what httpx documents.

    The factory adds the TLS decision and nothing else — no retries, no steps, no
    attaches. Anyone who wants those is asking for ``ApiClient``.
    """
    client = factory()

    assert type(client) in (httpx.Client, httpx.AsyncClient)
    _close(client)


def test_calls_through_it_are_still_invisible_to_coverage():
    """The factory removes a reason to leave the TLS policy, not a reason to use ApiClient.

    A raw client cannot be counted as covered — ``track_api_calls`` sits on
    ``ApiClient.make_request``. Saying so in a test keeps the boundary from drifting into
    "the light ApiClient".
    """
    from partest.call_storage import call_count

    before = dict(call_count)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    with httpx_client(transport=httpx.MockTransport(handler)) as http:
        http.get("https://stand.invalid/items")

    assert dict(call_count) == before


# --- the package itself does not bypass it --------------------------------


def test_no_module_in_the_package_builds_a_raw_httpx_client():
    """Five call sites repeated the same two lines; a sixth would repeat them again.

    The duplication was not the real cost — each copy was another place where the TLS
    decision could be forgotten, and two of them already had been at some point in the
    package's history. The factory is the only place allowed to call httpx's constructors.
    """
    import partest

    root = Path(partest.__file__).resolve().parent
    allowed = root / "http" / "client.py"

    offenders = []
    for path in sorted(root.rglob("*.py")):
        if path == allowed:
            continue
        text = path.read_text(encoding="utf-8")
        for spelling in ("httpx.Client(", "httpx.AsyncClient("):
            if spelling in text:
                offenders.append(f"{path.relative_to(root)}: {spelling})")

    assert offenders == [], (
        "these build an httpx client without partest.tls: "
        f"{offenders}. Use partest.http.httpx_client / httpx_async_client instead"
    )


def test_the_factory_is_public_under_both_names():
    """Consumers are told ``from partest import httpx_client``; ``partest.http`` is the module."""
    import partest
    from partest import http as http_pkg

    assert partest.httpx_client is httpx_client
    assert partest.httpx_async_client is httpx_async_client
    assert "httpx_client" in partest.__all__
    assert "httpx_async_client" in partest.__all__
    assert http_pkg.__all__ == [
        "Config",
        "HeaderSpec",
        "HeadersBind",
        "httpx_client",
        "httpx_async_client",
    ]
