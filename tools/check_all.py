"""Run every check that must pass before a release, in one command.

CI runs this same script, so what fails on a pull request is what fails on a laptop. The
checks are spread across pytest and three documentation tools; remembering all of them by
hand is how a stale ``partest/docs`` or an unregenerated index reaches PyPI.

Usage::

    python tools/check_all.py            # tests, docs lint, index, wheel docs
    python tools/check_all.py --package  # also build the distribution and twine check
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent


def run(name: str, command: Sequence[str], *, optional: bool = False) -> Tuple[str, bool, float, str]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            list(command), cwd=REPO_ROOT, capture_output=True, text=True
        )
    except OSError as exc:
        return (name, optional, time.monotonic() - started, f"could not run: {exc}")
    output = (result.stdout or "") + (result.stderr or "")
    return (name, result.returncode == 0, time.monotonic() - started, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package",
        action="store_true",
        help="also build the distribution and validate it with twine",
    )
    parser.add_argument(
        "--strict-docs",
        action="store_true",
        help="fail on documentation warnings too, not only errors (use before a release)",
    )
    args = parser.parse_args()

    # Staleness is a warning: a page whose sources moved is worth reporting on every
    # change but is not a reason to reject one. Before a release it is, because a
    # release publishes those pages.
    lint = [sys.executable, "tools/docs_lint.py"]
    if args.strict_docs:
        lint.append("--strict")

    checks: List[Tuple[str, List[str], bool]] = [
        ("tests", [sys.executable, "-m", "pytest", "tests/", "-q"], False),
        ("docs lint", lint, False),
        ("docs index", [sys.executable, "tools/docs_index.py", "--check"], False),
        ("wheel docs", [sys.executable, "tools/docs_build_wheel.py", "--check"], False),
    ]

    if args.package:
        # A stale dist/ is how the wrong artefact gets uploaded.
        for stale in ("dist", "build"):
            shutil.rmtree(REPO_ROOT / stale, ignore_errors=True)
        checks += [
            ("build", [sys.executable, "setup.py", "-q", "sdist", "bdist_wheel"], False),
            ("twine", [sys.executable, "-m", "twine", "check", "dist/*"], False),
        ]

    failures = []
    for name, command, optional in checks:
        label, ok, seconds, output = run(name, command, optional=optional)
        mark = "ok  " if ok else "FAIL"
        print(f"{mark} {label:<12} {seconds:5.1f}s")
        if not ok:
            failures.append((label, output))

    if not failures:
        print("\nall checks passed")
        return 0

    for label, output in failures:
        print(f"\n----- {label} -----")
        print(output.strip()[-4000:])
    print(f"\n{len(failures)} check(s) failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
