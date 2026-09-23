"""UI methodology: surface types, check types, matrix, depth.

Symmetric with :mod:`partest.methodology.api` in shape and deliberately asymmetric in
one place: **there is no classifier and no inference here.** The API half derives axis A
from the OpenAPI specification; no project has a machine-readable description of its
screens, so the surface type is declared by the consumer. ``tests/test_methodology_ui.py``
asserts that absence, so that a later "small helper" cannot drift back into guessing.
"""

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
