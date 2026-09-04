"""Assert steps inside a test case (axis C)."""

from enum import Enum
from typing import Dict, List


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


def depth_score(
    has_status: bool = False,
    has_validate_model: bool = False,
    has_value_assert: bool = False,
) -> int:
    """Rough depth score for a recorded call (0–3).

    Value asserts live in consumer code; library only sees status + validate_model.
    """
    score = 0
    if has_status:
        score += 1
    if has_validate_model:
        score += 1
    if has_value_assert:
        score += 1
    return score
