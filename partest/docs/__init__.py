"""Documentation shipped inside the installed package.

The wheel carries its own docs, so they are readable next to an installed copy without a
trip to the browser. Files here are generated from the project wiki by
``tools/docs_build_wheel.py`` — do not edit them by hand.

Access from Python::

    from partest.docs import list_docs, read_doc
    print(read_doc("howto-quickstart.md")[:200])

Or from the command line::

    python -m partest.docs list
    python -m partest.docs show howto-quickstart
    python -m partest.docs path
"""

from __future__ import annotations

from importlib import resources
from typing import List


def list_docs() -> List[str]:
    root = resources.files(__name__)
    return sorted(p.name for p in root.iterdir() if p.name.endswith(".md"))


def read_doc(name: str) -> str:
    """Read a shipped markdown doc by file name, with or without the ``.md`` suffix."""
    if not name.endswith(".md"):
        name = name + ".md"
    path = resources.files(__name__).joinpath(name)
    return path.read_text(encoding="utf-8")


def docs_path() -> str:
    """Filesystem location of the shipped docs, for opening them in an editor."""
    return str(resources.files(__name__))
