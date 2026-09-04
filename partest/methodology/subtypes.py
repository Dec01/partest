"""Method subtypes (axis A of the coverage methodology)."""

from enum import Enum
from typing import Dict


class MethodSubtype(str, Enum):
    """OpenAPI operation risk profile (classic 11 + operational specializations)."""

    # Classic 11
    GET_STATIC = "get_static_object"
    GET_DYNAMIC = "get_dynamic_object"
    GET_LIST = "get_list_objects"
    POST_CREATE = "post_create_object"
    POST_UPLOAD = "post_upload_file"
    POST_CREATE_TO_OBJECT = "post_create_object_to_object"
    POST_FILTER_LIST = "post_filter_sort_list"
    PATCH_OBJECT = "patch_object"
    PATCH_ELEM = "patch_elem_on_object"
    PUT_OBJECT = "put_object"
    DELETE_OBJECT = "delete_object"

    # Operational specializations
    GET_BY_PARENT = "get_by_parent"
    GET_BY_SELF = "get_by_self"
    DELETE_PHYSICAL = "delete_physical"
    DELETE_SOFT = "delete_soft"
    DELETE_BLOCKED = "delete_blocked"
    ACTION = "action"
    GET_EXTERNAL_ID = "get_external_id"

    # Fallback
    UNKNOWN = "unknown"


SUBTYPE_LABELS: Dict[MethodSubtype, str] = {
    MethodSubtype.GET_STATIC: "GET STATIC OBJECT",
    MethodSubtype.GET_DYNAMIC: "GET DYNAMIC OBJECT",
    MethodSubtype.GET_LIST: "GET LIST OBJECTS",
    MethodSubtype.POST_CREATE: "POST CREATE OBJECT",
    MethodSubtype.POST_UPLOAD: "POST UPLOAD FILE",
    MethodSubtype.POST_CREATE_TO_OBJECT: "POST CREATE OBJECT TO OBJECT",
    MethodSubtype.POST_FILTER_LIST: "POST FILTER/SORT ON LIST",
    MethodSubtype.PATCH_OBJECT: "PATCH OBJECT",
    MethodSubtype.PATCH_ELEM: "PATCH ELEM ON OBJECT",
    MethodSubtype.PUT_OBJECT: "PUT OBJECT",
    MethodSubtype.DELETE_OBJECT: "DELETE OBJECT",
    MethodSubtype.GET_BY_PARENT: "GET BY PARENT",
    MethodSubtype.GET_BY_SELF: "GET BY SELF / SCOPE",
    MethodSubtype.DELETE_PHYSICAL: "DELETE PHYSICAL",
    MethodSubtype.DELETE_SOFT: "DELETE SOFT",
    MethodSubtype.DELETE_BLOCKED: "DELETE BLOCKED",
    MethodSubtype.ACTION: "ACTION",
    MethodSubtype.GET_EXTERNAL_ID: "GET EXTERNAL ID",
    MethodSubtype.UNKNOWN: "UNKNOWN",
}
