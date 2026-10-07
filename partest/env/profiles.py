"""Optional env profiles (Keycloak, frontend) — no product secrets.

Usage::

    from partest.env.profiles import keycloak_settings, frontend_url

    kc = keycloak_settings()  # raises if required vars missing
    tm = TokenManager(**kc.as_token_manager_kwargs(), credentials_provider=…)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from partest.env import env, require_env


@dataclass(frozen=True)
class KeycloakSettings:
    url: str
    realm: str
    client_id: str
    client_secret: Optional[str] = None

    def as_token_manager_kwargs(self) -> dict:
        kw = {
            "keycloak_url": self.url,
            "realm": self.realm,
            "client_id": self.client_id,
        }
        if self.client_secret:
            kw["client_secret"] = self.client_secret
        return kw


def keycloak_url(env_name: str = "KEYCLOAK_URL") -> str:
    return require_env(env_name).rstrip("/")


def keycloak_realm(env_name: str = "KEYCLOAK_REALM") -> str:
    return require_env(env_name)


def keycloak_client_id(env_name: str = "KEYCLOAK_CLIENT_ID") -> str:
    return require_env(env_name)


def keycloak_client_secret(
    env_name: str = "KEYCLOAK_CLIENT_SECRET",
) -> Optional[str]:
    return env(env_name)


def keycloak_settings(
    *,
    url_env: str = "KEYCLOAK_URL",
    realm_env: str = "KEYCLOAK_REALM",
    client_id_env: str = "KEYCLOAK_CLIENT_ID",
    client_secret_env: str = "KEYCLOAK_CLIENT_SECRET",
    require_secret: bool = False,
) -> KeycloakSettings:
    """Load Keycloak OIDC password-grant settings from env (consumer fills .env)."""
    secret = keycloak_client_secret(client_secret_env)
    if require_secret and not secret:
        require_env(client_secret_env)
    return KeycloakSettings(
        url=keycloak_url(url_env),
        realm=keycloak_realm(realm_env),
        client_id=keycloak_client_id(client_id_env),
        client_secret=secret,
    )


def frontend_url(env_name: str = "FRONTEND_URL", default: str = "http://127.0.0.1:3000") -> str:
    return (env(env_name) or default).rstrip("/")


def base_url_optional(env_name: str = "BASE_URL", default: str = "http://127.0.0.1:8080") -> str:
    return (env(env_name) or default).rstrip("/")
