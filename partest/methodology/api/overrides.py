"""Explicit subtype overrides for endpoints the classifier gets wrong.

The classifier is a heuristic over method and path shape, and a heuristic is never
right for every API. When it guesses wrong the test does not fail — the endpoint
simply gets the required test-case set of the wrong subtype, and the coverage number
is confidently incorrect. An override is the escape hatch.

Applied **inside** ``classify_endpoint`` rather than by rebinding it. ``coverage.py``
does ``from partest.methodology.api.classifier import classify_endpoint`` at import time,
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

from partest.methodology.api.subtypes import MethodSubtype

Key = Tuple[str, str]

_overrides: Dict[Key, MethodSubtype] = {}
# ``confpartest.subtype_overrides`` is read on the first lookup, not on import. Once read —
# or once ``set_``/``clear_subtype_overrides`` was called, which is the last word — it is not
# read again in the session.
_conf_consulted = False
# Where the active overrides came from: an explicit call, or confpartest. Only the latter is
# dropped when a pytest session ends (:func:`_reset_session_state`).
_explicit = False
_from_conf = False


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
    global _conf_consulted, _explicit, _from_conf
    parsed: Dict[Key, MethodSubtype] = {}
    for raw_key, raw_value in (mapping or {}).items():
        parsed[_parse_key(raw_key)] = _parse_subtype(raw_value)
    _overrides.clear()
    _overrides.update(parsed)
    _conf_consulted, _explicit, _from_conf = True, True, False
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


def _apply_from_conf(module: Any, source: Any) -> Dict[Key, MethodSubtype]:
    global _explicit, _from_conf
    from partest.conf import _resolve_relative

    result = load_subtype_overrides(_resolve_relative(source, module))
    _explicit, _from_conf = False, True
    return result


def load_from_confpartest() -> Dict[Key, MethodSubtype]:
    """Read ``subtype_overrides`` from the project's confpartest, if present.

    Found the same way as everywhere else (:func:`partest.conf._find_confpartest`); a
    ``confpartest`` that fails to import raises ``ConfpartestError``.
    """
    from partest.conf import _find_confpartest

    module = _find_confpartest(reading="subtype_overrides")
    if module is None:
        return {}
    return _apply_from_conf(module, getattr(module, "subtype_overrides", None))


def _consult_confpartest() -> None:
    """Apply ``confpartest.subtype_overrides`` once, on first use.

    A bad entry raises — here and on every later lookup until it is fixed — rather than
    being ignored: an override that silently does nothing looks exactly like the
    misclassification it was written to fix. A project without the setting keeps whatever
    is active; it is not cleared. No ``confpartest`` while the pytest root is not reported
    yet decides nothing: the next lookup asks again.
    """
    global _conf_consulted
    if _conf_consulted:
        return
    from partest import conf as _conf

    with _conf._lock:
        if _conf_consulted:
            return
        module = _conf._find_confpartest(reading="subtype_overrides")
        if module is None:
            if _conf._project_roots:
                _conf_consulted = True
            return
        source = getattr(module, "subtype_overrides", None)
        if source is not None:
            _apply_from_conf(module, source)
        _conf_consulted = True


def _reset_session_state() -> None:
    """Called by the pytest plugin when a session ends: confpartest is read again next time.

    Overrides set by an explicit call stay; overrides taken from confpartest are dropped
    with the session that read them.
    """
    global _conf_consulted, _from_conf
    if _explicit:
        return
    if _from_conf:
        _overrides.clear()
        _from_conf = False
    _conf_consulted = False


def _snapshot() -> tuple:
    """The registry and where it came from, for the plugin to put back after a session."""
    return (dict(_overrides), _conf_consulted, _explicit, _from_conf)


def _restore(snapshot: tuple) -> None:
    global _conf_consulted, _explicit, _from_conf
    saved, _conf_consulted, _explicit, _from_conf = snapshot
    _overrides.clear()
    _overrides.update(saved)


def lookup(method: str, path: str) -> Optional[MethodSubtype]:
    _consult_confpartest()
    if not _overrides:
        return None
    return _overrides.get(((method or "").upper(), _normalize_path(path)))


def active_overrides() -> Dict[str, str]:
    """Current overrides, for reporting and debugging."""
    _consult_confpartest()
    return {f"{m} {p}": s.value for (m, p), s in sorted(_overrides.items())}


def clear_subtype_overrides() -> None:
    global _conf_consulted, _explicit, _from_conf
    _overrides.clear()
    _conf_consulted, _explicit, _from_conf = True, True, False
