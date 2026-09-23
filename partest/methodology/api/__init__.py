"""API methodology: subtypes, TC types, matrix, inference, steps.

Everything here is derived from a machine-readable source — the OpenAPI specification —
which is what makes a classifier possible at all. The UI half (``partest.methodology.ui``)
has no such source and therefore no classifier.
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
]
