"""Lint the documentation wiki.

Catches the failure modes that made the previous documentation set rot:
duplicated status, stale pages, broken cross-references, version literals copied by hand,
private data leaking into the PyPI wheel, and drift between the wiki and generated docs.

Usage::

    python tools/docs_lint.py            # report findings
    python tools/docs_lint.py --strict   # exit non-zero if anything was found
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from docs_common import (  # type: ignore[import-not-found]
    REPO_ROOT,
    REQUIRED_FIELDS,
    VALID_AUDIENCE,
    VALID_STATUS,
    WHEEL_DOCS_DIR,
    WIKI_LINK_RE,
    Page,
    load_pages,
    render_for_wheel,
    wheel_pages,
)

VERSION_RE = re.compile(r"\b\d+\.\d+\.\d+\b")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+\.md)[^)]*\)")

# Consumer-project identifiers that are real code and may stay in public docs.
ALLOWED_AQA_IDENTIFIERS = (
    "aqa_name", "aqa_code", "aqa_short", "aqa_fill", "aqa_prefixed",
    "_aqa_monitor", "aqa_*",
)
PRIVATE_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("windows absolute path", re.compile(r"\b[A-Za-z]:\\\\?[\w.]")),
    ("UNC path", re.compile(r"(?<![\w`])\\\\[A-Za-z0-9_.-]+\\")),
    ("home directory", re.compile(r"/home/[a-z]|/Users/[A-Za-z]")),
)


def _private_names():
    """Organisation or project names that must not appear in published pages.

    Deliberately not hardcoded: this repository is public, so a literal list here would
    publish the very names it exists to catch. Supply them per checkout — one per line in
    a git-ignored ``.private-names`` file, or comma-separated in ``PARTEST_PRIVATE_NAMES``.
    """
    raw = [part.strip() for part in os.getenv("PARTEST_PRIVATE_NAMES", "").split(",") if part.strip()]
    names_file = REPO_ROOT / ".private-names"
    if names_file.is_file():
        raw += [
            line.strip()
            for line in names_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
    return [re.compile(re.escape(name), re.IGNORECASE) for name in raw]


class Findings:
    def __init__(self) -> None:
        self.items: List[Tuple[str, str, str]] = []

    def add(self, severity: str, where: str, message: str) -> None:
        self.items.append((severity, where, message))

    @property
    def errors(self) -> List[Tuple[str, str, str]]:
        return [i for i in self.items if i[0] == "ERROR"]

    def report(self) -> None:
        if not self.items:
            print("docs_lint: clean")
            return
        for severity, where, message in self.items:
            print(f"{severity:5}  {where}: {message}")
        print(f"\n{len(self.errors)} error(s), {len(self.items) - len(self.errors)} warning(s)")


def git_last_change(path: Path) -> Optional[date]:
    """Date of the last commit touching *path*, or None when git cannot answer."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(path)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    stamp = out.stdout.strip()
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp).date()
    except ValueError:
        return None


def strip_code_and_frontmatter(body: str) -> str:
    """Remove fenced code blocks so prose checks do not fire on examples."""
    return re.sub(r"```.*?```", "", body, flags=re.DOTALL)


def check_frontmatter(page: Page, f: Findings) -> None:
    for err in page.errors:
        f.add("ERROR", page.rel, err)
    if not page.meta:
        return
    for field_name in REQUIRED_FIELDS:
        if field_name not in page.meta:
            f.add("ERROR", page.rel, f"frontmatter missing '{field_name}'")
    status = page.meta.get("status")
    if status is not None and status not in VALID_STATUS:
        f.add("ERROR", page.rel, f"status '{status}' not in {sorted(VALID_STATUS)}")
    audience = page.meta.get("audience")
    if audience is not None and audience not in VALID_AUDIENCE:
        f.add("ERROR", page.rel, f"audience '{audience}' not in {sorted(VALID_AUDIENCE)}")
    if "verified" in page.meta and page.verified is None:
        f.add("ERROR", page.rel, "verified is not an ISO date (YYYY-MM-DD)")


def check_sources(page: Page, f: Findings) -> None:
    if page.verified is None:
        return
    for source in page.sources:
        target = REPO_ROOT / source
        if not target.exists():
            f.add("ERROR", page.rel, f"sources: '{source}' does not exist")
            continue
        changed = git_last_change(target)
        if changed and changed > page.verified:
            f.add(
                "WARN", page.rel,
                f"stale: {source} changed {changed}, page verified {page.verified}",
            )


