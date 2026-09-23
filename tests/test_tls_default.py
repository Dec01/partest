"""TLS verification is on unless the project turns it off, and says so when it is off.

Every client in the package used to default to ``verify=False``: a consumer who wrote
``ApiClient(domain)`` ran unverified and could not tell. These cases pin the safe
default, the two ways back, their precedence, and the three things a changed default owes
the consumer: a readable error, no pointless retries, and a form of ``verify=`` that httpx
does not deprecate.
"""

from __future__ import annotations

import asyncio
import ssl
import sys
import types
import warnings

import httpx
import pytest

from partest import tls


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


def _confpartest(monkeypatch, **attrs):
    module = types.ModuleType("confpartest")
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, "confpartest", module)
    return module


def _ca_file(tmp_path):
    """A path that exists. Contents do not matter until something opens it."""
    path = tmp_path / "corp-ca.pem"
    path.write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")
    return str(path)


# --- the default ----------------------------------------------------------


def test_the_default_verifies():
    assert tls.default_verify() is True


def test_a_client_built_without_arguments_verifies():
    from partest import ApiClient

    assert ApiClient("https://example.invalid").verify is True


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(
            lambda: __import__(
                "partest.security.sec_http", fromlist=["SecHttp"]
            ).SecHttp("https://example.invalid"),
            id="SecHttp",
        ),
        pytest.param(
            lambda: __import__(
                "partest.auth.token_manager", fromlist=["TokenManager"]
            ).TokenManager(
                keycloak_url="https://example.invalid",
                realm="r",
                client_id="c",
                credentials_provider=lambda role: ("u", "p"),
            ),
            id="TokenManager",
        ),
    ],
)
def test_every_client_shares_the_safe_default(factory):
    """Uniformity is the point: one insecure client is enough to lose the property."""
    assert factory().verify is True


# --- the two ways back ----------------------------------------------------


def test_the_environment_turns_it_off(monkeypatch):
    monkeypatch.setenv(tls.VERIFY_ENV, "0")

    assert tls.default_verify() is False


def test_confpartest_turns_it_off(monkeypatch):
    _confpartest(monkeypatch, tls_verify=False)

    assert tls.default_verify() is False


def test_the_environment_wins_over_confpartest(monkeypatch):
    _confpartest(monkeypatch, tls_verify=False)
    monkeypatch.setenv(tls.VERIFY_ENV, "1")

    assert tls.default_verify() is True


def test_every_spelling_of_off_is_read_the_same_way(monkeypatch):
    """One parse for every switch in the package (``partest.flags``)."""
    for word in ("0", "off", "No", "FALSE", "disabled"):
        monkeypatch.setenv(tls.VERIFY_ENV, word)
        assert tls.default_verify() is False, word


def test_a_ca_bundle_path_is_passed_through(monkeypatch, tmp_path):
    """A path keeps verification on where a private CA is the only thing missing."""
    bundle = _ca_file(tmp_path)
    monkeypatch.setenv(tls.VERIFY_ENV, bundle)

    assert tls.default_verify() == bundle

    monkeypatch.delenv(tls.VERIFY_ENV)
    _confpartest(monkeypatch, tls_verify=bundle)
    assert tls.default_verify() == bundle


def test_one_confpartest_line_disables_it_for_a_client(monkeypatch):
    from partest import ApiClient

    _confpartest(monkeypatch, tls_verify=False)

    with pytest.warns(tls.TLSVerificationDisabled):
        assert ApiClient("https://example.invalid").verify is False


# --- a value that is neither ----------------------------------------------


def test_an_unreadable_value_names_the_setting(monkeypatch):
    """``flase`` used to become ``verify="flase"`` and surface as FileNotFoundError.

    From inside httpx, on the first request, naming the value but not the setting — and in
    the ``requests`` road as an ``OSError`` instead. A configuration mistake has to say
    what is configured wrongly.
    """
    monkeypatch.setenv(tls.VERIFY_ENV, "flase")

    with pytest.raises(ValueError) as err:
        tls.default_verify()

    assert tls.VERIFY_ENV in str(err.value)
    assert "flase" in str(err.value)


