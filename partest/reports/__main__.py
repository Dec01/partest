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

from partest.reports.badge import badge_from_payload
from partest.reports.compare import compare_payloads
from partest.reports.history import append_snapshot
from partest.reports.interactive_html import render_html
from partest.reports.stubs import generate_stubs


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _cmd_render(args: argparse.Namespace) -> int:
    payload = _load(args.json_path)
    title = (payload.get("meta") or {}).get("title") or "partest API coverage"
    Path(args.html_path).write_text(render_html(payload, title=title), encoding="utf-8")
    print(f"wrote {args.html_path}")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    diff = compare_payloads(_load(args.a), _load(args.b))
    text = json.dumps(diff, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    # Warnings go to stderr so piping the JSON stays clean, but a human comparing a
    # partial or unmerged run still sees why the delta may mean nothing.
    for warning in diff.get("warnings") or []:
        print(f"warning: {warning}", file=sys.stderr)
    if args.strict and not diff.get("comparable", True):
        return 2
    return 0


def _cmd_badge(args: argparse.Namespace) -> int:
    svg = badge_from_payload(_load(args.json_path), label=args.label)
    Path(args.out).write_text(svg, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


def _cmd_stubs(args: argparse.Namespace) -> int:
    src = generate_stubs(_load(args.json_path))
    Path(args.out).write_text(src, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    path = append_snapshot(_load(args.json_path), args.dir)
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
        help="exit 2 when the two runs are not comparable (partial or unmerged)",
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
    if args.cmd:
        return args.func(args)
    json_path = args.legacy_json or "coverage.json"
    html_path = args.legacy_html or "coverage_report.html"
    return _cmd_render(argparse.Namespace(json_path=json_path, html_path=html_path))


if __name__ == "__main__":
    raise SystemExit(main())
