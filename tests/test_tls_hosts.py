"""Which hosts a run accepted without a certificate check — not merely whether one did.

``meta.tlsVerified`` is one bit for a whole run, and one auxiliary service is enough to
switch it off. Measured on a consumer: a plugin of theirs sits in ``addopts`` and signs
into an auxiliary service with a self-signed certificate while pytest is still configuring
itself, so *every* run of that project reported the bit unset — including runs that never
call the API. The flag went to ``false`` honestly and on every run, and "the suite ran unverified
throughout" became indistinguishable from "one service host was accepted, the stand was
verified from the first call to the last".

These cases pin the two lists that put the difference back — hosts reached with
verification off, and hosts whose TLS partest did not decide — the moment each is
learned, and the fact that neither touches the flag they stand next to.
"""

from __future__ import annotations

import asyncio
import sys
import types

import httpx
import pytest

from partest import call_storage as cs
from partest import tls
from partest.http import httpx_async_client, httpx_client

pytestmark = pytest.mark.filterwarnings("ignore::partest.tls.TLSVerificationDisabled")


@pytest.fixture(autouse=True)
def clean_tls_state(monkeypatch):
    """A run's TLS record is process-wide state; each case starts and leaves it empty."""
    monkeypatch.delenv(tls.VERIFY_ENV, raising=False)
    monkeypatch.delitem(sys.modules, "confpartest", raising=False)
    saved = (set(cs.unverified_hosts), set(cs.unknown_tls_hosts))
    cs.unverified_hosts.clear()
    cs.unknown_tls_hosts.clear()
    tls._reset_warning_state()
    cs.run_info["tlsVerified"] = True
    yield
    tls._reset_warning_state()
    cs.run_info["tlsVerified"] = True
    cs.unverified_hosts.clear()
    cs.unverified_hosts.update(saved[0])
    cs.unknown_tls_hosts.clear()
    cs.unknown_tls_hosts.update(saved[1])


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


def _close(client) -> None:
    if hasattr(client, "aclose"):
        asyncio.run(client.aclose())
    else:
        client.close()


#: Both roads out of the factory; a sync-only record would leave half of a consumer's
#: clients out of the artifact.
BOTH = [
    pytest.param(httpx_client, id="sync"),
    pytest.param(httpx_async_client, id="async"),
]


# --- the host is learned when the request is sent, not when the client is built ---


def test_a_host_reached_without_verification_is_named():
    """The record the whole feature exists for."""
    with httpx_client(verify=False, transport=httpx.MockTransport(_ok)) as http:
        http.get("https://admin.invalid:9443/api/auth")

    assert cs.unverified_hosts == {"admin.invalid:9443"}
    assert cs.run_info["tlsVerified"] is False


async def test_the_async_road_records_it_too():
    """Half the consumers' clients are async; a sync-only record would miss them."""
    async with httpx_async_client(verify=False, transport=httpx.MockTransport(_ok)) as http:
        await http.get("https://admin.invalid/api/auth")

    assert cs.unverified_hosts == {"admin.invalid"}


@pytest.mark.parametrize("factory", BOTH)
def test_a_verifying_client_records_nothing(factory):
    _close(factory())

    assert cs.unverified_hosts == set()
    assert cs.unknown_tls_hosts == set()


def test_only_the_host_that_went_unchecked_is_listed():
    """The case from the consumer: one service host off, the system under test on.

    The flag says ``false`` for the run either way — that is what it has always meant.
    What was missing is the sentence after it: *one* host, and not the one the suite is
    about.
    """
    transport = httpx.MockTransport(_ok)

    with httpx_client(verify=False, transport=transport) as service:
        service.get("https://admin.invalid:9443/api/auth")
    with httpx_client(transport=transport) as stand:
        stand.get("https://stand.invalid/v1/items")

    assert cs.unverified_hosts == {"admin.invalid:9443"}
    assert "stand.invalid" not in cs.unverified_hosts
    assert cs.run_info["tlsVerified"] is False


def test_the_host_the_request_went_to_wins_over_the_one_it_was_pointed_at():
    """A redirect leaves ``base_url`` behind; the certificate that was accepted is the
    one on the host that answered.

    This is why the host is taken per request and not from ``base_url`` at construction.
    """

    def redirect(request: httpx.Request) -> httpx.Response:
        if request.url.host == "old.invalid":
            return httpx.Response(302, headers={"Location": "https://new.invalid/items"})
        return httpx.Response(200, json={})

    with httpx_client(
        base_url="https://old.invalid",
        verify=False,
        follow_redirects=True,
        transport=httpx.MockTransport(redirect),
    ) as http:
        http.get("/items")

    assert cs.unverified_hosts == {"old.invalid", "new.invalid"}


