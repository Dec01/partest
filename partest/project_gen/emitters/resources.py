"""Orchestrate G2–G3 emission: paths, collections, payloads, validations, tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Sequence, Union

from partest.project_gen.emitters.collections import (
    build_collection_module,
    build_collections_init,
    build_collections_manager,
)
from partest.project_gen.emitters.paths import build_paths_module
from partest.project_gen.emitters.payloads import build_payload_files, payload_wiring
from partest.project_gen.emitters.tests_default import build_test_files
from partest.project_gen.emitters.tests_p1 import build_p1_test_files
from partest.project_gen.emitters.util import GENERATED_BANNER, is_snake
from partest.project_gen.emitters.validations import (
    build_validation_files,
    validation_wiring,
)
from partest.project_gen.ir import SuiteIR
from partest.project_gen.skeleton import WriteResult

# depth: resources=G2, default=G3, p1=G4 full P1 stubs
DEPTH_RESOURCES = "resources"
DEPTH_DEFAULT = "default"
DEPTH_P1 = "p1"


def _filter_tags(suite: SuiteIR, tags_filter: Optional[Sequence[str]]) -> List[str]:
    all_tags = suite.tags()
    if not tags_filter:
        return list(all_tags)
    allow = {is_snake(t) for t in tags_filter}
    return [t for t in all_tags if is_snake(t) in allow]


def emit_resources(
    project_root: Union[str, Path],
    suite: SuiteIR,
    *,
    force: bool = False,
    tags_filter: Optional[Sequence[str]] = None,
    write_ir: bool = True,
    depth: str = DEPTH_DEFAULT,
) -> WriteResult:
    """Write G2 (+ G3 when depth is default/p1) artifacts."""
    root = Path(project_root).resolve()
    result = WriteResult(root=str(root))
    tags = _filter_tags(suite, tags_filter)
    depth = (depth or DEPTH_DEFAULT).lower()
    include_g3 = depth in {DEPTH_DEFAULT, DEPTH_P1, "g3", "full"}
    include_g4 = depth in {DEPTH_P1, "full", "g4"}

    paths_src, tag_attrs = build_paths_module(suite, tags_filter=tags)
    _emit_generated(
        root,
        "src/api/resources/endpoints/paths.py",
        paths_src,
        force=force,
        result=result,
    )

    endpoints_init = (
        GENERATED_BANNER
        + '"""Endpoints package."""\n\n'
        + "from src.api.resources.endpoints.paths import paths\n"
        + "from src.api.resources.endpoints import configs\n\n"
        + '__all__ = ["paths", "configs"]\n'
    )
    _emit_generated(
        root,
        "src/api/resources/endpoints/__init__.py",
        endpoints_init,
        force=force,
        result=result,
    )

    p_wire = payload_wiring(suite, tags_filter=tags) if include_g3 else {}
    v_wire = validation_wiring(suite, tags_filter=tags) if include_g3 else {}

    if include_g3:
        for rel, src in build_payload_files(suite, tags_filter=tags).items():
            _emit_generated(root, rel, src, force=force, result=result)
        for rel, src in build_validation_files(suite, tags_filter=tags).items():
            _emit_generated(root, rel, src, force=force, result=result)

    for tag in tags:
        path_attrs = tag_attrs.get(is_snake(tag), {})
        ops = [o for o in suite.operations if is_snake(o.tag) == is_snake(tag)]
        ops_summary = [
            (
                f"{o.method} {o.path}  [{o.subtype}]  p1={','.join(o.required_p1[:4])}…"
                if len(o.required_p1) > 4
                else f"{o.method} {o.path}  [{o.subtype}]  p1={','.join(o.required_p1) or '—'}"
            )
            for o in ops
        ]
        src = build_collection_module(
            tag,
            path_attrs,
            ops_summary=ops_summary,
            payload_wiring=p_wire.get(is_snake(tag)),
            validation_wiring=v_wire.get(is_snake(tag)),
        )
        _emit_generated(
            root,
            f"src/api/resources/collections/collection_{is_snake(tag)}.py",
            src,
            force=force,
            result=result,
        )

    _emit_generated(
        root,
        "src/api/resources/collections/collections_manager.py",
        build_collections_manager(tags),
        force=force,
        result=result,
    )
    _emit_generated(
        root,
        "src/api/resources/collections/__init__.py",
        build_collections_init(tags),
        force=force,
        result=result,
    )

    models_fixture = (
        GENERATED_BANNER
        + '"""Factory for CollectionsManager (import in tests conftest)."""\n\n'
        + "from src.api.resources.collections import CollectionsManager\n\n\n"
        + "def build_models(token: str | None = None) -> CollectionsManager:\n"
        + "    return CollectionsManager(token=token)\n"
    )
    _emit_generated(
        root,
        "src/api/resources/collections/factory.py",
        models_fixture,
        force=force,
        result=result,
    )

    if include_g3:
        for rel, src in build_test_files(
            suite, tag_attrs, tags_filter=tags
        ).items():
            _emit_generated(root, rel, src, force=force, result=result)

    if include_g4:
        for rel, src in build_p1_test_files(
            suite, tag_attrs, tags_filter=tags
        ).items():
            _emit_generated(root, rel, src, force=force, result=result)

    if write_ir:
        _write_ir_summary(
            root,
            suite,
            tags,
            tag_attrs,
            result,
            include_g3=include_g3,
            include_g4=include_g4,
            depth=depth,
        )

    return result


def _write_ir_summary(
    root, suite, tags, tag_attrs, result, *, include_g3: bool, include_g4: bool = False, depth: str = "default"
):
    ir_dir = root / ".partest"
    ir_dir.mkdir(parents=True, exist_ok=True)
    ir_path = ir_dir / "suite_ir.json"
    ir_path.write_text(
        json.dumps(suite.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    rel = ".partest/suite_ir.json"
    if rel not in result.created:
        result.created.append(rel)

    summary_lines = [
        f"# OpenAPI IR summary — {suite.title}",
        "",
        f"- version: `{suite.version}`",
        f"- openapi: `{suite.openapi_version}`",
        f"- source: `{suite.source}`",
        f"- operations: **{len(suite.operations)}**",
        f"- tags emitted: {', '.join(tags) or '—'}",
        f"- depth: `{depth}` "
        f"({'G4 P1' if include_g4 else 'G3 default' if include_g3 else 'G2 resources'})",
        "",
        "## Paths registry",
        "",
        "```text",
    ]
    for tag in tags:
        summary_lines.append(f"paths.paths_{is_snake(tag)}")
        for path, attr in sorted(
            tag_attrs.get(is_snake(tag), {}).items(), key=lambda x: x[1]
        ):
            summary_lines.append(f"  .{attr} = {path}")
    summary_lines.extend(
        [
            "```",
            "",
            "## Operations",
            "",
            "| Method | Path | Tag | Subtype | P1 TC | Body |",
            "|--------|------|-----|---------|-------|------|",
        ]
    )
    for op in suite.operations:
        if tags and is_snake(op.tag) not in {is_snake(t) for t in tags}:
            continue
        p1 = ", ".join(op.required_p1) if op.required_p1 else "—"
        body = "yes" if op.has_request_body else "—"
        summary_lines.append(
            f"| {op.method} | `{op.path}` | {op.tag} | `{op.subtype}` | {p1} | {body} |"
        )
    summary_lines.extend(["", "## Collections", ""])
    for tag in tags:
        summary_lines.append(
            f"- `src/api/resources/collections/collection_{is_snake(tag)}.py`"
        )
    if include_g3:
        summary_lines.extend(
            [
                "",
                "## G3 artifacts",
                "",
                "- payloads: `src/api/resources/payloads/<tag>/`",
                "- validations: `src/api/resources/validations/<tag>/`",
                "- tests: `test_*_default.py`, `test_*_not_allowed.py`",
                "",
            ]
        )
    if include_g4:
        summary_lines.extend(
            [
                "## G4 P1 stubs",
                "",
                "- per-TC files: permissions, new_object, update_object, incorrect_body,",
                "  elements, extra_data, not_found, benchmark, params, …",
                "- checklist: `src/api/tests/<tag>/P1_CHECKLIST.md`",
                "",
                "Next: fill skips, roles, seeds; run zorro for missing P1.",
                "",
            ]
        )
    elif include_g3:
        summary_lines.extend(
            [
                "Next: `partest-gen sync-openapi … --depth p1` for full P1 stubs.",
                "",
            ]
        )
    else:
        summary_lines.extend(
            [
                "",
                "Next: `partest-gen sync-openapi … --depth default` for G3.",
                "",
            ]
        )
    (ir_dir / "openapi_summary.md").write_text(
        "\n".join(summary_lines), encoding="utf-8"
    )
    rel_s = ".partest/openapi_summary.md"
    if rel_s not in result.created:
        result.created.append(rel_s)


def _emit_generated(
    root: Path,
    rel: str,
    content: str,
    *,
    force: bool,
    result: WriteResult,
) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    rel_n = rel.replace("\\", "/")
    banner_mark = GENERATED_BANNER.split("\n")[0]

    if path.exists() and not force:
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        if banner_mark not in existing:
            result.skipped.append(rel_n)
            return

    path.write_text(content, encoding="utf-8", newline="\n")
    if rel_n not in result.created:
        result.created.append(rel_n)
