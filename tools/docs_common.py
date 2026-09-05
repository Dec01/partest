"""Shared helpers for the documentation tools.

Frontmatter parsing, page discovery and the ships-in-wheel selection live here so that
``docs_lint``, ``docs_index`` and ``docs_build_wheel`` cannot disagree about them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = REPO_ROOT / "docs" / "wiki"
RAW_DIR = REPO_ROOT / "docs" / "raw"
WHEEL_DOCS_DIR = REPO_ROOT / "partest" / "docs"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)\]\]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

REQUIRED_FIELDS = ("title", "status", "verified", "sources", "audience", "ships_in_wheel")
VALID_STATUS = {"current", "draft", "stale", "archived"}
VALID_AUDIENCE = {"user", "maintainer", "agent"}


@dataclass
class Page:
    """One wiki page: frontmatter plus body."""

    path: Path
    meta: Dict[str, Any]
    body: str
    errors: List[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        """Path relative to the wiki root without extension, e.g. ``howto/quickstart``."""
        return self.path.relative_to(WIKI_DIR).with_suffix("").as_posix()

    @property
    def rel(self) -> str:
        return self.path.relative_to(REPO_ROOT).as_posix()

    @property
    def ships(self) -> bool:
        return bool(self.meta.get("ships_in_wheel"))

    @property
    def verified(self) -> Optional[date]:
        value = self.meta.get("verified")
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip())
            except ValueError:
                return None
        return None

    @property
    def sources(self) -> List[str]:
        value = self.meta.get("sources") or []
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value]

    @property
    def headings(self) -> List[Dict[str, Any]]:
        return [
            {"level": len(m.group(1)), "text": m.group(2)}
            for m in HEADING_RE.finditer(self.body)
        ]

    def wheel_name(self) -> str:
        """Flat file name used inside the wheel, e.g. ``howto-quickstart.md``."""
        return self.slug.replace("/", "-") + ".md"


def parse_page(path: Path) -> Page:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return Page(path=path, meta={}, body=text, errors=["missing frontmatter"])
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - malformed frontmatter is rare
        return Page(path=path, meta={}, body=text[match.end():], errors=[f"bad frontmatter: {exc}"])
    if not isinstance(meta, dict):
        return Page(path=path, meta={}, body=text[match.end():], errors=["frontmatter is not a mapping"])
    return Page(path=path, meta=meta, body=text[match.end():])


def load_pages() -> List[Page]:
    return [parse_page(p) for p in sorted(WIKI_DIR.rglob("*.md"))]


def wheel_pages(pages: List[Page]) -> List[Page]:
    return [p for p in pages if p.ships]


def render_for_wheel(page: Page, pages: List[Page]) -> str:
    """Strip frontmatter, expand wiki links to flat wheel file names, add a banner."""
    by_slug = {p.slug: p for p in pages}

    def replace(match: "re.Match[str]") -> str:
        slug = match.group(1).strip()
        target = by_slug.get(slug)
        if target is None or not target.ships:
            # Page not shipped: keep the human-readable title, drop the link.
            return (target.meta.get("title") if target else slug) or slug
        return f"[{target.meta.get('title', slug)}]({target.wheel_name()})"

    body = WIKI_LINK_RE.sub(replace, page.body).lstrip("\n")
    # This banner reaches every user of the package, so it describes what the file is
    # rather than pointing at repository paths they do not have.
    banner = (
        "<!-- Part of the partest package: generated documentation, not hand-written.\n"
        "     Read it with `python -m partest.docs`. Local edits are lost on upgrade. -->\n\n"
    )
    return banner + body
