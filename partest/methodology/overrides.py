"""Deprecated alias for :mod:`partest.methodology.api.overrides`. Removed in partest 3.0.0.

Importing this name warns once and then *is* the module it points at — one registry, so
``set_subtype_overrides`` through either spelling is visible to ``active_overrides`` through
the other. See ``partest/methodology/_moved.py``.
"""

from partest.methodology._moved import alias

alias(__name__)
