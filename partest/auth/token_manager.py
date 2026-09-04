"""OIDC password-grant TokenManager with per-role cache (Keycloak-compatible)."""

from __future__ import annotations

import logging
import time
from typing import Callable, Dict, Iterable, Optional, Sequence, Tuple

import httpx

from partest.auth.jwt_decode import decode_jwt_payload

CredentialsProvider = Callable[[str], Tuple[str, str]]
logger = logging.getLogger("partest.auth")


class TokenManager:
    """Fetch and cache access tokens by role.

    Domain-specific role lists and env key mapping stay in the consumer.
    Inject:

    - ``credentials_provider(role) -> (username, password)``
    - ``known_roles`` optional validation set
    - Keycloak URL / realm / client_id
    - ``verbose=False`` (default): refresh only at logger.debug; True → info
    """

    def __init__(
        self,
        *,
        keycloak_url: str,
        realm: str,
        client_id: str,
        credentials_provider: CredentialsProvider,
        known_roles: Optional[Sequence[str]] = None,
        default_role: str = "admin",
        safety_margin_sec: int = 45,
        default_lifetime_sec: int = 300,
        verify: bool = False,
        timeout: float = 30.0,
        domain: Optional[str] = None,
        client_secret: Optional[str] = None,
        verbose: bool = False,
    ):
        self.domain = domain
        self.keycloak_url = keycloak_url.rstrip("/")
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self._credentials_provider = credentials_provider
        self._known_roles = set(known_roles) if known_roles is not None else None
        self.default_role = default_role
        self._safety_margin_sec = max(int(safety_margin_sec), 0)
        self._default_lifetime_sec = max(int(default_lifetime_sec), 15)
        self.verify = verify
        self.timeout = timeout
        self.verbose = bool(verbose)
        # role -> (access_token, expires_at_unix)
        self._cache: Dict[str, Tuple[str, float]] = {}

        try:
            self.username, self.password = credentials_provider(default_role)
        except Exception:
            self.username, self.password = "", ""

    def _log(self, msg: str) -> None:
        if self.verbose:
            logger.info(msg)
        else:
            logger.debug(msg)

    def is_fresh(self, role: Optional[str] = None) -> bool:
        role = role or self.default_role
        cached = self._cache.get(role)
        return bool(cached) and time.time() < cached[1]

    def _validate_role(self, role: str) -> None:
        if self._known_roles is not None and role not in self._known_roles:
            raise ValueError(
                f"Unknown role {role!r}; known: {sorted(self._known_roles)}"
            )

    async def get_token(
        self, force_refresh: bool = False, *, role: Optional[str] = None
    ) -> str:
        role = role or self.default_role
        self._validate_role(role)

        now = time.time()
        cached = self._cache.get(role)
        should_refresh = cached is None or force_refresh or now >= cached[1]

        if should_refresh:
            self._log(f"TokenManager: refreshing token for role={role!r}")
            username, password = self._credentials_provider(role)
            token_data = await self._obtain_new_token(username, password)
            access_token = token_data.get("access_token")
            if not access_token:
                raise RuntimeError(
                    f"access_token missing in token response for role `{role}`: {token_data}"
                )
            expires_at = self._compute_expires_at(token_data, access_token)
            self._cache[role] = (access_token, expires_at)
            self._log(
                f"TokenManager: cached role={role!r} expires_in≈"
                f"{max(int(expires_at - time.time()), 0)}s"
            )

        return self._cache[role][0]

    async def get_access_token(
        self, force_refresh: bool = False, *, role: Optional[str] = None
    ) -> str:
        return await self.get_token(force_refresh=force_refresh, role=role)

    async def get_tokens_for_roles(
        self, roles: Optional[Iterable[str]] = None
    ) -> Dict[str, str]:
        if roles is None:
            if self._known_roles is None:
                raise ValueError("roles required when known_roles is not set")
            roles = tuple(self._known_roles)
        return {role: await self.get_token(role=role) for role in roles}

    def _compute_expires_at(self, token_data: dict, access_token: str) -> float:
        margin = self._safety_margin_sec
        try:
            payload = decode_jwt_payload(access_token)
            exp = payload.get("exp")
            if exp is not None:
                return float(exp) - margin
        except Exception:
            pass
        expires_in = token_data.get("expires_in")
        if expires_in is not None:
            return time.time() + max(int(expires_in) - margin, 15)
        return time.time() + max(self._default_lifetime_sec - margin, 15)

    async def _obtain_new_token(self, username: str, password: str) -> dict:
        url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"
        data = {
            "grant_type": "password",
            "client_id": self.client_id,
            "username": username,
            "password": password,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify) as client:
            try:
                response = await client.post(url, headers=headers, data=data)
                if response.status_code != 200:
                    response.raise_for_status()
                token_data = response.json()
                if "access_token" not in token_data:
                    raise RuntimeError(f"No access_token in response: {token_data}")
                return token_data
            except httpx.HTTPStatusError as e:
                raise RuntimeError(
                    f"OIDC HTTP error ({username}): "
                    f"{e.response.status_code} - {e.response.text}"
                ) from e
