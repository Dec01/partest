"""Unit tests for methodology modules (no live HTTP)."""

from partest.methodology.classifier import classify_endpoint
from partest.methodology.inference import infer_test_type
from partest.methodology.matrix import p1_test_cases, p2_test_cases
from partest.methodology.subtypes import MethodSubtype
from partest.test_types import TYPE_LABELS, B_PLUS_TYPES
from partest.test_types import TypesTestCases as T
from partest.test_types import canonicalize_type


def test_canonicalize_legacy_aliases():
    assert canonicalize_type("default") == T.request_default
    assert canonicalize_type("405") == T.request_not_allowed
    assert canonicalize_type("elem") == T.request_elements
    assert canonicalize_type("request_default") == T.request_default
    assert canonicalize_type("RequestNotFound") == T.request_not_found


def test_canonicalize_type_attribute_names():
    """LIB-CANON: `type_default` (attr name) maps, not only value `default`."""
    assert canonicalize_type("type_default") == T.request_default
    assert canonicalize_type("type_405") == T.request_not_allowed
    assert canonicalize_type("type_elem") == T.request_elements
    assert canonicalize_type("type_incorrect_body") == T.request_incorrect_body
    assert canonicalize_type("type_not_found") == T.request_not_found
    assert canonicalize_type("type_health") == T.type_health


def test_classify_get_list():
    st = classify_endpoint("GET", "/items", "List items")
    assert st == MethodSubtype.GET_LIST


def test_classify_get_dynamic():
    st = classify_endpoint("GET", "/items/{id}", "Get item by id")
    assert st == MethodSubtype.GET_DYNAMIC


def test_classify_post_create():
    st = classify_endpoint("POST", "/items", "Create item", has_body=True)
    assert st == MethodSubtype.POST_CREATE


def test_classify_delete():
    st = classify_endpoint("DELETE", "/items/{id}", "Delete item")
    assert st == MethodSubtype.DELETE_OBJECT


def test_p1_post_create_includes_new_and_incorrect_body():
    p1 = set(p1_test_cases(MethodSubtype.POST_CREATE))
    assert T.request_default in p1
    assert T.request_new_object in p1
    assert T.request_incorrect_body in p1
    assert T.request_elements in p1


def test_bplus_labels_and_optional_p2():
    """LIB-BPLUS: labels exist; B+ is P2 only (does not enter default P1)."""
    for tc in B_PLUS_TYPES:
        assert tc in TYPE_LABELS
        assert TYPE_LABELS[tc].startswith("Request")
    p1 = set(p1_test_cases(MethodSubtype.POST_CREATE))
    p2 = set(p2_test_cases(MethodSubtype.POST_CREATE))
    assert T.request_cross_field in p2
    assert T.request_cross_field not in p1
    delete_p2 = set(p2_test_cases(MethodSubtype.DELETE_OBJECT))
    assert T.request_lifecycle_delete in delete_p2
    assert T.request_lifecycle_delete not in set(p1_test_cases(MethodSubtype.DELETE_OBJECT))


def test_infer_405_high_confidence():
    r = infer_test_type(method="POST", endpoint="/x", expected_status_code=405)
    assert r.test_type == T.request_not_allowed
    assert r.confidence >= 0.99
    assert r.inferred is True


def test_infer_broken_json():
    r = infer_test_type(
        method="POST",
        endpoint="/x",
        content=b'{"a":',
        content_type="application/json",
    )
    assert r.test_type == T.request_incorrect_body
    assert r.confidence >= 0.99


def test_infer_explicit_wins():
    r = infer_test_type(
        method="GET",
        endpoint="/x",
        expected_status_code=200,
        explicit_type=T.request_permissions,
    )
    assert r.test_type == T.request_permissions
    assert r.confidence == 1.0
    assert r.inferred is False


def test_infer_ambiguous_2xx_is_low_confidence_default():
    r = infer_test_type(method="GET", endpoint="/x", expected_status_code=200)
    assert r.test_type == T.request_default
    assert r.confidence < 0.99
