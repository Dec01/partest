"""Emit BaseRequestBody modules from OpenAPI request schemas (G3)."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from partest.project_gen.emitters.schema_py import (
    build_payload_class_source,
    op_module_stem,
)
from partest.project_gen.emitters.util import GENERATED_BANNER, is_snake
from partest.project_gen.ir import OpIR, SuiteIR


def _payload_class_name(method: str, path: str) -> str:
    stem = op_module_stem(method, path)
    parts = [p for p in stem.split("_") if p]
    return "".join(p.capitalize() for p in parts) + "Body"


def collect_payload_ops(
    suite: SuiteIR,
    *,
    tags_filter: Optional[Sequence[str]] = None,
) -> List[OpIR]:
    allow = {is_snake(t) for t in tags_filter} if tags_filter else None
    out = []
    for op in suite.operations:
        if op.deprecated:
            continue
        if allow is not None and is_snake(op.tag) not in allow:
            continue
        if op.method in {"POST", "PUT", "PATCH"} and op.has_request_body:
            out.append(op)
    return out


def build_payload_files(
    suite: SuiteIR,
    *,
    tags_filter: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    """rel_path -> source. Also returns package inits."""
    files: Dict[str, str] = {}
    by_tag: Dict[str, List[Tuple[str, str, str]]] = {}
    # tag -> list of (module_stem, class_name, attr_name)

    for op in collect_payload_ops(suite, tags_filter=tags_filter):
        tag = is_snake(op.tag)
        stem = op_module_stem(op.method, op.path)
        cls = _payload_class_name(op.method, op.path)
        attr = stem  # post_items, put_items_by_id
        rel = f"src/api/resources/payloads/{tag}/{stem}_payload.py"
        body = GENERATED_BANNER + build_payload_class_source(
            cls,
            op.request_schema,
            module_doc=f"{op.method} {op.path} request body",
        )
        files[rel] = body
        by_tag.setdefault(tag, []).append((stem, cls, attr))

    for tag, items in by_tag.items():
        init_lines = [
            GENERATED_BANNER,
            f'"""Payloads for tag `{tag}`."""',
            "",
        ]
        for stem, cls, attr in items:
            init_lines.append(
                f"from src.api.resources.payloads.{tag}.{stem}_payload import {cls}"
            )
        init_lines.append("")
        init_lines.append("__all__ = [")
        for _, cls, _ in items:
            init_lines.append(f'    "{cls}",')
        init_lines.append("]")
        init_lines.append("")
        files[f"src/api/resources/payloads/{tag}/__init__.py"] = "\n".join(init_lines)

    # root payloads __init__
    tags = sorted(by_tag.keys())
    root = [
        GENERATED_BANNER,
        '"""Payloads package."""',
        "",
        "from partest.payloads import BaseRequestBody",
        "",
        '__all__ = ["BaseRequestBody"]',
        "",
    ]
    files["src/api/resources/payloads/__init__.py"] = "\n".join(root)
    return files


def payload_wiring(
    suite: SuiteIR,
    *,
    tags_filter: Optional[Sequence[str]] = None,
) -> Dict[str, List[Tuple[str, str, str]]]:
    """tag -> [(import_module, class_name, attr_name)]."""
    result: Dict[str, List[Tuple[str, str, str]]] = {}
    for op in collect_payload_ops(suite, tags_filter=tags_filter):
        tag = is_snake(op.tag)
        stem = op_module_stem(op.method, op.path)
        cls = _payload_class_name(op.method, op.path)
        mod = f"src.api.resources.payloads.{tag}.{stem}_payload"
        result.setdefault(tag, []).append((mod, cls, stem))
    return result
