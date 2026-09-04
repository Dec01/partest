"""CLI: partest-gen (G1 skeleton + G2 resources)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Sequence


def _parse_entities(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    return [p for p in parts if p]


def _resolve_openapi(args: argparse.Namespace) -> Optional[str]:
    if getattr(args, "openapi", None):
        return args.openapi
    if getattr(args, "file", None):
        return args.file
    if getattr(args, "url", None):
        return args.url
    return None


def _print_result(result, *, verbose: bool) -> None:
    print(f"Project root: {result.root}")
    print(f"Created/updated: {len(result.created)}  Skipped: {len(result.skipped)}")
    if verbose:
        for p in result.created:
            print(f"  + {p}")
        for p in result.skipped:
            print(f"  = {p}")


def _cmd_init(args: argparse.Namespace) -> int:
    from partest.project_gen.skeleton import init_skeleton

    suite_ir = None
    openapi = _resolve_openapi(args)

    if openapi:
        from partest.project_gen.openapi_load import load_openapi

        suite_ir = load_openapi(openapi)
        print(
            f"Loaded OpenAPI: {suite_ir.title} "
            f"({len(suite_ir.operations)} ops, tags={suite_ir.tags()})"
        )

    result = init_skeleton(
        args.path,
        name=args.name or Path(args.path).name or "api-suite",
        with_ui=bool(getattr(args, "with_ui", False)),
        force=bool(args.force),
        openapi_source=None,
        suite_ir=suite_ir,
    )

    # copy local openapi into docs/
    if openapi and not str(openapi).startswith("http"):
        src = Path(openapi)
        if src.is_file():
            dest = Path(result.root) / "docs" / "openapi.yaml"
            if args.force or not dest.exists() or dest.stat().st_size < 500:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                rel = "docs/openapi.yaml (from --openapi)"
                if rel not in result.created:
                    result.created.append(rel)

    # G2/G3: emit paths + collections (+ payloads/tests)
    if suite_ir is not None:
        from partest.project_gen.emitters.resources import emit_resources

        entities = _parse_entities(getattr(args, "entities", None))
        depth = getattr(args, "depth", None) or "default"
        r2 = emit_resources(
            result.root,
            suite_ir,
            force=bool(args.force),
            tags_filter=entities,
            write_ir=True,
            depth=depth,
        )
        result.created.extend(r2.created)
        result.skipped.extend(r2.skipped)
        print(
            f"Resources (depth={depth}): {len(r2.created)} files "
            f"(tags={entities or suite_ir.tags()})"
        )

    _print_result(result, verbose=bool(args.verbose))
    print("Next: pip install -r requirements/api.txt && cp env.example .env")
    if suite_ir is not None:
        print("See .partest/openapi_summary.md for paths registry + P1 matrix")
    return 0


def _cmd_dump_ir(args: argparse.Namespace) -> int:
    from partest.project_gen.openapi_load import load_openapi

    ir = load_openapi(args.openapi)
    out = Path(args.out) if args.out else None
    payload = ir.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote IR: {out} ({len(ir.operations)} operations)")
    else:
        print(text)
    return 0


def _cmd_from_openapi(args: argparse.Namespace) -> int:
    """Skeleton (if needed) + G2/G3 resources from OpenAPI."""
    openapi = _resolve_openapi(args)
    if not openapi:
        print("error: provide --file or --url", file=sys.stderr)
        return 2

    args.openapi = openapi
    if not getattr(args, "name", None):
        args.name = Path(args.path).name or "api-suite"
    depth = getattr(args, "depth", None) or "default"
    print(f"from-openapi: skeleton + IR + resources (depth={depth})")
    return _cmd_init(args)


def _cmd_init_ui(args: argparse.Namespace) -> int:
    """Add / refresh G5 UI tree on an existing project."""
    from partest.project_gen.skeleton import apply_ui_layout

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"error: project path not found: {root}", file=sys.stderr)
        return 2
    name = args.name or root.name or "api-suite"
    result = apply_ui_layout(root, name=name, force=bool(args.force))
    print(f"G5 UI layout → {result.root}")
    _print_result(result, verbose=bool(args.verbose))
    print("Next: pip install -r requirements/ui.txt && playwright install chromium")
    print("Docs: docs/UI_GUIDE.md")
    return 0


def _cmd_init_package_exports(args: argparse.Namespace) -> int:
    """Generate recursive ``__init__.py`` re-exports (L1.11)."""
    from partest.tools.generate_init import generate_init_for_directory

    root = Path(args.directory).resolve()
    try:
        written = generate_init_for_directory(
            root,
            recursive=not bool(getattr(args, "no_recursive", False)),
        )
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"init-package-exports: wrote {len(written)} file(s) under {root}")
    if args.verbose:
        for p in written:
            print(f"  + {p}")
    return 0


def _cmd_sync_openapi(args: argparse.Namespace) -> int:
    """Refresh paths/collections/IR for an existing project (no full re-init)."""
    from partest.project_gen.emitters.resources import emit_resources
    from partest.project_gen.openapi_load import load_openapi
    from partest.project_gen.skeleton import WriteResult

    openapi = _resolve_openapi(args)
    root = Path(args.path).resolve()
    if not openapi:
        # try project docs
        candidate = root / "docs" / "openapi.yaml"
        if candidate.is_file():
            openapi = str(candidate)
        else:
            print(
                "error: provide --file/--url or place docs/openapi.yaml in project",
                file=sys.stderr,
            )
            return 2

    if not root.is_dir():
        print(f"error: project path not found: {root}", file=sys.stderr)
        return 2

    suite = load_openapi(openapi)
    print(
        f"Sync OpenAPI: {suite.title} ({len(suite.operations)} ops) → {root}"
    )

    # copy local openapi into docs if different
    if not str(openapi).startswith("http"):
        src = Path(openapi)
        if src.is_file():
            dest = root / "docs" / "openapi.yaml"
            dest.parent.mkdir(parents=True, exist_ok=True)
            if args.force or not dest.exists() or src.resolve() != dest.resolve():
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    entities = _parse_entities(getattr(args, "entities", None))
    depth = getattr(args, "depth", None) or "default"
    result = emit_resources(
        root,
        suite,
        force=bool(args.force),
        tags_filter=entities,
        write_ir=True,
        depth=depth,
    )
    # mark copy
    if (root / "docs" / "openapi.yaml").is_file():
        if "docs/openapi.yaml" not in result.created:
            # only note if we may have written
            pass

    _print_result(result, verbose=bool(args.verbose))
    print("Updated .partest/suite_ir.json and openapi_summary.md")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="partest-gen",
        description="Scaffold partest API suites (monorepo layout).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument(
            "--entities",
            default=None,
            help="Comma-separated tags to emit (default: all)",
        )
        p.add_argument(
            "--depth",
            default="default",
            choices=["resources", "default", "p1"],
            help=(
                "resources=G2 only; default=G3 payloads+Default/NotAllowed; "
                "p1=G4 full P1 matrix stubs"
            ),
        )
        p.add_argument("--force", action="store_true", help="Overwrite non-generated files too")
        p.add_argument("-v", "--verbose", action="store_true")

    p_init = sub.add_parser("init", help="Create monorepo skeleton (+ G2 if --openapi)")
    p_init.add_argument("path", help="Target directory")
    p_init.add_argument("--name", default="api-suite", help="Project / service name")
    p_init.add_argument(
        "--openapi",
        default=None,
        help="Optional OpenAPI file or URL — IR + G2 resources",
    )
    p_init.add_argument("--with-ui", action="store_true", help="Include src/ui skeleton")
    add_common(p_init)
    p_init.set_defaults(func=_cmd_init)

    p_ir = sub.add_parser("dump-ir", help="Parse OpenAPI to SuiteIR JSON")
    p_ir.add_argument("openapi", help="OpenAPI file path or URL")
    p_ir.add_argument("-o", "--out", default=None, help="Output JSON path")
    p_ir.set_defaults(func=_cmd_dump_ir)

    p_fo = sub.add_parser(
        "from-openapi",
        help="Skeleton + IR + G2 paths/collections from OpenAPI",
    )
    p_fo.add_argument("path", help="Target project directory")
    p_fo.add_argument("--name", default=None, help="Project name (default: dir name)")
    p_fo.add_argument("--file", default=None, help="Local OpenAPI path")
    p_fo.add_argument("--url", default=None, help="OpenAPI URL")
    p_fo.add_argument("--with-ui", action="store_true")
    add_common(p_fo)
    p_fo.set_defaults(func=_cmd_from_openapi)

    p_ui = sub.add_parser(
        "init-ui",
        help="G5: add deep UI monorepo tree (isolated from API session)",
    )
    p_ui.add_argument("path", help="Existing project directory")
    p_ui.add_argument("--name", default=None, help="Project name for docs")
    p_ui.add_argument("--force", action="store_true")
    p_ui.add_argument("-v", "--verbose", action="store_true")
    p_ui.set_defaults(func=_cmd_init_ui)

    p_sync = sub.add_parser(
        "sync-openapi",
        help="Refresh paths/collections/IR in existing project (G2)",
    )
    p_sync.add_argument("path", help="Existing project directory")
    p_sync.add_argument("--file", default=None, help="Local OpenAPI path")
    p_sync.add_argument("--url", default=None, help="OpenAPI URL")
    p_sync.add_argument(
        "--openapi",
        default=None,
        help="Alias for --file/--url",
    )
    add_common(p_sync)
    p_sync.set_defaults(func=_cmd_sync_openapi)

    p_init_pkg = sub.add_parser(
        "init-package-exports",
        help="Generate recursive __init__.py re-exports (from .mod import *)",
    )
    p_init_pkg.add_argument(
        "directory",
        help="Package root to scan (e.g. src/api/resources)",
    )
    p_init_pkg.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only top-level directory",
    )
    p_init_pkg.add_argument("-v", "--verbose", action="store_true")
    p_init_pkg.set_defaults(func=_cmd_init_package_exports)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
