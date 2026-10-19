"""Generate pytest stubs for missing P1 types (LIB-COV-STUB)."""

from __future__ import annotations

import re
from typing import Any

from partest.test_types import TYPE_LABELS, TypesTestCases

_LABEL_TO_TYPE = {v: k for k, v in TYPE_LABELS.items()}


_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _type_attr(tc: str) -> str | None:
    """``types.<name>`` for a missing type, or ``None`` when it is not a plain name.

    The name goes into Python source: only ``[A-Za-z0-9_]`` is written, anything else is
    skipped (a comment says so) rather than escaped into an expression.
    """
    raw = _LABEL_TO_TYPE.get(tc, tc)
    if not _NAME.fullmatch(raw):
        return None
    if hasattr(TypesTestCases, raw) or raw.startswith("request_"):
        return f"types.{raw}"
    return "types.request_default"


def _slug(method: str, path: str, tc: str) -> str:
    raw = f"{method}_{path}_{tc}"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_").lower()
    return slug[:80] or "endpoint"


def _doc_text(text: str) -> str:
    """Text for a docstring: letters, digits and path punctuation only — no quote, backslash
    or line break can close the docstring early."""
    return re.sub(r"[^A-Za-z0-9 /{}_.:-]", "?", text)[:160]


def generate_stubs(payload: dict[str, Any]) -> str:
    """Emit a pytest module skeleton for missing P1 cells (no project imports).

    The payload may come from anywhere, and its strings end up in Python source: a method or
    a path is written as a ``repr()`` literal, into the docstring only through
    :func:`_doc_text`, and a type only as a plain name. A row that is not an object, or whose
    ``method`` / ``path`` / ``missing`` have the wrong type, is skipped; ``endpoints`` that is
    present and not a list (``{}``, ``0``, ``""`` included) is a ``ValueError``; absent or
    ``null`` is no endpoints.
    """
    if not isinstance(payload, dict):
        raise ValueError("a coverage.json is a JSON object")
    endpoints = payload.get("endpoints")
    if endpoints is None:
        endpoints = []
    elif not isinstance(endpoints, list):
        raise ValueError("'endpoints' is not a list")
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
    used: set[str] = set()
    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        missing = ep.get("missing") or []
        method = ep.get("method") or "GET"
        path = ep.get("path") or "/"
        if not isinstance(missing, list) or not isinstance(method, str) or not isinstance(path, str):
            continue
        for tc in missing:
            type_expr = _type_attr(tc) if isinstance(tc, str) else None
            if type_expr is None:
                lines.append("    # skipped: a missing type that is not a plain name")
                lines.append("")
                continue
            slug = _slug(method, path, tc)
            name, n = slug, 2
            while name in used:
                name, n = f"{slug}_{n}", n + 1
            used.add(name)
            lines.append("    @pytest.mark.skip(reason='coverage stub — implement')")
            lines.append(f"    async def test_{name}(self, api_client):")
            lines.append(f'        """{_doc_text(f"{method} {path} missing {tc}")}."""')
            lines.append("        await api_client.make_request(")
            lines.append(f"            {method!r},")
            lines.append(f"            {path!r},")
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
