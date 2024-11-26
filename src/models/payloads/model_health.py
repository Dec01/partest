from pydantic import Field, ValidationError, BaseModel, field_validator, ConfigDict
from src.models.processings.response import PydanticResponseError


class HealthValidateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(...)
    warnings: object = Field(...)

    @field_validator('status')
    @classmethod
    def force_x_positive_01(cls, v):
        assert v == 'alive'
        return v

    @field_validator('warnings')
    @classmethod
    def force_x_positive_02(cls, v):
        assert v == []
        return v

class HealthValidate:

    @staticmethod
    def response_default(data):
        try:
            return HealthValidateSchema.model_validate(data)
        except ValidationError as e:
            PydanticResponseError.print_error(e)

