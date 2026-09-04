"""Optional RFC 7807 Problem Detail response model."""

from __future__ import annotations

from typing import Type

from pydantic import BaseModel, Field

from partest.validation.base import BaseModelWithConfig, BaseResponseValidator


class ProblemDetailBody(BaseModelWithConfig):
    """Common 4xx/5xx error body (RFC 7807). Override fields if your API differs."""

    detail: str = Field(...)
    instance: str = Field(...)
    status: int = Field(...)
    title: str = Field(...)


class ProblemDetailValidation(BaseResponseValidator):
    @property
    def ResponseSuccessBody(self) -> Type[BaseModel]:
        return ProblemDetailBody
