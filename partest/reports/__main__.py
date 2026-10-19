"""Coverage report CLI.

  python -m partest.reports render --json coverage.json --html coverage_report.html
  python -m partest.reports compare --a old.json --b new.json
  python -m partest.reports badge --json coverage.json --out coverage.svg
  python -m partest.reports stubs --json coverage.json --out coverage_stubs.py
  python -m partest.reports history-append --json coverage.json --dir coverage_history
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from partest.reports._rules import json_safe
from partest.reports.badge import badge_from_payload
from partest.reports.compare import compare_payloads
from partest.reports.history import append_snapshot
from partest.reports.interactive_html import render_html
from partest.reports.stubs import generate_stubs


class _InputError(Exception):
    """A file the command cannot read as a coverage.json document."""


def _load(path: str) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise _InputError(f"{path}: cannot read ({exc.strerror or exc})") from None
    except (ValueError, RecursionError) as exc:
        reason = "nested too deep" if isinstance(exc, RecursionError) else str(exc)
        raise _InputError(f"{path}: not JSON ({reason})") from None
    if not isinstance(doc, dict):
        raise _InputError(f"{path}: a coverage.json is a JSON object, this is {type(doc).__name__}")
    return doc


def _write(path: str, text: str) -> None:
    try:
        Path(path).write_text(text, encoding="utf-8")
    except OSError as exc:
        raise _InputError(f"{path}: cannot write ({exc.strerror or exc})") from None


def _rows_of(doc: dict, path: str) -> list:
    """``endpoints`` as a list of objects, or an input error naming what is wrong."""
    endpoints = doc.get("endpoints")
    if not isinstance(endpoints, list):
        raise _InputError(f"{path}: 'endpoints' is not a list")
    if not all(isinstance(ep, dict) for ep in endpoints):
        raise _InputError(f"{path}: 'endpoints' holds something that is not an object")
    return endpoints


def _snapshot_of(path: str) -> dict:
    """A document fit for the history: endpoints of objects, ``meta`` and ``summary``
    objects. A snapshot of something else would be compared against the next run."""
    doc = _load(path)
    _rows_of(doc, path)
    for key in ("meta", "summary"):
        if not isinstance(doc.get(key), dict):
            raise _InputError(f"{path}: '{key}' is not an object")
    return doc


def _cmd_render(args: argparse.Namespace) -> int:
    payload = _load(args.json_path)
    meta = payload.get("meta")
    title = meta.get("title") if isinstance(meta, dict) else None
    title = title if isinstance(title, str) and title else "partest API coverage"
    try:
        page = render_html(payload, title=title)
    except RecursionError:
        raise _InputError(f"{args.json_path}: nested too deep to render") from None
    _write(args.html_path, page)
    print(f"wrote {args.html_path}")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    diff = compare_payloads(_load(args.a), _load(args.b))
    text = json.dumps(diff, ensure_ascii=False, indent=2)
    if args.out:
        _write(args.out, text)
        print(f"wrote {args.out}")
    else:
        print(text)
    # Warnings go to stderr so piping the JSON stays clean, but a human comparing a
    # partial or unmerged run still sees why the delta may mean nothing.
    for warning in diff.get("warnings") or []:
        print(f"warning: {warning}", file=sys.stderr)
    for note in diff.get("notes") or []:
        print(f"note: {note}", file=sys.stderr)
    if args.strict and not diff.get("comparable", True):
        return 2
    return 0


def _cmd_badge(args: argparse.Namespace) -> int:
    svg = badge_from_payload(_load(args.json_path), label=args.label)
    _write(args.out, svg)
    print(f"wrote {args.out}")
    return 0


def _cmd_stubs(args: argparse.Namespace) -> int:
    doc = _load(args.json_path)
    _rows_of(doc, args.json_path)
    src = generate_stubs(doc)
    _write(args.out, src)
    print(f"wrote {args.out}")
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    try:
        # `NaN` / `Infinity` from the input are not written back as bare tokens.
        doc = json_safe(_snapshot_of(args.json_path))
    except RecursionError:
        raise _InputError(f"{args.json_path}: nested too deep to store") from None
    try:
        path = append_snapshot(doc, args.dir)
    except OSError as exc:
        raise _InputError(f"{args.dir}: cannot write ({exc.strerror or exc})") from None
    print(f"wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="partest coverage report extras")
    sub = parser.add_subparsers(dest="cmd")

    p_render = sub.add_parser("render", help="HTML from coverage.json")
    p_render.add_argument("--json", dest="json_path", default="coverage.json")
    p_render.add_argument("--html", dest="html_path", default="coverage_report.html")
    p_render.set_defaults(func=_cmd_render)

    p_cmp = sub.add_parser("compare", help="diff two coverage.json")
    p_cmp.add_argument("--a", required=True)
    p_cmp.add_argument("--b", required=True)
    p_cmp.add_argument("--out", default="")
    p_cmp.add_argument(
        "--strict",
        action="store_true",
        help="exit 2 when the two runs are not comparable — any entry in 'warnings', for "
        "example: a partial, unmerged or subset run, different opt-in sets, endpoints covered "
        "before and not called now, a collapse in call volume, a run with no average, an "
        "averaging rule this package does not know, an older average that cannot be "
        "recomputed from its rows",
    )
    p_cmp.set_defaults(func=_cmd_compare)

    p_badge = sub.add_parser("badge", help="SVG badge from coverage.json")
    p_badge.add_argument("--json", dest="json_path", default="coverage.json")
    p_badge.add_argument("--out", default="coverage.svg")
    p_badge.add_argument("--label", default="coverage")
    p_badge.set_defaults(func=_cmd_badge)

    p_stubs = sub.add_parser("stubs", help="pytest stubs for missing P1")
    p_stubs.add_argument("--json", dest="json_path", default="coverage.json")
    p_stubs.add_argument("--out", default="coverage_stubs.py")
    p_stubs.set_defaults(func=_cmd_stubs)

    p_hist = sub.add_parser("history-append", help="append snapshot to a directory")
    p_hist.add_argument("--json", dest="json_path", default="coverage.json")
    p_hist.add_argument("--dir", default="coverage_history")
    p_hist.set_defaults(func=_cmd_history)

    parser.add_argument("--json", dest="legacy_json", default=None)
    parser.add_argument("--html", dest="legacy_html", default=None)

    args = parser.parse_args(argv)
    try:
        if args.cmd:
            return args.func(args)
        json_path = args.legacy_json or "coverage.json"
        html_path = args.legacy_html or "coverage_report.html"
        return _cmd_render(argparse.Namespace(json_path=json_path, html_path=html_path))
    except _InputError as exc:
        # 1 — the input could not be used; 2 stays what `compare --strict` means: not
        # comparable.
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
