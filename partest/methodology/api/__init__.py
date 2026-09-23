"""API methodology: subtypes, TC types, matrix, inference, steps.

Everything here is derived from a machine-readable source — the OpenAPI specification —
which is what makes a classifier possible at all. The UI half (``partest.methodology.ui``)
has no such source and therefore no classifier.

``active_overrides`` is re-exported although the rest of ``overrides`` is not: it is the one
function in that module a *suite* calls — to assert that its `subtype_overrides` reached the
library — while the setters are called by the harness itself, from
``partest.coverage``, and a suite that calls them is fighting its own configuration.
"""

from partest.methodology.api.subtypes import MethodSubtype, SUBTYPE_LABELS
from partest.methodology.api.matrix import (
    CoveragePriority,
    applicable_test_cases,
    required_test_cases,
    p1_test_cases,
    p2_test_cases,
)
from partest.methodology.api.classifier import classify_endpoint, classify_path_object
from partest.methodology.api.inference import InferResult, infer_test_type
from partest.methodology.api.steps import TestStep, STEPS_BY_GROUP
from partest.methodology.api.overrides import active_overrides

__all__ = [
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
]
