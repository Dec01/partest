"""Explicit subtype overrides for endpoints the classifier gets wrong.

The classifier is a heuristic over method and path shape, and a heuristic is never
right for every API. When it guesses wrong the test does not fail — the endpoint
simply gets the required test-case set of the wrong subtype, and the coverage number
is confidently incorrect. An override is the escape hatch.

Applied **inside** ``classify_endpoint`` rather than by rebinding it. ``coverage.py``
does ``from partest.methodology.classifier import classify_endpoint`` at import time,
before a project's configuration is read, so patching the module attribute afterwards
would never reach the decorator that actually records calls. Consulting a registry from
within the function sidesteps that entirely.

Configure in ``confpartest.py``::

    subtype_overrides = {
        "GET /media-types": "get_static_object",
        "POST /orders/{id}/recalculate": "action",
    }

or point at a YAML file::

    subtype_overrides = "src/api/resources/coverage/subtypes.yaml"
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from partest.methodology.subtypes import MethodSubtype

Key = Tuple[str, str]

_overrides: Dict[Key, MethodSubtype] = {}


def _normalize_path(path: str) -> str:
    """Compare templates by shape: ``/a/{id}`` and ``/a/{userId}`` are the same route."""
    text = (path or "").split("?", 1)[0].rstrip("/") or "/"
    if not text.startswith("/"):
        text = "/" + text
    return re.sub(r"\{[^}]*\}", "{}", text)


def _parse_key(raw: str) -> Key:
    parts = str(raw).split(None, 1)
    if len(parts) != 2:
        raise ValueError(
            f"subtype override key {raw!r} must look like 'GET /items/{{id}}'"
        )
    return parts[0].upper(), _normalize_path(parts[1])


def _parse_subtype(raw: Any) -> MethodSubtype:
    if isinstance(raw, MethodSubtype):
        return raw
    text = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return MethodSubtype(text)
    except ValueError:
        known = ", ".join(sorted(s.value for s in MethodSubtype))
        raise ValueError(f"unknown subtype {raw!r}; expected one of: {known}") from None


def set_subtype_overrides(mapping: Optional[Mapping[str, Any]]) -> Dict[Key, MethodSubtype]:
    """Replace the active overrides. Invalid entries raise rather than being ignored.

    A silently dropped override would leave the wrong subtype in place and look like
    the override never worked — the failure mode this feature exists to end.
    """
    parsed: Dict[Key, MethodSubtype] = {}
    for raw_key, raw_value in (mapping or {}).items():
        parsed[_parse_key(raw_key)] = _parse_subtype(raw_value)
    _overrides.clear()
    _overrides.update(parsed)
    return dict(_overrides)


def load_subtype_overrides(source: Union[str, Path, Mapping[str, Any], None]) -> Dict[Key, MethodSubtype]:
    """Load overrides from a mapping or a YAML/JSON file path."""
    if source is None:
        return set_subtype_overrides(None)
    if isinstance(source, Mapping):
        return set_subtype_overrides(source)

    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"subtype overrides file not found: {path}")
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, Mapping):
        raise ValueError(f"{path} must contain a mapping of 'METHOD /path' to subtype")
    return set_subtype_overrides(data)


def load_from_confpartest() -> Dict[Key, MethodSubtype]:
    """Read ``subtype_overrides`` from the project's confpartest, if present."""
    try:
        import confpartest  # type: ignore
    except ImportError:
        return {}
    return load_subtype_overrides(getattr(confpartest, "subtype_overrides", None))


def lookup(method: str, path: str) -> Optional[MethodSubtype]:
    if not _overrides:
        return None
    return _overrides.get(((method or "").upper(), _normalize_path(path)))


def active_overrides() -> Dict[str, str]:
    """Current overrides, for reporting and debugging."""
    return {f"{m} {p}": s.value for (m, p), s in sorted(_overrides.items())}


def clear_subtype_overrides() -> None:
    _overrides.clear()
