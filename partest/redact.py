"""Redact secrets from logs and Allure attaches (LIB-16)."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, Mapping, MutableMapping, Optional, Set

DEFAULT_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "api-key",
    }
)

DEFAULT_SENSITIVE_BODY_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "authorization",
        "api_key",
        "apikey",
        "private_key",
    }
)

_BEARER_RE = re.compile(r"(?i)^(bearer\s+)(.+)$")


def mask_secret(value: Any, *, keep_prefix: int = 8) -> str:
    """Mask a secret string; keep short prefix for debugging."""
    if value is None:
        return ""
    s = str(value)
    if not s:
        return ""
    m = _BEARER_RE.match(s)
    if m:
        prefix, token = m.group(1), m.group(2)
        if len(token) <= keep_prefix:
            return f"{prefix}***"
        return f"{prefix}{token[:keep_prefix]}…[masked]"
    if len(s) <= keep_prefix:
        return "***"
    return f"{s[:keep_prefix]}…[masked]"


def redact_headers(
    headers: Optional[Mapping[str, Any]],
    *,
    extra_keys: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Return a copy of headers with sensitive values masked."""
    if not headers:
        return {}
    sensitive = {k.lower() for k in DEFAULT_SENSITIVE_HEADERS}
    if extra_keys:
        sensitive |= {k.lower() for k in extra_keys}
    out: Dict[str, Any] = {}
    for k, v in headers.items():
        if str(k).lower() in sensitive and v is not None and str(v):
            out[k] = mask_secret(v)
        else:
            out[k] = v
    return out


def redact_mapping(
    data: Any,
    *,
    sensitive_keys: Optional[Set[str]] = None,
    depth: int = 6,
) -> Any:
    """Deep-copy mapping/list masking values under sensitive keys."""
    keys = {k.lower() for k in (sensitive_keys or DEFAULT_SENSITIVE_BODY_KEYS)}
    return _redact(data, keys, depth)


def _redact(data: Any, keys: Set[str], depth: int) -> Any:
    if depth < 0:
        return data
    if isinstance(data, Mapping):
        out = {}
        for k, v in data.items():
            if str(k).lower() in keys and v is not None and str(v) != "":
                out[k] = mask_secret(v)
            else:
                out[k] = _redact(v, keys, depth - 1)
        return out
    if isinstance(data, list):
        return [_redact(x, keys, depth - 1) for x in data]
    if isinstance(data, tuple):
        return tuple(_redact(x, keys, depth - 1) for x in data)
    return data
