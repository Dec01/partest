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


# --- What reaches PyPI ----------------------------------------------------

# The consumer project this library grew out of must not be named in anything
# published. `aqa_*` and `_aqa_monitor` are real public identifiers on a removal
# path and are allowed until the next major version.
_ALLOWED_LEGACY = ("aqa_name", "aqa_code", "aqa_short", "aqa_fill", "aqa_prefixed",
                   "_aqa_monitor", "aqa_*")


def _names_a_consumer(text: str) -> list:
    import re

    hits = []
    for match in re.finditer(r"\w*aqa\w*", text, re.IGNORECASE):
        token = match.group(0)
        if token.lower().startswith("aqa_") or token.lower().startswith("_aqa"):
            continue
        if token.lower() in (a.lower() for a in _ALLOWED_LEGACY):
            continue
        hits.append(token)
    return hits


def _shipped_files():
    """Files MANIFEST.in publishes, plus the package itself."""
    files = [REPO_ROOT / "CHANGELOG.md"]
    files += sorted((REPO_ROOT / "partest").rglob("*.md"))
    files += sorted((REPO_ROOT / "partest").rglob("*.py"))
    return [f for f in files if f.is_file() and "__pycache__" not in f.parts]


# The test-data marker defaults to "AQA", the ordinary abbreviation for automated QA.
# It is a deliberate neutral default, not a project name, and cleanup depends on it —
# so these two files are expected to contain it and are checked separately below.
_MARKER_DEFAULT_FILES = {"partest/data_marker.py", "partest/project_gen/skeleton.py"}


def test_nothing_published_names_the_consumer_project():
    offenders = {}
    for path in _shipped_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in _MARKER_DEFAULT_FILES:
            continue
        hits = _names_a_consumer(path.read_text(encoding="utf-8", errors="replace"))
        if hits:
            offenders[rel] = sorted(set(hits))
    assert not offenders, f"consumer project named in published files: {offenders}"


def test_the_marker_default_is_present_and_overridable():
    """Cleanup matches on the marker, so an empty one would make it match everything."""
    import os
    import subprocess
    import sys

    from partest.data_marker import TEST_MARKER, marked_name

    assert TEST_MARKER == "AQA"
    assert TEST_MARKER in marked_name("Client")

    env = {**os.environ, "TEST_DATA_MARKER": "QA1", "PYTHONPATH": str(REPO_ROOT)}
    result = subprocess.run(
        [sys.executable, "-c",
         "from partest.data_marker import TEST_MARKER, marked_name;"
         "print(TEST_MARKER); print(marked_name('X'))"],
        capture_output=True, text=True, env=env, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    marker, name = result.stdout.split()[0], result.stdout.strip().splitlines()[1]
    assert marker == "QA1", "TEST_DATA_MARKER must override the default"
    assert name.startswith("QA1"), "generated names must carry the overridden marker"


def test_manifest_excludes_the_repository_only_material():
    """Tests and the wiki carry internal references and repo-only dependencies."""
    manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    for pruned in ("prune tests", "prune docs", "prune tools", "prune .claude", "prune .grok"):
        assert pruned in manifest, f"MANIFEST.in must {pruned!r}"
    assert "exclude README.md" in manifest, (
        "the root README is repo-facing and links to paths that do not ship"
    )


def test_shipped_docs_do_not_point_at_repository_paths():
    """A user has no docs/wiki or tools/ to follow."""
    import re

    for path in sorted((REPO_ROOT / "partest" / "docs").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        stray = re.findall(r"docs/wiki/[\w/-]+|tools/[\w]+\.py|\.claude/skills", text)
        assert not stray, f"{path.name} points at repo-only paths: {sorted(set(stray))}"
