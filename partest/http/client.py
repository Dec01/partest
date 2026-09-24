"""httpx clients built inside the package's TLS policy.

:mod:`partest.tls` decides whether a run verifies certificates, warns once when it does
not, and records the answer in ``meta.tlsVerified``. Until now that decision reached only
the clients this package builds for itself. A consumer who needed a client of their own —
a fixture pulling the live specification, a probe against a second service, anything that
is not a suite call — wrote ``httpx.Client(verify=False)`` and left the policy entirely:
nothing was resolved, nothing warned, nothing recorded, and the report still said the run
verified. One consumer suite carried thirty-odd such call sites, one of them fetching a
swagger over an unverified connection in a run whose report read ``tlsVerified: true``.

These two functions are that client, with the decision applied::

    from partest import httpx_client, httpx_async_client

    with httpx_client(base_url=domain, timeout=5.0) as http:
        spec = http.get("/v3/api-docs").json()

    async with httpx_async_client(base_url=domain) as http:
        await http.post("/login", json=payload)

They are a **factory, not a second ``ApiClient``**: no retries, no coverage tracking, no
steps, no attaches, nothing to close differently. Everything the caller passes —
``base_url``, ``timeout``, ``headers``, ``http2``, ``auth``, a ``transport`` — reaches
httpx untouched, and what comes back is a plain ``httpx.Client``, not a subclass and not
a wrapper. ``verify=`` is the one argument that does not travel as given: it goes
through :func:`partest.tls.resolve_verify` first, so an explicit ``verify=False`` warns
and is recorded exactly like the one that comes from ``PARTEST_TLS_VERIFY``, and a CA
bundle path arrives as the :class:`ssl.SSLContext` httpx 0.28 asks for instead of the
string it deprecates.

A call made through such a client is still **invisible to coverage**, like any other raw
httpx call: what should count as covered belongs in ``ApiClient``. The factory removes the
reason to leave the TLS policy, not the reason to use the harness.

The package's own clients settle ``verify=`` once, in their constructor, because that is
where the warning belongs, and hand the settled value here. Re-resolving a settled value
is deliberate and harmless: the warning fires once per process, and recording an
unverified run twice records the same fact.

A client whose policy comes out **off** carries one extra thing: a request event hook
that writes the host of every request it sends into ``meta.tlsUnverifiedHosts``. It lives
here, and not at the call sites, because this is the one place that sees both halves of
the question — the policy, settled at construction, and the URL, known per request. The
alternatives were weighed and left:

* reading ``base_url`` at construction is free, but it answers a different question. It
  is what the client was *pointed at*, not where the request went — a redirect to another
  host leaves no trace — and ``ApiClient``, the road the system under test travels,
  passes no ``base_url`` at all: it builds an absolute URL per call. The signal worth
  saving would have been the one missing;
* wrapping the caller's ``transport`` sees the true host as well, but the wrapper is only
  reachable when a transport is given. Building one ourselves otherwise would hand httpx
  a ``transport=``, and a client built with an explicit transport **ignores** ``verify=``,
  ``http2=`` and the proxy settings — the TLS decision this module exists for would stop
  applying. The caller's transport reaches httpx as the caller's object.

``event_hooks`` is the only argument touched, only for an unverified client, and only by
appending: the caller's hooks run first and keep running.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import httpx

from partest.tls import (
    VerifySetting,
    _verification_is_off,
    note_unverified_host,
    resolve_verify,
    verify_for_httpx,
)

__all__ = ["httpx_client", "httpx_async_client"]

EventHooks = Optional[Mapping[str, list]]


def _recording_hooks(
    settled: VerifySetting, event_hooks: EventHooks, *, is_async: bool
) -> EventHooks:
    """The caller's ``event_hooks``, plus one that names the host — only when off.

    The policy is settled when a client is **built**; the host is known when a request is
    **sent**. httpx calls request hooks in ``_send_handling_redirects``, before the
    transport and once per redirect hop, which is the first moment both are known —
    and the client stays the plain ``httpx.Client`` the caller asked for.

    A verifying client is built exactly as before: no hook, no dictionary copied, nothing
    to pay for the runs that have nothing to record.
    """
    if not _verification_is_off(settled):
        return event_hooks

    def note(request: httpx.Request) -> None:
        note_unverified_host(request.url, settled)

    async def anote(request: httpx.Request) -> None:
        note_unverified_host(request.url, settled)

    hooks = dict(event_hooks or {})
    # Appended, not substituted: the caller's own hooks run first and keep running.
    hooks["request"] = [*(hooks.get("request") or []), anote if is_async else note]
    return hooks


def httpx_client(
    *,
    verify: Optional[VerifySetting] = None,
    env_only: bool = False,
    event_hooks: EventHooks = None,
    **kwargs: Any,
) -> httpx.Client:
    """A synchronous :class:`httpx.Client` under the package's TLS policy.

    ``verify=None`` — the default — means "not specified" and reads
    ``PARTEST_TLS_VERIFY`` / ``confpartest.tls_verify``; everything else is passed to
    httpx as given. ``env_only=True`` stops at the environment, the way
    :func:`partest.tls.default_verify` and :func:`partest.ui.ignore_https_errors` do:
    without it a caller who needed that road had to compute ``verify=`` in the submodule
    and hand the result back in, which is three functions to say one word.

    While verification is off, each request records its host — see
    :func:`partest.tls.note_unverified_host`.
    """
    settled = resolve_verify(verify, env_only=env_only)
    return httpx.Client(
        verify=verify_for_httpx(settled),
        event_hooks=_recording_hooks(settled, event_hooks, is_async=False),
        **kwargs,
    )


def httpx_async_client(
    *,
    verify: Optional[VerifySetting] = None,
    env_only: bool = False,
    event_hooks: EventHooks = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """The same for :class:`httpx.AsyncClient`; see :func:`httpx_client`."""
    settled = resolve_verify(verify, env_only=env_only)
    return httpx.AsyncClient(
        verify=verify_for_httpx(settled),
        event_hooks=_recording_hooks(settled, event_hooks, is_async=True),
        **kwargs,
    )
