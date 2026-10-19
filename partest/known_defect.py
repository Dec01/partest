"""``@pytest.mark.known_defect("BUG-123")``: a strict xfail that only an assertion can satisfy.

A test written to reproduce a known defect is marked ``xfail`` until the defect is fixed.
``xfail`` counts *any* failure as the expected one — the setup that could not reach the
stand, a fixture that timed out, a ``ConnectionError`` in the body — and reports it as
XFAIL, "the defect is still there", when nothing about the defect was observed. A run where
the stand was down then reads as a run where every known defect was confirmed.

``known_defect`` is narrower::

    @pytest.mark.known_defect("BUG-123", reason="total ignores the discount")
    async def test_total_with_discount(api):
        ...
        assert body["total"] == expected   # this failing is the reproduction

* an ``AssertionError`` raised from the test body (the ``call`` phase) — that is what
  ``assert``, partest's ``check_*`` and a status or schema mismatch in ``make_request``
  raise — is **XFAIL**: the defect reproduced;
* except a status mismatch (:class:`partest.StatusMismatchError`) with a status of a
  gateway rather than the service — 502, 503, 504: the stand did not let the request
  through, the service was not observed. It stays **failed**. A 500 is a reproduction —
  "the server answers 500" is an ordinary defect — and so is a 429: throttling a login or
  a quota is behaviour of the service itself. When the defect *is* one of the gateway
  statuses (an ingress answering 502 because the service falls over), say so in the test,
  and only for that status::

      try:
          await api.make_request(..., expected_status_code=200)
      except StatusMismatchError as err:
          if err.status_code != 502:
              raise
          raise AssertionError(f"BUG-123 reproduced: {err.status_code}") from None

  The set is not configurable yet: where the line belongs is an open question;
* any other exception in the body (a network error, ``httpx``'s timeout, ``KeyError``,
  ``pytest.fail``) stays **failed**, and an error in setup or teardown stays an **error**: the
  defect was not observed. The report carries a ``known_defect`` section that says so;
* a body that passes is **failed** ``[XPASS(strict)]``: the defect did not reproduce — fixed,
  or the test no longer tests it. Remove the marker.

Where the line is drawn is the exception's type, not its meaning. A helper that reports a
timeout as an ``AssertionError`` — :class:`partest.polling.PollTimeout`, Playwright's
``expect`` — reproduces the defect as far as this marker can tell; so does any assertion
from inside the body that is about the environment rather than the service. Keep such waits
out of the body (in a fixture: its failure is an error), or assert what the defect is about.

The defect id is in the XFAIL reason (``-rx`` shows ``XFAIL … - BUG-123: <reason>``), in
``item.user_properties`` as ``("known_defect", "BUG-123")`` — JUnit XML writes it as a
property — and, when allure-pytest is running, as an Allure issue link (an id resolves to a
URL through ``--allure-link-pattern=issue:…/{}``). Report wrappers of other plugins —
allure-pytest, pytest-rerunfailures — see the final verdict: a reproduced defect is an
xfail to them (Allure: skipped, "XFAIL …"; rerunfailures does not re-run it). ``--runxfail``
turns the marker off, as it does for ``xfail``; combining it with ``xfail`` on one test is a
setup error.

Registered by the partest pytest plugin in every session — ``-p no:partest`` removes it, and
``--strict-markers`` then rejects the marker.
"""

from __future__ import annotations

from typing import Tuple

import pytest

MARKER = "known_defect"
MARKER_HELP = (
    "known_defect(id, reason=''): strict xfail for defect <id> that counts only an "
    "AssertionError from the test body as the defect reproducing"
)

#: Status mismatches that say a gateway did not let the request through, not that the
#: service misbehaved. 429 is not here: throttling and quotas are the service's own
#: behaviour. Private: the boundary is an open question and may move.
_STAND_STATUSES = frozenset({502, 503, 504})


def defect_of(mark) -> Tuple[str, str]:
    """``(id, reason)`` from a ``known_defect`` mark; ``TypeError`` when the id is missing."""
    args = list(mark.args)
    defect = args[0] if args else mark.kwargs.get("id")
    reason = mark.kwargs.get("reason", args[1] if len(args) > 1 else "")
    if not isinstance(defect, str) or not defect.strip():
        raise TypeError(
            f"@pytest.mark.{MARKER} needs the defect id as its first argument, "
            f'e.g. @pytest.mark.{MARKER}("BUG-123", reason="...")'
        )
    return defect.strip(), str(reason or "")


def _not_a_reproduction(exc: BaseException) -> str:
    """Why this exception from the body does not reproduce the defect; ``""`` if it does."""
    if not isinstance(exc, AssertionError):
        return (
            f"{type(exc).__name__} is not a reproduction of the defect: only an "
            "AssertionError from the test body counts"
        )
    try:
        from partest.client import StatusMismatchError
    except Exception:  # pragma: no cover - the client is part of the package
        return ""
    status = getattr(exc, "status_code", None)
    if isinstance(exc, StatusMismatchError) and status in _STAND_STATUSES:
        return (
            f"status {status} is not a reproduction of the defect: a gateway did not let the "
            "request through"
        )
    return ""


