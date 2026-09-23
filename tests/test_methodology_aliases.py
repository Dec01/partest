"""The deprecated ``partest.methodology.<name>`` paths, kept until 3.0.0.

2.0.0 moved the API methodology into ``partest/methodology/api/``. Removing the old paths
outright made the upgrade atomic — a consumer had to change its import lines and its pinned
version in one commit, because neither spelling worked on both releases — and the failure it
produced was unreadable: ``confpartest.py`` is imported from inside the pytest plugin, so a
stale import surfaced as an ``INTERNALERROR`` with a pluggy traceback during collection of
the *whole* tree. The quiet variant was worse: on the old release ``confpartest`` failed to
import, ``active_overrides()`` came back empty, and coverage counted subtypes against the
wrong required sets without a word.

So the old paths stay, as aliases that warn. What is asserted here is that they are aliases
and not copies: the same module object, therefore the same classes for ``isinstance`` and
one shared ``_overrides`` registry.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from partest.methodology import _moved

#: What existed as ``partest/methodology/<name>.py`` in 1.8.x, read off the tree at the tag
#: rather than recalled: ``git ls-tree -r v1.8.1 --name-only -- partest/methodology``. The
#: same six are there at v1.7.1 and at 1.8.0, and nothing was deleted from that directory in
#: between (``git log --diff-filter=D -- 'partest/methodology/*.py'`` is empty), so this is
#: the complete set a consumer on any 1.8.x could be importing.
MOVED_IN_2_0_0 = (
    "classifier",
    "inference",
    "matrix",
    "overrides",
    "steps",
    "subtypes",
)

METHODOLOGY_DIR = Path(_moved.__file__).resolve().parent


def fresh_import(old_name: str):
    """Import an alias with its module body actually executing, and collect its warnings.

    An alias replaces its own ``sys.modules`` entry, so a second import is a cache hit and
    warns about nothing — which is the point of the alias, and the reason a test that wants
    to see the warning has to evict the entry first.
    """
    sys.modules.pop(old_name, None)
    parent = sys.modules.get("partest.methodology")
    if parent is not None:
        setattr(parent, old_name.rpartition(".")[2], None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module = importlib.import_module(old_name)
    return module, caught


@pytest.fixture(autouse=True)
def _restore_real_modules():
    """Leave the session with both spellings pointing at the moved modules again."""
    yield
    for leaf in MOVED_IN_2_0_0:
        old = f"partest.methodology.{leaf}"
        sys.modules[old] = importlib.import_module(f"partest.methodology.api.{leaf}")
        setattr(sys.modules["partest.methodology"], leaf, sys.modules[old])


@pytest.mark.parametrize("leaf", MOVED_IN_2_0_0)
def test_every_module_that_moved_has_an_alias_file(leaf):
    """A missing file here is a consumer's ``ModuleNotFoundError`` at collection time."""
    assert (METHODOLOGY_DIR / f"{leaf}.py").is_file()
    assert leaf in _moved.MOVED


def test_the_alias_list_matches_what_is_on_disk():
    """No alias for a module that never moved, and none left over after 3.0.0 removes them."""
    on_disk = {
        path.stem
        for path in METHODOLOGY_DIR.glob("*.py")
        if not path.stem.startswith("_")
    }

    assert on_disk == set(MOVED_IN_2_0_0)
    assert set(_moved.MOVED) == set(MOVED_IN_2_0_0)


@pytest.mark.parametrize("leaf", MOVED_IN_2_0_0)
def test_the_old_path_is_the_new_module_not_a_copy(leaf):
    """Two executions of one source give two classes with one name, and the failures land far away."""
    old, _ = fresh_import(f"partest.methodology.{leaf}")
    new = importlib.import_module(f"partest.methodology.api.{leaf}")

    assert old is new


@pytest.mark.parametrize("leaf", MOVED_IN_2_0_0)
def test_importing_the_old_path_warns_and_names_the_new_one(leaf):
    """"Deprecated" without a replacement makes the reader go looking. Name the path."""
    _, caught = fresh_import(f"partest.methodology.{leaf}")

    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecations) == 1, [str(w.message) for w in caught]

    message = str(deprecations[0].message)
    assert f"partest.methodology.api.{leaf}" in message, message
    assert "3.0.0" in message, message


