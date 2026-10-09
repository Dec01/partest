"""Problem Detail extension members (RFC 9457): declared ones pass, the rest still fail."""

from typing import List, Optional

import httpx
import pytest
from pydantic import ConfigDict, ValidationError

import partest
import partest.validation as validation
from partest.client import ApiClient
from partest.reporting import ErrorTemplates
from partest.validation import (
    ProblemDetailBody,
    ProblemDetailErrorItem,
    ProblemDetailValidation,
    ProblemDetailWithErrors,
)

CORE = {"detail": "d", "instance": "/items", "status": 400, "title": "Bad Request"}


def _extra_locs(exc: ValidationError):
    return [e["loc"] for e in exc.errors() if e["type"] == "extra_forbidden"]


# --- default stays strict ---------------------------------------------------------


def test_default_body_still_forbids_extension_members():
    with pytest.raises(ValidationError) as info:
        ProblemDetailBody.model_validate({**CORE, "code": "E1"})
    assert _extra_locs(info.value) == [("code",)]


def test_default_body_accepts_the_standard_type_member():
    m = ProblemDetailBody.model_validate({**CORE, "type": "about:blank"})
    assert m.type == "about:blank"
    assert ProblemDetailBody.model_validate(CORE).type is None


def test_type_does_not_open_the_body_to_other_members():
    with pytest.raises(ValidationError) as info:
        ProblemDetailBody.model_validate({**CORE, "type": "about:blank", "trace_id": "abc"})
    assert _extra_locs(info.value) == [("trace_id",)]


def test_type_must_be_a_string():
    with pytest.raises(ValidationError):
        ProblemDetailBody.model_validate({**CORE, "type": 1})


def test_default_validator_checks_the_core_model():
    v = ProblemDetailValidation()
    assert v.ResponseSuccessBody is ProblemDetailBody
    assert v.validate_error(CORE).status == 400
    with pytest.raises(ValidationError):
        v.validate_error({**CORE, "errors": []})


# --- declared by subclassing ------------------------------------------------------


class _CodedProblem(ProblemDetailBody):
    code: str


def test_declared_extension_passes():
    m = ProblemDetailValidation(_CodedProblem).validate_error({**CORE, "code": "E1"})
    assert m.code == "E1"


def test_undeclared_member_still_fails_next_to_a_declared_one():
    with pytest.raises(ValidationError) as info:
        ProblemDetailValidation(_CodedProblem).validate_error(
            {**CORE, "code": "E1", "trace_id": "abc"}
        )
    assert _extra_locs(info.value) == [("trace_id",)]


def test_declared_extension_can_be_required():
    with pytest.raises(ValidationError) as info:
        _CodedProblem.model_validate(CORE)
    assert [e["loc"] for e in info.value.errors()] == [("code",)]


def test_validator_rejects_a_non_model():
    with pytest.raises(TypeError):
        ProblemDetailValidation({"code": str})
    with pytest.raises(TypeError):
        ProblemDetailValidation(_CodedProblem(**CORE, code="E1"))


# --- ready-made common shape ------------------------------------------------------


def test_with_errors_accepts_code_and_errors():
    body = {
        **CORE,
        "code": "VALIDATION_FAILED",
        "errors": [
            {"field": "name", "code": "required", "message": "must not be blank"},
            {"field": "qty", "code": 1002, "message": "must be positive"},
        ],
    }
    m = ProblemDetailWithErrors.model_validate(body)
    assert m.code == "VALIDATION_FAILED"
    assert [e.field for e in m.errors] == ["name", "qty"]
    assert m.errors[1].code == 1002


def test_with_errors_extensions_are_optional():
    m = ProblemDetailWithErrors.model_validate(CORE)
    assert m.code is None and m.errors is None


def test_with_errors_still_forbids_other_top_level_members():
    with pytest.raises(ValidationError) as info:
        ProblemDetailWithErrors.model_validate({**CORE, "code": "E1", "trace_id": "abc"})
    assert _extra_locs(info.value) == [("trace_id",)]


def test_unknown_key_in_an_error_item_is_allowed_and_kept():
    body = {
        **CORE,
        "errors": [{"field": "age", "message": "too low", "pointer": "#/age", "min": 18}],
    }
    m = ProblemDetailWithErrors.model_validate(body)
    item = m.errors[0]
    assert isinstance(item, ProblemDetailErrorItem)
    assert item.model_extra == {"pointer": "#/age", "min": 18}


def test_known_item_keys_are_still_typed():
    with pytest.raises(ValidationError) as info:
        ProblemDetailWithErrors.model_validate({**CORE, "errors": [{"message": {"x": 1}}]})
    assert info.value.errors()[0]["loc"][:3] == ("errors", 0, "message")


def test_errors_must_be_a_list():
    with pytest.raises(ValidationError):
        ProblemDetailWithErrors.model_validate({**CORE, "errors": {"field": "name"}})


def test_item_can_be_pinned_down_by_subclassing():
    class StrictItem(ProblemDetailErrorItem):
        model_config = ConfigDict(extra="forbid")

    class StrictProblem(ProblemDetailWithErrors):
        errors: Optional[List[StrictItem]] = None

    StrictProblem.model_validate({**CORE, "errors": [{"field": "a", "message": "m"}]})
    with pytest.raises(ValidationError) as info:
        StrictProblem.model_validate({**CORE, "errors": [{"field": "a", "pointer": "#/a"}]})
    assert _extra_locs(info.value) == [("errors", 0, "pointer")]


# --- through ApiClient ------------------------------------------------------------


async def _call(body, validate_model):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
        api = ApiClient("http://stand", client=hx)
        return await api.make_request(
            "POST",
            "/items",
            expected_status_code=400,
            validate_model=validate_model,
            type=partest.TypesTestCases.request_incorrect_body,
        )


@pytest.mark.asyncio
async def test_api_client_accepts_declared_extensions():
    body = {**CORE, "code": "E1", "errors": [{"field": "name", "code": "required"}]}
    await _call(body, ProblemDetailValidation(ProblemDetailWithErrors))


@pytest.mark.asyncio
async def test_api_client_default_validator_fails_on_extensions():
    with pytest.raises(AssertionError, match="validation failed(.|\n)*Extra inputs are not permitted"):
        await _call({**CORE, "code": "E1"}, ProblemDetailValidation())


# --- exports and the conflict message ---------------------------------------------


def test_exports():
    for name in ("ProblemDetailErrorItem", "ProblemDetailWithErrors"):
        assert name in validation.__all__
        assert name in partest.__all__
        assert getattr(partest, name) is getattr(validation, name)


def test_conflict_message_shows_the_code_extension():
    text = ErrorTemplates.conflict_409(
        method="POST",
        path="/items",
        expected=201,
        response_body={**CORE, "status": 409, "code": "DUPLICATE", "errors": [{"field": "name"}]},
    )
    assert "code='DUPLICATE'" in text
    assert "errors=" in text
