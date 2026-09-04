"""Generate pytest stubs for missing P1 types (LIB-COV-STUB)."""

from __future__ import annotations

import re
from typing import Any

from partest.test_types import TYPE_LABELS, TypesTestCases

_LABEL_TO_TYPE = {v: k for k, v in TYPE_LABELS.items()}


def _type_attr(tc: str) -> str:
    raw = _LABEL_TO_TYPE.get(tc, tc)
    if hasattr(TypesTestCases, raw):
        return f"types.{raw}"
    if raw.startswith("request_"):
        return f"types.{raw}"
    return "types.request_default"


def _slug(method: str, path: str, tc: str) -> str:
    raw = f"{method}_{path}_{tc}"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_").lower()
    return slug[:80] or "endpoint"


def generate_stubs(payload: dict[str, Any]) -> str:
    """Emit a pytest module skeleton for missing P1 cells (no project imports)."""
    lines = [
        '"""Auto-generated coverage stubs — fill in client/path/headers."""',
        "",
        "import pytest",
        "from partest import TypesTestCases as types",
        "",
        "",
        "class TestCoverageStubs:",
        '    """Replace `client` / url / headers with your suite fixtures."""',
        "",
    ]
    count = 0
    for ep in payload.get("endpoints") or []:
        missing = ep.get("missing") or []
        if not missing:
            continue
        method = ep.get("method") or "GET"
        path = ep.get("path") or "/"
        for tc in missing:
            type_expr = _type_attr(str(tc))
            slug = _slug(method, path, str(tc))
            lines.append("    @pytest.mark.skip(reason='coverage stub — implement')")
            lines.append(f"    async def test_{slug}(self, api_client):")
            lines.append(f'        """{method} {path} missing {tc}."""')
            lines.append("        await api_client.make_request(")
            lines.append(f'            "{method}",')
            lines.append(f'            "{path}",')
            lines.append("            headers={},")
            lines.append("            expected_status_code=200,")
            lines.append(f"            type={type_expr},")
            lines.append("        )")
            lines.append("")
            count += 1
    if count == 0:
        lines.append("    def test_no_missing_p1(self):")
        lines.append("        assert True")
        lines.append("")
    return "\n".join(lines)
