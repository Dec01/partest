"""Assertion depth inside a UI check (axis C of the UI methodology).

Four levels, in order. The first two are the UI twins of "status code" and "value
assert" on the API side. The third is the one this axis was written for.

``SURVIVES_RELOAD`` — every other level describes **one** load of a screen. A test that
opens a page, sets a filter and asserts the rows is complete at ``VALUE_CORRECT`` and
still passes while the filter is stored nowhere: the assertion and the state it checks
live inside a single page lifetime. Reloading and asserting again is a different depth,
not a different test, and an ordinary end-to-end run never reaches it because it starts
from a clean profile every time.

``MATCHES_BASELINE`` is last because it is the most expensive and the most fragile, not
because it is the most thorough: a pixel baseline catches what no selector can (a chart),
and fails on what no user would notice (a font hint).
"""

from enum import Enum
from typing import Dict, List

from partest.methodology.ui.checks import _canonical
from partest.methodology.ui.checks import UiTestCases as T


class UiStep(str, Enum):
    ELEMENT_VISIBLE = "element_visible"
    VALUE_CORRECT = "value_correct"
    SURVIVES_RELOAD = "survives_reload"
    MATCHES_BASELINE = "matches_baseline"


UI_STEPS_BY_GROUP: Dict[str, List[UiStep]] = {
    "presence": [UiStep.ELEMENT_VISIBLE],
    "value": [UiStep.VALUE_CORRECT],
    "persistence": [UiStep.SURVIVES_RELOAD],
    "pixel": [UiStep.MATCHES_BASELINE],
}

_DEPTH_ORDER: List[UiStep] = [
    UiStep.ELEMENT_VISIBLE,
    UiStep.VALUE_CORRECT,
    UiStep.SURVIVES_RELOAD,
    UiStep.MATCHES_BASELINE,
]

# The depth a check is not covered below. This is the half of the methodology that says
# "a screenshot of a grid is not a sorting test": a family whose whole point is a value
# is not covered by seeing the element that holds it.
_MINIMUM_DEPTH: Dict[str, UiStep] = {
    T.screen_render: UiStep.ELEMENT_VISIBLE,
    # A submit that only turns a spinner off proves nothing: the result has to be read
    # back, which is a value, not the presence of a success toast.
    T.screen_submit: UiStep.VALUE_CORRECT,
    T.screen_filter: UiStep.VALUE_CORRECT,
    T.screen_sort: UiStep.VALUE_CORRECT,
    T.screen_columns: UiStep.VALUE_CORRECT,
    T.screen_paging: UiStep.VALUE_CORRECT,
    T.screen_state_persistence: UiStep.SURVIVES_RELOAD,
    T.screen_permissions: UiStep.VALUE_CORRECT,
    T.screen_empty_state: UiStep.ELEMENT_VISIBLE,
    T.screen_error_state: UiStep.ELEMENT_VISIBLE,
    T.screen_visual: UiStep.MATCHES_BASELINE,
}


def minimum_depth(check: str) -> UiStep:
    """Shallowest step at which *check* counts as covered; raises on an unknown check."""
    key = _canonical(check)
    if key not in _MINIMUM_DEPTH:
        raise ValueError(
            f"unknown UI check {check!r}; expected one of {sorted(_MINIMUM_DEPTH)}"
        )
    return _MINIMUM_DEPTH[key]


def ui_depth_score(
    element_visible: bool = False,
    value_correct: bool = False,
    survives_reload: bool = False,
    matches_baseline: bool = False,
) -> int:
    """Rough depth score for one UI check (0–4).

    Unlike the API side, nothing in the library observes a browser assertion, so the
    flags come from the suite. The score exists to make "we have a test for it" and
    "the test asserts anything" different numbers in a report.
    """
    score = 0
    if element_visible:
        score += 1
    if value_correct:
        score += 1
    if survives_reload:
        score += 1
    if matches_baseline:
        score += 1
    return score


def reaches_minimum_depth(check: str, reached: UiStep) -> bool:
    """Whether *reached* is deep enough for *check*.

    ``MATCHES_BASELINE`` is not treated as "deeper than" the levels below it: a pixel
    comparison is a different kind of evidence, so it satisfies only the check that asks
    for it. Everything else compares by position in the order.
    """
    required = minimum_depth(check)
    reached = UiStep(reached)
    if required is UiStep.MATCHES_BASELINE:
        return reached is UiStep.MATCHES_BASELINE
    if reached is UiStep.MATCHES_BASELINE:
        return False
    return _DEPTH_ORDER.index(reached) >= _DEPTH_ORDER.index(required)
