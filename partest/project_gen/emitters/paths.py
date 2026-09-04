"""Emit src/api/resources/endpoints/paths.py from SuiteIR."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Set

from partest.project_gen.emitters.util import (
    GENERATED_BANNER,
    class_name,
    is_snake,
    path_to_attr,
)
from partest.project_gen.ir import OpIR, SuiteIR


def _unique_attr(preferred: str, used: Set[str]) -> str:
    name = preferred
    n = 2
    while name in used:
        name = f"{preferred}_{n}"
        n += 1
    used.add(name)
    return name


def build_paths_module(
    suite: SuiteIR,
    *,
    tags_filter: Optional[Sequence[str]] = None,
) -> str:
    """Return full Python source for paths.py."""
    allowed = {is_snake(t) for t in tags_filter} if tags_filter else None
    by_tag: Dict[str, List[OpIR]] = defaultdict(list)
    for op in suite.operations:
        if op.deprecated:
            continue
        tag = is_snake(op.tag)
        if allowed is not None and tag not in allowed:
            continue
        by_tag[tag].append(op)

    lines: List[str] = [
        GENERATED_BANNER,
        '"""OpenAPI path constants grouped by tag."""',
        "",
        "from typing import Optional",
        "",
        "",
        "class PathsBase:",
        '    """Lookup helper: paths.get_path(\'paths_items\', \'items\')."""',
        "",
        "    def get_path(self, service: str, endpoint: str) -> Optional[str]:",
        "        svc = getattr(self, service, None)",
        "        if svc is None:",
        "            return None",
        "        return getattr(svc, endpoint, None)",
        "",
    ]

    tag_class_names: Dict[str, str] = {}
    # per-tag path attrs for collections emitter
    tag_path_attrs: Dict[str, Dict[str, str]] = {}

    for tag in sorted(by_tag.keys()):
        ops = by_tag[tag]
        cls = class_name(tag, "Paths")
        tag_class_names[tag] = cls
        used: Set[str] = set()
        # unique paths -> attr
        path_map: Dict[str, str] = {}
        for op in ops:
            if op.path not in path_map:
                path_map[op.path] = _unique_attr(path_to_attr(op.path), used)

        tag_path_attrs[tag] = dict(path_map)

        lines.append(f"class {cls}(PathsBase):")
        lines.append(f'    """Paths for tag `{tag}` ({len(path_map)} templates)."""')
        lines.append("")
        lines.append("    def __init__(self):")
        if not path_map:
            lines.append("        pass")
        else:
            for path, attr in sorted(path_map.items(), key=lambda x: x[1]):
                lines.append(f'        self.{attr} = "{path}"')
        lines.append("")
        # also document methods as comments
        lines.append("    # operations:")
        for op in sorted(ops, key=lambda o: (o.path, o.method)):
            lines.append(
                f"    #   {op.method:6} {op.path}  subtype={op.subtype}  id={op.operation_id}"
            )
        lines.append("")
        lines.append("")

    lines.append("class Paths(PathsBase):")
    lines.append('    """Root registry: ``paths.paths_<tag>.<attr>``."""')
    lines.append("")
    lines.append("    def __init__(self):")
    if not tag_class_names:
        lines.append("        pass")
    else:
        for tag, cls in sorted(tag_class_names.items()):
            lines.append(f"        self.paths_{tag} = {cls}()")
    lines.append("")
    lines.append("")
    lines.append("paths = Paths()")
    lines.append("")

    return "\n".join(lines), tag_path_attrs


def build_paths_module_source(
    suite: SuiteIR,
    *,
    tags_filter: Optional[Sequence[str]] = None,
) -> str:
    source, _ = build_paths_module(suite, tags_filter=tags_filter)
    return source


def get_tag_path_attrs(
    suite: SuiteIR,
    *,
    tags_filter: Optional[Sequence[str]] = None,
) -> Dict[str, Dict[str, str]]:
    _, attrs = build_paths_module(suite, tags_filter=tags_filter)
    return attrs
