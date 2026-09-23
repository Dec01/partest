"""Deprecated alias for :mod:`partest.methodology.api.inference`. Removed in partest 3.0.0.

Importing this name warns once and then *is* the module it points at, not a second copy.
See ``partest/methodology/_moved.py``.
"""

from partest.methodology._moved import alias

alias(__name__)
