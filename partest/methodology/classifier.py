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
# Self-scope, upload and action detection work on **path segments and identifier
# tokens**, not on a substring of the whole text. Substring matching used to make
# "/media-types" and "/departments" look like GET BY SELF (both contain "me"), which
# silently changed the required P1 set for those endpoints.
_SELF_SEGMENTS = frozenset(
    {
        "me",
        "self",
        "my",
        "mine",
        "current",
        "profile",
        "currentuser",
        "current-user",
        "my-profile",
        "myprofile",
    }
)
_SELF_DESCRIPTION = re.compile(
    r"\b(current user|currently authenticated|authenticated user|"
    r"own profile|my profile)\b",
    re.I,
)

_UPLOAD_SEGMENTS = frozenset(
    {"upload", "uploads", "file", "files", "multipart", "attachment", "attachments", "media"}
)
_UPLOAD_DESCRIPTION = re.compile(r"\b(upload|multipart|attachment)\b", re.I)

_ACTION_WORDS = frozenset(
    {
        "approve",
        "reject",
        "calculate",
        "publish",
        "unpublish",
        "activate",
        "deactivate",
        "cancel",
        "restore",
        "clone",
        "copy",
        "execute",
        "run",
        "trigger",
        "invite",
        "confirm",
    }
)
_ACTION_HINTS = re.compile("(" + "|".join(sorted(_ACTION_WORDS)) + ")", re.I)
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


def _path_segments(path: str) -> List[str]:
    return [s for s in (path or "").split("/") if s]


def _literal_segments(path: str) -> List[str]:
    """Path segments that are not ``{placeholders}``, lower-cased."""
    return [
        s.lower()
        for s in _path_segments(path)
        if not (s.startswith("{") and s.endswith("}"))
    ]


def _identifier_tokens(text: str) -> List[str]:
    """Split ``getCurrentUser`` / ``get_current_user`` into lower-case tokens."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text or "")
    return [t.lower() for t in re.findall(r"[A-Za-z0-9]+", spaced)]


def _is_self_scope(path: str, description: str = "", operation_id: str = "") -> bool:
    """True when the operation addresses the caller's own object ("me" / "self")."""
    segments = _literal_segments(path)
    if any(s in _SELF_SEGMENTS for s in segments):
        return True
    # historical rule: a path ending in "/user" with no path parameter
    if segments and segments[-1] == "user" and "{" not in (path or ""):
        return True

    tokens = _identifier_tokens(operation_id)
    if {"me", "self", "mine", "my"} & set(tokens):
        return True
    for first, second in zip(tokens, tokens[1:]):
        if first == "current" and second in {"user", "profile", "account"}:
            return True

    return bool(_SELF_DESCRIPTION.search(description or ""))


def _is_upload_scope(path: str, description: str = "", operation_id: str = "") -> bool:
    """True when the operation uploads a file.

    Segment-exact on the path so that ``/media-types`` is not mistaken for ``/media``.
    """
    if any(s in _UPLOAD_SEGMENTS for s in _literal_segments(path)):
        return True
    if set(_identifier_tokens(operation_id)) & {
        "upload",
        "attachment",
        "attachments",
        "multipart",
    }:
        return True
    return bool(_UPLOAD_DESCRIPTION.search(description or ""))


def _is_action_call(path: str, operation_id: str = "") -> bool:
    """True when the last path segment (or operationId) is an action verb.

    Structural signal: ``POST /items/{id}/publish`` is an ACTION, not a create under
    a parent. Checked before POST CREATE OBJECT TO OBJECT so that the required P1 set
    does not gain RequestNewObject for an operation that creates nothing.
    """
    segments = _literal_segments(path)
    if segments and segments[-1] in _ACTION_WORDS:
        return True
    tokens = _identifier_tokens(operation_id)
    return bool(tokens) and tokens[-1] in _ACTION_WORDS


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
        if _is_self_scope(p, description, operation_id):
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
        if is_multipart or _is_upload_scope(p, description, operation_id):
            return MethodSubtype.POST_UPLOAD
        create_like = re.search(r"\b(create|add|new|register|insert)\b", text, re.I)
        # A verb as the last segment wins over "child under parent": /items/{id}/publish
        # creates nothing, so RequestNewObject must not enter its P1 set.
        if _is_action_call(p, operation_id):
            return MethodSubtype.ACTION
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
        if _is_action_call(p, operation_id):
            return MethodSubtype.ACTION
        if _ACTION_HINTS.search(text) and not ends_with_param:
            return MethodSubtype.ACTION
        return MethodSubtype.PUT_OBJECT

    if m == "PATCH":
        if _is_action_call(p, operation_id):
            return MethodSubtype.ACTION
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
    operation_id = (
        getattr(path_obj, "operation_id", "") or getattr(path_obj, "operationId", "") or ""
    )
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
        operation_id=str(operation_id),
    )


def classify_all(paths: Sequence[Any]) -> List[tuple]:
    """Return list of (path_obj, MethodSubtype)."""
    return [(p, classify_path_object(p)) for p in paths]