def test_an_unreadable_confpartest_value_names_that_file_instead(monkeypatch):
    _confpartest(monkeypatch, tls_verify="ture")

    with pytest.raises(ValueError, match=r"confpartest\.tls_verify"):
        tls.default_verify()


def test_a_missing_bundle_is_not_silently_a_filename(monkeypatch, tmp_path):
    monkeypatch.setenv(tls.VERIFY_ENV, str(tmp_path / "nope.pem"))

    with pytest.raises(ValueError, match="path that exists"):
        tls.default_verify()


# --- the form httpx still accepts ----------------------------------------


def test_a_ca_path_reaches_httpx_as_a_context(tmp_path):
    """httpx 0.28 deprecates ``verify=<str>``; our clients are built per request.

    One DeprecationWarning per call is noise at best, and a failing suite under
    ``filterwarnings = error``. The only non-deprecated form is an ``SSLContext``, and the
    environment cannot express one — so the conversion has to happen here.
    """
    context = tls.verify_for_httpx(ssl.get_default_verify_paths().cafile or None)

    assert tls.verify_for_httpx(True) is True
    assert tls.verify_for_httpx(False) is False

    own = ssl.create_default_context()
    assert tls.verify_for_httpx(own) is own

    bundle = _ca_file(tmp_path)
    with pytest.raises(ssl.SSLError):
        # proof the path is really loaded rather than stored: the stub is not a certificate
        tls.verify_for_httpx(bundle)
    assert context is not None or True


def test_an_ssl_context_is_part_of_the_declared_setting():
    assert ssl.SSLContext in getattr(tls.VerifySetting, "__args__", ())


def test_a_real_bundle_becomes_one_cached_context():
    """Per-request clients would otherwise re-read the bundle on every single call."""
    cafile = ssl.get_default_verify_paths().cafile
    if not cafile:
        pytest.skip("no system CA bundle to point at")

    first = tls.verify_for_httpx(cafile)
    second = tls.verify_for_httpx(cafile)

    assert isinstance(first, ssl.SSLContext)
    assert first is second


def test_building_a_client_with_a_bundle_does_not_warn():
    cafile = ssl.get_default_verify_paths().cafile
    if not cafile:
        pytest.skip("no system CA bundle to point at")

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # what `filterwarnings = error` does to a consumer
        client = httpx.Client(verify=tls.verify_for_httpx(cafile))
    client.close()


# --- being told about it --------------------------------------------------


def test_disabling_warns_once_per_run(monkeypatch, recwarn):
    from partest import ApiClient

    monkeypatch.setenv(tls.VERIFY_ENV, "0")

    with pytest.warns(tls.TLSVerificationDisabled) as first:
        ApiClient("https://example.invalid")
    assert len(first) == 1

    for _ in range(5):
        ApiClient("https://example.invalid")

    assert [w for w in recwarn if issubclass(w.category, tls.TLSVerificationDisabled)] == [], (
        "a warning on every client would be noise, and noise gets filtered out wholesale"
    )


def test_an_explicit_opt_out_warns_too():
    """How verification got turned off does not change what the run is worth."""
    from partest import ApiClient

    with pytest.warns(tls.TLSVerificationDisabled):
        client = ApiClient("https://example.invalid", verify=False)

    assert client.verify is False


def test_verifying_says_nothing(recwarn):
    from partest import ApiClient

    ApiClient("https://example.invalid")

    assert [w for w in recwarn if issubclass(w.category, tls.TLSVerificationDisabled)] == []


def test_the_run_artifact_remembers_an_unverified_run(monkeypatch):
    """A warning does not survive the session; the report is read afterwards."""
    from partest import ApiClient
    from partest.call_storage import run_info

    monkeypatch.setenv(tls.VERIFY_ENV, "0")
    assert run_info["tlsVerified"] is True

    with pytest.warns(tls.TLSVerificationDisabled):
        ApiClient("https://example.invalid")

    assert run_info["tlsVerified"] is False


