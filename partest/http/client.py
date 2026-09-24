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
httpx untouched. ``verify=`` is the one argument that does not travel as given: it goes
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
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from partest.tls import VerifySetting, resolve_verify, verify_for_httpx

__all__ = ["httpx_client", "httpx_async_client"]


def _settled(verify: Optional[VerifySetting]) -> Any:
    """The caller's ``verify=`` after the policy, in the form httpx accepts."""
    return verify_for_httpx(resolve_verify(verify))


def httpx_client(
    *, verify: Optional[VerifySetting] = None, **kwargs: Any
) -> httpx.Client:
    """A synchronous :class:`httpx.Client` under the package's TLS policy.

    ``verify=None`` — the default — means "not specified" and reads
    ``PARTEST_TLS_VERIFY`` / ``confpartest.tls_verify``; everything else is passed to
    httpx as given.
    """
    return httpx.Client(verify=_settled(verify), **kwargs)


def httpx_async_client(
    *, verify: Optional[VerifySetting] = None, **kwargs: Any
) -> httpx.AsyncClient:
    """The same for :class:`httpx.AsyncClient`; see :func:`httpx_client`."""
    return httpx.AsyncClient(verify=_settled(verify), **kwargs)
