"""UI methodology: surfaces, checks, matrix, depth — and the two absences that are decisions.

The UI half is not a copy of the API half. Two things are deliberately missing and are
asserted as missing here, because both are the kind of thing a later change adds back "as
a small helper": a classifier (there is no machine-readable source to classify from) and
a generous fallback row (a guess read as a requirement is worse than a gap).
"""

from __future__ import annotations

import pytest

from partest.methodology import CoveragePriority
from partest.methodology.ui import matrix as ui_matrix
from partest.methodology.ui import steps as ui_steps
from partest.methodology.ui.checks import (
    UI_CHECK_DESCRIPTIONS,
    UI_CORE_CHECKS,
    UI_TYPE_LABELS,
    ui_check_label,
)
from partest.methodology.ui.checks import UiTestCases as U
from partest.methodology.ui.matrix import (
    applicable_checks,
    p1_checks,
    p2_checks,
    priority_of,
    required_checks,
)
from partest.methodology.ui.steps import (
    UI_STEPS_BY_GROUP,
    UiStep,
    minimum_depth,
    reaches_minimum_depth,
    ui_depth_score,
)
from partest.methodology.ui.surfaces import (
    SURFACE_DESCRIPTIONS,
    SURFACE_LABELS,
    SurfaceType,
    surface_label,
)

# --- Axis A ---------------------------------------------------------------


def test_every_surface_has_a_label_and_a_description():
    for surface in SurfaceType:
        assert SURFACE_LABELS[surface].strip()
        assert SURFACE_DESCRIPTIONS[surface].strip()
    assert surface_label(SurfaceType.LIST_TABLE) == "LIST / TABLE"


def test_surface_values_are_unique_strings():
    values = [s.value for s in SurfaceType]
    assert len(values) == len(set(values))
    assert all(v == v.lower() for v in values)


def test_a_surface_type_earns_its_place_by_changing_the_required_set():
    """Axis A exists to change the required checks; two identical rows mean one is noise."""
    rows = {
        surface: tuple(sorted(required_checks(surface)))
        for surface in SurfaceType
        if surface is not SurfaceType.UNKNOWN
    }
    duplicates = [s for s, row in rows.items() if list(rows.values()).count(row) > 1]
    assert not duplicates, f"surfaces with an identical required set: {duplicates}"


# --- Axis B ---------------------------------------------------------------


def test_state_persistence_is_part_of_the_vocabulary():
    """The family the project's own methodology had no place for. It is the point of axis B."""
    assert U.screen_state_persistence in UI_CORE_CHECKS
    assert UI_TYPE_LABELS[U.screen_state_persistence] == "ScreenStatePersistence"


def test_a_form_and_a_card_are_told_apart_by_the_submit_family():
    """Why axis B has a family the mined list did not: without it these two rows coincide.

    The ten families mined from practice all describe *presenting* data, because they come
    from a methodology written around a list screen. A form differs from a read-only card
    by the act it performs, so that act needs a family — otherwise axis A's own rule would
    force one of the two surface types out.
    """
    assert priority_of(SurfaceType.EDIT_FORM, U.screen_submit) == CoveragePriority.P1
    assert priority_of(SurfaceType.ENTITY_CARD, U.screen_submit) == CoveragePriority.NA
    assert set(required_checks(SurfaceType.EDIT_FORM)) != set(
        required_checks(SurfaceType.ENTITY_CARD)
    )


def test_every_check_has_a_label_and_an_unknown_one_raises():
    for check in UI_CORE_CHECKS:
        assert UI_TYPE_LABELS[check].startswith("Screen")
    assert ui_check_label("screen-render") == "ScreenRender"
    with pytest.raises(ValueError):
        ui_check_label("screen_rendering")


def test_axis_b_is_enumerated_the_same_way_everywhere():
    """The eleven names are written out in four places; a gap in any one is a defect.

    `_MINIMUM_DEPTH` is the expensive one: a family present in the matrix but missing
    from the depth table answers "unknown UI check" for a check the methodology itself
    requires. `UI_CHECK_DESCRIPTIONS` is the cheap one — a family with no description is
    a legend with a hole in it — and neither was checked by anything before.
    """
    expected = set(UI_CORE_CHECKS)

    assert {c.strip() for c in expected} == expected, "a name with whitespace in it"
    assert len(UI_CORE_CHECKS) == len(expected), "a name is listed twice in axis B"
    assert expected == {
        value
        for name, value in vars(U).items()
        if not name.startswith("_") and isinstance(value, str)
    }, "UiTestCases and UI_CORE_CHECKS disagree about the vocabulary"

    for name, table in (
        ("UI_TYPE_LABELS", UI_TYPE_LABELS),
        ("UI_CHECK_DESCRIPTIONS", UI_CHECK_DESCRIPTIONS),
        ("_MINIMUM_DEPTH", ui_steps._MINIMUM_DEPTH),
    ):
        assert set(table) == expected, (
            f"{name} is out of step with axis B: "
            f"missing {sorted(expected - set(table))}, extra {sorted(set(table) - expected)}"
        )