def test_the_warning_is_once_per_module_not_once_per_name():
    """A per-name warning turns one stale import line into a wall of output."""
    _, caught = fresh_import("partest.methodology.subtypes")
    assert len([w for w in caught if issubclass(w.category, DeprecationWarning)]) == 1

    with warnings.catch_warnings(record=True) as again:
        warnings.simplefilter("always")
        from partest.methodology.subtypes import MethodSubtype, SUBTYPE_LABELS  # noqa: F401
        import partest.methodology.subtypes  # noqa: F401

    assert [str(w.message) for w in again] == []


def test_both_import_forms_work_and_agree():
    """``from X import name`` and ``import X as x`` take different paths through the machinery."""
    fresh_import("partest.methodology.subtypes")

    from partest.methodology.subtypes import MethodSubtype as from_old
    import partest.methodology.subtypes as old_module
    from partest.methodology.api.subtypes import MethodSubtype as from_new
    import partest.methodology.api.subtypes as new_module

    assert from_old is from_new
    assert old_module is new_module
    assert old_module.MethodSubtype is from_new


def test_importing_the_submodule_off_the_package_works_too():
    """``from partest.methodology import subtypes`` — a third path through the machinery.

    It only reaches the import system when the parent has no such attribute yet, which is
    why this evicts the attribute as well as the ``sys.modules`` entry.
    """
    parent = sys.modules["partest.methodology"]
    sys.modules.pop("partest.methodology.subtypes", None)
    if hasattr(parent, "subtypes"):
        delattr(parent, "subtypes")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from partest.methodology import subtypes
    import partest.methodology.api.subtypes as new

    assert subtypes is new


def test_isinstance_holds_across_the_two_spellings():
    """The reason an alias must not re-execute the source: enums compared across copies."""
    fresh_import("partest.methodology.subtypes")

    from partest.methodology.subtypes import MethodSubtype as Old
    from partest.methodology.api.subtypes import MethodSubtype as New

    assert isinstance(Old.GET_LIST, New)
    assert Old.GET_LIST is New.GET_LIST


def test_module_level_state_is_shared_through_the_alias():
    """One override registry. Two would make `active_overrides()` answer for the wrong copy."""
    fresh_import("partest.methodology.overrides")

    import partest.methodology.overrides as old
    from partest.methodology.api.overrides import active_overrides, clear_subtype_overrides

    try:
        old.set_subtype_overrides({"GET /widgets": "get_list_objects"})
        assert active_overrides() == {"GET /widgets": "get_list_objects"}
        assert old.active_overrides() == active_overrides()
    finally:
        clear_subtype_overrides()


def test_the_package_itself_does_not_warn():
    """`from partest.methodology import …` never moved; warning about it would be noise.

    In a subprocess, because the honest version of this evicts the whole package from
    ``sys.modules`` — and re-importing it in-process would hand the rest of the session a
    second ``CoveragePriority`` and a second override registry, which is the exact failure
    the aliases exist to prevent.
    """
    result = subprocess.run(
        [sys.executable, "-W", "error::DeprecationWarning", "-c",
         "import partest.methodology, partest.methodology.api, partest.methodology.ui"],
        capture_output=True,
        text=True,
        cwd=METHODOLOGY_DIR.parents[1],
    )

    assert result.returncode == 0, result.stderr


def test_active_overrides_is_on_the_package():
    """A suite asserting its overrides arrived had only a deep import to do it with.

    That is what made the move breaking for the consumer that found this: the assertion
    lived in a contract test, the import was of a module that moved, and the failure came
    back as an `INTERNALERROR` from the plugin rather than a failed test.
    """
    import partest.methodology as facade
    from partest.methodology.api.overrides import active_overrides

    assert facade.active_overrides is active_overrides
    assert "active_overrides" in facade.__all__

    import partest.methodology.api as api

    assert api.active_overrides is active_overrides
    assert "active_overrides" in api.__all__
