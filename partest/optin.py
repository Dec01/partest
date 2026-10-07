"""Opt-in marker sets: tests that run only when someone asks for them by name.

Some tests should not be part of a plain ``pytest`` run — long ones, ones that cost money,
ones that need a stand prepared by hand. ``skip`` is the usual answer and the wrong one: an
everlasting skip sits in every report, and people learn to read past the yellow. These
tests are **deselected** instead — not collected into the run at all — until they are
asked for::

    # pytest.ini
    [pytest]
    partest_optin_markers =
        slow:RUN_SLOW
        nightly
    markers =
        slow: long-running; opt-in
        slow_db: the database part of slow
        nightly: runs only when asked for

A test carrying ``slow`` (or any ``slow_*`` marker — the set's *family*) is selected when
the environment variable named after the colon reads as true (``RUN_SLOW=1``), which takes
the whole set regardless of ``-m``; or when the ``-m`` expression asks for the family.
"Asks for" means the expression depends on the family **positively in at least one
context**. With ``M`` the test's markers, ``F`` its markers of the family, and ``I`` the
marker names the expression mentions outside the family, the test is selected when::

    expr(M)  and  there is S ⊆ I with  expr(S) = False  and  expr(S ∪ F) = True

— adding the test's family markers to some set of the other markers turns the expression
from false to true. Evaluated with pytest's own parser, by trying every ``S``:

* ``-m slow``, ``-m slow_db``, ``-m "slow and not flaky"`` — ``S = ∅`` already shows it.
* ``-m "slow or api"`` on a test marked both — ``S = ∅``: false without ``slow``, true with.
* ``-m "slow or not flaky"`` — ``S = {flaky}``: false, and true once ``slow`` is added. The
  test is selected whether or not it is itself marked ``flaky``.
* ``-m "not slow_db and not flaky"`` — no ``S`` works: adding ``slow`` never turns it true,
  so this workaround does not pull the set in. Likewise ``-m smoke`` on a test marked
  ``smoke`` and ``slow``: the family changes nothing about ``smoke``.

``S`` is drawn from plain marker names; a keyword-qualified atom such as ``x(level=2)`` on a
name outside the family is false for every ``S``. When the expression mentions more than
:data:`MAX_CONTEXT_NAMES` names outside the family, the 2^k search is not run and the rule
falls back to two contexts only — the test's own markers without the family, and the empty
set: ``expr(M) and (not expr(M − F) or (expr(F) and not expr(∅)))``. That fallback never
selects more than the full search would; it can miss a request phrased through many names.

Keyword matching (``-m "slow(level=2)"``) means exactly what it means to pytest.

**Sub-markers are taken by prefix.** ``slow`` covers ``slow`` and every marker starting with
``slow_``. A set is one family of names, and a prefix keeps a new member from slipping out
of it because someone forgot to extend a list. An unrelated marker that should belong to
the set is a second entry with the same variable (``heavy:RUN_SLOW``). A test in two sets
must be opted into both. The session header names the registered markers each prefix
captured, and the collection summary the ones it met on tests.

Nothing happens when ``partest_optin_markers`` is empty: no hook is registered, nothing is
printed. Markers still have to be registered under ``markers`` as usual —
``--strict-markers`` is not this plugin's business. ``-p no:partest`` turns the whole
plugin off, this part included: the opt-in sets then run like any other test.

How each set was decided is recorded in ``partest.call_storage.run_info["selection"]
["optin"]`` — ``coverage.json`` ``meta.selection.optin`` — so two runs with different
opt-in states are not compared as if they ran the same suite.
"""

from __future__ import annotations

import itertools
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pytest

from partest.flags import coerce_bool

INI_NAME = "partest_optin_markers"
INI_HELP = (
    "opt-in marker sets: 'marker[:ENV_VAR] ...'. Tests with such a marker (or marker_*) "
    "are deselected unless -m asks for the set, or ENV_VAR is true."
)

#: How a set ended up in this run, as recorded in the run metadata.
STATE_ENV = "env"
STATE_MARKEXPR = "markexpr"
STATE_OFF = "off"

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


_MISSING = object()


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


def _evaluate(markexpr: str, marks: Sequence[Any]) -> bool:
    # A private pytest module: the `pytest<10` cap in setup.py is what keeps it honest.
    from _pytest.mark.expression import Expression

    return bool(Expression.compile(markexpr).evaluate(_matcher(marks)))


#: Above this many marker names outside the family, the context search (2^k evaluations)
#: gives way to the two-context fallback described in the module docstring.
MAX_CONTEXT_NAMES = 8


def _names(markexpr: str) -> Optional[List[str]]:
    """Marker names an expression mentions — identifiers outside keyword parentheses."""
    try:
        from _pytest.mark.expression import Scanner, TokenType

        scanner = Scanner(markexpr)
        names: List[str] = []
        depth = 0
        token = scanner.current
        while token.type is not TokenType.EOF:
            if token.type is TokenType.LPAREN:
                depth += 1
            elif token.type is TokenType.RPAREN:
                depth -= 1
            elif token.type is TokenType.IDENT and depth == 0 and token.value not in names:
                names.append(token.value)
            scanner.accept(token.type)
            token = scanner.current
        return names
    except Exception:  # a private API that moved: use the fallback rule
        return None


