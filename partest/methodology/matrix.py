"""Subtype × test-case applicability matrix (methodology axes A × B)."""

from enum import IntEnum
from typing import Dict, List, Optional, Set

from partest.methodology.subtypes import MethodSubtype
from partest.test_types import TypesTestCases as T


class CoveragePriority(IntEnum):
    """1 = implement first, 2 = next, 3 = later. 0 = not applicable."""

    NA = 0
    P1 = 1
    P2 = 2
    P3 = 3


# Matrix cells: priority or NA. Keys are canonical TC type strings.
# Based on methodology parts 2–6 + operational subtypes.
_MATRIX: Dict[MethodSubtype, Dict[str, CoveragePriority]] = {
    MethodSubtype.GET_STATIC: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P1,
        T.request_permissions: CoveragePriority.NA,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.NA,
        T.request_env_list: CoveragePriority.NA,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.NA,
        T.request_not_found: CoveragePriority.P3,
        T.request_extra_data: CoveragePriority.NA,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.GET_DYNAMIC: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,  # vertical lives on write methods
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.NA,
        T.request_env_list: CoveragePriority.P2,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.NA,
        T.request_not_found: CoveragePriority.P1,
        T.request_extra_data: CoveragePriority.NA,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.GET_LIST: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.NA,
        T.request_env_list: CoveragePriority.P2,
        T.request_params: CoveragePriority.P2,
        T.request_elements: CoveragePriority.NA,
        T.request_not_found: CoveragePriority.NA,
        T.request_extra_data: CoveragePriority.NA,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.GET_BY_PARENT: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.NA,
        T.request_env_list: CoveragePriority.NA,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.NA,
        T.request_not_found: CoveragePriority.P1,
        T.request_extra_data: CoveragePriority.NA,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.GET_BY_SELF: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.NA,
        T.request_env_list: CoveragePriority.NA,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.NA,
        T.request_not_found: CoveragePriority.NA,
        T.request_extra_data: CoveragePriority.NA,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.GET_EXTERNAL_ID: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.NA,
        T.request_env_list: CoveragePriority.NA,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.NA,
        T.request_not_found: CoveragePriority.P1,
        T.request_extra_data: CoveragePriority.NA,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.POST_CREATE: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.P1,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.P1,
        T.request_env_list: CoveragePriority.P2,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.P1,
        T.request_not_found: CoveragePriority.NA,
        T.request_extra_data: CoveragePriority.P1,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.POST_UPLOAD: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.P1,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.P1,
        T.request_env_list: CoveragePriority.NA,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.P1,
        T.request_not_found: CoveragePriority.NA,
        T.request_extra_data: CoveragePriority.P2,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.POST_CREATE_TO_OBJECT: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.P1,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.P1,
        T.request_env_list: CoveragePriority.NA,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.P1,
        T.request_not_found: CoveragePriority.P1,
        T.request_extra_data: CoveragePriority.P1,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.POST_FILTER_LIST: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.P1,
        T.request_env_list: CoveragePriority.P2,
        T.request_params: CoveragePriority.P1,
        T.request_elements: CoveragePriority.P2,
        T.request_not_found: CoveragePriority.NA,
        T.request_extra_data: CoveragePriority.P2,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.PATCH_OBJECT: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.P1,
        T.request_incorrect_body: CoveragePriority.P1,
        T.request_env_list: CoveragePriority.P2,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.P1,
        T.request_not_found: CoveragePriority.P1,
        T.request_extra_data: CoveragePriority.P1,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.PATCH_ELEM: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.P1,
        T.request_incorrect_body: CoveragePriority.P1,
        T.request_env_list: CoveragePriority.NA,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.P1,
        T.request_not_found: CoveragePriority.P1,
        T.request_extra_data: CoveragePriority.P1,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.PUT_OBJECT: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.P1,
        T.request_incorrect_body: CoveragePriority.P1,
        T.request_env_list: CoveragePriority.P2,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.P1,
        T.request_not_found: CoveragePriority.P1,
        T.request_extra_data: CoveragePriority.P1,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.DELETE_OBJECT: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.NA,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.NA,
        T.request_env_list: CoveragePriority.NA,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.NA,
        T.request_not_found: CoveragePriority.P1,
        T.request_extra_data: CoveragePriority.NA,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.DELETE_PHYSICAL: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.NA,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.NA,
        T.request_env_list: CoveragePriority.NA,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.NA,
        T.request_not_found: CoveragePriority.P1,
        T.request_extra_data: CoveragePriority.NA,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.DELETE_SOFT: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.NA,
        T.request_env_list: CoveragePriority.NA,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.NA,
        T.request_not_found: CoveragePriority.P1,
        T.request_extra_data: CoveragePriority.NA,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.DELETE_BLOCKED: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.NA,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.NA,
        T.request_update_object: CoveragePriority.NA,
        T.request_incorrect_body: CoveragePriority.NA,
        T.request_env_list: CoveragePriority.NA,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.NA,
        T.request_not_found: CoveragePriority.P2,
        T.request_extra_data: CoveragePriority.NA,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.ACTION: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P1,
        T.request_new_object: CoveragePriority.P2,
        T.request_update_object: CoveragePriority.P2,
        T.request_incorrect_body: CoveragePriority.P1,
        T.request_env_list: CoveragePriority.NA,
        T.request_params: CoveragePriority.NA,
        T.request_elements: CoveragePriority.P1,
        T.request_not_found: CoveragePriority.P1,
        T.request_extra_data: CoveragePriority.P1,
        T.request_not_allowed: CoveragePriority.P3,
    },
    MethodSubtype.UNKNOWN: {
        T.request_default: CoveragePriority.P1,
        T.request_compare_benchmark: CoveragePriority.P2,
        T.request_permissions: CoveragePriority.P2,
        T.request_new_object: CoveragePriority.P2,
        T.request_update_object: CoveragePriority.P2,
        T.request_incorrect_body: CoveragePriority.P2,
        T.request_env_list: CoveragePriority.P3,
        T.request_params: CoveragePriority.P2,
        T.request_elements: CoveragePriority.P2,
        T.request_not_found: CoveragePriority.P2,
        T.request_not_allowed: CoveragePriority.P3,
        T.request_extra_data: CoveragePriority.P3,
    },
}


