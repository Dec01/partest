"""Pydantic response validators compatible with ApiClient.validate_model."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, Type

from pydantic import BaseModel, ConfigDict, ValidationError

from partest.utils.checking import PydanticResponseError


class BaseModelWithConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BaseResponseValidator(ABC):
    """Base validation model. ApiClient calls validate_success / validate_error."""

    @property
    @abstractmethod
    def ResponseSuccessBody(self) -> Type[BaseModel]:
        pass

    def validate_success(self, data: Any) -> Optional[Any]:
        try:
            return self.ResponseSuccessBody.model_validate(data)
        except ValidationError as e:
            PydanticResponseError.print_error(e)
            raise

    def validate_error(self, data: Any) -> Optional[Any]:
        """Default: validate error body with the same model.

        Override when error shape differs (e.g. Problem Detail).
        """
        try:
            return self.ResponseSuccessBody.model_validate(data)
        except ValidationError as e:
            PydanticResponseError.print_error(e)
            raise