def test_the_stand_an_api_client_called_unverified_is_named(monkeypatch):
    """``ApiClient`` — the road the system under test travels — passes no ``base_url``.

    It builds an absolute URL per call, so reading ``base_url`` at construction would
    have recorded nothing for precisely the client the answer is about.
    """
    import partest.client as client_module
    from partest import ApiClient

    real = client_module.httpx_async_client
    monkeypatch.setattr(
        client_module,
        "httpx_async_client",
        lambda **kwargs: real(transport=httpx.MockTransport(_ok), **kwargs),
    )

    api = ApiClient("https://stand.invalid", verify=False)
    asyncio.run(
        api.make_request("GET", "/health", expected_status_code=200, type="request_default")
    )

    assert cs.unverified_hosts == {"stand.invalid"}


def test_a_client_built_unverified_and_never_used_names_no_host(monkeypatch):
    """Nothing was accepted, so nothing is named — while the flag still says the run
    stopped verifying. The two answer different questions on purpose."""
    monkeypatch.setenv(tls.VERIFY_ENV, "0")

    _close(httpx_client())

    assert cs.unverified_hosts == set()
    assert cs.run_info["tlsVerified"] is False


def test_the_specification_fetch_is_named_too(monkeypatch):
    """``parparser`` is the one road out of the package that is not httpx, so the
    factory's hook cannot see it — and a specification usually lives on its own host."""
    from partest import parparser

    class _Resp:
        text = "openapi: 3.0.0\npaths: {}\n"

        def raise_for_status(self):
            return None

    monkeypatch.setenv(tls.VERIFY_ENV, "0")
    monkeypatch.setattr(parparser.requests, "get", lambda url, **kwargs: _Resp())

    parparser.OpenAPIParser.load_swagger_yaml("url", "https://swagger.invalid/openapi.yaml")

    assert cs.unverified_hosts == {"swagger.invalid"}


# --- what the caller passed still arrives ---------------------------------


