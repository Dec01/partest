"""Opt-in marker sets: tests that run only when someone asks for them by name.

Some tests should not be part of a plain ``pytest`` run — long ones, ones that cost money,
ones that need a stand prepared by hand. ``skip`` is the usual answer and the wrong one: an
everlasting skip sits in every report, and people learn to read past the yellow. These
tests are **deselected** instead — not collected into the run at all — until they are
asked for::

    # pytest.ini
    [pytest]
    optin_markers =
        slow:RUN_SLOW
        nightly
    markers =
        slow: long-running; opt-in
        slow_db: the database part of slow
        nightly: runs only when asked for

A test carrying ``slow`` (or any ``slow_*`` marker) is selected when

* the ``-m`` expression **depends on the set positively**: it is true on the test's
  markers and false on the same markers with every ``slow``/``slow_*`` marker removed —
  ``-m slow``, ``-m slow_db``, ``-m "slow and not flaky"``; or
* the environment variable named after the colon reads as true (``RUN_SLOW=1``), which
  selects the whole set regardless of ``-m``.

Why evaluate rather than search for the word: ``-m "not slow_db and not flaky"`` is true
for every test that lacks those two markers, including the whole ``slow`` set; a substring
test would pull it in, an evaluation sees that removing ``slow`` changes nothing and keeps
it out. The expression is compiled by pytest's own parser, so ``-m`` means exactly what it
means to pytest, keyword matching (``-m "slow(level=2)"``) included.

**Sub-markers are taken by prefix.** ``slow`` covers ``slow`` and every marker starting with
``slow_``. A set is one family of names, and a prefix keeps a new member from slipping out
of it because someone forgot to extend a list. An unrelated marker that should belong to
the set is a second entry with the same variable (``heavy:RUN_SLOW``). A test in two sets
must be opted into both.

Nothing happens when ``optin_markers`` is empty: no hook is registered, no header line is
printed. Markers still have to be registered under ``markers`` as usual —
``--strict-markers`` is not this plugin's business.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

import pytest

from partest.flags import coerce_bool

INI_NAME = "optin_markers"
INI_HELP = (
    "opt-in marker sets: 'marker[:ENV_VAR] ...'. Tests with such a marker (or marker_*) "
    "are deselected unless -m selects them through it, or ENV_VAR is true."
)

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class OptInSet:
    """One opt-in family: ``marker`` and every ``marker_*``, optionally switched by ``env``."""

    marker: str
    env: Optional[str] = None

    def covers(self, name: str) -> bool:
        return name == self.marker or name.startswith(self.marker + "_")

    def env_enabled(self, environ: Optional[Mapping[str, str]] = None) -> bool:
        if not self.env:
            return False
        source = os.environ if environ is None else environ
        return coerce_bool(source.get(self.env)) is True

    def __str__(self) -> str:
        return f"{self.marker} (or {self.env}=1)" if self.env else self.marker


def parse_optin_markers(entries: Iterable[str]) -> Tuple[OptInSet, ...]:
    """``["slow:RUN_SLOW", "nightly"]`` → two :class:`OptInSet`. Raises ``ValueError``."""
    sets: List[OptInSet] = []
    seen = set()
    for raw in entries:
        entry = (raw or "").strip()
        if not entry:
            continue
        marker, sep, env = entry.partition(":")
        marker, env = marker.strip(), env.strip()
        if not marker.isidentifier():
            raise ValueError(f"{INI_NAME}: {entry!r} — marker name must be an identifier")
        if sep and not _ENV_NAME.match(env):
            raise ValueError(
                f"{INI_NAME}: {entry!r} — expected 'marker' or 'marker:ENV_VAR'"
            )
        if marker in seen:
            raise ValueError(f"{INI_NAME}: marker {marker!r} is listed twice")
        seen.add(marker)
        sets.append(OptInSet(marker, env or None))
    return tuple(sets)


class _Mark:
    """The part of a pytest ``Mark`` the matcher reads — name and keyword arguments."""

    def __init__(self, name: str, kwargs: Optional[Mapping[str, Any]] = None) -> None:
        self.name = name
        self.kwargs = dict(kwargs or {})


def _matcher(marks: Sequence[Any]):
    """What ``-m`` evaluates against: same rule as pytest's own mark matcher."""

    def match(name: str, /, **kwargs: Any) -> bool:
        for mark in marks:
            if mark.name != name:
                continue
            if all(mark.kwargs.get(k, _MISSING) == v for k, v in kwargs.items()):
                return True
        return False

    return match


_MISSING = object()


def _evaluate(markexpr: str, marks: Sequence[Any]) -> bool:
    from _pytest.mark.expression import Expression

    return bool(Expression.compile(markexpr).evaluate(_matcher(marks)))


def selected_through(markexpr: Optional[str], marks: Sequence[Any], optin: OptInSet) -> bool:
    """Does ``-m`` select a test with these marks *because of* the opt-in set?

    ``marks`` are objects with ``name`` and ``kwargs`` (pytest's ``Mark`` or anything
    shaped like it). True only when the expression holds on ``marks`` and fails once the
    set's markers are taken away.
    """
    expr = (markexpr or "").strip()
    if not expr:
        return False
    marks = [m if hasattr(m, "kwargs") else _Mark(str(m)) for m in marks]
    if not _evaluate(expr, marks):
        return False
    without = [m for m in marks if not optin.covers(m.name)]
    return not _evaluate(expr, without)


def is_selected(
    optin: OptInSet,
    markexpr: Optional[str],
    marks: Sequence[Any],
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    """The whole rule for one set: its variable, or a positive dependence of ``-m``."""
    return optin.env_enabled(environ) or selected_through(markexpr, marks, optin)


class OptInPlugin:
    """Registered by :mod:`partest.pytest_plugin` only when the ini option is not empty."""

    def __init__(self, sets: Sequence[OptInSet]) -> None:
        self.sets = tuple(sets)

    def pytest_report_header(self, config) -> str:
        return "partest opt-in markers: " + ", ".join(str(s) for s in self.sets)

    # Last, so pytest's own ``-m`` handling has already run — and has already turned an
    # unparsable expression into a usage error before this compiles it again.
    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config, items) -> None:
        markexpr = getattr(config.option, "markexpr", "") or ""
        kept, deselected = [], []
        for item in items:
            marks = list(item.iter_markers())
            names = {m.name for m in marks}
            relevant = [s for s in self.sets if any(s.covers(n) for n in names)]
            if all(is_selected(s, markexpr, marks) for s in relevant):
                kept.append(item)
            else:
                deselected.append(item)
        if deselected:
            config.hook.pytest_deselected(items=deselected)
            items[:] = kept


def add_ini(parser) -> None:
    parser.addini(INI_NAME, INI_HELP, type="args", default=[])


def configure(config) -> Optional[OptInPlugin]:
    """Register the plugin if ``optin_markers`` names anything; return it (or ``None``)."""
    try:
        entries = config.getini(INI_NAME)
    except ValueError:  # the option was never added: partest's hooks are not loaded
        return None
    try:
        sets = parse_optin_markers(entries)
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from None
    if not sets:
        return None
    plugin = OptInPlugin(sets)
    config.pluginmanager.register(plugin, "partest-optin")
    return plugin


__all__ = [
    "INI_NAME",
    "OptInPlugin",
    "OptInSet",
    "is_selected",
    "parse_optin_markers",
    "selected_through",
]
