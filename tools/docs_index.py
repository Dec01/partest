"""Build the machine-readable documentation index.

Emits ``docs/wiki/index.json``: one record per wiki page plus heading-level chunks for every
raw source. Two consumers:

* today — deterministic lookup (which page owns a topic, which pages depend on a code file);
* later — a vector index, if the corpus ever outgrows grep. See ``docs/wiki/WIKI.md`` for the
  criteria; this file is the reason enabling RAG stays a small change.

Usage::

    python tools/docs_index.py            # write the index
    python tools/docs_index.py --check    # fail if the index is out of date
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from docs_common import (  # type: ignore[import-not-found]
    HEADING_RE,
    RAW_DIR,
    REPO_ROOT,
    WIKI_DIR,
    load_pages,
)

INDEX_PATH = WIKI_DIR / "index.json"


def chunk_raw(path: Path) -> List[Dict[str, Any]]:
    """Split a raw source into heading-bounded chunks (RAG-ready, no embeddings today)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    marks = [(m.start(), len(m.group(1)), m.group(2)) for m in HEADING_RE.finditer(text)]
    if not marks:
        return [{"heading": None, "level": 0, "start": 0, "chars": len(text)}]
    chunks = []
    for i, (start, level, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        chunks.append({"heading": title, "level": level, "start": start, "chars": end - start})
    return chunks


def build() -> Dict[str, Any]:
    pages = []
    for page in load_pages():
        pages.append(
            {
                "slug": page.slug,
                "path": page.rel,
                "title": page.meta.get("title"),
                "status": page.meta.get("status"),
                "verified": str(page.meta.get("verified", "")),
                "audience": page.meta.get("audience"),
                "ships_in_wheel": page.ships,
                "sources": page.sources,
                "headings": page.headings,
                "chars": len(page.body),
            }
        )

    raw = []
    if RAW_DIR.exists():
        for path in sorted(RAW_DIR.rglob("*.md")):
            raw.append(
                {
                    "path": path.relative_to(REPO_ROOT).as_posix(),
                    "chars": path.stat().st_size,
                    "chunks": chunk_raw(path),
                }
            )

    # Reverse map: code file -> pages that claim to describe it.
    by_source: Dict[str, List[str]] = {}
    for record in pages:
        for source in record["sources"]:
            by_source.setdefault(source, []).append(record["slug"])

    return {
        "generated_by": "tools/docs_index.py",
        "pages": pages,
        "raw": raw,
        "pages_by_source": {k: sorted(v) for k, v in sorted(by_source.items())},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail instead of writing")
    args = parser.parse_args()

    payload = json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=False) + "\n"

    if args.check:
        current = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
        if current != payload:
            print("docs_index: index.json is out of date — run tools/docs_index.py")
            return 1
        print("docs_index: up to date")
        return 0

    INDEX_PATH.write_text(payload, encoding="utf-8")
    data = json.loads(payload)
    print(f"docs_index: {len(data['pages'])} pages, {len(data['raw'])} raw sources → {INDEX_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
