"""One place that decides whether a client verifies TLS certificates.

Every HTTP client in this package used to default to ``verify=False``, so a consumer who
wrote ``ApiClient(domain)`` ran the whole suite without certificate validation and had no
way of knowing. A test harness is a poor place to learn that a stand serves the wrong
certificate, but silently accepting any certificate is worse: it also hides a proxy that
should not be there, and it trains a suite to pass in a setup that production would
refuse.

The default is now safe. Turning it back off is one line, because a stand with a
self-signed certificate is ordinary and nobody should have to edit every call site::

    PARTEST_TLS_VERIFY=0                    # environment, wins
    tls_verify = False                      # confpartest.py
    PARTEST_TLS_VERIFY=/etc/ssl/corp.pem    # or trust a private CA instead

The third form keeps verification on where a company CA is the only thing missing. A value
that is neither a boolean word nor an existing path is rejected here, by name: ``flase``
used to travel on as a filename and surfaced much later as a ``FileNotFoundError`` from
inside httpx, which named the value but not the setting it came from.

There are two roads out of this module and they do not accept the same thing:

* **httpx** (``ApiClient``, ``SecHttp``, ``TokenManager``, ``partest.openapi``) deprecated
  ``verify=<path>`` in 0.28 in favour of an :class:`ssl.SSLContext`, and our clients are
  built per request — one deprecation warning per call, which is a hard failure under
  ``filterwarnings = error``. :func:`verify_for_httpx` converts, and caches the context;
* **requests** (``partest.parparser``) takes the path as it is, and reads a different
  environment for its root store when ``verify=True``: ``REQUESTS_CA_BUNDLE`` /
  ``CURL_CA_BUNDLE``, where httpx follows ``ssl``'s own ``SSL_CERT_FILE`` /
  ``SSL_CERT_DIR``. Point ``PARTEST_TLS_VERIFY`` at the bundle and both roads agree.

Disabling verification warns once per process (:class:`TLSVerificationDisabled`): a choice
this consequential should be visible in the run output, and once is enough. A warning does
not survive the session, so the same fact is also recorded in
``partest.call_storage.run_info["tlsVerified"]`` and reaches the report's ``meta``.

That flag is one bit for the whole run and says only that **at least one** connection
went unchecked. One auxiliary service — a self-signed certificate reached while a plugin
configures itself, before a single test runs — turns it off for a run that verified the
system under test from the first call to the last. :func:`note_unverified_host` and
:func:`note_unknown_tls_host` write *which* hosts those were, next to the flag and
without touching it (``meta.tlsUnverifiedHosts``, ``meta.tlsUnknownHosts``).
"""

from __future__ import annotations

import os
import ssl
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Union

from partest.flags import coerce_bool

__all__ = [
    "VerifySetting",
    "VERIFY_ENV",
    "VERIFY_CONF_ATTR",
    "TLSVerificationDisabled",
    "default_verify",
    "resolve_verify",
    "verify_for_httpx",
    "is_certificate_error",
    "certificate_error",
    "note_unverified_host",
    "note_unknown_tls_host",
]

#: What a client may be told: on/off, a CA bundle to trust, or a ready SSL context —
#: the only form httpx does not deprecate. A path cannot express a context, so
#: ``PARTEST_TLS_VERIFY`` covers the first two and code covers the third.
VerifySetting = Union[bool, str, ssl.SSLContext]

VERIFY_ENV = "PARTEST_TLS_VERIFY"
VERIFY_CONF_ATTR = "tls_verify"

#: The release that made verification the default. Named in the failure message, because
#: that message is where most consumers will first meet the change.
VERIFIED_SINCE = "2.0.0"

_warned = False


class TLSVerificationDisabled(UserWarning):
    """Certificate verification is off for this run.

    Its own category so a project that means it can silence exactly this one:
    ``filterwarnings = ignore::partest.tls.TLSVerificationDisabled``.
    """


def _coerce(value: Any, *, source: str) -> Optional[VerifySetting]:
    """``None`` when nothing was said; otherwise a bool, a CA bundle path or a context.

    *source* names where the value came from, so a rejected value can say which setting to
    go and fix.
    """
    if value is None or isinstance(value, (bool, ssl.SSLContext)):
        return value
    text = str(value).strip()
    if not text:
        return None
    flag = coerce_bool(text)
    if flag is not None:
        return flag
    if not Path(text).exists():
        raise ValueError(
            f"partest: {source}={value!r} is neither a boolean nor a path that exists. "
            f"Use 1/0 (true/false, on/off) to switch certificate verification, or give "
            f"the path to a CA bundle file or directory. Nothing was verified or "
            f"disabled — fix the setting."
        )
    return text


