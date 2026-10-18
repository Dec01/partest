"""API call tracking decorator for OpenAPI coverage."""

from __future__ import annotations

import re
import threading
from functools import wraps
from time import perf_counter
from typing import Any, Callable, List, Optional
from uuid import UUID

from partest.call_storage import (
    call_count,
    call_type,
    endpoint_subtype,
    record_call,
    update_last_meta,
)
from partest.methodology.api.classifier import classify_endpoint
from partest.methodology.api.inference import infer_test_type
from partest.path_match import build_concrete_url, resolve_endpoint_template
from partest.test_types import canonicalize_type

# The project's OpenAPI specification, loaded by :func:`_ensure_spec` on the first tracked
# call or report — never on import, so importing the package reads no project file and does
# no network I/O.
#
# ``SWAGGER_AVAILABLE`` is ``None`` until then: not decided. ``True`` — operations are loaded
# and calls are counted; ``False`` — nothing to count. Code that sets these names itself (a
# test, a consumer fixture) is left alone: ``SWAGGER_AVAILABLE = False`` switches counting
# off, and a non-empty ``paths_info`` or a ``swagger_files`` set by hand are used as given.
# ``SWAGGER_AVAILABLE = True`` alone is not taken as "set by hand" — with nothing to count
# against it would only switch counting off. ``paths_info`` is filled in place, so a name
# imported from here sees the operations.
swagger_files = None
SWAGGER_AVAILABLE: Optional[bool] = None
paths_info: List[Any] = []

# True once _ensure_spec decided the three names above for this session.
_spec_loaded = False
_spec_error: Optional[BaseException] = None
# Why there is nothing to count, once decided.
_spec_note = ""
# Held while the specification is fetched, so two threads making the first tracked call do
# not fetch it twice. Separate from ``partest.conf._lock``: reading a switch never waits for
# a slow fetch.
_spec_lock = threading.RLock()

_LOCAL_KINDS = {"local", "file", "path"}


def _set_by_hand() -> bool:
    return not _spec_loaded and (
        SWAGGER_AVAILABLE is False or bool(paths_info) or swagger_files is not None
    )


def _decide(available: bool, note: str = "") -> None:
    global SWAGGER_AVAILABLE, _spec_loaded, _spec_note
    SWAGGER_AVAILABLE = available
    _spec_loaded = True
    _spec_note = note


def _ensure_spec() -> None:
    """Decide what coverage counts against, once per session.

    * a ``confpartest`` that fails to import, or a spec named in a ``confpartest`` found on
      ``sys.path`` that fails to load — :class:`~partest.conf.ConfpartestError`, raised again
      on every later call: loud, because the run would otherwise end green with an empty
      report;
    * the same spec failure when ``confpartest`` was found only in the pytest root
      (:func:`partest.conf._load_from_project_root`) — nothing counted and a line in the
      terminal summary: that file was found by a guess about the layout, and a guess must
      not fail a run;
    * no ``confpartest`` while the pytest root is not reported yet (a conftest's
      ``pytest_configure`` runs before the plugin's) — nothing decided, asked again next
      time.
    """
    global _spec_error
    if _spec_loaded:
        if _spec_error is not None:
            raise _spec_error.with_traceback(None) from None
        return
    if _set_by_hand():
        return
    from partest import conf as _conf

    with _spec_lock:
        if _spec_loaded or _set_by_hand():
            return _ensure_spec()
        try:
            module = _conf._find_confpartest()
        except _conf.ConfpartestError as exc:
            _decide(False, str(exc))
            _spec_error = exc
            raise
        if module is None:
            if _conf._project_roots:
                _decide(False, _conf._absence_reason())
            return
        # The raw sources stay inside _load_operations: its frame has returned before
        # anything is raised, so `pytest -l` (locals in tracebacks) cannot show them.
        failure = _load_operations(module)
        if failure is None:
            return
        _decide(False, failure)
        if _conf._loaded_by_location(module) is not None:
            _conf._note(_conf.NOTES_COVERAGE, failure)
            return
        _spec_error = _conf.ConfpartestError(failure)
        raise _spec_error from None