def _note(item, rep, text: str) -> None:
    """Say why this is not a reproduction: a report section (terminal) and a property
    (``known_defect_note``) — JUnit XML writes properties, not sections, and reads them from
    the item when the test ends."""
    rep.sections.append((MARKER, text))
    prop = (f"{MARKER}_note", text)
    if prop not in item.user_properties:
        item.user_properties.append(prop)
    if prop not in rep.user_properties:  # a teardown report is already built from the item
        rep.user_properties.append(prop)


def _drop_pytest_xfail(item) -> None:
    """Make pytest's own xfail handling ignore this item's xfail mark for the rest of it."""
    try:
        from _pytest.skipping import xfailed_key  # private; pytest is capped below 10
    except Exception:  # pragma: no cover - a moved private name: the failure still stands
        return
    item.stash[xfailed_key] = None


class KnownDefectPlugin:
    """Registered by :mod:`partest.pytest_plugin` in every session."""

    @staticmethod
    def _mark(item):
        if getattr(item.config.option, "runxfail", False):  # absent with -p no:skipping
            return None
        return item.get_closest_marker(MARKER)

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item) -> None:
        mark = self._mark(item)
        if mark is None:
            return
        defect, _ = defect_of(mark)  # a malformed marker is a setup error, not an XFAIL
        if item.get_closest_marker("xfail") is not None:
            raise TypeError(
                f"@pytest.mark.{MARKER} and @pytest.mark.xfail on one test: use one of them"
            )
        if (MARKER, defect) not in item.user_properties:
            item.user_properties.append((MARKER, defect))
        try:
            import allure

            allure.dynamic.issue(defect, name=defect)
        except Exception:  # allure is optional, and may be installed without its plugin
            pass

    # Outermost of the call wrappers, so before pytest's: an xfail added by a fixture
    # (`request.applymarker`) is refused before pytest's xfail can act on it — with
    # `run=False` pytest would not run the body and report "[NOTRUN]" as an XFAIL, which the
    # report hook below cannot undo (pytest's report wrapper reads the exception itself).
    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_runtest_call(self, item):
        if self._mark(item) is not None and item.get_closest_marker("xfail") is not None:
            raise TypeError(
                f"@pytest.mark.{MARKER} and an xfail added at run time on one test: "
                "use one of them"
            )
        return (yield)

    # Innermost of the report wrappers: allure-pytest and pytest-rerunfailures wrap this one
    # and read the report after it has its verdict. pytest's own xfail handling wraps it
    # too, which is why ``pytest.xfail()`` from the body is left for it below.
    @pytest.hookimpl(wrapper=True, trylast=True)
    def pytest_runtest_makereport(self, item, call):
        rep = yield
        mark = self._mark(item)
        if mark is None or rep.skipped:
            return rep
        try:
            defect, reason = defect_of(mark)
        except TypeError:
            return rep
        label = f"{defect}: {reason}" if reason else defect
        # Before the `pytest.xfail()` exit below: an xfail added at run time with `run=False`
        # would otherwise reach the report as pytest's "[NOTRUN]" XFAIL with the defect id.
        if call.when == "call" and item.get_closest_marker("xfail") is not None:
            # Added at run time (``request.applymarker`` in a fixture): the check in setup
            # did not see it. Two markers deciding one outcome is refused here too, and
            # pytest's xfail is told to stand down, or it would turn this into an XFAIL.
            _drop_pytest_xfail(item)
            rep.outcome = "failed"
            rep.longrepr = (
                f"{label} — @pytest.mark.xfail was added to this test at run time "
                "(request.applymarker?): known_defect and xfail on one test cannot both "
                "decide its outcome; use one of them"
            )
            return rep
        if call.excinfo is not None and isinstance(call.excinfo.value, pytest.xfail.Exception):
            return rep  # pytest.xfail() in the body: pytest's own xfail decides
        if call.when != "call":
            if rep.failed:
                _note(item, rep, f"{label} — an error in {call.when} is not a reproduction of the defect")
            return rep
        if call.excinfo is None:
            rep.outcome = "failed"
            rep.longrepr = (
                f"[XPASS(strict)] {label} — the test passed: the defect did not reproduce. "
                f"Fixed? Remove @pytest.mark.{MARKER}."
            )
            return rep
        why = _not_a_reproduction(call.excinfo.value)
        if why:
            _note(item, rep, f"{label} — {why}")
        else:
            rep.outcome = "skipped"
            rep.wasxfail = label
            if not item.config.pluginmanager.has_plugin("skipping"):
                # Without pytest's skipping plugin nobody reads `wasxfail`, and the terminal
                # summary (`-ra`) folds skips from a `(path, lineno, reason)` longrepr only.
                rep.longrepr = (str(item.path), (item.location[1] or 0) + 1, f"XFAIL {label}")
        return rep


def configure(config) -> KnownDefectPlugin:
    """Register the marker and its hooks; called from the plugin's ``pytest_configure``."""
    config.addinivalue_line("markers", MARKER_HELP)
    plugin = KnownDefectPlugin()
    config.pluginmanager.register(plugin, "partest-known-defect")
    return plugin


# Nothing to import: the marker is used through pytest, ``@pytest.mark.known_defect``.
__all__: list = []