def _from_confpartest() -> Optional[VerifySetting]:
    # Imported here, not at module scope: the browser side of the package reaches this
    # module through ``default_verify(env_only=True)``, and a UI job must not load
    # ``confpartest`` at all (AGENTS.md red line 8, tests/test_ui_isolation.py). Keeping
    # the import inside the branch that is never taken there makes that structural.
    from partest.conf import conf_attr

    return _coerce(
        conf_attr(VERIFY_CONF_ATTR), source=f"confpartest.{VERIFY_CONF_ATTR}"
    )


def default_verify(*, env_only: bool = False) -> VerifySetting:
    """The ``verify=`` a client uses when the caller did not say (env wins).

    ``env_only=True`` reads the environment and stops there. That is the UI road: the
    browser context must not pull ``confpartest`` into a UI job, so on that road
    ``tls_verify`` in the project file is deliberately invisible — and the pages say so.
    """
    value = _coerce(os.getenv(VERIFY_ENV), source=VERIFY_ENV)
    if value is None and not env_only:
        value = _from_confpartest()
    if value is None:
        return True
    return value


def _reset_warning_state() -> None:
    """Allow the warning to fire again (tests; a fresh process starts unwarned)."""
    global _warned
    _warned = False


def _warn_once() -> None:
    global _warned
    if _warned:
        return
    _warned = True
    warnings.warn(
        "partest: TLS certificate verification is disabled for this run — responses "
        f"can come from anyone on the path. Set {VERIFY_ENV}=1 (or a CA bundle path) "
        "to turn it back on.",
        TLSVerificationDisabled,
        stacklevel=3,
    )


def _record_unverified() -> None:
    """Leave the fact in the run artifact; a warning does not outlive the session."""
    try:
        from partest.call_storage import run_info

        run_info["tlsVerified"] = False
    except Exception:  # storage is optional for a library-only user
        pass


def note_unverified_host(url: Any, setting: VerifySetting) -> None:
    """Record *url*'s host when *setting* means its certificate was not checked.

    ``tlsVerified`` is one bit for a whole run, and one auxiliary service is enough to
    switch it off: on one consumer a plugin signs into an auxiliary service with a
    self-signed certificate during ``pytest_configure``, so *every* run of that project
    reported ``false`` — including runs that never called the API at all. The bit stayed honest and stopped being
    informative. Naming the hosts puts the difference back: "the whole suite ran
    unverified" and "one service host was accepted, the stand was verified" are again two
    different artifacts.

    *setting* is re-checked rather than assumed, so a caller cannot record a host under a
    policy that verifies. Nothing is recorded for a URL without a host.
    """
    if not _verification_is_off(setting):
        return
    try:
        from partest.call_storage import record_unverified_host

        record_unverified_host(url)
    except Exception:  # storage is optional for a library-only user
        pass


def note_unknown_tls_host(url: Any) -> None:
    """Record a host whose TLS partest did not decide and cannot read.

    The one case the library knows it does not know: ``ApiClient(domain, client=hx)``
    sets ``self.verify = None`` because the injected client settled ``verify=`` before
    partest saw it — and the artifact of that same run used to say ``tlsVerified: true``.
    A separate list rather than a third value of the flag: adding a key to ``meta`` is
    compatible, changing the type of one is not.
    """
    try:
        from partest.call_storage import record_unknown_tls_host

        record_unknown_tls_host(url)
    except Exception:  # storage is optional for a library-only user
        pass


def _verification_is_off(value: VerifySetting) -> bool:
    """Whether *value* means "this run does not check certificates".

    ``False`` is the obvious spelling, and it is not the only one: :data:`VerifySetting`
    publicly accepts an :class:`ssl.SSLContext`, and a context built with
    ``verify_mode = ssl.CERT_NONE`` accepts any certificate exactly as ``verify=False``
    does. Reading only the boolean let such a context travel through unwarned and
    unrecorded, and the report then said ``meta.tlsVerified: true`` about a run that
    verified nothing — which is the one thing that field exists to prevent.

    ``check_hostname`` is deliberately not consulted: a context that still builds the
    chain to a trusted root is weakened, not off, and calling it off would make the flag
    lie in the other direction.
    """
    if value is False:
        return True
    if isinstance(value, ssl.SSLContext):
        return value.verify_mode == ssl.CERT_NONE
    return False


def resolve_verify(
    verify: Optional[VerifySetting] = None,
    *,
    env_only: bool = False,
) -> VerifySetting:
    """Settle the ``verify=`` of one client and warn if it ends up off.

    ``None`` means "not specified" and falls back to :func:`default_verify`. An explicit
    ``verify=False`` is honoured — and still warns, because the point of the warning is
    that the run is unverified, not how it got that way. A context with
    ``verify_mode = ssl.CERT_NONE`` is the same choice spelled differently and is treated
    the same. ``env_only`` is passed through for the UI road; see :func:`default_verify`.
    """
    if verify is None:
        value: VerifySetting = default_verify(env_only=env_only)
    else:
        value = _coerce(verify, source="verify=")  # type: ignore[assignment]
    if _verification_is_off(value):
        _warn_once()
        _record_unverified()
    return value


