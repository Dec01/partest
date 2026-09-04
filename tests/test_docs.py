"""Documentation health, checked with the rest of the suite.

Documentation rot is a regression like any other, so the wiki linter runs inside pytest rather
than as an optional chore. See ``docs/wiki/decisions/docs-architecture.md``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "tools"

pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / "docs" / "wiki").is_dir(),
    reason="documentation wiki is not part of the installed package",
)


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / script), *args],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )


def test_wiki_lint_has_no_errors():
    result = _run("docs_lint.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_wheel_docs_match_the_wiki():
    """partest/docs is generated; a stale copy would ship wrong or internal content."""
    result = _run("docs_build_wheel.py", "--check")
    assert result.returncode == 0, (
        "partest/docs is out of date — run `python tools/docs_build_wheel.py`\n"
        + result.stdout
    )


def test_shipped_docs_are_readable_through_the_package():
    from partest.docs import list_docs, read_doc

    names = list_docs()
    assert names, "no documentation shipped in the package"
    for name in names:
        assert read_doc(name).strip(), f"{name} is empty"


def test_agents_file_stays_short():
    """AGENTS.md is always in context; length is a budget, not a style preference."""
    lines = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 60, f"AGENTS.md grew to {len(lines)} lines (limit 60)"


def test_every_skill_declares_name_and_description():
    skills = sorted((REPO_ROOT / ".claude" / "skills").glob("*/SKILL.md"))
    assert skills, "no skills found"
    for skill in skills:
        head = skill.read_text(encoding="utf-8").split("---", 2)
        assert len(head) >= 3, f"{skill.name}: missing frontmatter"
        assert "name:" in head[1] and "description:" in head[1], f"{skill}: incomplete frontmatter"


def test_package_advertises_its_types():
    """py.typed is a promise to consumers' type checkers; it must ship."""
    assert (REPO_ROOT / "partest" / "py.typed").is_file()
    setup = (REPO_ROOT / "setup.py").read_text(encoding="utf-8")
    assert "py.typed" in setup, "py.typed must be listed in package_data"


def test_legacy_aliases_warn_before_they_are_removed():
    """A deprecation that never warns never expires."""
    import warnings

    from partest.data_marker import aqa_name, marked_name

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        value = aqa_name("Item")

    assert value, "the alias must still work while it is deprecated"
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        marked_name("Item")
    assert not caught, "the supported name must stay quiet"
