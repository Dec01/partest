"""Read the documentation shipped inside the installed package.

    python -m partest.docs list
    python -m partest.docs show howto-quickstart
    python -m partest.docs path
"""

from __future__ import annotations

import argparse
import sys

from partest.docs import docs_path, list_docs, read_doc


def _title(name: str) -> str:
    """First markdown heading of a shipped doc, for the listing."""
    for line in read_doc(name).splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m partest.docs", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list", help="list shipped documents")
    show = sub.add_parser("show", help="print one document")
    show.add_argument("name", help="document name, with or without .md")
    sub.add_parser("path", help="print the directory holding the documents")

    args = parser.parse_args(argv)
    command = args.command or "list"

    if command == "list":
        names = list_docs()
        if not names:
            print("no documents in this build", file=sys.stderr)
            return 1
        width = max(len(n) for n in names)
        for name in names:
            print(f"{name:<{width}}  {_title(name)}")
        return 0

    if command == "show":
        try:
            print(read_doc(args.name))
        except FileNotFoundError:
            print(f"unknown document: {args.name}", file=sys.stderr)
            print("available: " + ", ".join(list_docs()), file=sys.stderr)
            return 1
        return 0

    print(docs_path())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
