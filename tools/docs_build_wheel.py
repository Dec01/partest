"""Generate ``partest/docs`` from the wiki pages marked ``ships_in_wheel: true``.

There is no public source mirror, so the wheel is the only way a user reads documentation
(``python -m partest.docs``). Copying files by hand is what previously leaked internal notes
into the published package; this script makes the selection explicit and checkable.

Usage::

    python tools/docs_build_wheel.py            # regenerate
    python tools/docs_build_wheel.py --check    # fail if regeneration would change anything
"""

from __future__ import annotations

import argparse

from docs_common import (  # type: ignore[import-not-found]
    WHEEL_DOCS_DIR,
    load_pages,
    render_for_wheel,
    wheel_pages,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail instead of writing")
    args = parser.parse_args()

    pages = load_pages()
    shipped = wheel_pages(pages)
    expected = {p.wheel_name(): render_for_wheel(p, pages) for p in shipped}

    WHEEL_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    present = {p.name: p.read_text(encoding="utf-8") for p in WHEEL_DOCS_DIR.glob("*.md")}

    if args.check:
        if expected == present:
            print(f"docs_build_wheel: up to date ({len(expected)} pages)")
            return 0
        for name in sorted(set(expected) - set(present)):
            print(f"missing: {name}")
        for name in sorted(set(present) - set(expected)):
            print(f"stray:   {name}")
        for name in sorted(set(expected) & set(present)):
            if expected[name] != present[name]:
                print(f"changed: {name}")
        return 1

    for name in sorted(set(present) - set(expected)):
        (WHEEL_DOCS_DIR / name).unlink()
        print(f"removed {name}")
    for name, text in sorted(expected.items()):
        path = WHEEL_DOCS_DIR / name
        if present.get(name) != text:
            path.write_text(text, encoding="utf-8")
            print(f"wrote   {name}")

    print(f"docs_build_wheel: {len(expected)} pages in {WHEEL_DOCS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