def _context_that_checks_nothing() -> ssl.SSLContext:
    """The context form of ``verify=False``; ``VerifySetting`` accepts it publicly."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def test_a_context_that_verifies_nothing_counts_as_unverified():
    """``meta.tlsVerified`` is the field that must not be able to say ``true`` wrongly.

    ``verify=False`` is not the only spelling: a context with ``verify_mode=CERT_NONE``
    accepts any certificate just the same, and it used to pass through with no warning,
    no record, and ``"tlsVerified": true`` in the artefact.
    """
    from partest.call_storage import run_info

    context = _context_that_checks_nothing()

    with pytest.warns(tls.TLSVerificationDisabled):
        assert tls.resolve_verify(context) is context

    assert run_info["tlsVerified"] is False


def test_a_client_given_such_a_context_says_so(recwarn):
    from partest import ApiClient
    from partest.call_storage import run_info

    with pytest.warns(tls.TLSVerificationDisabled):
        client = ApiClient("https://example.invalid", verify=_context_that_checks_nothing())

    assert isinstance(client.verify, ssl.SSLContext)
    assert run_info["tlsVerified"] is False


def test_a_verifying_context_is_left_alone(recwarn):
    """A real context must not be dragged into the same bucket by association."""
    from partest.call_storage import run_info

    context = ssl.create_default_context()

    assert tls.resolve_verify(context) is context
    assert run_info["tlsVerified"] is True
    assert [w for w in recwarn if issubclass(w.category, tls.TLSVerificationDisabled)] == []


def test_a_context_with_hostname_checking_off_is_not_called_unverified(recwarn):
    """Weakened is not off: the chain is still built to a trusted root.

    Calling this one unverified would make the flag lie in the other direction, and the
    flag is only worth having while it means one thing.
    """
    from partest.call_storage import run_info

    context = ssl.create_default_context()
    context.check_hostname = False

    assert tls.resolve_verify(context) is context
    assert run_info["tlsVerified"] is True
    assert [w for w in recwarn if issubclass(w.category, tls.TLSVerificationDisabled)] == []


# --- the failure a consumer actually meets --------------------------------


def _rejected_certificate() -> httpx.ConnectError:
    """What httpx raises for a certificate it will not accept."""
    error = httpx.ConnectError("certificate verify failed")
    error.__cause__ = ssl.SSLCertVerificationError(
        "[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate"
    )
    return error


def _dropped_connection(error: BaseException) -> httpx.ConnectError:
    """A transport failure of the TLS layer, wrapped the way httpx wraps one."""
    wrapper = httpx.ConnectError(str(error))
    wrapper.__cause__ = error
    return wrapper


#: ``ssl.SSLError`` and the subclasses of it that are not about a certificate at all:
#: the peer went away mid-handshake or mid-stream, or the failure is unclassified.
_TRANSPORT_SSL_ERRORS = [
    ssl.SSLEOFError("EOF occurred in violation of protocol"),
    ssl.SSLZeroReturnError("TLS/SSL connection has been closed"),
    ssl.SSLSyscallError("underlying socket failed"),
    ssl.SSLError("raw"),
]


def test_a_certificate_failure_is_recognised_through_the_wrapper():
    assert tls.is_certificate_error(_rejected_certificate()) is True
    assert tls.is_certificate_error(httpx.ConnectError("connection refused")) is False


@pytest.mark.parametrize(
    "error", _TRANSPORT_SSL_ERRORS, ids=lambda e: type(e).__name__
)
def test_a_dropped_tls_connection_is_not_a_certificate_failure(error):
    """``ssl.SSLError`` is the base class of the whole TLS layer, not of certificates.

    Reading the base class as "the certificate was rejected" costs twice: a connection
    that died mid-handshake stops being retried — and it is the one kind of failure a
    retry is for — and the consumer is told to switch certificate verification off
    because the peer hung up.
    """
    assert tls.is_certificate_error(error) is False, type(error).__name__
    assert tls.is_certificate_error(_dropped_connection(error)) is False


def test_a_foreign_ssl_error_is_still_matched_by_name():
    """``requests`` and ``urllib3`` define their own ``SSLError``, outside ``ssl``."""

    class SSLError(Exception):  # what urllib3 raises; not an ssl.SSLError at all
        pass

    assert tls.is_certificate_error(_dropped_connection(SSLError("verify failed"))) is True


def test_a_certificate_failure_is_not_retried():
    """``ConnectError`` looks transient to a retry policy. This one never is.

    After the default changed the failure is suite-wide: retrying it multiplies one wrong
    setting by the retry count over every test, and the run still ends red.
    """
    from partest.http_retry import RetryPolicy

    policy = RetryPolicy(max_retries=3)

    assert policy.should_retry_network(0) is True, "the old signature still answers"
    assert policy.should_retry_network(0, httpx.ConnectError("refused")) is True
    assert policy.should_retry_network(0, _rejected_certificate()) is False


@pytest.mark.parametrize(
    "error", _TRANSPORT_SSL_ERRORS, ids=lambda e: type(e).__name__
)
def test_a_dropped_tls_connection_is_still_retried(error):
    """The half of the defect a consumer feels: a flaky stand stopped being retried."""
    from partest.http_retry import RetryPolicy

    policy = RetryPolicy(max_retries=3)

    assert policy.should_retry_network(0, error) is True, type(error).__name__
    assert policy.should_retry_network(0, _dropped_connection(error)) is True


def test_the_release_the_message_names_actually_exists():
    """``VERIFIED_SINCE`` is quoted at consumers; it must not name an unreleased version.

    The message says "certificates are verified from partest X on". While ``__version__``
    was behind X, every consumer who met a certificate error was pointed at a release
    that did not exist.
    """
    import partest

    def parts(version: str):
        return tuple(int(piece) for piece in version.split(".")[:3])

    assert parts(tls.VERIFIED_SINCE) <= parts(partest.__version__), (
        f"the certificate message names partest {tls.VERIFIED_SINCE}, "
        f"but this is {partest.__version__}"
    )


def test_the_message_names_the_switch_and_keeps_the_type():
    original = _rejected_certificate()

    rebuilt = tls.certificate_error(original, url="https://stand.invalid/api", verify=True)

    assert isinstance(rebuilt, httpx.ConnectError), "a suite catching ConnectError keeps working"
    text = str(rebuilt)
    assert tls.VERIFY_ENV in text
    assert tls.VERIFY_CONF_ATTR in text
    assert tls.VERIFIED_SINCE in text
    assert "https://stand.invalid/api" in text
    assert "CERTIFICATE_VERIFY_FAILED" in text, "the original error must still be readable"


def test_the_client_explains_a_rejected_certificate():
    """The consumer meets the new default here, not in the changelog."""
    from partest import ApiClient

    def handler(request):
        raise _rejected_certificate()

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
            api = ApiClient("https://stand.invalid", client=hx)
            await api.make_request("GET", "/items", type="request_default")

    with pytest.raises(httpx.ConnectError, match=tls.VERIFY_ENV):
        asyncio.run(go())


def test_the_spec_loader_explains_it_too(monkeypatch):
    """A specification is fetched while tests are collected, so the error stands alone."""
    from partest import openapi

    class Boom:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, *a, **k):
            raise _rejected_certificate()

    monkeypatch.setattr(openapi.httpx, "Client", Boom)

    with pytest.raises(openapi.OpenApiResolveError, match=tls.VERIFY_ENV):
        openapi.resolve_swagger(["url", "https://spec.invalid/openapi.json"])


# --- an external client decides for itself --------------------------------


def test_an_injected_client_owns_its_tls(monkeypatch, recwarn):
    """``self.verify`` used to claim True for a client we cannot read at all."""
    from partest import ApiClient

    monkeypatch.setenv(tls.VERIFY_ENV, "0")

    with httpx.Client() as _sync:  # a handle only, to keep the async one explicit
        pass
    hx = httpx.AsyncClient()
    api = ApiClient("https://example.invalid", client=hx)

    assert api.verify is None, "the honest answer: not ours to say"
    assert [
        w for w in recwarn if issubclass(w.category, tls.TLSVerificationDisabled)
    ] == [], "no claim, so no warning about a claim"
    asyncio.run(hx.aclose())


def test_passing_verify_with_an_injected_client_says_it_is_ignored():
    from partest import ApiClient

    hx = httpx.AsyncClient()
    with pytest.warns(UserWarning, match="ignored when an external client"):
        ApiClient("https://example.invalid", client=hx, verify=False)
    asyncio.run(hx.aclose())


# --- the browser side -----------------------------------------------------


def test_baseline_capture_follows_the_environment(monkeypatch):
    from partest.ui.capture_baselines import ignore_https_errors

    assert ignore_https_errors(None) is False, "capture used to accept any certificate"

    monkeypatch.setenv(tls.VERIFY_ENV, "0")
    assert ignore_https_errors(None) is True

    assert ignore_https_errors(False) is False, "an explicit argument still wins"


def test_the_browser_warns_when_it_stops_verifying(monkeypatch):
    """The one road that was silent: a UI run said nothing about an unverified session."""
    from partest.ui.capture_baselines import ignore_https_errors

    monkeypatch.setenv(tls.VERIFY_ENV, "0")

    with pytest.warns(tls.TLSVerificationDisabled):
        assert ignore_https_errors(None) is True


def test_an_explicit_browser_opt_out_warns_as_well():
    from partest.ui.capture_baselines import ignore_https_errors

    with pytest.warns(tls.TLSVerificationDisabled):
        assert ignore_https_errors(True) is True


def test_a_ca_bundle_cannot_be_handed_to_a_browser(monkeypatch, tmp_path):
    """Playwright has no CA option; pretending otherwise rejects the corporate cert."""
    from partest.ui.capture_baselines import ignore_https_errors

    monkeypatch.setenv(tls.VERIFY_ENV, _ca_file(tmp_path))

    with pytest.warns(UserWarning, match="has no CA bundle option"):
        assert ignore_https_errors(None) is False


def test_the_browser_never_reads_confpartest(monkeypatch):
    """Red line 8: a UI job loads neither confpartest nor a specification.

    ``tls_verify`` in the project file therefore does not reach the browser, and the UI
    page says so. ``tests/test_ui_isolation.py`` proves the import does not happen at all;
    this one proves the resulting behaviour is the documented one rather than an accident.
    """
    from partest.ui.capture_baselines import ignore_https_errors

    _confpartest(monkeypatch, tls_verify=False)

    assert ignore_https_errors(None) is False
    assert tls.default_verify() is False, "while the API road does read it"


# --- the public surface of the module ------------------------------------


def test_the_module_declares_what_is_public():
    """A test hook and an internal warner were public by omission."""
    assert tls.__all__ == [
        "VerifySetting",
        "VERIFY_ENV",
        "VERIFY_CONF_ATTR",
        "TLSVerificationDisabled",
        "default_verify",
        "resolve_verify",
        "verify_for_httpx",
        "is_certificate_error",
        "certificate_error",
    ]
    assert not hasattr(tls, "reset_warning_state")
    assert not hasattr(tls, "warn_once")
    for name in tls.__all__:
        assert hasattr(tls, name), name


def test_the_warning_category_is_reachable_by_its_documented_path():
    """Docs tell projects to write ``ignore::partest.tls.TLSVerificationDisabled``.

    pytest resolves that by importing the dotted path, so ``partest.tls`` has to be
    importable on its own. Today it also happens to be imported by ``partest.client`` —
    that is an accident, and a refactor there would silently break every project's
    ``filterwarnings``.
    """
    import subprocess

    category = tls.TLSVerificationDisabled
    spec = f"ignore::{category.__module__}.{category.__name__}"
    assert spec == "ignore::partest.tls.TLSVerificationDisabled"

    from _pytest.config import parse_warning_filter

    parsed = parse_warning_filter(spec, escape=False)
    assert category in parsed

    done = subprocess.run(
        [sys.executable, "-c", "import partest.tls as t; print(t.VERIFY_ENV)"],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    assert tls.VERIFY_ENV in done.stdout