def test_every_check_answers_the_three_questions_asked_of_it():
    """The dictionaries above are reachable through the functions that read them."""
    for check in UI_CORE_CHECKS:
        assert ui_check_label(check)
        assert UI_CHECK_DESCRIPTIONS[check].strip()
        assert minimum_depth(check) in UiStep
        for surface in SurfaceType:
            assert priority_of(surface, check) in CoveragePriority


def test_a_check_name_is_canonicalised_the_same_way_on_every_road():
    """Three copies of one expression is how two roads start disagreeing."""
    spelling = "  Screen-State_Persistence  "

    assert ui_check_label(spelling) == "ScreenStatePersistence"
    assert priority_of(SurfaceType.LIST_TABLE, spelling) == CoveragePriority.P1
    assert minimum_depth(spelling) is UiStep.SURVIVES_RELOAD


# --- Axis A × B -----------------------------------------------------------


def test_matrix_prices_every_check_on_every_surface():
    for surface in SurfaceType:
        cells = applicable_checks(surface)
        assert set(cells) == set(UI_CORE_CHECKS), f"{surface} has an incomplete row"


def test_list_table_requires_state_persistence_as_p1():
    """The finding from practice: view state has to survive a reload of the same screen."""
    assert priority_of(SurfaceType.LIST_TABLE, U.screen_state_persistence) == CoveragePriority.P1
    assert U.screen_state_persistence in p1_checks(SurfaceType.LIST_TABLE)


def test_a_modal_cannot_persist_state_so_the_cell_is_na():
    """Not "unproven" but impossible — a reload returns to the surface underneath."""
    assert priority_of(SurfaceType.MODAL, U.screen_state_persistence) == CoveragePriority.NA
    assert U.screen_state_persistence not in required_checks(SurfaceType.MODAL)


def test_view_state_families_belong_to_the_list_surface_only():
    """Columns, sorting and paging are what makes a list a list."""
    for check in (U.screen_columns, U.screen_sort, U.screen_paging):
        required_on = [
            s for s in SurfaceType if priority_of(s, check) != CoveragePriority.NA
        ]
        assert required_on == [SurfaceType.LIST_TABLE], f"{check} priced on {required_on}"


def test_a_report_is_the_one_surface_where_a_baseline_is_p1():
    """A chart has no text to assert, so pixels are the cheapest real evidence there."""
    p1_visual = [s for s in SurfaceType if priority_of(s, U.screen_visual) == CoveragePriority.P1]
    assert p1_visual == [SurfaceType.REPORT_VIEW]


def test_priority_of_raises_on_a_typo_instead_of_answering_na():
    """`NA` reads as "the methodology does not ask for it" — a typo must not say that."""
    with pytest.raises(ValueError):
        priority_of(SurfaceType.LIST_TABLE, "screen_filters")


def test_required_checks_respects_the_priority_ceiling():
    p1_only = required_checks(SurfaceType.LIST_TABLE, CoveragePriority.P1)
    everything = required_checks(SurfaceType.LIST_TABLE)
    assert set(p1_only) == set(p1_checks(SurfaceType.LIST_TABLE))
    assert set(p1_only) < set(everything)
    assert set(p2_checks(SurfaceType.LIST_TABLE)) <= set(everything)
    assert U.screen_visual in everything and U.screen_visual not in p1_only


def test_required_checks_keeps_axis_b_order():
    order = [c for c in UI_CORE_CHECKS if c in set(required_checks(SurfaceType.LIST_TABLE))]
    assert required_checks(SurfaceType.LIST_TABLE) == order


def test_the_matrix_stays_small_and_honest():
    """At least half the table is NA, and that is the intended shape, not a gap.

    A guard against the natural drift of such a table: once a column exists, filling it
    in reads like progress. Here a cell without a reason is the opposite of progress.
    """
    cells = [
        priority_of(s, c)
        for s in SurfaceType
        if s is not SurfaceType.UNKNOWN
        for c in UI_CORE_CHECKS
    ]
    na = sum(1 for p in cells if p == CoveragePriority.NA)
    assert na >= len(cells) / 2, f"only {na} of {len(cells)} cells are NA"


def test_an_undeclared_surface_gets_the_floor_not_a_generous_default():
    assert required_checks(SurfaceType.UNKNOWN) == [U.screen_render]


def test_applicable_checks_returns_a_copy():
    cells = applicable_checks(SurfaceType.MODAL)
    cells[U.screen_visual] = CoveragePriority.P1
    assert priority_of(SurfaceType.MODAL, U.screen_visual) == CoveragePriority.P3


# --- Axis C ---------------------------------------------------------------


def test_depth_has_the_reload_level_between_value_and_baseline():
    assert [s.value for s in UiStep] == [
        "element_visible",
        "value_correct",
        "survives_reload",
        "matches_baseline",
    ]
    assert UI_STEPS_BY_GROUP["persistence"] == [UiStep.SURVIVES_RELOAD]


