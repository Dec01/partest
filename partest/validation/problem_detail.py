"""Optional RFC 7807 / RFC 9457 Problem Detail response model.

``ProblemDetailBody`` forbids every member it does not declare. RFC 9457 allows extension
members, so an API that adds them declares them the way any other model here is declared —
by subclassing::

    class OrderProblem(ProblemDetailBody):
        code: str

    validate_model = ProblemDetailValidation(OrderProblem)

Declared members pass; anything else still fails with ``extra_forbidden``.
``ProblemDetailWithErrors`` is the common shape (``code`` and ``errors[]``) ready-made.
"""

from __future__ import annotations

from typing import List, Optional, Type, Union

from pydantic import BaseModel, Field

from partest.validation.base import BaseModelWithConfig, BaseResponseValidator


class ProblemDetailBody(BaseModelWithConfig):
    """Common 4xx/5xx error body (RFC 7807). Override fields if your API differs.

    ``type`` is a standard member (RFC 9457) and optional. Undeclared members are rejected.
    Subclass to declare the extensions your API sends.
    """

    detail: str = Field(...)
    instance: str = Field(...)
    status: int = Field(...)
    title: str = Field(...)
    type: Optional[str] = None


class ProblemDetailErrorItem(BaseModelWithConfig):
    """One element of ``errors[]``, every member optional.

    ``detail`` and ``pointer`` are the shape RFC 9457 §3 shows (``{"detail": "must be a
    positive integer", "pointer": "#/age"}``); ``field``, ``code`` and ``message`` the common
    one. Any other key is rejected, as everywhere in this package: with every field optional,
    an element that accepted anything would let ``field`` → ``fieldName`` pass unnoticed.
    Declare yours (``rejectedValue`` …) in a subclass, or open one with
    ``model_config = ConfigDict(extra="allow")``.
    """

    field: Optional[str] = None
    code: Optional[Union[str, int]] = None
    message: Optional[str] = None
    detail: Optional[str] = None
    pointer: Optional[str] = None


class ProblemDetailWithErrors(ProblemDetailBody):
    """``ProblemDetailBody`` plus the two common extensions, both optional.

    ``code`` — a machine-readable error code; ``errors`` — per-field errors. Any other
    top-level member is still rejected.
    """

    code: Optional[Union[str, int]] = None
    errors: Optional[List[ProblemDetailErrorItem]] = None


class ProblemDetailValidation(BaseResponseValidator):
    """Validator for a Problem Detail error body.

    ``ProblemDetailValidation()`` checks against ``ProblemDetailBody``;
    ``ProblemDetailValidation(model)`` against the model given — a subclass declaring
    your extensions, or ``ProblemDetailWithErrors``. Pass the instance as ``validate_model=``.
    """

    _model: Optional[Type[BaseModel]] = None

    def __init__(self, model: Optional[Type[BaseModel]] = None) -> None:
        if model is not None and not (isinstance(model, type) and issubclass(model, BaseModel)):
            raise TypeError(f"model must be a pydantic model class, got {model!r}")
        if model is not None:
            self._model = model

    @property
    def ResponseSuccessBody(self) -> Type[BaseModel]:
        return self._model or ProblemDetailBody