# LIB-BPLUS: optional P2 cells — never promote to P1 (coverage % stays P1-only).
_BPLUS_P2: Dict[MethodSubtype, tuple] = {
    MethodSubtype.GET_LIST: (
        T.request_list_visibility,
        T.request_ownership_filter,
    ),
    MethodSubtype.GET_DYNAMIC: (T.request_ownership_filter,),
    MethodSubtype.GET_BY_PARENT: (
        T.request_child_fk,
        T.request_parent_constraint,
        T.request_multi_child,
    ),
    MethodSubtype.GET_BY_SELF: (T.request_ownership_filter,),
    MethodSubtype.POST_CREATE: (
        T.request_cross_field,
        T.request_server_defaults,
        T.request_author_integrity,
    ),
    MethodSubtype.POST_CREATE_TO_OBJECT: (
        T.request_cross_field,
        T.request_server_defaults,
        T.request_parent_constraint,
    ),
    MethodSubtype.POST_UPLOAD: (T.request_cross_field,),
    MethodSubtype.PATCH_OBJECT: (
        T.request_partial_update,
        T.request_unchanged_fields,
        T.request_cross_field,
        T.request_idempotency,
    ),
    MethodSubtype.PATCH_ELEM: (
        T.request_partial_update,
        T.request_unchanged_fields,
        T.request_cross_field,
    ),
    MethodSubtype.PUT_OBJECT: (
        T.request_unchanged_fields,
        T.request_cross_field,
        T.request_idempotency,
        T.request_contract_mismatch,
    ),
    MethodSubtype.DELETE_OBJECT: (
        T.request_lifecycle_delete,
        T.request_parent_constraint,
    ),
    MethodSubtype.DELETE_PHYSICAL: (
        T.request_lifecycle_delete,
        T.request_parent_constraint,
    ),
    MethodSubtype.DELETE_SOFT: (
        T.request_lifecycle_delete,
        T.request_state_machine,
    ),
    MethodSubtype.DELETE_BLOCKED: (
        T.request_parent_constraint,
        T.request_child_fk,
    ),
    MethodSubtype.ACTION: (
        T.request_state_machine,
        T.request_user_journey,
        T.request_contract_mismatch,
    ),
}

for _subtype, _types in _BPLUS_P2.items():
    _cells = _MATRIX.setdefault(_subtype, {})
    for _tc in _types:
        _cells.setdefault(_tc, CoveragePriority.P2)


def applicable_test_cases(subtype: MethodSubtype) -> Dict[str, CoveragePriority]:
    """Return full priority map for subtype (including NA)."""
    return dict(_MATRIX.get(subtype, _MATRIX[MethodSubtype.UNKNOWN]))


def required_test_cases(
    subtype: MethodSubtype,
    max_priority: CoveragePriority = CoveragePriority.P3,
) -> List[str]:
    """TC types with priority 1..max_priority (excludes NA)."""
    cells = applicable_test_cases(subtype)
    out = [
        tc
        for tc, prio in cells.items()
        if prio != CoveragePriority.NA and int(prio) <= int(max_priority)
    ]
    return out


def p1_test_cases(subtype: MethodSubtype) -> List[str]:
    """First-priority TC set for the subtype."""
    return [
        tc
        for tc, prio in applicable_test_cases(subtype).items()
        if prio == CoveragePriority.P1
    ]


def p2_test_cases(subtype: MethodSubtype) -> List[str]:
    """Optional B+ / second-priority TC set (does not affect default coverage %)."""
    return [
        tc
        for tc, prio in applicable_test_cases(subtype).items()
        if prio == CoveragePriority.P2
    ]


def normalize_executed_types(raw_types: List[str]) -> Set[str]:
    """Map any recorded type (legacy or canonical) to canonical names."""
    from partest.test_types import canonicalize_type

    return {canonicalize_type(t) for t in raw_types if t}
