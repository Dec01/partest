"""Helpers for the four RequestPermissions cells.

``request_permissions`` is one test-case type covering four different security layers.
Suites routinely collapse them into "there is a 401 somewhere", which leaves three
classes of bug uncovered: a filter chain that guards the collection but not
``/{id}``, an account disabled in the application rather than in the identity
provider, and an object that exists but belongs to someone else.

Nothing here knows about roles, users or an ``active`` flag — those are the project's.
The library provides the vocabulary and the anonymous header builders; the project
supplies real credentials and an implementation of :class:`UserActivity`.

See the cookbook page (``python -m partest.docs show howto-permissions``).
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, NamedTuple, Optional, Sequence, Union

from partest.test_types import PERMISSION_CELLS, TypesTestCases, permission_cell_label

# A deliberately malformed compact JWS: three segments, valid characters, garbage
# payload. Enough for a server to reject it as unparsable without any key material.
INVALID_BEARER = "eyJhbGciOiJIUzI1NiJ9.bm90LWEtcmVhbC1wYXlsb2Fk.bm90LWEtc2lnbmF0dXJl"


def anonymous_headers(extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Headers for the ``unauth`` cell: everything except authentication."""
    headers = {"Accept": "application/json"}
    if extra:
        headers.update(dict(extra))
    headers.pop("Authorization", None)
    return headers


def invalid_bearer_headers(
    extra: Optional[Mapping[str, str]] = None,
    *,
    token: str = INVALID_BEARER,
    scheme: str = "Bearer",
) -> Dict[str, str]:
    """Headers carrying a syntactically valid but unusable token.

    Distinct from :func:`anonymous_headers`: a missing header and a broken token can
    take different code paths, and only one of them is usually tested.
    """
    headers = anonymous_headers(extra)
    headers["Authorization"] = f"{scheme} {token}".strip()
    return headers


class AccessCase(NamedTuple):
    """One permission cell, ready to feed into ``pytest.mark.parametrize``."""

    cell: str
    method: str
    path: str
    headers: Optional[Mapping[str, str]]
    expected: Union[int, Sequence[int]]

    @property
    def label(self) -> str:
        return permission_cell_label(self.cell)

    @property
    def test_type(self) -> str:
        """All four cells record as the same test-case type — see the ADR."""
        return TypesTestCases.request_permissions

    @property
    def id(self) -> str:
        """Readable parametrize id: ``unauth-GET-/items/{id}``."""
        return f"{self.cell}-{self.method.upper()}-{self.path}"


def access_cases(
    method: str,
    path: str,
    *,
    allowed_headers: Optional[Mapping[str, str]] = None,
    foreign_headers: Optional[Mapping[str, str]] = None,
    inactive_headers: Optional[Mapping[str, str]] = None,
    allow_status: Union[int, Sequence[int]] = 200,
    deny_status: Union[int, Sequence[int]] = 403,
    unauth_status: Union[int, Sequence[int]] = 401,
) -> list:
    """Build the cells the project can actually exercise.

    Cells whose headers are not supplied are skipped rather than guessed — an
    endpoint on an open reference catalogue genuinely has no ``no_access`` cell, and
    inventing a passing case there is worse than leaving it out. Mark such cells N/A
    explicitly in the suite instead of letting them disappear silently.
    """
    cases = []
    if allowed_headers is not None:
        cases.append(AccessCase("allow", method, path, allowed_headers, allow_status))
    if foreign_headers is not None:
        cases.append(AccessCase("no_access", method, path, foreign_headers, deny_status))
    if inactive_headers is not None:
        cases.append(AccessCase("inactive", method, path, inactive_headers, deny_status))
    cases.append(AccessCase("unauth", method, path, anonymous_headers(), unauth_status))
    return cases


class UserActivity:
    """Protocol for disabling an account **in the application**, not in the IdP.

    Disabling a user in the identity provider invalidates tokens and tends to break
    the whole stand for everyone. The ``inactive`` cell needs the opposite: a valid
    token whose account the application refuses to serve.

    Implement with whatever the project has — an admin endpoint, a service call, a
    direct update — and always restore in a ``finally``:

        class ApiUserActivity(UserActivity):
            def __init__(self, admin_client):
                self._client = admin_client

            async def set_active(self, user_id, active):
                await self._client.make_request(
                    "PATCH", "/admin/users", add_url1=f"/{user_id}",
                    json_data={"active": active}, expected_status_code=200,
                )
    """

    async def set_active(self, user_id: Any, active: bool) -> None:
        raise NotImplementedError

    async def snapshot(self, user_id: Any) -> bool:
        """Current state, so the caller can restore exactly what it found."""
        raise NotImplementedError


__all__ = [
    "INVALID_BEARER",
    "AccessCase",
    "UserActivity",
    "access_cases",
    "anonymous_headers",
    "invalid_bearer_headers",
    "PERMISSION_CELLS",
]