def _load_operations(module: Any) -> Optional[str]:
    """Load every spec in ``module.swagger_files``; the failure as sanitised text, or ``None``.

    Never raises: the caller raises, from a frame that holds no URL.
    """
    global swagger_files
    from partest import conf as _conf

    files = getattr(module, "swagger_files", None)
    if not files:
        _decide(False, "confpartest.swagger_files is empty")
        return None
    from partest.parparser import SwaggerSettings

    loaded: List[Any] = []
    for key, entry in dict(files).items():
        location = entry[1] if isinstance(entry, (list, tuple)) and len(entry) > 1 else None
        try:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                # The kinds `validate_confpartest` accepts, in any case; the parser
                # itself knows only "local" and "url".
                kind = str(entry[0]).strip().lower()
                if kind in _LOCAL_KINDS:
                    entry = ["local", _conf._resolve_relative(entry[1], module), *entry[2:]]
                elif kind == "url":
                    entry = ["url", *entry[1:]]
            loaded.extend(SwaggerSettings({key: entry}).collect_paths_info())
        except Exception as exc:
            # Text only: the original exception is not chained, or a traceback would print
            # its message — credentials and query strings included.
            return (
                f"could not load the OpenAPI specification swagger_files[{key!r}]: "
                f"{_conf._failure_text(exc, secrets_of=location)}"
            )
    swagger_files = files
    paths_info[:] = loaded
    _decide(True, "" if loaded else "the specification in confpartest.swagger_files has no operations")
    return None


def _reset_session_state() -> None:
    """Forget what :func:`_ensure_spec` decided; names set by hand are left as they are.

    Called by the pytest plugin when a session ends, so a second session in the same process
    (``pytest.main`` twice, an in-process ``pytester``) decides for its own project.
    """
    global swagger_files, SWAGGER_AVAILABLE, _spec_loaded, _spec_error, _spec_note
    if not _spec_loaded:
        return
    swagger_files = None
    SWAGGER_AVAILABLE = None
    paths_info[:] = []
    _spec_loaded = False
    _spec_error = None
    _spec_note = ""


def _snapshot() -> tuple:
    """Everything :func:`_ensure_spec` decides, for the plugin to put back after a session."""
    return (swagger_files, SWAGGER_AVAILABLE, list(paths_info), _spec_loaded, _spec_error, _spec_note)


def _restore(snapshot: tuple) -> None:
    global swagger_files, SWAGGER_AVAILABLE, _spec_loaded, _spec_error, _spec_note
    swagger_files, SWAGGER_AVAILABLE, saved, _spec_loaded, _spec_error, _spec_note = snapshot
    paths_info[:] = saved


def _coverage_unavailable_reason() -> str:
    """Why coverage has nothing to count, or ``""``. Loads the spec if not loaded yet."""
    try:
        _ensure_spec()
    except Exception as exc:
        return str(exc)
    if SWAGGER_AVAILABLE is False and not _spec_loaded:
        return "counting is switched off (partest.coverage.SWAGGER_AVAILABLE = False)"
    if paths_info:
        return ""
    if _spec_loaded:
        return _spec_note or "no OpenAPI operations are loaded"
    from partest import conf as _conf

    return _conf._absence_reason()


def _ensure_unmatched_keys() -> None:
    for path in paths_info:
        key = (path.method, path.path, path.description)
        if key not in call_count:
            call_count[key] = 0
            call_type[key] = []
        sk = (path.method, path.path)
        if sk not in endpoint_subtype:
            try:
                subtype = classify_endpoint(
                    path.method,
                    path.path,
                    path.description or "",
                    has_body=getattr(path, "request_body", None) is not None,
                )
                endpoint_subtype[sk] = subtype.value
            except Exception:
                endpoint_subtype[sk] = "unknown"


