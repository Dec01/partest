"""The mechanism behind the deprecated ``partest.methodology.<name>`` paths.

The six API submodules moved into ``partest/methodology/api/`` in 2.0.0. The old paths stay
as aliases until 3.0.0 so that a consumer can raise its version and rewrite its imports as
two separate steps rather than one atomic one — the reasoning is in ``CHANGELOG.md`` and in
``docs/wiki/howto/migration.md``.

An alias resolves to the **same module object** as the new path, exactly as the
``partest.project_gen`` bridge does, and for the same reason: re-executing the source under a
second name would give two ``MethodSubtype`` enums that compare unequal, and two copies of
the ``_overrides`` registry — so ``set_subtype_overrides`` through one spelling would leave
``active_overrides`` through the other reporting nothing. That failure surfaces far from the
import that caused it.

The trick is the one the import system supports on purpose: a module that replaces its own
entry in ``sys.modules`` while it is executing. ``importlib._bootstrap._load`` re-reads
``sys.modules[spec.name]`` after ``exec_module``, so the replacement is what both
``import partest.methodology.subtypes as s`` and
``from partest.methodology.subtypes import MethodSubtype`` end up seeing, and it is what gets
bound onto the parent package. A finder on ``sys.meta_path`` — what ``project_gen`` needs,
because it redirects a whole tree of modules it does not know the names of — would work too,
but here the six names are known and fixed, and a file per name is the version a reader finds
by looking where the old import points.

The warning fires while the alias module executes, which happens once per interpreter: one
warning per deprecated module, not one per name imported from it.
"""

from __future__ import annotations

import importlib
import sys
import warnings

#: Old submodule names, i.e. everything that was ``partest/methodology/<name>.py`` in 1.8.x.
MOVED = ("classifier", "inference", "matrix", "overrides", "steps", "subtypes")

_PACKAGE = "partest.methodology"
_AREA = "api"


def alias(old_name: str) -> None:
    """Make ``old_name`` resolve to its module under ``partest.methodology.api``.

    Call as ``alias(__name__)`` from the body of the deprecated module and write nothing
    else there: after this returns, the name refers to the moved module itself.
    """
    leaf = old_name.rpartition(".")[2]
    new_name = f"{_PACKAGE}.{_AREA}.{leaf}"
    target = importlib.import_module(new_name)

    warnings.warn(
        f"{old_name} moved in partest 2.0.0; use {new_name} instead. "
        "The old path is removed in partest 3.0.0.",
        DeprecationWarning,
        stacklevel=3,
    )

    sys.modules[old_name] = target
