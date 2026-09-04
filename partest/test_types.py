"""Test-case type vocabulary (axis B) with methodology names and legacy aliases."""

from __future__ import annotations

import re
from typing import Dict, FrozenSet, Optional


class TypesTestCases:
    """Canonical coverage types + backward-compatible short aliases.

    Canonical names follow the coverage methodology (Request*).
    Legacy short names from partest <1.0 remain valid and map via
    :func:`canonicalize_type`.
    """

    # --- Canonical core 12 (methodology) ---
    request_default = "request_default"
    request_compare_benchmark = "request_compare_benchmark"
    request_permissions = "request_permissions"
    request_new_object = "request_new_object"
    request_update_object = "request_update_object"
    request_incorrect_body = "request_incorrect_body"
    request_env_list = "request_env_list"
    request_params = "request_params"
    request_elements = "request_elements"
    request_not_found = "request_not_found"
    request_extra_data = "request_extra_data"
    request_not_allowed = "request_not_allowed"

    # --- B+ named extensions ---
    request_lifecycle_delete = "request_lifecycle_delete"
    request_parent_constraint = "request_parent_constraint"
    request_child_fk = "request_child_fk"
    request_multi_child = "request_multi_child"
    request_ownership_filter = "request_ownership_filter"
    request_server_defaults = "request_server_defaults"
    request_author_integrity = "request_author_integrity"
    request_cross_field = "request_cross_field"
    request_partial_update = "request_partial_update"
    request_unchanged_fields = "request_unchanged_fields"
    request_idempotency = "request_idempotency"
    request_contract_mismatch = "request_contract_mismatch"
    request_state_machine = "request_state_machine"
    request_list_visibility = "request_list_visibility"
    request_user_journey = "request_user_journey"

    # --- Meta / suite markers ---
    type_health = "health"
    type_gen = "generation_data"
    type_unknown = "unknown"

    # --- Legacy short aliases (partest 0.x) ---
    type_default = "default"
    type_405 = "405"
    type_params = "params"
    type_elem = "elem"
    type_env = "env"
    type_benchmark = "benchmark"
    type_permissions = "permissions"
    type_new = "new_object"
    type_update = "update_object"
    type_incorrect_body = "incorrect_body"
    type_not_found = "not_found"
    type_extra = "extra_data"


CORE_TEST_TYPES = (
    TypesTestCases.request_default,
    TypesTestCases.request_compare_benchmark,
    TypesTestCases.request_permissions,
    TypesTestCases.request_new_object,
    TypesTestCases.request_update_object,
    TypesTestCases.request_incorrect_body,
    TypesTestCases.request_env_list,
    TypesTestCases.request_params,
    TypesTestCases.request_elements,
    TypesTestCases.request_not_found,
    TypesTestCases.request_extra_data,
    TypesTestCases.request_not_allowed,
)

B_PLUS_TYPES = (
    TypesTestCases.request_lifecycle_delete,
    TypesTestCases.request_parent_constraint,
    TypesTestCases.request_child_fk,
    TypesTestCases.request_multi_child,
    TypesTestCases.request_ownership_filter,
    TypesTestCases.request_server_defaults,
    TypesTestCases.request_author_integrity,
    TypesTestCases.request_cross_field,
    TypesTestCases.request_partial_update,
    TypesTestCases.request_unchanged_fields,
    TypesTestCases.request_idempotency,
    TypesTestCases.request_contract_mismatch,
    TypesTestCases.request_state_machine,
    TypesTestCases.request_list_visibility,
    TypesTestCases.request_user_journey,
)

_ALIAS_TO_CANONICAL: Dict[str, str] = {
    "default": TypesTestCases.request_default,
    "405": TypesTestCases.request_not_allowed,
    "params": TypesTestCases.request_params,
    "param": TypesTestCases.request_params,
    "elem": TypesTestCases.request_elements,
    "env": TypesTestCases.request_env_list,
    "benchmark": TypesTestCases.request_compare_benchmark,
    "permissions": TypesTestCases.request_permissions,
    "new_object": TypesTestCases.request_new_object,
    "update_object": TypesTestCases.request_update_object,
    "incorrect_body": TypesTestCases.request_incorrect_body,
    "not_found": TypesTestCases.request_not_found,
    "extra_data": TypesTestCases.request_extra_data,
    "not_allowed": TypesTestCases.request_not_allowed,
    "generation_data": TypesTestCases.type_gen,
    "health": TypesTestCases.type_health,
    "unknown": TypesTestCases.type_unknown,
}

for _t in CORE_TEST_TYPES + B_PLUS_TYPES:
    _ALIAS_TO_CANONICAL[_t] = _t