def _resolve_endpoint(endpoint: str, kwargs: dict, method: Optional[str] = None) -> str:
    """Coverage key for a call: OpenAPI template if one matches, else legacy guess."""
    defining_url = kwargs.get("defining_url", None)
    if defining_url:
        return defining_url

    # Preferred: rebuild the URL the client sent and match it against the templates
    # of this method. Handles nested paths that the legacy heuristic below cannot.
    if method and paths_info:
        concrete = build_concrete_url(
            endpoint or "",
            [kwargs.get(f"add_url{i}") for i in range(1, 6)],
            kwargs.get("after_url", "") or "",
        )
        template = resolve_endpoint_template(str(method), concrete, paths_info)
        if template:
            return template

    # Legacy fallback: append path-parameter names guessed from the whole spec.
    # Kept so suites that relied on it before 1.6 do not lose their coverage keys.
    path_params = {}
    for path in paths_info:
        for param in path.parameters or []:
            if param is None:
                continue
            if param.type == "path":
                if param.name not in path_params:
                    if param.schema is not None and "enum" in param.schema:
                        path_params[param.name] = param.schema["enum"]
                    else:
                        path_params[param.name] = []

    for i in range(1, 4):
        add_url = kwargs.get(f"add_url{i}")
        if add_url:
            new_param = re.sub(r"^/", "", add_url)
            matched = False
            for param_name, enum_values in path_params.items():
                if new_param in enum_values:
                    endpoint += "/{" + f"{param_name}" + "}"
                    matched = True
                    break
            if not matched:
                if len(path_params) == 1:
                    for param_name in path_params.keys():
                        endpoint += "/{" + f"{param_name}" + "}"
                else:
                    for param_name in path_params.keys():
                        if param_name not in endpoint:
                            endpoint += "/{" + f"{param_name}" + "}"
                            break
                break

    after_url = kwargs.get("after_url", "") or ""
    if after_url:
        endpoint += after_url
    return endpoint


def track_api_calls(func: Callable) -> Callable:
    """Decorator: match request to OpenAPI path and record TC type."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        _ensure_spec()
        if not SWAGGER_AVAILABLE or not swagger_files:
            return await func(*args, **kwargs)

        method = args[1] if len(args) > 1 else kwargs.get("method")
        endpoint = args[2] if len(args) > 2 else kwargs.get("endpoint", "")

        explicit_type = kwargs.get("type", None)
        inference = infer_test_type(
            method=str(method or ""),
            endpoint=str(endpoint or ""),
            expected_status_code=kwargs.get("expected_status_code"),
            params=kwargs.get("params"),
            json_data=kwargs.get("json_data"),
            data=kwargs.get("data"),
            content=kwargs.get("content"),
            content_type=kwargs.get("content_type"),
            files=kwargs.get("files"),
            headers=kwargs.get("headers"),
            explicit_type=explicit_type,
            graphql_query=kwargs.get("graphql_query"),
        )
        test_type = canonicalize_type(inference.test_type)

        final_endpoint = _resolve_endpoint(endpoint or "", kwargs, method)
        recorded_key = None

        if method is not None and final_endpoint is not None:
            found_match = False
            for path in paths_info:
                if path.method == method and path.path == final_endpoint:
                    key = (method, final_endpoint, path.description)
                    subtype = classify_endpoint(
                        path.method,
                        path.path,
                        path.description or "",
                        has_body=getattr(path, "request_body", None) is not None,
                    )
                    record_call(
                        key,
                        test_type,
                        meta={
                            # The type lives in the meta entry too, so timing can be
                            # grouped by it without relying on two parallel lists
                            # staying index-aligned.
                            "type": test_type,
                            "inferred": inference.inferred,
                            "confidence": inference.confidence,
                            "reason": inference.reason,
                            "explicit": explicit_type is not None,
                            "subtype": subtype.value,
                            "has_validate_model": kwargs.get("validate_model") is not None,
                            "has_status_check": kwargs.get("expected_status_code") is not None,
                        },
                        subtype=subtype.value,
                    )
                    found_match = True
                    recorded_key = key
                    break

            _ensure_unmatched_keys()

            if not found_match:
                # Still ensure zero-call keys exist for report
                pass

        # The call is recorded before it runs, so a failing request still counts as
        # an attempt. Timing can only be known afterwards, so it amends the entry —
        # in the failure path too, where slowness is often the point.
        started = perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            if recorded_key is not None:
                update_last_meta(
                    recorded_key,
                    {"elapsed_ms": round((perf_counter() - started) * 1000.0, 2)},
                )

    return wrapper


def is_valid_uuid(uuid_to_test, version=4):
    """Return True if string is a valid UUID of the given version."""
    try:
        uuid_obj = UUID(uuid_to_test, version=version)
    except ValueError:
        return False
    return str(uuid_obj) == uuid_to_test


def get_paths_info():
    """Expose loaded OpenAPI paths (may be empty if confpartest missing).

    Loads the specification on first call; a spec that cannot be loaded raises.
    """
    _ensure_spec()
    return list(paths_info)
