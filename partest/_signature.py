"""``inspect.signature`` for code that only needs the parameters, never the annotations."""

from __future__ import annotations

import inspect
import sys
from typing import Any, Optional


def signature_of(func: Any) -> Optional[inspect.Signature]:
    """The signature of *func* with annotations left unevaluated; ``None`` when it cannot be read.

    From Python 3.14 annotations are evaluated lazily, and ``inspect.signature`` evaluates
    them by default: a parameter annotated with a name imported under ``TYPE_CHECKING``, or a
    class defined further down the module, raises ``NameError``. Callers here look at names
    and kinds of parameters only, so annotations are read as forward references; anything
    that still fails (a broken ``__signature__``, a builtin without one) is ``None``.
    """
    try:
        if sys.version_info >= (3, 14):
            import annotationlib

            return inspect.signature(func, annotation_format=annotationlib.Format.FORWARDREF)
        return inspect.signature(func)
    except Exception:
        return None
