"""Base request body builder for consumer payload classes."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping


def _resolve_mapping(owner: Any, attr: str = "_json_main") -> Dict[str, Any]:
    """Resolve class-attr dict, ``@property``, or zero-arg callable (LIB-06).

    Trap: defining ``_json_main`` as an instance ``@property`` without this
    helper breaks ``type(self)._json_main`` (returns the property object).
    Prefer a plain class dict of callables; property form is supported for
    migration from older suites.
    """
    cls = owner if isinstance(owner, type) else type(owner)
    # Prefer class dict to detect property descriptor
    raw = cls.__dict__.get(attr, None)
    if raw is None:
        raw = getattr(cls, attr, {})
    if isinstance(raw, property):
        # property on class — bind to instance when available
        inst = owner if not isinstance(owner, type) else None
        if inst is None:
            # class-level access: try fget on a throwaway if needed
            raise TypeError(
                f"{cls.__name__}.{attr} is a property; resolve on an instance "
                f"or use a class-level dict of callables "
                f"(see `python -m partest.docs show howto-migration`)."
            )
        value = raw.fget(inst)
    elif callable(raw) and not isinstance(raw, type):
        value = raw() if isinstance(owner, type) else raw(owner) if _needs_self(raw) else raw()
    else:
        value = raw if raw is not None else {}
        if not isinstance(owner, type) and callable(getattr(owner, attr, None)):
            # instance override method
            cand = getattr(owner, attr)
            if callable(cand) and not isinstance(cand, dict):
                try:
                    value = cand()
                except TypeError:
                    value = getattr(owner, attr)

    if not isinstance(value, Mapping):
        raise TypeError(
            f"{cls.__name__}.{attr} must resolve to a mapping, got {type(value).__name__}"
        )
    return dict(value)


def _needs_self(fn) -> bool:
    try:
        import inspect

        sig = inspect.signature(fn)
        params = [
            p
            for p in sig.parameters.values()
            if p.kind
            in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        return bool(params)
    except Exception:
        return False


def _materialize(main: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value() if callable(value) else value for key, value in main.items()}


class BaseRequestBody:
    """Payload base: subclasses define ``_json_main`` and ``_required``.

    Preferred form (class attributes — callables evaluated per instance)::

        class RequestBody(BaseRequestBody):
            _required = ["name"]
            _json_main = {
                "name": lambda: marked_name("Item"),
                "code": "X",
            }

    Property form (supported)::

        class RequestBody(BaseRequestBody):
            _required = ["name"]

            @property
            def _json_main(self):
                return {"name": marked_name("Item")}
    """

    _json_main: Dict[str, Any] = {}
    _required: List[str] = []
    # Extra fields to include in ``get_json_required_marked``. Name the text fields
    # that carry the test-data marker, so a required-only create can still be found
    # by a delete-by-marker cleanup. The cleanup SQL itself stays in the project.
    _cleanup_fields: List[str] = []

    def __init__(self):
        main = _resolve_mapping(self, "_json_main")
        self._json_main_instance = _materialize(main)
        self._json_serialized = json.dumps(self._json_main_instance, ensure_ascii=False)

    @property
    def json(self) -> Dict[str, Any]:
        """Dict body for ``ApiClient.make_request(json_data=...)``."""
        return self._json_main_instance

    @property
    def json_serialized(self) -> str:
        return self._json_serialized

    def set_payload_field(self, key: str, value: Any) -> None:
        self._json_main_instance[key] = value
        self._json_serialized = json.dumps(self._json_main_instance, ensure_ascii=False)

    @classmethod
    def get_json_required(cls) -> Dict[str, Any]:
        # class-level: only plain dict or zero-arg callable works without instance
        raw = cls.__dict__.get("_json_main", getattr(cls, "_json_main", {}))
        if isinstance(raw, property):
            # instantiate lightweight for property resolve
            inst = object.__new__(cls)
            main = _resolve_mapping(inst, "_json_main")
        elif callable(raw) and not isinstance(raw, type):
            main = dict(raw())
        else:
            main = dict(raw or {})
        required = list(getattr(cls, "_required", []) or [])
        return {
            key: value() if callable(value) else value
            for key, value in main.items()
            if key in required
        }

    @classmethod
    def get_json_required_marked(cls) -> Dict[str, Any]:
        """Required fields plus ``_cleanup_fields``, so the row carries the marker.

        ``get_json_required`` sends the minimum the API accepts. If none of those
        fields holds ``TEST_MARKER``, the created row is invisible to a cleanup that
        deletes by marker, and it stays on the stand forever. Opt-in: declare which
        fields to add.

            class RequestBody(BaseRequestBody):
                _required = ["buyUnit"]
                _cleanup_fields = ["name"]      # name comes from marked_name(...)
        """
        raw = cls.__dict__.get("_json_main", getattr(cls, "_json_main", {}))
        if isinstance(raw, property):
            inst = object.__new__(cls)
            main = _resolve_mapping(inst, "_json_main")
        elif callable(raw) and not isinstance(raw, type):
            main = dict(raw())
        else:
            main = dict(raw or {})

        keep = list(getattr(cls, "_required", []) or []) + list(
            getattr(cls, "_cleanup_fields", []) or []
        )
        return {
            key: value() if callable(value) else value
            for key, value in main.items()
            if key in keep
        }

    @classmethod
    def get_cleanup_fields(cls) -> List[str]:
        return list(getattr(cls, "_cleanup_fields", []) or [])

    @classmethod
    def get_json_miss_required(cls, req: str) -> Dict[str, Any]:
        json_data = cls.get_json_required()
        json_data.pop(req, None)
        return json_data

    @classmethod
    def get_required_fields(cls) -> List[str]:
        return list(cls._required)

    def __str__(self) -> str:
        return self._json_serialized
