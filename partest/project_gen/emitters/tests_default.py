"""Emit RequestDefault + RequestNotAllowed test stubs (G3)."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Set, Tuple

from partest.project_gen.emitters.schema_py import op_module_stem
from partest.project_gen.emitters.util import GENERATED_BANNER, is_snake, path_to_attr
from partest.project_gen.ir import OpIR, SuiteIR

_VERBS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def _path_attr(path: str, tag_attrs: Dict[str, str]) -> str:
    return tag_attrs.get(path) or path_to_attr(path)


def _needs_path_values(op: OpIR) -> bool:
    return bool(op.path_params)


def build_default_test_module(
    tag: str,
    ops: List[OpIR],
    path_attrs: Dict[str, str],
) -> str:
    tag_s = is_snake(tag)
    lines: List[str] = [
        GENERATED_BANNER,
        f'"""RequestDefault stubs for `{tag_s}` — fill TODOs / seed data."""',
        "",
        "from __future__ import annotations",
        "",
        "import allure",
        "import pytest",
        "",
        "from partest import TypesTestCases",
        "import partest.reporting as ah",
        "",
        "types = TypesTestCases",
        "",
        "",
        f'@allure.epic("API")',
        f'@allure.feature("{tag_s}")',
        "@pytest.mark.asyncio",
        f"class Test{''.join(p.capitalize() for p in tag_s.split('_'))}Default:",
        '    """Happy-path / smoke defaults (G3 stubs)."""',
        "",
    ]

    for op in sorted(ops, key=lambda o: (o.path, o.method)):
        if op.deprecated:
            continue
        attr = _path_attr(op.path, path_attrs)
        stem = op_module_stem(op.method, op.path)
        test_name = f"test_{stem}_default"
        needs_id = _needs_path_values(op)
        has_body = op.has_request_body and op.method in {"POST", "PUT", "PATCH"}
        status = op.success_status
        use_write = op.method in {"POST", "PUT", "PATCH", "DELETE"}

        lines.append("    @ah.testcase(")
        lines.append(f'        title="{op.method} {op.path} default",')
        lines.append('        story="RequestDefault",')
        lines.append("    )")
        if needs_id:
            lines.append("    @pytest.mark.skip(reason=\"TODO: provide path params / seed id\")")
        lines.append(f"    async def {test_name}(self, api_client, models):")
        lines.append(f'        """{op.summary or op.operation_id} — subtype `{op.subtype}`."""')
        if has_body:
            lines.append(f"        payload = models.{tag_s}.payload.{stem}()")
            lines.append(f"        # TODO: set FK fields via payload.set_payload_field(...)")
        headers = "write" if use_write else "read"
        lines.append("        response = await api_client.make_request(")
        lines.append(f'            "{op.method}",')
        lines.append(f"            models.{tag_s}.paths.{attr},")
        if needs_id:
            lines.append('            # add_url1="/{id}",  # TODO')
            lines.append(f'            defining_url="{op.path}",')
        else:
            lines.append(f'            defining_url="{op.path}",')
        lines.append(f"            headers=models.{tag_s}.headers.{headers},")
        if has_body:
            lines.append("            json_data=payload.json,")
        lines.append(f"            expected_status_code={status},")
        # validate_model if we generated one
        if not (status == 204 and not op.success_response_schema):
            lines.append(
                f"            validate_model=getattr(models.{tag_s}.validate, \"{stem}\", None),"
            )
        lines.append("            type=types.request_default,")
        lines.append("        )")
        lines.append("        # TODO: ah.check_eq / ah.check_true on deterministic fields")
        lines.append("        assert response is not None or response == \"\"")
        lines.append("")

    return "\n".join(lines)


def build_not_allowed_test_module(
    tag: str,
    ops: List[OpIR],
    path_attrs: Dict[str, str],
) -> str:
    tag_s = is_snake(tag)
    by_path: Dict[str, Set[str]] = defaultdict(set)
    for op in ops:
        if not op.deprecated:
            by_path[op.path].add(op.method.upper())

    lines: List[str] = [
        GENERATED_BANNER,
        f'"""RequestNotAllowed (405) stubs for `{tag_s}`."""',
        "",
        "from __future__ import annotations",
        "",
        "import allure",
        "import pytest",
        "",
        "from partest import TypesTestCases",
        "import partest.reporting as ah",
        "",
        "types = TypesTestCases",
        "",
        "",
        f'@allure.epic("API")',
        f'@allure.feature("{tag_s}")',
        "@pytest.mark.asyncio",
        f"class Test{''.join(p.capitalize() for p in tag_s.split('_'))}NotAllowed:",
        '    """Unsupported methods on known paths."""',
        "",
    ]

    any_case = False
    for path, allowed in sorted(by_path.items()):
        forbidden = [v for v in _VERBS if v not in allowed]
        if not forbidden:
            continue
        method = forbidden[0]
        attr = _path_attr(path, path_attrs)
        # skip path templates that need ids for clean 405 (still valid on many servers)
        needs_id = "{" in path
        test_name = f"test_{method.lower()}_{path_to_attr(path)}_not_allowed"
        any_case = True
        lines.append("    @ah.testcase(")
        lines.append(f'        title="{method} {path} not allowed",')
        lines.append('        story="RequestNotAllowed",')
        lines.append("    )")
        if needs_id:
            lines.append(
                "    @pytest.mark.skip(reason=\"TODO: path params for 405 probe\")"
            )
        lines.append(f"    async def {test_name}(self, api_client, models):")
        lines.append(
            f'        """Expect 405: allowed={sorted(allowed)}, try {method}."""'
        )
        lines.append("        await api_client.make_request(")
        lines.append(f'            "{method}",')
        lines.append(f"            models.{tag_s}.paths.{attr},")
        lines.append(f'            defining_url="{path}",')
        lines.append(f"            headers=models.{tag_s}.headers.read,")
        lines.append("            expected_status_code=405,")
        lines.append("            type=types.request_not_allowed,")
        lines.append("        )")
        lines.append("")

    if not any_case:
        lines.append("    async def test_no_not_allowed_candidates(self):")
        lines.append('        """All common verbs are declared for every path — nothing to probe."""')
        lines.append("        assert True")
        lines.append("")

    return "\n".join(lines)


def build_test_files(
    suite: SuiteIR,
    tag_path_attrs: Dict[str, Dict[str, str]],
    *,
    tags_filter: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    allow = {is_snake(t) for t in tags_filter} if tags_filter else None
    by_tag: Dict[str, List[OpIR]] = defaultdict(list)
    for op in suite.operations:
        if op.deprecated:
            continue
        tag = is_snake(op.tag)
        if allow is not None and tag not in allow:
            continue
        by_tag[tag].append(op)

    files: Dict[str, str] = {}
    for tag, ops in by_tag.items():
        path_attrs = tag_path_attrs.get(tag, {})
        # invert path->attr if needed: tag_path_attrs is path->attr
        files[f"src/api/tests/{tag}/__init__.py"] = (
            GENERATED_BANNER + f'"""Tests for `{tag}`."""\n'
        )
        files[f"src/api/tests/{tag}/test_{tag}_default.py"] = build_default_test_module(
            tag, ops, path_attrs
        )
        files[f"src/api/tests/{tag}/test_{tag}_not_allowed.py"] = (
            build_not_allowed_test_module(tag, ops, path_attrs)
        )
    return files
