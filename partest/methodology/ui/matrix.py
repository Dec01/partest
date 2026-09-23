"""Surface × check applicability matrix (UI methodology axes A × B).

**Read this before adding a cell.** On the API side every priority comes from a written
methodology, so the matrix there can be dense. Here there is no such source: the only
justification available is "a suite writes this, and it finds defects". So the rule for
this table is the opposite of completeness —

    a cell nobody can justify is ``NA``, not "probably P2".

``NA`` here means *this matrix does not require the check on this surface*, which is a
statement about the evidence, not a ban. A project that knows better requires it anyway;
what it must not do is read a guess as a requirement.

Every non-``NA`` cell below carries its reason on the line. Cells whose only reason would
be "it seems likely" are empty on purpose, and the tempting ones are marked as such, so
that the next reader does not have to rediscover why they were left out.

The priority vocabulary is shared with the API half (``CoveragePriority``) deliberately:
P1 means the same thing in both areas — implement first — and two enums with identical
members would only make a report pick one at random.
"""

from typing import Dict, List

from partest.methodology.api.matrix import CoveragePriority
from partest.methodology.ui.checks import UI_CHECK_SET, UI_CORE_CHECKS
from partest.methodology.ui.checks import UiTestCases as T
from partest.methodology.ui.surfaces import SurfaceType

NA = CoveragePriority.NA
P1 = CoveragePriority.P1
P2 = CoveragePriority.P2
P3 = CoveragePriority.P3


_MATRIX: Dict[SurfaceType, Dict[str, CoveragePriority]] = {
    # The surface the whole axis was mined from, and the only one with evidence for the
    # view-state families. Everything a user configures here is also what breaks here.
    SurfaceType.LIST_TABLE: {
        T.screen_render: P1,
        T.screen_submit: NA,                # a list shows; a row's own form is its own surface
        T.screen_filter: P1,                # a filter that narrows nothing is the classic defect
        T.screen_sort: P1,                  # written in practice, and cheap to assert
        T.screen_columns: P1,               # set and order both: a reordered column breaks exports
        T.screen_paging: P1,                # page two is where off-by-one lives
        T.screen_state_persistence: P1,     # the finding: filters/sorting/columns after a reload
        T.screen_permissions: P1,           # which rows and which row actions a role gets
        T.screen_empty_state: P2,           # a placeholder, not data: wrong here is cosmetic
        T.screen_error_state: P2,           # the list has a working view to fall back to
        T.screen_visual: P3,                # most expensive, most brittle; DOM asserts cover more
    },
    SurfaceType.EDIT_FORM: {
        T.screen_render: P1,                # all fields present: nothing else is assertable
        T.screen_submit: P1,                # what the surface is for: saved, refused, cancelled
        T.screen_filter: NA,
        T.screen_sort: NA,
        T.screen_columns: NA,
        T.screen_paging: NA,
        # NA with a reason: whether a half-filled form survives F5 is a product decision
        # this library has no evidence about. Most applications deliberately drop it.
        T.screen_state_persistence: NA,
        T.screen_permissions: P1,           # read-only vs editable per role is a real branch
        T.screen_empty_state: NA,           # a pristine form is the normal state, not an empty one
        T.screen_error_state: P1,           # a refused save has nowhere else to appear
        T.screen_visual: P3,
    },
    SurfaceType.ENTITY_CARD: {
        T.screen_render: P1,
        T.screen_submit: NA,                # read-only; an action on it opens another surface
        T.screen_filter: NA,
        T.screen_sort: NA,
        T.screen_columns: NA,
        T.screen_paging: NA,
        T.screen_state_persistence: NA,     # nothing on a card is the user's to configure
        T.screen_permissions: P1,           # who sees the card, and which fields on it
        T.screen_empty_state: NA,
        T.screen_error_state: P1,           # a card of an object that failed to load, or is gone
        T.screen_visual: P3,
    },
    SurfaceType.NAV_SHELL: {
        T.screen_render: P1,
        T.screen_submit: NA,
        T.screen_filter: NA,
        T.screen_sort: NA,
        T.screen_columns: NA,
        T.screen_paging: NA,
        # Tempting and empty: a collapsed sidebar surviving a reload is plausible, and
        # there is no evidence any suite checks it. Plausible is not a priority.
        T.screen_state_persistence: NA,
        T.screen_permissions: P1,           # the menu is where a role's surface area is visible
        T.screen_empty_state: NA,
        T.screen_error_state: NA,           # a shell that fails to load is a render failure
        T.screen_visual: P3,                # stable chrome makes the cheapest honest baseline
    },
    SurfaceType.MODAL: {
        T.screen_render: P1,                # it opens, and it closes again
        T.screen_submit: P1,                # confirm does it, cancel does not — classic defect
        T.screen_filter: NA,
        T.screen_sort: NA,
        T.screen_columns: NA,
        T.screen_paging: NA,
        # Not "unproven" but impossible: a reload returns to the surface underneath.
        T.screen_state_persistence: NA,
        # Who may open it is a property of the control that opens it — priced on the
        # parent surface. A dialog with fields of its own is an EDIT_FORM; declare it so.
        T.screen_permissions: NA,
        T.screen_empty_state: NA,
        T.screen_error_state: P1,           # a dialog's own failure has no other place to show
        T.screen_visual: P3,
    },
    SurfaceType.REPORT_VIEW: {
        T.screen_render: P1,
        T.screen_submit: NA,                # parameters are a filter here, not a write
        T.screen_filter: P1,                # a report is its parameters: wrong period, wrong data
        T.screen_sort: NA,
        T.screen_columns: NA,
        T.screen_paging: NA,
        T.screen_state_persistence: NA,     # the chosen period surviving a reload: no evidence yet
        T.screen_permissions: P1,           # aggregates are the data roles are most often denied
        T.screen_empty_state: P1,           # no rows in the period is normal input; charts break
        T.screen_error_state: P2,
        # The one surface where a baseline is the cheapest real assertion: a chart has no
        # text to read, so "it drew something plausible" is only checkable as pixels.
        T.screen_visual: P1,
    },
    # Undeclared surface. Only the check that every surface shares is required — not a
    # generous default like the API's UNKNOWN row, because there the fallback at least
    # knows it is looking at an HTTP operation. Declaring the type is how a real required
    # set appears; this row is not meant to be livable.
    SurfaceType.UNKNOWN: {
        T.screen_render: P1,
        T.screen_submit: NA,
        T.screen_filter: NA,
        T.screen_sort: NA,
        T.screen_columns: NA,
        T.screen_paging: NA,
        T.screen_state_persistence: NA,
        T.screen_permissions: NA,
        T.screen_empty_state: NA,
        T.screen_error_state: NA,
        T.screen_visual: NA,
    },
}


