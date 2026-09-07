"""Deprecated bridge to the ``partest-gen`` distribution.

The scaffold generator used to live here. It is now its own package, ``partest_gen``, because
its release cadence, its dependencies and its notion of a breaking change all differ from the
harness — for a code generator the *names and locations of the files it writes* are the public
API. See ``docs/wiki/components/project-gen.md``.

Old imports keep working while ``partest-gen`` is installed::

    pip install 'partest[gen]'      # or: pip install partest-gen

    from partest.project_gen.cli import main       # deprecated, works
    from partest_gen.cli import main               # supported

Every submodule redirects too, and to the *same* module object rather than a second copy, so
``isinstance`` checks and module-level state behave as they did before the move.

The ``partest-gen`` command itself is declared by ``partest-gen``: two distributions cannot
both own one console script without the winner depending on installation order.

This module is removed in the next major version of ``partest``.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
import warnings

_OLD = __name__          # "partest.project_gen"
_NEW = "partest_gen"

_MISSING = (
    "partest.project_gen moved to the 'partest-gen' distribution.\n"
    "  pip install partest-gen        (or: pip install 'partest[gen]')\n"
    "Then import from 'partest_gen'; 'partest.project_gen' keeps working until the next "
    "major release of partest."
)


class _Redirect(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Resolve ``partest.project_gen.X`` to the already-imported ``partest_gen.X``.

    Returning the existing module object from ``create_module`` is the point: aliasing by
    re-executing the source would give two distinct classes with the same name, and the
    failures that causes surface far from here.
    """

    def find_spec(self, fullname, path=None, target=None):
        if fullname != _OLD and not fullname.startswith(_OLD + "."):
            return None
        return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        return importlib.import_module(_NEW + spec.name[len(_OLD):])

    def exec_module(self, module):
        """Already executed under its real name."""


try:
    _target = importlib.import_module(_NEW)
except ImportError as exc:  # pragma: no cover - exercised in a subprocess
    raise ImportError(_MISSING) from exc

if not any(isinstance(finder, _Redirect) for finder in sys.meta_path):
    sys.meta_path.insert(0, _Redirect())

warnings.warn(
    "partest.project_gen is deprecated; import from partest_gen instead. "
    "This bridge is removed in the next major version of partest.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export the same public surface the old package had.
from partest_gen import (  # noqa: E402  (must follow the import guard above)
    OpIR,
    ParamIR,
    SuiteIR,
    build_ir_from_openapi_dict,
    emit_resources,
    build_ui_files,
    load_openapi,
)

__all__ = [
    "OpIR",
    "ParamIR",
    "SuiteIR",
    "build_ir_from_openapi_dict",
    "load_openapi",
    "emit_resources",
    "build_ui_files",
]