def selected_through(markexpr: Optional[str], marks: Sequence[Any], optin: OptInSet) -> bool:
    """Does ``-m`` ask for the opt-in family of a test with these marks?

    ``marks`` are objects with ``name`` and ``kwargs`` (pytest's ``Mark`` or anything
    shaped like it). True when ``expr(M)`` holds and some set ``S`` of the expression's
    other marker names has ``expr(S)`` false and ``expr(S ∪ F)`` true, ``F`` being the
    test's family markers — see the module docstring, including the fallback above
    :data:`MAX_CONTEXT_NAMES` names.
    """
    expr = (markexpr or "").strip()
    if not expr:
        return False
    marks = [m if hasattr(m, "kwargs") else _Mark(str(m)) for m in marks]
    if not _evaluate(expr, marks):
        return False
    family = [m for m in marks if optin.covers(m.name)]
    names = _names(expr)
    if names is not None:
        others = [n for n in names if not optin.covers(n)]
        if len(others) <= MAX_CONTEXT_NAMES:
            for size in range(len(others) + 1):
                for chosen in itertools.combinations(others, size):
                    context = [_Mark(n) for n in chosen]
                    if not _evaluate(expr, context) and _evaluate(expr, context + family):
                        return True
            return False
    rest = [m for m in marks if not optin.covers(m.name)]
    if not _evaluate(expr, rest):
        return True
    return _evaluate(expr, family) and not _evaluate(expr, [])


def is_selected(
    optin: OptInSet,
    markexpr: Optional[str],
    marks: Sequence[Any],
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    """The whole rule for one set: its variable, or ``-m`` asking for the family."""
    return optin.env_enabled(environ) or selected_through(markexpr, marks, optin)


class OptInPlugin:
    """Registered by :mod:`partest.pytest_plugin` only when the ini option is not empty."""

    def __init__(self, sets: Sequence[OptInSet]) -> None:
        self.sets = tuple(sets)
        self.summary: Dict[str, Dict[str, Any]] = {}
        self._seen: Dict[str, set] = {}

    def _registered(self, config) -> List[str]:
        names = []
        for line in config.getini("markers") or []:
            name = line.split(":", 1)[0].split("(", 1)[0].strip()
            if name:
                names.append(name)
        return names

    def pytest_report_header(self, config) -> List[str]:
        registered = self._registered(config)
        lines = []
        for s in self.sets:
            captured = sorted(n for n in registered if s.covers(n))
            lines.append(
                f"partest opt-in markers: {s} covers: "
                + (", ".join(captured) if captured else "no registered marker")
            )
        return lines

    def pytest_report_collectionfinish(self, config, start_path=None, items=None) -> List[str]:
        lines = []
        for s in self.sets:
            info = self.summary.get(s.marker)
            if info is None:
                continue
            seen = sorted(self._seen.get(s.marker, ()))
            lines.append(
                f"partest opt-in {s.marker}: {info['state']}, {info['deselected']} deselected"
                + (f" (markers met: {', '.join(seen)})" if seen else "")
            )
        return lines

    # Last, so pytest's own ``-m`` handling has already run — and has already turned an
    # unparsable expression into a usage error before this compiles it again.
    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config, items) -> None:
        markexpr = getattr(config.option, "markexpr", "") or ""
        env_on = {s.marker: s.env_enabled() for s in self.sets}
        kept_by_set = {s.marker: 0 for s in self.sets}
        dropped_by_set = {s.marker: 0 for s in self.sets}
        kept, deselected = [], []
        for item in items:
            marks = list(item.iter_markers())
            names = {m.name for m in marks}
            verdicts = []
            for s in self.sets:
                members = {n for n in names if s.covers(n)}
                if not members:
                    continue
                self._seen.setdefault(s.marker, set()).update(members)
                ok = env_on[s.marker] or selected_through(markexpr, marks, s)
                verdicts.append(ok)
                if ok:
                    kept_by_set[s.marker] += 1
                else:
                    dropped_by_set[s.marker] += 1
            if all(verdicts):
                kept.append(item)
            else:
                deselected.append(item)
        self.summary = {
            s.marker: {
                "state": (
                    STATE_ENV if env_on[s.marker]
                    else STATE_MARKEXPR if kept_by_set[s.marker]
                    else STATE_OFF
                ),
                **({"env": s.env} if s.env else {}),
                "deselected": dropped_by_set[s.marker],
            }
            for s in self.sets
        }
        _record(self.summary)
        if deselected:
            config.hook.pytest_deselected(items=deselected)
            items[:] = kept


def _record(summary: Dict[str, Dict[str, Any]]) -> None:
    """Put the per-set decision into the run metadata (unless run metadata is off)."""
    try:
        from partest.call_storage import record_optin
        from partest.pytest_plugin import run_metadata_enabled
    except Exception:
        return
    if run_metadata_enabled():
        record_optin(summary)


def add_ini(parser) -> None:
    parser.addini(INI_NAME, INI_HELP, type="args", default=[])


def configure(config) -> Optional[OptInPlugin]:
    """Register the plugin if the ini option names anything; return it (or ``None``)."""
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
    "OptInSet",
    "parse_optin_markers",
]