def check_links(page: Page, slugs: Dict[str, Page], f: Findings) -> None:
    for match in WIKI_LINK_RE.finditer(page.body):
        slug = match.group(1).strip()
        target = slugs.get(slug)
        if target is None:
            f.add("ERROR", page.rel, f"broken wiki link [[{slug}]]")
        elif page.ships and not target.ships:
            # The wheel renderer would leave the target's title behind — often internal text
            # in another language. Shipped pages must only link to shipped pages.
            f.add(
                "ERROR", page.rel,
                f"[[{slug}]] does not ship in the wheel; rewrite the sentence instead",
            )
    for match in MD_LINK_RE.finditer(page.body):
        target = match.group(1)
        if target.startswith(("http://", "https://", "#")):
            continue
        resolved = (page.path.parent / target).resolve()
        if not resolved.exists():
            f.add("ERROR", page.rel, f"broken relative link '{target}'")
        else:
            f.add("WARN", page.rel, f"use [[wiki-link]] instead of relative '{target}'")


def check_versions(page: Page, f: Findings) -> None:
    if page.meta.get("allow_version_literals"):
        return
    prose = strip_code_and_frontmatter(page.body)
    hits = {m.group(0) for m in VERSION_RE.finditer(prose)}
    # Dates and section numbers are not versions.
    hits = {h for h in hits if not h.startswith(("19", "20"))}
    for hit in sorted(hits):
        f.add(
            "ERROR", page.rel,
            f"version literal '{hit}' — versions belong in status.md/CHANGELOG "
            f"(or set allow_version_literals: true)",
        )


def check_private(page: Page, f: Findings) -> None:
    if not page.ships:
        return
    body = page.body
    for label, pattern in PRIVATE_PATTERNS:
        for match in pattern.finditer(body):
            f.add("ERROR", page.rel, f"{label} in a page that ships in the wheel: {match.group(0)!r}")
    for pattern in _private_names():
        if pattern.search(body):
            f.add("ERROR", page.rel, "a configured private name appears in a page that ships")
    for match in re.finditer(r"\w*aqa\w*", body, re.IGNORECASE):
        token = match.group(0).lower()
        if token.startswith("aqa_") or token.startswith("_aqa"):
            continue  # real public identifiers, see decisions/no-domain
        if token in (i.lower() for i in ALLOWED_AQA_IDENTIFIERS):
            continue
        f.add(
            "ERROR", page.rel,
            f"consumer project name '{token}' in a page that ships in the wheel",
        )


def check_status_singleton(pages: List[Page], f: Findings) -> None:
    """Only status.md may carry the release/wave tables."""
    markers = ("what is next", "что дальше", "roadmap", "роадмап")
    for page in pages:
        if page.slug in ("status", "log", "index", "WIKI"):
            continue
        if page.slug.startswith("decisions/"):
            continue
        lowered = page.body.lower()
        for marker in markers:
            if f"## {marker}" in lowered:
                f.add("WARN", page.rel, f"section '{marker}' duplicates status.md")


def check_wheel_drift(pages: List[Page], f: Findings) -> None:
    shipped = wheel_pages(pages)
    expected = {p.wheel_name(): render_for_wheel(p, pages) for p in shipped}
    present = {p.name: p.read_text(encoding="utf-8") for p in WHEEL_DOCS_DIR.glob("*.md")}
    for name in sorted(set(expected) - set(present)):
        f.add("ERROR", "partest/docs", f"missing '{name}' — run tools/docs_build_wheel.py")
    for name in sorted(set(present) - set(expected)):
        f.add("ERROR", "partest/docs", f"stray '{name}' — not generated from any wiki page")
    for name in sorted(set(expected) & set(present)):
        if expected[name] != present[name]:
            f.add("ERROR", f"partest/docs/{name}", "out of date — run tools/docs_build_wheel.py")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit non-zero on warnings too")
    args = parser.parse_args()

    pages = load_pages()
    slugs = {p.slug: p for p in pages}
    f = Findings()

    for page in pages:
        check_frontmatter(page, f)
        if not page.meta:
            continue
        check_sources(page, f)
        check_links(page, slugs, f)
        check_versions(page, f)
        check_private(page, f)

    check_status_singleton(pages, f)
    check_wheel_drift(pages, f)

    f.report()
    if args.strict:
        return 1 if f.items else 0
    return 1 if f.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