def applicable_checks(surface: SurfaceType) -> Dict[str, CoveragePriority]:
    """Full priority map for a surface, including ``NA`` cells."""
    return dict(_MATRIX[SurfaceType(surface)])


def priority_of(surface: SurfaceType, check: str) -> CoveragePriority:
    """Priority of one cell; raises on an unknown check name.

    A typo must not answer ``NA``: that reads as "the methodology does not ask for it".
    """
    key = (check or "").strip().lower().replace("-", "_")
    if key not in UI_CHECK_SET:
        raise ValueError(
            f"unknown UI check {check!r}; expected one of {sorted(UI_CHECK_SET)}"
        )
    return _MATRIX[SurfaceType(surface)][key]


def required_checks(
    surface: SurfaceType,
    max_priority: CoveragePriority = CoveragePriority.P3,
) -> List[str]:
    """Checks with priority 1..max_priority, in axis-B order (excludes ``NA``)."""
    cells = applicable_checks(surface)
    return [
        check
        for check in UI_CORE_CHECKS
        if cells[check] != NA and int(cells[check]) <= int(max_priority)
    ]


def p1_checks(surface: SurfaceType) -> List[str]:
    """First-priority check set for the surface."""
    return [c for c in UI_CORE_CHECKS if applicable_checks(surface)[c] == P1]


def p2_checks(surface: SurfaceType) -> List[str]:
    """Second-priority check set for the surface."""
    return [c for c in UI_CORE_CHECKS if applicable_checks(surface)[c] == P2]
