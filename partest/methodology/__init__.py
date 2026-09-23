"""Coverage methodology, in two areas: ``api`` and ``ui``.

The two halves have the same shape — axis A (what this thing is), axis B (what is being
checked), axis C (how deep the check goes) and an A × B matrix of priorities — and one
structural difference that is not an oversight:

* ``partest.methodology.api`` derives axis A from the OpenAPI specification, so it has a
  classifier and type inference.
* ``partest.methodology.ui`` has neither. No project ships a machine-readable description
  of its screens, so the surface type is **declared by the consumer**.

Names re-exported here are flat and unprefixed for the API half (they predate the split
and did not move) and ``ui``/``Ui``-prefixed for the UI half. The submodules moved in
2.0.0: ``partest.methodology.subtypes`` is now ``partest.methodology.api.subtypes``, and
so on — the table of old and new paths is in the migration guide. The old paths still
import, resolving to the same module objects and warning once each; they are removed in
3.0.0. See ``partest/methodology/_moved.py``.

``active_overrides`` joined this list in 2.0.0. It was public and called by suites from
the day overrides existed, but only ever through a deep import, so a consumer had no
spelling of it that survived a move of the module underneath.
"""

from partest.methodology.api import (
    CoveragePriority,
    InferResult,
    MethodSubtype,
    STEPS_BY_GROUP,
    SUBTYPE_LABELS,
    TestStep,
    active_overrides,
    applicable_test_cases,
    classify_endpoint,
    classify_path_object,
    infer_test_type,
    p1_test_cases,
    p2_test_cases,
    required_test_cases,
)
from partest.methodology.ui import (
    SURFACE_DESCRIPTIONS,
    SURFACE_LABELS,
    SurfaceType,
    UI_CHECK_DESCRIPTIONS,
    UI_CHECK_SET,
    UI_CORE_CHECKS,
    UI_STEPS_BY_GROUP,
    UI_TYPE_LABELS,
    UiStep,
    UiTestCases,
    applicable_checks,
    minimum_depth,
    p1_checks,
    p2_checks,
    priority_of,
    reaches_minimum_depth,
    required_checks,
    ui_check_label,
    ui_depth_score,
    surface_label,
)

__all__ = [
    # --- API methodology ---
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
    "active_overrides",
    # --- UI methodology ---
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