_ALIAS_TO_CANONICAL[TypesTestCases.type_gen] = TypesTestCases.type_gen
_ALIAS_TO_CANONICAL[TypesTestCases.type_health] = TypesTestCases.type_health
_ALIAS_TO_CANONICAL[TypesTestCases.type_unknown] = TypesTestCases.type_unknown

# LIB-CANON: attribute names (`type_default`) used as strings, not just values (`default`)
for _name in dir(TypesTestCases):
    if not _name.startswith("type_") or _name.startswith("type__"):
        continue
    _val = getattr(TypesTestCases, _name)
    if isinstance(_val, str):
        _ALIAS_TO_CANONICAL[_name.lower()] = _ALIAS_TO_CANONICAL.get(_val, _val)

TYPE_LABELS: Dict[str, str] = {
    TypesTestCases.request_default: "RequestDefault",
    TypesTestCases.request_compare_benchmark: "RequestCompareBenchmark",
    TypesTestCases.request_permissions: "RequestPermissions",
    TypesTestCases.request_new_object: "RequestNewObject",
    TypesTestCases.request_update_object: "RequestUpdateObject",
    TypesTestCases.request_incorrect_body: "RequestIncorrectBody",
    TypesTestCases.request_env_list: "RequestEnvList",
    TypesTestCases.request_params: "RequestsParams",
    TypesTestCases.request_elements: "RequestElements",
    TypesTestCases.request_not_found: "RequestNotFound",
    TypesTestCases.request_extra_data: "RequestExtraData",
    TypesTestCases.request_not_allowed: "RequestNotAllowed",
    TypesTestCases.request_lifecycle_delete: "RequestLifecycleDelete",
    TypesTestCases.request_parent_constraint: "RequestParentConstraint",
    TypesTestCases.request_child_fk: "RequestChildFk",
    TypesTestCases.request_multi_child: "RequestMultiChild",
    TypesTestCases.request_ownership_filter: "RequestOwnershipFilter",
    TypesTestCases.request_server_defaults: "RequestServerDefaults",
    TypesTestCases.request_author_integrity: "RequestAuthorIntegrity",
    TypesTestCases.request_cross_field: "RequestCrossField",
    TypesTestCases.request_partial_update: "RequestPartialUpdate",
    TypesTestCases.request_unchanged_fields: "RequestUnchangedFields",
    TypesTestCases.request_idempotency: "RequestIdempotency",
    TypesTestCases.request_contract_mismatch: "RequestContractMismatch",
    TypesTestCases.request_state_machine: "RequestStateMachine",
    TypesTestCases.request_list_visibility: "RequestListVisibility",
    TypesTestCases.request_user_journey: "RequestUserJourney",
    TypesTestCases.type_health: "Health",
    TypesTestCases.type_gen: "GenerationData",
    TypesTestCases.type_unknown: "Unknown",
}

EXCEPTION_TYPES: FrozenSet[str] = frozenset(
    {
        TypesTestCases.type_health,
        "health",
    }
)


def canonicalize_type(raw: Optional[str]) -> str:
    """Normalize any recorded type string to canonical form."""
    if raw is None or str(raw).strip() == "":
        return TypesTestCases.type_unknown

    original = str(raw).strip()
    key = original.lower().replace("-", "_").replace(" ", "_")

    if key in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[key]

    # RequestDefault / camelCase
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", original).lower().replace("-", "_")
    if snake in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[snake]

    compact = key.replace("_", "")
    for alias, canon in _ALIAS_TO_CANONICAL.items():
        if alias.replace("_", "") == compact:
            return canon

    return key


# --- Permission cells (LIB-PERM-QUAD) -------------------------------------
# RequestPermissions is one test-case type covering four distinct security layers.
# Collapsing them into "there is a 401" is the gap this names: an unauthenticated
# request, a disabled account and an object outside the caller's scope fail in
# different components and hide different bugs.
#
# These are labels, not new types: a call still passes
# ``type=TypesTestCases.request_permissions`` and marks the cell separately
# (Allure story, tag, or test id).
PERMISSION_CELLS: Dict[str, str] = {
    "allow": "Permissions/Allow",
    "no_access": "Permissions/NoAccess",
    "inactive": "Permissions/Inactive",
    "unauth": "Permissions/Unauthenticated",
}

PERMISSION_CELL_EXPECTATIONS: Dict[str, str] = {
    "allow": "2xx per the consumer contract",
    "no_access": "403 (404 when the project hides existence)",
    "inactive": "403 — token still valid, account disabled in the application",
    "unauth": "401 — no session at all",
}


def permission_cell_label(cell: str) -> str:
    """Human label for a permission cell; raises on an unknown cell name."""
    key = (cell or "").strip().lower().replace("-", "_")
    if key not in PERMISSION_CELLS:
        raise ValueError(
            f"unknown permission cell {cell!r}; expected one of {sorted(PERMISSION_CELLS)}"
        )
    return PERMISSION_CELLS[key]
