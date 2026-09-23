"""One reading of a boolean-ish setting, shared by every switch in the package.

Four places used to spell this out for themselves — :mod:`partest.tls`, two different
dictionaries in :mod:`partest.pytest_plugin`, and :mod:`partest.ui.hooks` — and they
disagreed. ``PARTEST_PYTEST_PLUGIN=disabled`` switched the plugin off, while
``pytest_plugin = "disabled"`` in ``confpartest`` was not recognised and read as *on*; the
UI helper had no list of false words at all. A switch that means different things
depending on where it is written is worse than no switch, because the project believes it
is set.

Deliberately tiny and dependency-free: :mod:`partest.ui` imports it, and a UI job must
never load ``confpartest`` or an OpenAPI specification (``tests/test_ui_isolation.py``).
"""

from __future__ import annotations

import os
from typing import Any, Optional

#: Words that mean yes. Written out rather than "anything but 0" so that a typo is an
#: unreadable value — see :func:`coerce_bool` — instead of silently meaning *on*.
TRUE_WORDS = frozenset({"1", "true", "on", "yes", "y", "enable", "enabled"})
FALSE_WORDS = frozenset({"0", "false", "off", "no", "n", "disable", "disabled"})


def coerce_bool(value: Any) -> Optional[bool]:
    """``True``/``False`` for anything recognisable, ``None`` when nothing was said.

    ``None``, an empty string and a word in neither list all read as "not said": the
    caller owns its default, and an unreadable value never flips a switch by accident.
    Non-strings keep Python's own truthiness, so ``tls_verify = 0`` works as written.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if not low:
            return None
        if low in TRUE_WORDS:
            return True
        if low in FALSE_WORDS:
            return False
        return None
    return bool(value)


def env_bool(name: str) -> Optional[bool]:
    """:func:`coerce_bool` of an environment variable; ``None`` when unset or unreadable."""
    return coerce_bool(os.getenv(name))