@lru_cache(maxsize=8)
def _context_for(path: str) -> ssl.SSLContext:
    """An SSL context trusting *path*, built once per path.

    Cached because the default client is built per request: re-reading the bundle on every
    call would be pure overhead. The cost is that editing the bundle mid-run is not picked
    up, which no run does.
    """
    if Path(path).is_dir():
        return ssl.create_default_context(capath=path)
    return ssl.create_default_context(cafile=path)


def verify_for_httpx(setting: Optional[VerifySetting]) -> Union[bool, ssl.SSLContext]:
    """The same decision in the form httpx still accepts.

    httpx 0.28 warns on ``verify=<str>`` and asks for ``ssl.create_default_context(
    cafile=...)``; ``requests`` has no such deprecation, which is why the conversion lives
    at the httpx call sites and not in :func:`resolve_verify`. ``None`` — nobody decided —
    verifies.
    """
    if setting is None:
        return True
    if isinstance(setting, str):
        return _context_for(setting)
    return setting


def is_certificate_error(exc: BaseException) -> bool:
    """Whether *exc* is a rejected certificate wrapped by an HTTP client.

    httpx reports one as ``ConnectError``, a subclass of ``RequestError`` — which to a
    retry policy looks exactly like a refused connection. It is not transient: nothing the
    next attempt does will make the certificate valid, and after the default changed the
    failure is suite-wide, so retrying multiplies one wrong setting by the retry count
    over every test.

    Only a **certificate** failure qualifies. ``ssl.SSLEOFError``,
    ``ssl.SSLZeroReturnError`` and ``ssl.SSLSyscallError`` are subclasses of
    ``ssl.SSLError`` and say nothing about a certificate — they are a connection that
    dropped, and a connection that dropped is exactly what a retry is for. Matching the
    base class stopped them from being retried and answered a dropped connection with a
    message advising the consumer to turn certificate verification off.

    The chain is walked through both ``__cause__`` and ``__context__``, and
    ``requests``/``urllib3`` are matched by class name: they define their own ``SSLError``
    and this module does not import either. That branch skips anything from ``ssl``
    itself — there the class hierarchy is the better evidence, and a bare
    ``ssl.SSLError`` would otherwise come back through the name and undo the narrowing.
    """
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        if not isinstance(current, ssl.SSLError) and type(current).__name__ in {
            "SSLError",
            "SSLCertVerificationError",
        }:
            return True
        current = current.__cause__ or current.__context__
    return False


def certificate_error(
    exc: BaseException,
    *,
    url: str = "",
    verify: Any = None,
) -> BaseException:
    """The same failure with a message that names the switch. Returns, does not raise.

    ``[SSL: CERTIFICATE_VERIFY_FAILED]`` re-logged as "Network/request error" tells a
    consumer nothing about a default that changed under them, and neither
    ``PARTEST_TLS_VERIFY`` nor this module appears in it. The type is preserved, so a suite
    that catches ``httpx.ConnectError`` keeps catching it; the original stays reachable as
    ``__cause__`` at the ``raise ... from`` call site.
    """
    where = f" for {url}" if url else ""
    # httpx wraps the ssl failure, and its own text is terse — "certificate verify
    # failed". What tells the consumer *which* check failed ("unable to get local issuer
    # certificate", "hostname mismatch", an expiry date) lives in the ssl error it wraps.
    # Quoting only the wrapper would replace a useless message with a longer useless one.
    detail = f"{type(exc).__name__}: {exc}"
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if isinstance(cause, ssl.SSLError) and str(cause) not in str(exc):
        detail += f" ← {type(cause).__name__}: {cause}"
    message = (
        f"partest: TLS certificate verification failed{where}.\n"
        f"  Certificates are verified from partest {VERIFIED_SINCE} on; before that every "
        f"client in the package accepted any certificate, silently.\n"
        f"  Signed by your own CA? Trust it and keep checking:\n"
        f"      {VERIFY_ENV}=/path/to/ca.pem   "
        f"(or {VERIFY_CONF_ATTR} = \"/path/to/ca.pem\" in confpartest.py)\n"
        f"  Or switch verification off for the run — every response then comes from "
        f"whoever answered:\n"
        f"      {VERIFY_ENV}=0                 "
        f"(or {VERIFY_CONF_ATTR} = False in confpartest.py)\n"
        f"  This call used verify={verify!r}.\n"
        f"  Original error: {detail}"
    )
    try:
        rebuilt = type(exc)(message)
    except Exception:  # an exception type with a signature of its own
        return RuntimeError(message)
    try:  # httpx's RequestError.request raises unless it was set
        rebuilt.request = exc.request  # type: ignore[attr-defined]
    except Exception:
        pass
    return rebuilt
