"""JWT payload helpers for tests (no signature verification)."""

from __future__ import annotations

import base64
import json
from typing import Any, Optional


def decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload section without verifying the signature."""
    if not token or token.count(".") < 2:
        raise ValueError("Not a JWT-like token")
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64.encode("ascii")))


def jwt_claim(token: str, claim: str, default: Any = None) -> Any:
    """Return a single claim from JWT payload, or default."""
    try:
        payload = decode_jwt_payload(token)
    except Exception:
        return default
    return payload.get(claim, default)
