"""Crafted / tampered JWT fixtures for security tests (no real signing keys)."""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, Optional, Union


def b64url_encode(data: Union[dict, str, bytes, bytearray]) -> str:
    if isinstance(data, dict):
        raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    elif isinstance(data, str):
        raw = data.encode("utf-8")
    else:
        raw = bytes(data)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def decode_payload(token: str) -> Dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("not a JWT")
    return json.loads(b64url_decode(parts[1]))


def build_alg_none_token(
    payload: Optional[Dict[str, Any]] = None,
    *,
    sub: str = "attacker",
    roles: Optional[list] = None,
    exp: int = 9999999999,
) -> str:
    """JWT with alg=none (unsigned) — must be rejected by the server."""
    header = {"alg": "none", "typ": "JWT"}
    body = dict(payload or {})
    body.setdefault("sub", sub)
    body.setdefault("exp", exp)
    if roles is not None:
        body.setdefault("realm_access", {"roles": list(roles)})
    return f"{b64url_encode(header)}.{b64url_encode(body)}."


def build_tampered_payload_token(
    valid_token: str,
    *,
    patch: Optional[Dict[str, Any]] = None,
) -> str:
    """Keep header+signature of a valid token, alter payload (classic tamper)."""
    parts = valid_token.split(".")
    if len(parts) != 3:
        raise ValueError("valid_token must be a 3-part JWT")
    header_b64, payload_b64, signature = parts
    payload = json.loads(b64url_decode(payload_b64))
    payload.update(patch or {"preferred_username": "hacker"})
    return f"{header_b64}.{b64url_encode(payload)}.{signature}"


def build_tampered_set(
    valid_token: str,
    *,
    forged_sub: str = "attacker",
    forged_roles: Optional[list] = None,
    payload_patch: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Named set of invalid tokens for parametrized security tests.

    Keys: ``alg_none``, ``tampered_payload``, ``garbage``, ``not_a_jwt``.
    """
    roles = forged_roles if forged_roles is not None else ["ADMIN"]
    patch = dict(payload_patch or {})
    patch.setdefault("preferred_username", "hacker")
    if "realm_access" not in patch:
        patch["realm_access"] = {"roles": list(roles)}

    return {
        "alg_none": build_alg_none_token(sub=forged_sub, roles=roles),
        "tampered_payload": build_tampered_payload_token(valid_token, patch=patch),
        "garbage": "xxx.yyy.zzz",
        "not_a_jwt": "definitely-not-a-token",
    }
