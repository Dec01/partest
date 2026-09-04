"""Emit pydantic ResponseValidation modules from OpenAPI response schemas (G3)."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from partest.project_gen.emitters.schema_py import (
    build_validation_module_source,
    op_module_stem,
    _schema_type,
)
from partest.project_gen.emitters.util import GENERATED_BANNER, is_snake
from partest.project_gen.ir import OpIR, SuiteIR


def collect_validation_ops(
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
        # skip pure 204 no-content unless we still want a marker
        if op.success_status == 204 and not op.success_response_schema:
            continue
        out.append(op)
    return out


def build_validation_files(
    suite: SuiteIR,
    *,
    tags_filter: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    files: Dict[str, str] = {}
    by_tag: Dict[str, List[Tuple[str, str]]] = {}

    for op in collect_validation_ops(suite, tags_filter=tags_filter):
        tag = is_snake(op.tag)
        stem = op_module_stem(op.method, op.path)
        rel = f"src/api/resources/validations/{tag}/{stem}_validation.py"
        is_list = False
        schema = op.success_response_schema
        if schema and _schema_type(schema) == "array":
            is_list = True
        # GET list without schema — treat as list if path has no path params
        if schema is None and op.method == "GET" and not op.path_params:
            is_list = True
        body = GENERATED_BANNER + build_validation_module_source(
            schema,
            is_list=is_list,
            module_doc=f"{op.method} {op.path} success body",
        )
        files[rel] = body
        by_tag.setdefault(tag, []).append((stem, stem))

    for tag, items in by_tag.items():
        lines = [
            GENERATED_BANNER,
            f'"""Validations for tag `{tag}`."""',
            "",
        ]
        for stem, _ in items:
            lines.append(
                f"from src.api.resources.validations.{tag} import {stem}_validation"
            )
        # fix imports - modules not package
        lines = [
            GENERATED_BANNER,
            f'"""Validations for tag `{tag}`."""',
            "",
        ]
        for stem, _ in items:
            lines.append(
                f"from src.api.resources.validations.{tag}.{stem}_validation import ResponseValidation as _{stem}"
            )
        lines.append("")
        lines.append("# re-export module accessors via collection wiring")
        lines.append("__all__ = [")
        for stem, _ in items:
            lines.append(f'    "{stem}_validation",')
        lines.append("]")
        lines.append("")
        # simpler init - just empty package
        files[f"src/api/resources/validations/{tag}/__init__.py"] = (
            GENERATED_BANNER + f'"""Validations package for `{tag}`."""\n'
        )

    files["src/api/resources/validations/__init__.py"] = (
        GENERATED_BANNER
        + '"""Validations package."""\n\n'
        + "from partest.validation import BaseModelWithConfig, BaseResponseValidator\n\n"
        + '__all__ = ["BaseModelWithConfig", "BaseResponseValidator"]\n'
    )
    # keep common problem detail
    files["src/api/resources/validations/common/__init__.py"] = (
        GENERATED_BANNER + '"""Common validations."""\n'
    )
    files["src/api/resources/validations/common/problem_detail.py"] = (
        GENERATED_BANNER
        + '"""RFC 7807 error model — library preset."""\n\n'
        + "from partest.validation import ProblemDetailBody, ProblemDetailValidation\n\n"
        + "ResponseSuccessBody = ProblemDetailBody\n"
        + "ResponseValidation = ProblemDetailValidation\n"
    )
    return files


def validation_wiring(
    suite: SuiteIR,
    *,
    tags_filter: Optional[Sequence[str]] = None,
) -> Dict[str, List[Tuple[str, str, str]]]:
    """tag -> [(module, ResponseValidation_attr_name, attr)]."""
    result: Dict[str, List[Tuple[str, str, str]]] = {}
    for op in collect_validation_ops(suite, tags_filter=tags_filter):
        tag = is_snake(op.tag)
        stem = op_module_stem(op.method, op.path)
        mod = f"src.api.resources.validations.{tag}.{stem}_validation"
        result.setdefault(tag, []).append((mod, "ResponseValidation", stem))
    return result
