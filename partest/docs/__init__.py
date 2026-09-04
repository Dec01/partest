"""Installable documentation (LIB-12).

Access::

    from partest.docs import read_doc, list_docs
    print(read_doc(\"QUICKSTART.md\")[:200])
"""
from __future__ import annotations

from importlib import resources
from typing import List


def list_docs() -> List[str]:
    root = resources.files(__name__)
    return sorted(p.name for p in root.iterdir() if p.name.endswith(".md"))


def read_doc(name: str) -> str:
    """Read a shipped markdown doc by filename (e.g. ``QUICKSTART.md``)."""
    path = resources.files(__name__).joinpath(name)
    return path.read_text(encoding="utf-8")
