"""Emit full P1 test-case stubs per methodology matrix (G4)."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Set, Tuple

from partest.project_gen.emitters.schema_py import op_module_stem
from partest.project_gen.emitters.util import GENERATED_BANNER, is_snake, path_to_attr
from partest.project_gen.ir import OpIR, SuiteIR
from partest.test_types import TYPE_LABELS, TypesTestCases as T

# P1 types handled here (default + not_allowed remain in tests_default.py)
_P1_EXTRA = {
    T.request_compare_benchmark,
    T.request_permissions,
    T.request_new_object,
    T.request_update_object,
    T.request_incorrect_body,
    T.request_elements,
    T.request_extra_data,
    T.request_not_found,
    T.request_params,
    T.request_env_list,
}

# short file suffix per TC
_FILE_SUFFIX = {
    T.request_compare_benchmark: "benchmark",
    T.request_permissions: "permissions",
    T.request_new_object: "new_object",
    T.request_update_object: "update_object",
    T.request_incorrect_body: "incorrect_body",
    T.request_elements: "elements",
    T.request_extra_data: "extra_data",
    T.request_not_found: "not_found",
    T.request_params: "params",
    T.request_env_list: "env_list",
}


def _path_attr(path: str, path_attrs: Dict[str, str]) -> str:
    return path_attrs.get(path) or path_to_attr(path)


def _class_prefix(tag: str) -> str:
    return "".join(p.capitalize() for p in is_snake(tag).split("_"))


def _ops_for_tc(ops: List[OpIR], tc: str) -> List[OpIR]:
    return [o for o in ops if tc in (o.required_p1 or []) and not o.deprecated]


def _common_header(tag: str, tc: str, story: str) -> List[str]:
    tag_s = is_snake(tag)
    label = TYPE_LABELS.get(tc, tc)
    return [
        GENERATED_BANNER,
        f'"""{label} (P1) stubs for `{tag_s}` — fill roles/seeds/asserts."""',
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
        '@allure.epic("API")',
        f'@allure.feature("{tag_s}")',
        "@pytest.mark.asyncio",
        f"class Test{_class_prefix(tag_s)}{''.join(p.capitalize() for p in _FILE_SUFFIX.get(tc, tc).split('_'))}:",
        f'    """P1: {label}."""',
        "",
    ]


def _emit_permissions(tag: str, ops: List[OpIR], path_attrs: Dict[str, str]) -> str:
    tag_s = is_snake(tag)
    lines = _common_header(tag, T.request_permissions, "RequestPermissions")
    for op in sorted(ops, key=lambda o: (o.path, o.method)):
        attr = _path_attr(op.path, path_attrs)
        stem = op_module_stem(op.method, op.path)
        needs_id = bool(op.path_params)
        lines.append("    @ah.testcase(")
        lines.append(f'        title="{op.method} {op.path} permissions",')
        lines.append('        story="RequestPermissions",')
        lines.append("    )")
        if needs_id:
            lines.append(
                '    @pytest.mark.skip(reason="TODO: seed resource id + multi-role tokens")'
            )
        else:
            lines.append(
                '    @pytest.mark.skip(reason="TODO: wire TokenManager roles (401/403 matrix)")'
            )
        lines.append(f"    async def test_{stem}_permissions(self, api_client, models):")
        lines.append(
            '        """No auth → 401; wrong role → 403; allowed role → 2xx. Horizontal check."""'
        )
        lines.append("        # 1) anonymous / missing token")
        lines.append("        headers = dict(models.{}.headers.read)".format(tag_s))
        lines.append('        headers.pop("Authorization", None)')
        lines.append("        await api_client.make_request(")
        lines.append(f'            "{op.method}",')
        lines.append(f"            models.{tag_s}.paths.{attr},")
        lines.append(f'            defining_url="{op.path}",')
        lines.append("            headers=headers,")
        lines.append("            expected_status_code=401,")
        lines.append("            type=types.request_permissions,")
        lines.append("        )")
        lines.append("        # 2) TODO: role without access → 403")
        lines.append("        # 3) TODO: role with access → success")
        lines.append("")
    if len(lines) < 20:
        lines.append("    async def test_permissions_placeholder(self):")
        lines.append("        assert True  # no P1 permission ops for this tag")
        lines.append("")
    return "\n".join(lines)


def _emit_not_found(tag: str, ops: List[OpIR], path_attrs: Dict[str, str]) -> str:
    tag_s = is_snake(tag)
    lines = _common_header(tag, T.request_not_found, "RequestNotFound")
    for op in sorted(ops, key=lambda o: (o.path, o.method)):
        if not op.path_params and op.method not in {"GET", "PUT", "PATCH", "DELETE"}:
            continue
        attr = _path_attr(op.path, path_attrs)
        stem = op_module_stem(op.method, op.path)
        lines.append("    @ah.testcase(")
        lines.append(f'        title="{op.method} {op.path} not found",')
        lines.append('        story="RequestNotFound",')
        lines.append("    )")
        lines.append(f"    async def test_{stem}_not_found(self, api_client, models):")
        lines.append('        """Missing / deleted resource → 404."""')
        if op.path_params:
            # pick first path param filler
            fake = "/999999001"
            lines.append(f"        await api_client.make_request(")
            lines.append(f'            "{op.method}",')
            lines.append(f"            models.{tag_s}.paths.{attr},")
            lines.append(f'            add_url1="{fake}",  # TODO: align with path template')
            lines.append(f'            defining_url="{op.path}",')
            lines.append(f"            headers=models.{tag_s}.headers.read,")
            lines.append("            expected_status_code=404,")
            lines.append("            type=types.request_not_found,")
            lines.append("        )")
        else:
            lines.append(
                '        pytest.skip("No path id on this op — use double-delete profile if DELETE")'
            )
        lines.append("")
    return "\n".join(lines)


def _emit_incorrect_body(tag: str, ops: List[OpIR], path_attrs: Dict[str, str]) -> str:
    tag_s = is_snake(tag)
    lines = _common_header(tag, T.request_incorrect_body, "RequestIncorrectBody")
    # Insert helper import after the types = TypesTestCases block
    insert_at = next(i for i, ln in enumerate(lines) if ln.startswith("types = "))
    extra = [
        "from partest.validation import RAW_INCORRECT_BODY_CASES, assert_raw_incorrect_body",
        "",
    ]
    lines = lines[: insert_at + 1] + extra + lines[insert_at + 1 :]
    for op in sorted(ops, key=lambda o: (o.path, o.method)):
        if not op.has_request_body:
            continue
        attr = _path_attr(op.path, path_attrs)
        stem = op_module_stem(op.method, op.path)
        needs_id = bool(op.path_params)
        lines.append("    @ah.testcase(")
        lines.append(f'        title="{op.method} {op.path} incorrect body",')
        lines.append('        story="RequestIncorrectBody",')
        lines.append("    )")
        if needs_id:
            lines.append('    @pytest.mark.skip(reason="TODO: path params for transport abuse")')
        lines.append("    @pytest.mark.parametrize(")
        lines.append('        "content, content_type, expected",')
        lines.append("        RAW_INCORRECT_BODY_CASES,")
        lines.append("    )")
        lines.append(
            f"    async def test_{stem}_incorrect_body("
            "self, api_client, models, content, content_type, expected):"
        )
        lines.append('        """Broken JSON / wrong Content-Type → clean 4xx (no leak)."""')
        lines.append("        await assert_raw_incorrect_body(")
        lines.append("            api_client,")
        lines.append(f'            "{op.method}",')
        lines.append(f"            models.{tag_s}.paths.{attr},")
        lines.append(f"            models.{tag_s}.headers.write,")
        lines.append("            content=content,")
        lines.append("            content_type=content_type,")
        lines.append("            expected_status_code=expected,")
        lines.append(f'            defining_url="{op.path}",')
        lines.append("        )")
        lines.append("")
    return "\n".join(lines)


def _emit_elements(tag: str, ops: List[OpIR], path_attrs: Dict[str, str]) -> str:
    tag_s = is_snake(tag)
    lines = _common_header(tag, T.request_elements, "RequestElements")
    for op in sorted(ops, key=lambda o: (o.path, o.method)):
        if not op.has_request_body:
            continue
        attr = _path_attr(op.path, path_attrs)
        stem = op_module_stem(op.method, op.path)
        needs_id = bool(op.path_params)
        lines.append("    @ah.testcase(")
        lines.append(f'        title="{op.method} {op.path} elements",')
        lines.append('        story="RequestElements",')
        lines.append("    )")
        if needs_id:
            lines.append('    @pytest.mark.skip(reason="TODO: path params + field matrix")')
        lines.append(f"    async def test_{stem}_elements_missing_required(self, api_client, models):")
        lines.append('        """Each required field missing → 4xx (contract)."""')
        lines.append(f"        payload_cls = models.{tag_s}.payload.{stem}")
        lines.append("        required = payload_cls.get_required_fields()")
        lines.append("        if not required:")
        lines.append('            pytest.skip("no required fields in generated payload")')
        lines.append("        for field in required:")
        lines.append("            body = payload_cls.get_json_miss_required(field)")
        lines.append("            await api_client.make_request(")
        lines.append(f'                "{op.method}",')
        lines.append(f"                models.{tag_s}.paths.{attr},")
        lines.append(f'                defining_url="{op.path}",')
        lines.append(f"                headers=models.{tag_s}.headers.write,")
        lines.append("                json_data=body,")
        lines.append("                expected_status_code=400,")
        lines.append(
            f"                validate_model=getattr(models.{tag_s}.validate, \"error\", None),"
        )
        lines.append("                type=types.request_elements,")
        lines.append("            )")
        lines.append("        # TODO: type mismatch / maxLength / boundary per field")
        lines.append("")
    return "\n".join(lines)


def _emit_extra_data(tag: str, ops: List[OpIR], path_attrs: Dict[str, str]) -> str:
    tag_s = is_snake(tag)
    lines = _common_header(tag, T.request_extra_data, "RequestExtraData")
    for op in sorted(ops, key=lambda o: (o.path, o.method)):
        if not op.has_request_body:
            continue
        attr = _path_attr(op.path, path_attrs)
        stem = op_module_stem(op.method, op.path)
        needs_id = bool(op.path_params)
        status = op.success_status if op.method == "POST" else op.success_status
        lines.append("    @ah.testcase(")
        lines.append(f'        title="{op.method} {op.path} extra data",')
        lines.append('        story="RequestExtraData",')
        lines.append("    )")
        if needs_id:
            lines.append('    @pytest.mark.skip(reason="TODO: path params for mass-assign probe")')
        lines.append(f"    async def test_{stem}_extra_data(self, api_client, models):")
        lines.append('        """Unknown fields must not mass-assign / change behaviour."""')
        lines.append(f"        payload = models.{tag_s}.payload.{stem}()")
        lines.append("        body = dict(payload.json)")
        lines.append('        body["__partest_extra_field__"] = "should-be-ignored"')
        lines.append("        # TODO: also try is_admin / owner_id style probes for your domain")
        lines.append("        response = await api_client.make_request(")
        lines.append(f'            "{op.method}",')
        lines.append(f"            models.{tag_s}.paths.{attr},")
        lines.append(f'            defining_url="{op.path}",')
        lines.append(f"            headers=models.{tag_s}.headers.write,")
        lines.append("            json_data=body,")
        lines.append(f"            expected_status_code={status},  # or 400 if API rejects unknown")
        lines.append(
            f"            validate_model=getattr(models.{tag_s}.validate, \"{stem}\", None),"
        )
        lines.append("            type=types.request_extra_data,")
        lines.append("        )")
        lines.append("        # TODO: ah.check that privileged fields were not applied")
        lines.append("        assert response is not None or response == \"\"")
        lines.append("")
    return "\n".join(lines)


def _emit_new_object(tag: str, ops: List[OpIR], path_attrs: Dict[str, str]) -> str:
    tag_s = is_snake(tag)
    lines = _common_header(tag, T.request_new_object, "RequestNewObject")
    creates = [o for o in ops if o.method == "POST" and o.has_request_body]
    for op in sorted(creates, key=lambda o: o.path):
        attr = _path_attr(op.path, path_attrs)
        stem = op_module_stem(op.method, op.path)
        lines.append("    @ah.testcase(")
        lines.append(f'        title="vertical new object via {op.method} {op.path}",')
        lines.append('        story="RequestNewObject",')
        lines.append("    )")
        lines.append(f"    async def test_{stem}_new_object(self, api_client, models):")
        lines.append(
            '        """Create → immediately GET/list visibility + permissions moment."""'
        )
        lines.append(f"        payload = models.{tag_s}.payload.{stem}()")
        lines.append("        # TODO: payload.set_payload_field for FKs")
        lines.append("        created = await api_client.make_request(")
        lines.append(f'            "POST",')
        lines.append(f"            models.{tag_s}.paths.{attr},")
        lines.append(f'            defining_url="{op.path}",')
        lines.append(f"            headers=models.{tag_s}.headers.write,")
        lines.append("            json_data=payload.json,")
        lines.append(f"            expected_status_code={op.success_status},")
        lines.append(
            f"            validate_model=getattr(models.{tag_s}.validate, \"{stem}\", None),"
        )
        lines.append("            type=types.request_new_object,")
        lines.append("        )")
        lines.append("        # TODO: GET by id immediately; list contains id; author/permissions")
        lines.append('        ah.check_true(isinstance(created, dict), field="created")')
        lines.append('        # rid = created.get("id")')
        lines.append("")
    return "\n".join(lines)


def _emit_update_object(tag: str, ops: List[OpIR], path_attrs: Dict[str, str]) -> str:
    tag_s = is_snake(tag)
    lines = _common_header(tag, T.request_update_object, "RequestUpdateObject")
    updates = [o for o in ops if o.method in {"PUT", "PATCH"} and o.has_request_body]
    for op in sorted(updates, key=lambda o: o.path):
        attr = _path_attr(op.path, path_attrs)
        stem = op_module_stem(op.method, op.path)
        lines.append("    @ah.testcase(")
        lines.append(f'        title="vertical update via {op.method} {op.path}",')
        lines.append('        story="RequestUpdateObject",')
        lines.append("    )")
        lines.append(
            '    @pytest.mark.skip(reason="TODO: create/seed entity then update + cache check")'
        )
        lines.append(f"    async def test_{stem}_update_object(self, api_client, models):")
        lines.append('        """Update → state visible in GET/list (incl. cache invalidation)."""')
        lines.append(f"        payload = models.{tag_s}.payload.{stem}()")
        lines.append("        await api_client.make_request(")
        lines.append(f'            "{op.method}",')
        lines.append(f"            models.{tag_s}.paths.{attr},")
        lines.append('            # add_url1=f"/{entity_id}",')
        lines.append(f'            defining_url="{op.path}",')
        lines.append(f"            headers=models.{tag_s}.headers.write,")
        lines.append("            json_data=payload.json,")
        lines.append(f"            expected_status_code={op.success_status},")
        lines.append("            type=types.request_update_object,")
        lines.append("        )")
        lines.append("")
    return "\n".join(lines)


def _emit_benchmark(tag: str, ops: List[OpIR], path_attrs: Dict[str, str]) -> str:
    tag_s = is_snake(tag)
    lines = _common_header(tag, T.request_compare_benchmark, "RequestCompareBenchmark")
    for op in sorted(ops, key=lambda o: (o.path, o.method)):
        attr = _path_attr(op.path, path_attrs)
        stem = op_module_stem(op.method, op.path)
        needs_id = bool(op.path_params)
        lines.append("    @ah.testcase(")
        lines.append(f'        title="{op.method} {op.path} benchmark",')
        lines.append('        story="RequestCompareBenchmark",')
        lines.append("    )")
        if needs_id:
            lines.append('    @pytest.mark.skip(reason="TODO: stable seed for exact values")')
        lines.append(f"    async def test_{stem}_benchmark(self, api_client, models):")
        lines.append('        """Values match fixed baseline (not only schema)."""')
        lines.append("        response = await api_client.make_request(")
        lines.append(f'            "{op.method}",')
        lines.append(f"            models.{tag_s}.paths.{attr},")
        lines.append(f'            defining_url="{op.path}",')
        lines.append(f"            headers=models.{tag_s}.headers.read,")
        lines.append(f"            expected_status_code={op.success_status},")
        lines.append(
            f"            validate_model=getattr(models.{tag_s}.validate, \"{stem}\", None),"
        )
        lines.append("            type=types.request_compare_benchmark,")
        lines.append("        )")
        lines.append("        # TODO: ah.check_eq(response[\"field\"], EXPECTED)")
        lines.append("        assert response is not None")
        lines.append("")
    return "\n".join(lines)


def _emit_params(tag: str, ops: List[OpIR], path_attrs: Dict[str, str]) -> str:
    tag_s = is_snake(tag)
    lines = _common_header(tag, T.request_params, "RequestsParams")
    for op in sorted(ops, key=lambda o: (o.path, o.method)):
        attr = _path_attr(op.path, path_attrs)
        stem = op_module_stem(op.method, op.path)
        lines.append("    @ah.testcase(")
        lines.append(f'        title="{op.method} {op.path} params",')
        lines.append('        story="RequestsParams",')
        lines.append("    )")
        lines.append(
            '    @pytest.mark.skip(reason="TODO: seed list data + filter/sort/page expectations")'
        )
        lines.append(f"    async def test_{stem}_params(self, api_client, models):")
        lines.append('        """Filter / sort / pagination affect the result set."""')
        qnames = [p.name for p in op.query_params] or ["page", "size"]
        lines.append(f"        params = {{  # suggested from OpenAPI: {qnames!r}")
        for q in qnames[:4]:
            lines.append(f'            "{q}": 1,')
        lines.append("        }")
        lines.append("        response = await api_client.make_request(")
        lines.append(f'            "{op.method}",')
        lines.append(f"            models.{tag_s}.paths.{attr},")
        lines.append(f'            defining_url="{op.path}",')
        lines.append("            params=params,")
        lines.append(f"            headers=models.{tag_s}.headers.read,")
        lines.append(f"            expected_status_code={op.success_status},")
        lines.append("            type=types.request_params,")
        lines.append("        )")
        lines.append("        # TODO: assert filtered size / order")
        lines.append("        assert response is not None")
        lines.append("")
    return "\n".join(lines)


def _emit_env_list(tag: str, ops: List[OpIR], path_attrs: Dict[str, str]) -> str:
    tag_s = is_snake(tag)
    lines = _common_header(tag, T.request_env_list, "RequestEnvList")
    lines.append(
        '    @pytest.mark.skip(reason="TODO: multi-slice admin/public visibility if applicable")'
    )
    lines.append("    async def test_env_list_placeholder(self):")
    lines.append(
        '        """Object visible where it should be, hidden where it should not."""'
    )
    lines.append("        assert True")
    lines.append("")
    return "\n".join(lines)


_EMITTERS = {
    T.request_permissions: _emit_permissions,
    T.request_not_found: _emit_not_found,
    T.request_incorrect_body: _emit_incorrect_body,
    T.request_elements: _emit_elements,
    T.request_extra_data: _emit_extra_data,
    T.request_new_object: _emit_new_object,
    T.request_update_object: _emit_update_object,
    T.request_compare_benchmark: _emit_benchmark,
    T.request_params: _emit_params,
    T.request_env_list: _emit_env_list,
}


def build_p1_test_files(
    suite: SuiteIR,
    tag_path_attrs: Dict[str, Dict[str, str]],
    *,
    tags_filter: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    """Generate per-tag P1 extra test modules (not default/not_allowed)."""
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
        # which extra P1 types appear on this tag?
        needed: Set[str] = set()
        for op in ops:
            for tc in op.required_p1 or []:
                if tc in _P1_EXTRA:
                    needed.add(tc)

        for tc in sorted(needed):
            emitter = _EMITTERS.get(tc)
            if not emitter:
                continue
            tc_ops = _ops_for_tc(ops, tc)
            if not tc_ops and tc != T.request_env_list:
                continue
            # for env_list may be empty but still emit placeholder if in needed
            if not tc_ops and tc == T.request_env_list:
                tc_ops = ops[:1]
            suffix = _FILE_SUFFIX.get(tc, tc.replace("request_", ""))
            rel = f"src/api/tests/{tag}/test_{tag}_{suffix}.py"
            files[rel] = emitter(tag, tc_ops, path_attrs)

        # ensure package init exists
        files.setdefault(
            f"src/api/tests/{tag}/__init__.py",
            GENERATED_BANNER + f'"""Tests for `{tag}`."""\n',
        )

        # checklist markdown for humans/agents
        checklist = [
            GENERATED_BANNER.replace("# ", ""),  # not valid md with #
            f"# P1 coverage checklist — `{tag}`",
            "",
            "Generated from methodology matrix. Mark when implemented for real.",
            "",
            "| Operation | Subtype | P1 TC | Stub file |",
            "|-----------|---------|-------|-----------|",
        ]
        for op in sorted(ops, key=lambda o: (o.path, o.method)):
            for tc in op.required_p1 or []:
                label = TYPE_LABELS.get(tc, tc)
                if tc in (T.request_default, T.request_not_allowed):
                    stub = f"test_{tag}_default.py / not_allowed"
                else:
                    stub = f"test_{tag}_{_FILE_SUFFIX.get(tc, tc)}.py"
                checklist.append(
                    f"| {op.method} `{op.path}` | `{op.subtype}` | {label} | `{stub}` |"
                )
        checklist.append("")
        files[f"src/api/tests/{tag}/P1_CHECKLIST.md"] = "\n".join(checklist)

    return files
