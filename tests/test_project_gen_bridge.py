"""The deprecated bridge from `partest.project_gen` to the `partest-gen` distribution.

The generator moved out of this package. What stays behind is a redirect, and a redirect is
only worth having if it is exact: the same module objects, the same classes, and a message a
reader can act on when the other distribution is not installed.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import warnings

import pytest

partest_gen = pytest.importorskip(
    "partest_gen", reason="partest-gen is an optional dependency (partest[gen])"
)


@pytest.fixture
def bridge():
    """Import the bridge fresh, so the deprecation warning is observable."""
    for name in [n for n in sys.modules if n.startswith("partest.project_gen")]:
        del sys.modules[name]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module = importlib.import_module("partest.project_gen")
    module._warnings_seen = caught  # type: ignore[attr-defined]
    return module


def test_importing_the_old_path_warns(bridge):
    """A deprecation nobody sees never expires."""
    assert any(
        issubclass(w.category, DeprecationWarning) and "partest_gen" in str(w.message)
        for w in bridge._warnings_seen
    ), [str(w.message) for w in bridge._warnings_seen]


def test_the_old_public_names_still_resolve(bridge):
    for name in bridge.__all__:
        assert getattr(bridge, name) is getattr(partest_gen, name), name


def test_submodules_redirect_to_the_same_object(bridge):
    """Not a copy: a second execution would give two classes with one name."""
    old = importlib.import_module("partest.project_gen.skeleton")
    new = importlib.import_module("partest_gen.skeleton")
    assert old is new

    deep_old = importlib.import_module("partest.project_gen.emitters.util")
    deep_new = importlib.import_module("partest_gen.emitters.util")
    assert deep_old is deep_new


def test_from_import_through_the_bridge_works(bridge):
    from partest.project_gen.cli import main as bridged
    from partest_gen.cli import main as direct

    assert bridged is direct


def test_missing_distribution_says_what_to_install():
    """The failure a consumer hits after upgrading partest without installing the generator."""
    script = (
        "import sys\n"
        "class Block:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'partest_gen' or name.startswith('partest_gen.'):\n"
        "            raise ImportError('blocked for the test')\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "import partest.project_gen\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)

    assert result.returncode != 0
    assert "pip install partest-gen" in result.stderr, result.stderr


def test_the_console_script_is_not_declared_here():
    """Two distributions declaring one command make the winner depend on install order."""
    from pathlib import Path

    setup = (Path(__file__).resolve().parents[1] / "setup.py").read_text(encoding="utf-8")
    assert "partest-gen=" not in setup, (
        "the partest-gen console script belongs to the partest-gen distribution"
    )
