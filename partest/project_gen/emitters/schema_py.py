"""JSON Schema → Python source helpers for payloads and pydantic models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from partest.project_gen.emitters.util import is_snake, path_to_attr


def op_module_stem(method: str, path: str) -> str:
    """post_items, get_items_by_id, put_items_by_id, …"""
    return f"{method.lower()}_{path_to_attr(path)}"


def op_symbol(method: str, path: str, kind: str = "validation") -> str:
    """Python-safe attribute / module symbol for an operation."""
    return op_module_stem(method, path)


def _schema_type(schema: Optional[Dict[str, Any]]) -> str:
    if not schema:
        return "any"
    if "type" in schema:
        t = schema["type"]
        if isinstance(t, list):
            # nullable union
            non_null = [x for x in t if x != "null"]
            return str(non_null[0]) if non_null else "any"
        return str(t)
    if "properties" in schema:
        return "object"
    if "items" in schema:
        return "array"
    if "allOf" in schema or "oneOf" in schema or "anyOf" in schema:
        return "object"
    return "any"


def pydantic_annotation(schema: Optional[Dict[str, Any]], *, required: bool) -> str:
    """Return annotation string for a field."""
    t = _schema_type(schema)
    base = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "array": "List[Any]",
        "object": "Dict[str, Any]",
        "any": "Any",
    }.get(t, "Any")
    if schema and t == "array":
        items = schema.get("items") if isinstance(schema, dict) else None
        if isinstance(items, dict):
            it = _schema_type(items)
            inner = {
                "string": "str",
                "integer": "int",
                "number": "float",
                "boolean": "bool",
                "object": "Dict[str, Any]",
            }.get(it, "Any")
            base = f"List[{inner}]"
    if not required:
        return f"Optional[{base}]"
    return base


def payload_default_expr(name: str, schema: Optional[Dict[str, Any]]) -> str:
    """Expression for ``_json_main`` value (callable or literal)."""
    t = _schema_type(schema)
    lname = name.lower()

    if t == "string":
        if "code" in lname:
            return f'lambda: marked_code("{is_snake(name)[:8].upper() or "X"}")'
        if lname in {"name", "title", "label"} or lname.endswith("name"):
            return f'lambda: marked_name("{name[:24]}")'
        return f'lambda: marked_name("{name[:24]}")'

    if t == "integer":
        if lname.endswith("id") or lname.endswith("_id"):
            return "0  # TODO: seed FK / path dependency"
        return "1"

    if t == "number":
        return "1.0"

    if t == "boolean":
        return "True"

    if t == "array":
        return "list"

    if t == "object":
        return "dict"

    return "None"


def schema_properties(schema: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """Return (properties, required_names) from object schema (best-effort)."""
    if not schema or not isinstance(schema, dict):
        return {}, []
    # unwrap allOf single object
    if "allOf" in schema and isinstance(schema["allOf"], list):
        props: Dict[str, Any] = {}
        required: List[str] = []
        for part in schema["allOf"]:
            if not isinstance(part, dict):
                continue
            p, r = schema_properties(part)
            props.update(p)
            required.extend(r)
        required = list(dict.fromkeys(required + list(schema.get("required") or [])))
        return props, required

    props = schema.get("properties") or {}
    if not isinstance(props, dict):
        props = {}
    required = list(schema.get("required") or [])
    return props, required


def build_payload_class_source(
    class_name: str,
    schema: Optional[Dict[str, Any]],
    *,
    module_doc: str = "",
) -> str:
    """Full module source with one BaseRequestBody subclass."""
    props, required = schema_properties(schema)
    lines = [
        "from __future__ import annotations",
        "",
        "from partest.payloads import BaseRequestBody",
        "from partest.data_marker import marked_code, marked_name",
        "",
        "",
        f"class {class_name}(BaseRequestBody):",
    ]
    if module_doc:
        lines.append(f'    """{module_doc}"""')
        lines.append("")
    if not props:
        lines.append("    _required = []")
        lines.append("    _json_main = {}")
        lines.append("")
        return "\n".join(lines)

    req_list = ", ".join(repr(r) for r in required if r in props)
    lines.append(f"    _required = [{req_list}]")
    lines.append("    _json_main = {")
    for name, sub in props.items():
        if not isinstance(name, str):
            continue
        expr = payload_default_expr(name, sub if isinstance(sub, dict) else None)
        lines.append(f'        "{name}": {expr},')
    lines.append("    }")
    lines.append("")
    return "\n".join(lines)


def build_validation_module_source(
    schema: Optional[Dict[str, Any]],
    *,
    is_list: bool = False,
    module_doc: str = "",
) -> str:
    """Module with ResponseSuccessBody + ResponseValidation."""
    # list of objects
    body_schema = schema
    if is_list and schema and _schema_type(schema) == "array":
        items = schema.get("items") if isinstance(schema, dict) else None
        body_schema = items if isinstance(items, dict) else None

    props, required = schema_properties(body_schema)
    lines = [
        "from __future__ import annotations",
        "",
        "from typing import Any, Dict, List, Optional, Type",
        "",
        "from pydantic import BaseModel, Field",
        "",
        "from partest.validation import BaseModelWithConfig, BaseResponseValidator",
        "",
        "",
    ]
    if not props:
        if is_list:
            lines = [
                "from __future__ import annotations",
                "",
                "from typing import Any, Dict, List, Optional, Type",
                "",
                "from pydantic import BaseModel, ConfigDict, Field, RootModel",
                "",
                "from partest.validation import BaseResponseValidator",
                "",
                "",
                "class ResponseSuccessBody(RootModel[List[Dict[str, Any]]]):",
                '    """List response without item schema."""',
                "",
                "",
            ]
        else:
            lines.extend(
                [
                    "class ResponseSuccessBody(BaseModelWithConfig):",
                    '    """OpenAPI response schema not detailed — allow extra fields."""',
                    "",
                    "    model_config = ConfigDict(extra=\"allow\")",
                    "",
                    "",
                ]
            )
            # need ConfigDict import
            lines[5] = "from pydantic import BaseModel, ConfigDict, Field"
    else:
        lines.append("class ResponseSuccessBody(BaseModelWithConfig):")
        if module_doc:
            lines.append(f'    """{module_doc}"""')
            lines.append("")
        for name, sub in props.items():
            if not isinstance(name, str):
                continue
            req = name in required
            ann = pydantic_annotation(sub if isinstance(sub, dict) else None, required=req)
            if req:
                lines.append(f"    {is_snake(name) if False else name}: {ann} = Field(...)")
            else:
                lines.append(f"    {name}: {ann} = Field(None)")
        lines.append("")
        lines.append("")
        if is_list:
            # wrap as list via RootModel
            lines = [
                "from __future__ import annotations",
                "",
                "from typing import Any, Dict, List, Optional, Type",
                "",
                "from pydantic import BaseModel, Field, RootModel",
                "",
                "from partest.validation import BaseModelWithConfig, BaseResponseValidator",
                "",
                "",
                "class _Item(BaseModelWithConfig):",
            ]
            for name, sub in props.items():
                if not isinstance(name, str):
                    continue
                req = name in required
                ann = pydantic_annotation(sub if isinstance(sub, dict) else None, required=req)
                if req:
                    lines.append(f"    {name}: {ann} = Field(...)")
                else:
                    lines.append(f"    {name}: {ann} = Field(None)")
            lines.extend(
                [
                    "",
                    "",
                    "class ResponseSuccessBody(RootModel[List[_Item]]):",
                    '    """Array response."""',
                    "",
                    "",
                ]
            )

    lines.extend(
        [
            "class ResponseValidation(BaseResponseValidator):",
            "    @property",
            "    def ResponseSuccessBody(self) -> Type[BaseModel]:",
            "        return ResponseSuccessBody",
            "",
        ]
    )
    return "\n".join(lines)
