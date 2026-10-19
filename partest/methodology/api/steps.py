"""Assert steps inside a test case (axis C)."""

from enum import Enum
from typing import Dict, List

__all__ = ["TestStep", "STEPS_BY_GROUP", "call_depth", "depth_score"]


class TestStep(str, Enum):
    STATUS_CODE = "status_code"
    COMPARE_BODY_SWAGGER = "compare_body_swagger"
    VALIDATE_BODY_SCHEME = "validate_body_scheme"
    GET_ELEMENT = "get_element"
    COMPARE_BENCHMARK = "compare_benchmark"
    COMPARE_BOUNDARY = "compare_boundary"


STEPS_BY_GROUP: Dict[str, List[TestStep]] = {
    "alive": [TestStep.STATUS_CODE],
    "form": [TestStep.COMPARE_BODY_SWAGGER, TestStep.VALIDATE_BODY_SCHEME],
    "value": [TestStep.GET_ELEMENT, TestStep.COMPARE_BENCHMARK, TestStep.COMPARE_BOUNDARY],
}


def call_depth(has_status: bool = False, has_validate_model: bool = False) -> int:
    """How deep a tracked call asked to be checked: 0 — nothing, 1 — status, 2 — schema.

    Steps go in order, status → schema: ``make_request`` validates the body only after it
    has checked ``expected_status_code``, so a ``validate_model`` without a status check is
    no check at all and adds nothing. This is what a call *asked for* (the arguments it was
    given), not what a test asserted afterwards.
    """
    if not has_status:
        return 0
    return 2 if has_validate_model else 1


def depth_score(
    has_status: bool = False,
    has_validate_model: bool = False,
    has_value_assert: bool = False,
) -> int:
    """Rough depth score for a recorded call (0–3): :func:`call_depth` plus a value assert.

    Value asserts live in consumer code; library only sees status + validate_model.
    """
    return call_depth(has_status, has_validate_model) + (1 if has_value_assert else 0)
