"""Intermediate representation of an OpenAPI suite for project generation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from partest.methodology.classifier import classify_endpoint
from partest.methodology.matrix import p1_test_cases
from partest.methodology.subtypes import MethodSubtype


@dataclass
class ParamIR:
    name: str
    location: str  # path | query | header | cookie
    required: bool = False
    schema: Optional[Dict[str, Any]] = None
    description: str = ""


@dataclass
class OpIR:
    method: str
    path: str
    operation_id: str
    tag: str
    summary: str
    description: str
    subtype: str
    required_p1: List[str]
    path_params: List[ParamIR] = field(default_factory=list)
    query_params: List[ParamIR] = field(default_factory=list)
    header_params: List[ParamIR] = field(default_factory=list)
    has_request_body: bool = False
    request_content_types: List[str] = field(default_factory=list)
    request_schema: Optional[Dict[str, Any]] = None
    success_status: int = 200
    error_statuses: List[int] = field(default_factory=list)
    success_response_schema: Optional[Dict[str, Any]] = None
    deprecated: bool = False
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class SuiteIR:
    """Full suite IR: ops + metadata for generators."""

    title: str
    version: str
    openapi_version: str
    operations: List[OpIR] = field(default_factory=list)
    source: str = ""  # file path or url

    def by_tag(self) -> Dict[str, List[OpIR]]:
        groups: Dict[str, List[OpIR]] = {}
        for op in self.operations:
            groups.setdefault(op.tag, []).append(op)
        return groups

    def tags(self) -> List[str]:
        return sorted(self.by_tag().keys())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "version": self.version,
            "openapi_version": self.openapi_version,
            "source": self.source,
            "operation_count": len(self.operations),
            "tags": self.tags(),
            "operations": [op.to_dict() for op in self.operations],
        }


_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})


def _slug_tag(raw: str) -> str:
    s = (raw or "common").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_") or "common"
    return s


def _path_to_tag_fallback(path: str) -> str:
    parts = [p for p in (path or "").split("/") if p and not p.startswith("{")]
    if not parts:
        return "common"
    # skip common api prefixes
    while parts and parts[0] in {"api", "v1", "v2", "v3"}:
        parts.pop(0)
    return _slug_tag(parts[0] if parts else "common")


def _param_from_dict(p: Dict[str, Any]) -> ParamIR:
    return ParamIR(
        name=str(p.get("name", "")),
        location=str(p.get("in", "query")),
        required=bool(p.get("required", False)),
        schema=p.get("schema") if isinstance(p.get("schema"), dict) else None,
        description=str(p.get("description") or ""),
    )


def _resolve_ref(ref: str, root: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not ref.startswith("#/"):
        return None
    node: Any = root
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node if isinstance(node, dict) else None


def _request_body_info(details: Dict[str, Any], root: Dict[str, Any]) -> tuple:
    rb = details.get("requestBody")
    if not isinstance(rb, dict):
        return False, [], None
    content = rb.get("content") or {}
    if not isinstance(content, dict):
        return True, [], None
    ctypes = list(content.keys())
    schema = None
    for ct in ("application/json", "application/*+json"):
        if ct in content and isinstance(content[ct], dict):
            schema = content[ct].get("schema")
            break
    if schema is None and ctypes:
        first = content.get(ctypes[0])
        if isinstance(first, dict):
            schema = first.get("schema")
    if isinstance(schema, dict):
        schema = _resolve_schema(schema, root)
    return True, ctypes, schema if isinstance(schema, dict) else None


def _resolve_schema(schema: Any, root: Dict[str, Any], depth: int = 0) -> Optional[Dict[str, Any]]:
    if not isinstance(schema, dict) or depth > 8:
        return schema if isinstance(schema, dict) else None
    if "$ref" in schema:
        resolved = _resolve_ref(schema["$ref"], root)
        if resolved is None:
            return schema
        return _resolve_schema(resolved, root, depth + 1)
    # shallow resolve nested property refs
    out = dict(schema)
    props = out.get("properties")
    if isinstance(props, dict):
        new_props = {}
        for k, v in props.items():
            if isinstance(v, dict) and "$ref" in v:
                new_props[k] = _resolve_schema(v, root, depth + 1) or v
            else:
                new_props[k] = v
        out["properties"] = new_props
    items = out.get("items")
    if isinstance(items, dict) and "$ref" in items:
        out["items"] = _resolve_schema(items, root, depth + 1) or items
    return out


def _response_statuses(details: Dict[str, Any]) -> tuple:
    responses = details.get("responses") or {}
    success = 200
    errors: List[int] = []
    for code in responses.keys():
        try:
            c = int(code)
        except (TypeError, ValueError):
            if str(code).lower() == "default":
                continue
            continue
        if 200 <= c < 300:
            # prefer 201 for create if present
            if c == 201 or success == 200:
                success = c
        elif c >= 400:
            errors.append(c)
    return success, sorted(set(errors))


def _success_response_schema(
    details: Dict[str, Any], root: Dict[str, Any], success_status: int
) -> Optional[Dict[str, Any]]:
    responses = details.get("responses") or {}
    # try exact status then any 2xx
    candidates = [str(success_status), "200", "201", "202", "204"]
    for code, resp in responses.items():
        try:
            c = int(code)
        except (TypeError, ValueError):
            continue
        if 200 <= c < 300 and str(c) not in candidates:
            candidates.append(str(c))
    for code in candidates:
        resp = responses.get(code)
        if not isinstance(resp, dict):
            continue
        content = resp.get("content") or {}
        if not isinstance(content, dict):
            continue
        for ct in ("application/json", "application/*+json"):
            if ct in content and isinstance(content[ct], dict):
                schema = content[ct].get("schema")
                if isinstance(schema, dict):
                    return _resolve_schema(schema, root)
        for block in content.values():
            if isinstance(block, dict) and isinstance(block.get("schema"), dict):
                return _resolve_schema(block["schema"], root)
    return None


def _collect_parameters(details: Dict[str, Any], root: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = list(details.get("parameters") or [])
    # path-level params may be merged by caller
    out = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        if "$ref" in p:
            resolved = _resolve_ref(p["$ref"], root)
            if resolved:
                out.append(resolved)
        else:
            out.append(p)
    return out


def build_op_ir(
    method: str,
    path: str,
    details: Dict[str, Any],
    root: Dict[str, Any],
    *,
    path_item_params: Optional[Sequence[Dict[str, Any]]] = None,
) -> Optional[OpIR]:
    if details.get("deprecated"):
        # still include but mark — generator may skip
        pass

    params_raw = list(path_item_params or []) + _collect_parameters(details, root)
    path_params: List[ParamIR] = []
    query_params: List[ParamIR] = []
    header_params: List[ParamIR] = []
    for p in params_raw:
        pir = _param_from_dict(p)
        if not pir.name:
            continue
        if pir.location == "path":
            path_params.append(pir)
        elif pir.location == "query":
            query_params.append(pir)
        elif pir.location == "header":
            header_params.append(pir)

    has_body, ctypes, schema = _request_body_info(details, root)
    success, errors = _response_statuses(details)
    response_schema = _success_response_schema(details, root, success)

    tags = details.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(t) for t in tags]
    tag = _slug_tag(tags[0]) if tags else _path_to_tag_fallback(path)

    summary = str(details.get("summary") or "")
    description = str(details.get("description") or summary)
    op_id = str(details.get("operationId") or f"{method.lower()}_{_slug_tag(path)}")

    is_multipart = any("multipart" in c.lower() or "form-data" in c.lower() for c in ctypes)
    subtype_enum = classify_endpoint(
        method.upper(),
        path,
        description,
        has_body=has_body,
        is_multipart=is_multipart,
        query_list_hints=any(
            q.name.lower() in {"page", "size", "limit", "offset", "sort", "filter", "q"}
            for q in query_params
        ),
        operation_id=op_id,
    )
    if not isinstance(subtype_enum, MethodSubtype):
        subtype_enum = MethodSubtype.UNKNOWN

    p1 = p1_test_cases(subtype_enum)

    return OpIR(
        method=method.upper(),
        path=path,
        operation_id=op_id,
        tag=tag,
        summary=summary,
        description=description,
        subtype=subtype_enum.value,
        required_p1=list(p1),
        path_params=path_params,
        query_params=query_params,
        header_params=header_params,
        has_request_body=has_body,
        request_content_types=ctypes,
        request_schema=schema,
        success_status=success,
        error_statuses=errors,
        success_response_schema=response_schema,
        deprecated=bool(details.get("deprecated", False)),
        tags=tags,
    )


def build_ir_from_openapi_dict(
    swagger: Dict[str, Any],
    *,
    source: str = "",
) -> SuiteIR:
    """Build SuiteIR from a loaded OpenAPI 2/3 dict."""
    info = swagger.get("info") or {}
    title = str(info.get("title") or "API")
    version = str(info.get("version") or "")
    oas = str(swagger.get("openapi") or swagger.get("swagger") or "")

    paths = swagger.get("paths") or {}
    ops: List[OpIR] = []

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_params = path_item.get("parameters") or []
        if not isinstance(path_params, list):
            path_params = []
        # resolve path-level param refs
        resolved_path_params = []
        for p in path_params:
            if isinstance(p, dict) and "$ref" in p:
                r = _resolve_ref(p["$ref"], swagger)
                if r:
                    resolved_path_params.append(r)
            elif isinstance(p, dict):
                resolved_path_params.append(p)

        for method, details in path_item.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            if not isinstance(details, dict):
                continue
            op = build_op_ir(
                method,
                path,
                details,
                swagger,
                path_item_params=resolved_path_params,
            )
            if op is not None:
                ops.append(op)

    # stable order
    ops.sort(key=lambda o: (o.tag, o.path, o.method))
    return SuiteIR(
        title=title,
        version=version,
        openapi_version=oas,
        operations=ops,
        source=source,
    )
