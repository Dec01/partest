"""API call tracking decorator for OpenAPI coverage."""

from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable, Optional
from uuid import UUID

from partest.call_storage import call_count, call_type, endpoint_subtype, record_call
from partest.methodology.classifier import classify_endpoint
from partest.methodology.inference import infer_test_type
from partest.test_types import canonicalize_type

try:
    from confpartest import swagger_files
    from partest.parparser import SwaggerSettings

    SWAGGER_AVAILABLE = True
except ImportError:
    swagger_files = None
    SWAGGER_AVAILABLE = False

paths_info = []
if SWAGGER_AVAILABLE and swagger_files:
    swagger_settings = SwaggerSettings(swagger_files)
    paths_info = swagger_settings.collect_paths_info()


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


def _resolve_endpoint(endpoint: str, kwargs: dict) -> str:
    defining_url = kwargs.get("defining_url", None)
    if defining_url:
        return defining_url

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

        final_endpoint = _resolve_endpoint(endpoint or "", kwargs)

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
                    break

            _ensure_unmatched_keys()

            if not found_match:
                # Still ensure zero-call keys exist for report
                pass

        return await func(*args, **kwargs)

    return wrapper


def is_valid_uuid(uuid_to_test, version=4):
    """Return True if string is a valid UUID of the given version."""
    try:
        uuid_obj = UUID(uuid_to_test, version=version)
    except ValueError:
        return False
    return str(uuid_obj) == uuid_to_test


def get_paths_info():
    """Expose loaded OpenAPI paths (may be empty if confpartest missing)."""
    return list(paths_info)
