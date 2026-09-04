"""Classify OpenAPI operations into method subtypes (axis A)."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Sequence

from partest.methodology.subtypes import MethodSubtype

# Description/operationId tokens that usually mean "collection list / search"
# Do NOT match generic resource names like "items" in the path alone.
_LIST_HINTS = re.compile(
    r"\b(list|search|find|query|filter|filters|sort|pageable|pagination)\b",
    re.I,
)
_FILTER_BODY_HINTS = re.compile(
    r"\b(filter|filters|sort|search|query|pageable|pagination)\b",
    re.I,
)
_SELF_HINTS = re.compile(
    r"(me|self|current|my|mine|/user$|/users/me|/profile)",
    re.I,
)
_UPLOAD_HINTS = re.compile(r"(upload|file|files|multipart|attachment|media)", re.I)
_ACTION_HINTS = re.compile(
    r"(approve|reject|calculate|publish|unpublish|activate|deactivate|"
    r"cancel|restore|clone|copy|execute|run|trigger|invite|confirm)",
    re.I,
)
_PARENT_PATH = re.compile(
    r"/\{[^}/]+\}/\{[^}/]+\}|"  # two path params in a row (rare)
    r"/\{[^}/]+\}/[^/{]+|"  # /{parentId}/children
    r"/[^/{]+/\{[^}/]+\}/[^/{]+",  # /resource/{id}/nested
    re.I,
)
_EXTERNAL_ID = re.compile(
    r"(keycloak|external|uuid|guid|slug|code|login|username)",
    re.I,
)
_STATIC_HINTS = re.compile(
    r"(enum|enums|dict|dictionary|static|config|configs|reference|"
    r"catalog|metadata|version|health|ping|status|constants)",
    re.I,
)


def _path_param_names(path: str) -> List[str]:
    return re.findall(r"\{([^}]+)\}", path or "")


def _has_request_body(path_obj: Any) -> bool:
    return getattr(path_obj, "request_body", None) is not None


def _content_types(path_obj: Any) -> List[str]:
    body = getattr(path_obj, "request_body", None)
    if body is None:
        return []
    content = getattr(body, "content", None)
    if isinstance(content, dict):
        return list(content.keys())
    # RequestBody may wrap application/json only
    return ["application/json"] if content else []


def _is_multipart(path_obj: Any) -> bool:
    for ct in _content_types(path_obj):
        if "multipart" in ct.lower() or "form-data" in ct.lower():
            return True
    return False


def _param_names(path_obj: Any) -> List[str]:
    params = getattr(path_obj, "parameters", None) or []
    names = []
    for p in params:
        if p is None:
            continue
        name = getattr(p, "name", None)
        if name:
            names.append(str(name))
    return names


def _query_suggests_list(path_obj: Any) -> bool:
    names = {n.lower() for n in _param_names(path_obj)}
    list_keys = {
        "page",
        "size",
        "limit",
        "offset",
        "sort",
        "order",
        "filter",
        "q",
        "query",
        "search",
    }
    return bool(names & list_keys)


def classify_endpoint(
    method: str,
    path: str,
    description: str = "",
    *,
    has_body: bool = False,
    is_multipart: bool = False,
    query_list_hints: bool = False,
    operation_id: str = "",
) -> MethodSubtype:
    """Heuristic subtype for a single HTTP method + path.

    Pure function — no I/O. Prefer explicit consumer overrides when certainty
    is low (returned UNKNOWN only if method is empty).
    """
    m = (method or "").upper().strip()
    p = path or ""
    text = f"{p} {description or ''} {operation_id or ''}"
    params = _path_param_names(p)
    last_segment = p.rstrip("/").split("/")[-1] if p else ""
    ends_with_param = bool(re.match(r"^\{[^}]+\}$", last_segment))

    if not m:
        return MethodSubtype.UNKNOWN

    if m == "GET":
        if _SELF_HINTS.search(text):
            return MethodSubtype.GET_BY_SELF
        if _EXTERNAL_ID.search(" ".join(params)) or (
            ends_with_param and _EXTERNAL_ID.search(params[-1] if params else "")
        ):
            # only if not a plain numeric id style
            if params and _EXTERNAL_ID.search(params[-1]):
                return MethodSubtype.GET_EXTERNAL_ID
        # /parents/{id}/children pattern
        if len(params) >= 1 and not ends_with_param and "{" in p:
            # e.g. /packages/{taskId}/list or /splits/package/{id}
            if re.search(r"/\{[^}]+\}/[^/{]+$", p) or re.search(
                r"/[^/{]+/\{[^}]+\}$", p
            ):
                # /resource/{id} is dynamic single; /resource/parent/{id} is by-parent
                if re.search(r"/[^/{]+/\{[^}]+\}$", p) and not ends_with_param:
                    pass
                if re.search(r"/[A-Za-z0-9_-]+/\{[^}]+\}/?$", p) is None:
                    pass
            # path like /splits/package/{packageId}
            if re.search(r"/[A-Za-z0-9_-]+/\{[^}]+\}/?$", p) and p.count("/") >= 3:
                segments = [s for s in p.split("/") if s]
                if len(segments) >= 3 and not segments[-2].startswith("{"):
                    return MethodSubtype.GET_BY_PARENT
        if ends_with_param:
            if _STATIC_HINTS.search(text) and not params:
                return MethodSubtype.GET_STATIC
            return MethodSubtype.GET_DYNAMIC
        if query_list_hints or _LIST_HINTS.search(text) or not params:
            if _STATIC_HINTS.search(text) and not query_list_hints:
                return MethodSubtype.GET_STATIC
            if not params:
                # collection without id
                if _STATIC_HINTS.search(text):
                    return MethodSubtype.GET_STATIC
                return MethodSubtype.GET_LIST
        if not params:
            return MethodSubtype.GET_LIST
        return MethodSubtype.GET_DYNAMIC

    if m == "POST":
        if is_multipart or _UPLOAD_HINTS.search(text):
            return MethodSubtype.POST_UPLOAD
        create_like = re.search(r"\b(create|add|new|register|insert)\b", text, re.I)
        # filter/sort body on list — only when wording suggests filter, not create
        if _FILTER_BODY_HINTS.search(text) and not create_like and not ends_with_param:
            return MethodSubtype.POST_FILTER_LIST
        # child under parent: POST /posts/{id}/comments
        if (not ends_with_param) and params:
            if re.search(r"/\{[^}]+\}/[^/{]+/?$", p):
                return MethodSubtype.POST_CREATE_TO_OBJECT
        if _ACTION_HINTS.search(text) and not create_like:
            return MethodSubtype.ACTION
        return MethodSubtype.POST_CREATE

    if m == "PUT":
        if _ACTION_HINTS.search(text) and not ends_with_param:
            return MethodSubtype.ACTION
        return MethodSubtype.PUT_OBJECT

    if m == "PATCH":
        # /resource/{id}/field style → elem
        if re.search(r"/\{[^}]+\}/[A-Za-z0-9_-]+/?$", p):
            return MethodSubtype.PATCH_ELEM
        return MethodSubtype.PATCH_OBJECT

    if m == "DELETE":
        # generic delete; soft/physical/blocked need consumer metadata
        return MethodSubtype.DELETE_OBJECT

    return MethodSubtype.UNKNOWN


def classify_path_object(path_obj: Any) -> MethodSubtype:
    """Classify a ``parparser.Path``-like object."""
    method = getattr(path_obj, "method", "") or ""
    path = getattr(path_obj, "path", "") or ""
    description = getattr(path_obj, "description", "") or ""
    has_body = _has_request_body(path_obj)
    multi = _is_multipart(path_obj)
    qlist = _query_suggests_list(path_obj)
    return classify_endpoint(
        method,
        path,
        description,
        has_body=has_body,
        is_multipart=multi,
        query_list_hints=qlist,
    )


def classify_all(paths: Sequence[Any]) -> List[tuple]:
    """Return list of (path_obj, MethodSubtype)."""
    return [(p, classify_path_object(p)) for p in paths]
