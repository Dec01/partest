"""Emit BaseCollection façades per OpenAPI tag (G2 + G3 wiring)."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from partest.project_gen.emitters.util import (
    GENERATED_BANNER,
    collection_class_name,
    is_snake,
)


def build_collection_module(
    tag: str,
    path_attrs: Dict[str, str],
    *,
    ops_summary: Optional[List[str]] = None,
    payload_wiring: Optional[List[Tuple[str, str, str]]] = None,
    validation_wiring: Optional[List[Tuple[str, str, str]]] = None,
) -> str:
    """Single collection_{tag}.py source.

    payload_wiring: list of (module, class_name, attr)
    validation_wiring: list of (module, class_or_symbol, attr)
    """
    tag_s = is_snake(tag)
    cls = collection_class_name(tag_s)
    payload_wiring = payload_wiring or []
    validation_wiring = validation_wiring or []

    lines: List[str] = [
        GENERATED_BANNER,
        f'"""Collection façade for `{tag_s}`."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Optional",
        "",
        "from partest.collections import BaseCollection",
        "from partest.validation import ProblemDetailValidation",
        "",
        "from src.api.resources.endpoints import configs",
        "from src.api.resources.endpoints.paths import paths",
    ]

    for mod, class_name, attr in payload_wiring:
        lines.append(f"from {mod} import {class_name}")
    for mod, _sym, attr in validation_wiring:
        lines.append(f"from {mod} import ResponseValidation as _Val_{attr}")

    lines.extend(
        [
            "",
            "",
            "class ModelsValidations:",
            '    """Response validators + shared error model."""',
            "",
            "    error = ProblemDetailValidation()",
        ]
    )
    for _mod, _sym, attr in validation_wiring:
        lines.append(f"    {attr} = _Val_{attr}()")
    if not validation_wiring:
        lines.append("    # G3: no response schemas generated for this tag")
    lines.append("")
    lines.append("")
    lines.append("class ModelsPayloads:")
    lines.append('    """Request body builders (BaseRequestBody subclasses)."""')
    lines.append("")
    if payload_wiring:
        for _mod, class_name, attr in payload_wiring:
            lines.append(f"    {attr} = {class_name}")
    else:
        lines.append("    pass")
    lines.append("")
    lines.append("")
    lines.append("class ModelsPaths:")
    if path_attrs:
        for path, attr in sorted(path_attrs.items(), key=lambda x: x[1]):
            lines.append(f"    {attr} = paths.paths_{tag_s}.{attr}  # {path}")
    else:
        lines.append("    pass")
    lines.extend(
        [
            "",
            "",
            "class ModelsHeaders:",
            "    def __init__(self, token: Optional[str] = None):",
            "        cfg = configs.Config()",
            "        self._read = cfg.headers_bind([\"Accept\", \"X-Request-ID\"], token=token)",
            "        self._write = cfg.headers_bind(",
            "            [\"Accept\", \"Content-Type\", \"X-Request-ID\"], token=token",
            "        )",
            "",
            "    @property",
            "    def read(self):",
            "        return self._read.headers",
            "",
            "    @property",
            "    def write(self):",
            "        return self._write.headers",
            "",
            "    def apply_token(self, token: str) -> None:",
            "        self._read.apply_token(token)",
            "        self._write.apply_token(token)",
            "",
            "",
            f"class {cls}(BaseCollection):",
            f'    """Resources for tag `{tag_s}`."""',
            "",
            "    def __init__(self, token: Optional[str] = None):",
            "        self.validate = ModelsValidations()",
            "        self.payload = ModelsPayloads()",
            "        self.paths = ModelsPaths()",
            "        self.headers = ModelsHeaders(token)",
            "",
        ]
    )
    if ops_summary:
        lines.append("# OpenAPI operations:")
        for line in ops_summary:
            lines.append(f"#   {line}")
        lines.append("")
    return "\n".join(lines)


def build_collections_manager(tags: Sequence[str]) -> str:
    tags_s = [is_snake(t) for t in tags]
    lines: List[str] = [
        GENERATED_BANNER,
        '"""Unified access to entity collections."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Optional",
        "",
        "from partest.collections import CollectionsManager as _LibManager",
        "",
    ]
    for tag in tags_s:
        cls = collection_class_name(tag)
        lines.append(
            f"from src.api.resources.collections.collection_{tag} import {cls}"
        )
    lines.extend(
        [
            "",
            "",
            "class CollectionsManager(_LibManager):",
            '    """Session façade: ``models.items``, ``models.health``, …"""',
            "",
            "    def __init__(self, token: Optional[str] = None):",
            "        super().__init__(",
        ]
    )
    if not tags_s:
        lines.append("        )")
    else:
        for i, tag in enumerate(tags_s):
            cls = collection_class_name(tag)
            comma = "," if i < len(tags_s) - 1 else ","
            lines.append(f"            {tag}={cls}(token=token){comma}")
        lines.append("        )")
    lines.append("")
    return "\n".join(lines)


def build_collections_init(tags: Sequence[str]) -> str:
    tags_s = [is_snake(t) for t in tags]
    lines = [
        GENERATED_BANNER,
        '"""Collections package."""',
        "",
        "from src.api.resources.collections.collections_manager import CollectionsManager",
        "",
    ]
    for tag in tags_s:
        cls = collection_class_name(tag)
        lines.append(f"from src.api.resources.collections.collection_{tag} import {cls}")
    lines.append("")
    lines.append('__all__ = ["CollectionsManager",')
    for tag in tags_s:
        lines.append(f'    "{collection_class_name(tag)}",')
    lines.append("]")
    lines.append("")
    return "\n".join(lines)