def test_state_persistence_is_not_covered_by_a_value_assert():
    """Every other level describes one load of the screen; this one needs the second."""
    assert minimum_depth(U.screen_state_persistence) is UiStep.SURVIVES_RELOAD
    assert not reaches_minimum_depth(U.screen_state_persistence, UiStep.VALUE_CORRECT)
    assert reaches_minimum_depth(U.screen_state_persistence, UiStep.SURVIVES_RELOAD)


def test_seeing_an_element_is_not_a_filter_test():
    assert minimum_depth(U.screen_filter) is UiStep.VALUE_CORRECT
    assert not reaches_minimum_depth(U.screen_filter, UiStep.ELEMENT_VISIBLE)
    assert reaches_minimum_depth(U.screen_filter, UiStep.VALUE_CORRECT)


def test_a_baseline_is_different_evidence_not_deeper_evidence():
    assert not reaches_minimum_depth(U.screen_sort, UiStep.MATCHES_BASELINE)
    assert reaches_minimum_depth(U.screen_visual, UiStep.MATCHES_BASELINE)
    assert not reaches_minimum_depth(U.screen_visual, UiStep.VALUE_CORRECT)


def test_minimum_depth_rejects_an_unknown_check():
    with pytest.raises(ValueError):
        minimum_depth("screen_renderr")


def test_depth_score_counts_the_four_levels():
    assert ui_depth_score() == 0
    assert ui_depth_score(element_visible=True) == 1
    assert ui_depth_score(element_visible=True, value_correct=True) == 2
    assert ui_depth_score(True, True, True, True) == 4


# --- The decisions, asserted as code -------------------------------------


def test_the_ui_half_has_no_classifier_and_no_inference():
    """No project has a machine-readable description of its screens.

    The surface type is declared by the consumer. A helper that guesses it from markup is
    research with unpredictable accuracy and was not ordered — and a wrong guess here
    swaps in the required set of another kind of screen, silently.
    """
    import partest.methodology.ui as ui_pkg

    offenders = [
        name
        for name in dir(ui_pkg)
        if any(word in name.lower() for word in ("classif", "infer", "detect", "guess"))
    ]
    assert not offenders, f"the UI methodology must not derive the surface type: {offenders}"
    assert not hasattr(ui_matrix, "classify_surface")


def test_the_facade_exports_both_areas_and_keeps_the_api_names():
    import partest.methodology as m

    for name in (
        "MethodSubtype",
        "SUBTYPE_LABELS",
        "CoveragePriority",
        "applicable_test_cases",
        "required_test_cases",
        "p1_test_cases",
        "p2_test_cases",
        "classify_endpoint",
        "classify_path_object",
        "InferResult",
        "infer_test_type",
        "TestStep",
        "STEPS_BY_GROUP",
    ):
        assert hasattr(m, name), f"the move dropped {name} from the facade"
    for name in ("SurfaceType", "UiTestCases", "UiStep", "required_checks", "priority_of"):
        assert hasattr(m, name)


def test_the_ui_area_exports_the_priority_it_answers_with():
    """``priority_of`` returns one and ``required_checks`` defaults to one.

    A consumer of the UI area had to import it from ``methodology.api`` to name the type
    of a value this area handed it — which reads as though the vocabulary were borrowed
    rather than shared.
    """
    import partest.methodology.ui as ui_pkg

    assert "CoveragePriority" in ui_pkg.__all__
    assert ui_pkg.CoveragePriority is CoveragePriority


# The old ``partest.methodology.<name>`` paths were removed outright while 2.0.0 was being
# prepared, and a test here asserted the ``ImportError``. The decision was reversed before
# publication — see ``tests/test_methodology_aliases.py``, which now owns that question, and
# the reasoning in ``CHANGELOG.md``. The API half's compatibility does not belong in the UI
# file either way.


def test_the_ui_methodology_carries_no_product_domain():
    """Axis B names behaviours, not a project's entities, columns or roles."""
    from pathlib import Path

    import partest.methodology.ui as ui_pkg

    root = Path(ui_pkg.__file__).resolve().parent
    modules = sorted(root.glob("*.py"))
    # The premise: the walk read the package and the four modules the UI methodology is made
    # of — the same four this file imports at the top. Without it an empty glob (a moved
    # root, a narrowed mask) makes the loop below assert nothing and report no offenders.
    assert {"__init__", "surfaces", "checks", "matrix", "steps"} <= {m.stem for m in modules}, (
        f"the walk over {root} found {[m.name for m in modules]}, not the UI methodology"
    )

    for module in modules:
        text = module.read_text(encoding="utf-8").lower()
        assert "http://" not in text and "https://" not in text, module.name
        for word in ("admin", "manager", "operator"):
            assert word not in text, f"{module.name} names a role: {word}"