def test_the_callers_transport_handles_the_request_itself():
    """The hook is a hook, not a wrapper around the transport.

    Wrapping would also see the host — and would have to build a transport when the
    caller passed none, at which point httpx ignores ``verify=``, ``http2=`` and the
    proxies, and the TLS decision this module exists for stops applying.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    with httpx_client(verify=False, transport=transport) as http:
        response = http.get("https://admin.invalid/api/auth")

    assert type(http) is httpx.Client
    assert http._transport is transport
    assert [str(r.url) for r in seen] == ["https://admin.invalid/api/auth"]
    assert response.json() == {"ok": True}


def test_the_callers_own_event_hooks_keep_running():
    """``event_hooks`` is the one argument touched, and only by appending to it."""
    mine: list[str] = []

    with httpx_client(
        verify=False,
        event_hooks={"request": [lambda request: mine.append(str(request.url))]},
        transport=httpx.MockTransport(_ok),
    ) as http:
        http.get("https://admin.invalid/api/auth")

    assert mine == ["https://admin.invalid/api/auth"]
    assert cs.unverified_hosts == {"admin.invalid"}


def test_a_verifying_client_is_given_exactly_the_hooks_it_was_built_with():
    """Nothing to record, nothing added: a verified run pays nothing for this."""

    def mine(request: httpx.Request) -> None:
        pass

    with httpx_client(event_hooks={"request": [mine]}) as http:
        assert http.event_hooks == {"request": [mine], "response": []}


# --- what must never reach the artifact -----------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://stand.invalid/v1/items", "stand.invalid"),
        ("https://stand.invalid:443/v1", "stand.invalid"),
        ("http://stand.invalid:80/v1", "stand.invalid"),
        ("https://admin.invalid:9443/api", "admin.invalid:9443"),
        ("https://STAND.Invalid/v1", "stand.invalid"),
        ("/v1/items", ""),
        ("", ""),
    ],
)
def test_what_a_host_is(url, expected):
    assert cs.host_of(url) == expected


def test_credentials_in_a_url_do_not_reach_the_artifact():
    """The report is a file people attach to tickets; a URL can carry a token."""
    with httpx_client(verify=False, transport=httpx.MockTransport(_ok)) as http:
        http.get("https://svc:s3cret@admin.invalid/api/auth")

    assert cs.unverified_hosts == {"admin.invalid"}
    assert not any("s3cret" in host for host in cs.unverified_hosts)


# --- the honest "we do not know" ------------------------------------------


def test_an_injected_client_is_recorded_as_undecided_not_as_verified():
    """``ApiClient(domain, client=hx)`` knows that it does not know — and used to say
    ``tlsVerified: true`` about it anyway."""
    from partest import ApiClient

    api = ApiClient("https://stand.invalid", client=httpx.AsyncClient())

    assert api.verify is None
    assert cs.unknown_tls_hosts == {"stand.invalid"}


def test_an_undecided_host_is_not_called_unverified():
    """Two different answers to two different questions; mixing them would trade one
    overstatement for another."""
    from partest import ApiClient

    ApiClient("https://stand.invalid", client=httpx.AsyncClient())

    assert cs.unverified_hosts == set()
    assert cs.run_info["tlsVerified"] is True


def test_a_client_partest_builds_itself_is_not_undecided():
    from partest import ApiClient

    ApiClient("https://stand.invalid", verify=False)

    assert cs.unknown_tls_hosts == set()


# --- the artifact ---------------------------------------------------------


def _meta() -> dict:
    from partest.reports.payload import build_payload

    return build_payload(types.SimpleNamespace(endpoints=[]))["meta"]


def test_the_report_carries_both_lists_next_to_the_flag():
    cs.record_unverified_host("https://admin.invalid:9443/api")
    cs.record_unknown_tls_host("https://stand.invalid")

    meta = _meta()

    assert meta["tlsUnverifiedHosts"] == ["admin.invalid:9443"]
    assert meta["tlsUnknownHosts"] == ["stand.invalid"]


def test_the_flag_keeps_its_type_and_its_meaning():
    """Adding a key to ``meta`` is compatible; changing the type of one is not, and
    ``partest-atlas``, ``partest-load`` and the map read this one as a boolean."""
    cs.record_unverified_host("https://admin.invalid/api")

    meta = _meta()

    assert meta["tlsVerified"] is True, "recording a host does not decide the flag"
    assert isinstance(meta["tlsVerified"], bool)


def test_the_lists_are_there_even_when_empty():
    """So that "nothing was accepted unverified" and "an artifact from an older partest"
    stay distinguishable to whoever reads the file."""
    meta = _meta()

    assert meta["tlsUnverifiedHosts"] == []
    assert meta["tlsUnknownHosts"] == []


def test_the_lists_are_sorted_so_two_runs_can_be_compared():
    for url in ("https://b.invalid", "https://a.invalid", "https://c.invalid"):
        cs.record_unverified_host(url)

    assert _meta()["tlsUnverifiedHosts"] == ["a.invalid", "b.invalid", "c.invalid"]


# --- parallel runs --------------------------------------------------------


def test_a_workers_hosts_reach_the_controller():
    """Under ``-n`` the report is built in a process that made none of the calls."""
    cs.record_unverified_host("https://admin.invalid:9443/api")
    cs.record_unknown_tls_host("https://stand.invalid")
    dump = cs.dump_storage()

    cs.unverified_hosts.clear()
    cs.unknown_tls_hosts.clear()
    cs.load_storage(dump, merge=True)

    assert cs.unverified_hosts == {"admin.invalid:9443"}
    assert cs.unknown_tls_hosts == {"stand.invalid"}


def test_two_workers_that_reached_one_host_report_it_once():
    cs.record_unverified_host("https://admin.invalid/api")
    first = cs.dump_storage()
    cs.record_unverified_host("https://other.invalid/api")
    second = cs.dump_storage()

    cs.unverified_hosts.clear()
    cs.load_storage(first, merge=True)
    cs.load_storage(second, merge=True)

    assert cs.unverified_hosts == {"admin.invalid", "other.invalid"}


def test_the_session_fixture_does_not_erase_them():
    """``reset_storage`` runs after the clients are built — and after ``pytest_configure``
    has already logged into the service host, which is where the measured case happens."""
    cs.record_unverified_host("https://admin.invalid/api")

    cs.reset_storage()

    assert cs.unverified_hosts == {"admin.invalid"}


# --- env_only for the factory ---------------------------------------------


@pytest.mark.parametrize("factory", BOTH)
def test_the_factory_can_stop_at_the_environment(factory, monkeypatch):
    """A consumer wrote three functions to compute ``verify=`` in the submodule and hand
    it back in, only because the factory had no ``env_only=``."""
    module = types.ModuleType("confpartest")
    module.tls_verify = False
    monkeypatch.setitem(sys.modules, "confpartest", module)

    _close(factory(env_only=True))

    assert cs.run_info["tlsVerified"] is True, "confpartest is not read on this road"


@pytest.mark.parametrize("factory", BOTH)
def test_env_only_still_reads_the_environment(factory, monkeypatch):
    monkeypatch.setenv(tls.VERIFY_ENV, "0")

    _close(factory(env_only=True))

    assert cs.run_info["tlsVerified"] is False


@pytest.mark.parametrize("factory", BOTH)
def test_confpartest_is_still_read_by_default(factory, monkeypatch):
    """``env_only`` is opt-in; the ordinary road keeps both sources."""
    module = types.ModuleType("confpartest")
    module.tls_verify = False
    monkeypatch.setitem(sys.modules, "confpartest", module)

    _close(factory())

    assert cs.run_info["tlsVerified"] is False
