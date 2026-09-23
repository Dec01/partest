"""UI check types (axis B of the UI methodology).

Eleven families, and the list is short for a reason: each one is something that is
**written as a test in a real suite**, not something that sounds plausible on a
whiteboard. The API side could afford a large axis B because the methodology it came from
priced every cell; here the only evidence is practice, so a family nobody writes is not
named.

``screen_state_persistence`` is the family this axis was extended for. A suite that
starts every test from a clean browser profile never checks the second load of a screen,
so "the filter the user set is still set after F5" has nowhere to live — and the defect
it catches (view state written nowhere, or written and never read back) is invisible to
every other family here.

``screen_submit`` is the one family here that practice did not hand over ready-made, and
it is in for a structural reason rather than a hopeful one. The ten mined families are
all about *presenting* data — they come from a methodology written around a list screen.
Without a family for the act a form exists to perform, a create/edit form and a read-only
card require exactly the same checks, and axis A's own rule ("a type that does not change
the required set is not a type") would have forced one of the two out of the vocabulary.
A form and a card are not the same surface, so the missing family was the defect, not the
surface type.
"""

from typing import Dict, FrozenSet, Tuple


class UiTestCases:
    """Canonical UI check names (axis B).

    Plain string constants, like :class:`partest.test_types.TypesTestCases` — a suite
    passes them as ``check=`` / tags / Allure stories, so they have to survive being
    written into a report and read back.
    """

    screen_render = "screen_render"
    screen_submit = "screen_submit"
    screen_filter = "screen_filter"
    screen_sort = "screen_sort"
    screen_columns = "screen_columns"
    screen_paging = "screen_paging"
    screen_state_persistence = "screen_state_persistence"
    screen_permissions = "screen_permissions"
    screen_empty_state = "screen_empty_state"
    screen_error_state = "screen_error_state"
    screen_visual = "screen_visual"


UI_CORE_CHECKS: Tuple[str, ...] = (
    UiTestCases.screen_render,
    UiTestCases.screen_submit,
    UiTestCases.screen_filter,
    UiTestCases.screen_sort,
    UiTestCases.screen_columns,
    UiTestCases.screen_paging,
    UiTestCases.screen_state_persistence,
    UiTestCases.screen_permissions,
    UiTestCases.screen_empty_state,
    UiTestCases.screen_error_state,
    UiTestCases.screen_visual,
)

UI_CHECK_SET: FrozenSet[str] = frozenset(UI_CORE_CHECKS)

UI_TYPE_LABELS: Dict[str, str] = {
    UiTestCases.screen_render: "ScreenRender",
    UiTestCases.screen_submit: "ScreenSubmit",
    UiTestCases.screen_filter: "ScreenFilter",
    UiTestCases.screen_sort: "ScreenSort",
    UiTestCases.screen_columns: "ScreenColumns",
    UiTestCases.screen_paging: "ScreenPaging",
    UiTestCases.screen_state_persistence: "ScreenStatePersistence",
    UiTestCases.screen_permissions: "ScreenPermissions",
    UiTestCases.screen_empty_state: "ScreenEmptyState",
    UiTestCases.screen_error_state: "ScreenErrorState",
    UiTestCases.screen_visual: "ScreenVisual",
}

# What the family covers. Read this before deciding a cell is missing: several checks a
# suite writes separately belong to one family here (a filter by date and a filter by
# status are both ``screen_filter``).
UI_CHECK_DESCRIPTIONS: Dict[str, str] = {
    UiTestCases.screen_render: "the surface loads and its expected elements are there",
    UiTestCases.screen_submit: (
        "the action the surface exists for: valid input is accepted and the result is "
        "shown, invalid input is refused and said so, cancelling changes nothing"
    ),
    UiTestCases.screen_filter: "a filter narrows what is shown, and to the right subset",
    UiTestCases.screen_sort: "sorting reorders rows, in the direction asked for",
    UiTestCases.screen_columns: "the column set and its order are what the surface promises",
    UiTestCases.screen_paging: "page size, page switching, and the total the surface reports",
    UiTestCases.screen_state_persistence: (
        "view state the user configured — filters, sorting, columns, page size — is still "
        "in effect after a reload of the same screen"
    ),
    UiTestCases.screen_permissions: "what a role is allowed to see and to do on this surface",
    UiTestCases.screen_empty_state: (
        "nothing to show is shown as nothing to show, not as a broken screen"
    ),
    UiTestCases.screen_error_state: "a failed load or a refused action is reported to the user",
    UiTestCases.screen_visual: "the rendering matches an approved baseline",
}


def _canonical(check: str) -> str:
    """How this area spells a check name: trimmed, lower case, dashes as underscores.

    One function rather than one copy per module. ``screen-render`` reaching the matrix
    and ``screen-render`` reaching the depth table have to become the same string, and
    three private copies of the same expression is how they stop doing that.
    """
    return (check or "").strip().lower().replace("-", "_")


def ui_check_label(check: str) -> str:
    """Human label for a UI check name; raises on an unknown name.

    Unknown names raise instead of passing through: on the API side a stray type string
    degrades a percentage, here it would silently read as "not applicable" and remove a
    required check from the plan.
    """
    key = _canonical(check)
    if key not in UI_TYPE_LABELS:
        raise ValueError(
            f"unknown UI check {check!r}; expected one of {sorted(UI_CHECK_SET)}"
        )
    return UI_TYPE_LABELS[key]
