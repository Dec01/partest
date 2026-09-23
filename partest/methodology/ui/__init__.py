"""UI methodology: surface types, check types, matrix, depth.

Symmetric with :mod:`partest.methodology.api` in shape and deliberately asymmetric in
one place: **there is no classifier and no inference here.** The API half derives axis A
from the OpenAPI specification; no project has a machine-readable description of its
screens, so the surface type is declared by the consumer. ``tests/test_methodology_ui.py``
asserts that absence, so that a later "small helper" cannot drift back into guessing.
"""

# Shared with the API half on purpose: P1 means "implement first" in both areas, and two
# enums with identical members would only make a report pick one at random. Re-exported
# here because it is the return type of ``priority_of`` and the default of
# ``required_checks`` — a consumer of this area should not have to import from ``api`` to
# read an answer this area gave it.
from partest.methodology.api.matrix import CoveragePriority
from partest.methodology.ui.surfaces import (
    SurfaceType,
    SURFACE_LABELS,
    SURFACE_DESCRIPTIONS,
    surface_label,
)
from partest.methodology.ui.checks import (
    UiTestCases,
    UI_CORE_CHECKS,
    UI_CHECK_SET,
    UI_TYPE_LABELS,
    UI_CHECK_DESCRIPTIONS,
    ui_check_label,
)
from partest.methodology.ui.matrix import (
    applicable_checks,
    priority_of,
    required_checks,
    p1_checks,
    p2_checks,
)
from partest.methodology.ui.steps import (
    UiStep,
    UI_STEPS_BY_GROUP,
    minimum_depth,
    reaches_minimum_depth,
    ui_depth_score,
)

__all__ = [
    "CoveragePriority",
    "SurfaceType",
    "SURFACE_LABELS",
    "SURFACE_DESCRIPTIONS",
    "surface_label",
    "UiTestCases",
    "UI_CORE_CHECKS",
    "UI_CHECK_SET",
    "UI_TYPE_LABELS",
    "UI_CHECK_DESCRIPTIONS",
    "ui_check_label",
    "applicable_checks",
    "priority_of",
    "required_checks",
    "p1_checks",
    "p2_checks",
    "UiStep",
    "UI_STEPS_BY_GROUP",
    "minimum_depth",
    "reaches_minimum_depth",
    "ui_depth_score",
]
