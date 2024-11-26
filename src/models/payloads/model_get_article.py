import random

from faker import Faker

from pydantic import Field, ValidationError, BaseModel, field_validator, ConfigDict
from src.models.processings.response import PydanticResponseError
from typing import List, Optional

fake = Faker(locale="ru_RU")

class ResponseGetArticlePayloadItemsMetaCreateDate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(...)

class ResponseGetArticlePayloadItemsMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    createDate: Optional[ResponseGetArticlePayloadItemsMetaCreateDate] = Field(...)
    updateDate: Optional[ResponseGetArticlePayloadItemsMetaCreateDate] = Field(...)
    authorId: str = Field(...)
    authorFullName: str = Field(...)
    editorId: Optional[str] = Field(...)
    editorFullName: Optional[str] = Field(...)


class ResponseGetArticlePayloadItemsDateActiveFrom(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(...)

class ResponseGetArticlePayloadItemsType(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(...)
    code: str = Field(...)
    name: str = Field(...)
    comment: Optional[str] = Field(...)

class ResponseGetArticlePayloadItemsImage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Optional[str] = Field(...)
    alt: Optional[str] = Field(...)
    title: Optional[str] = Field(...)
    caption: Optional[str] = Field(...)
    source: Optional[str] = Field(...)

class ResponseGetArticlePayloadItems(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int = Field(...)
    draftId: str = Field(...)
    uuid: str = Field(...)
    urlCode: str = Field(...)
    shortDescription: Optional[str] = Field(...)
    image: Optional[ResponseGetArticlePayloadItemsImage] = Field(...)
    isActive: bool = Field(...)
    title: str = Field(...)
    type: str = Field(...)
    tags: Optional[object] = Field(...)
    readerRole: object = Field(...)
    direction: object = Field(...)
    typeOfControl: object = Field(...)
    digitalService: object = Field(...)
    educationLevel: object = Field(...)
    age: object = Field(...)
    theme: object = Field(...)
    subject: object = Field(...)
    author: object = Field(...)
    lineUmk: object = Field(...)
    sort: int = Field(...)
    readingTime: Optional[int] = Field(...)
    isDisplayViews: bool = Field(...)
    viewsCount: int = Field(...)
    modifiedViewsCount: int = Field(...)
    isGenerateTableOfContents: bool = Field(...)
    isContainsVideo: bool = Field(...)
    isContainsDownloadMaterial: bool = Field(...)
    isMainArticle: bool = Field(...)
    targetPages: list = Field(...)
    dateActiveFrom: ResponseGetArticlePayloadItemsDateActiveFrom = Field(...)
    dateActiveTo: Optional[ResponseGetArticlePayloadItemsDateActiveFrom] = Field(...)
    displayOnSites: object = Field(...)
    meta: ResponseGetArticlePayloadItemsMeta = Field(...)

class ResponseGetArticlePayloadMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total: int = Field(...)

class ResponseGetArticlePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[ResponseGetArticlePayloadItems] = Field(...)
    meta: ResponseGetArticlePayloadMeta = Field(...)

class ResponseGetArticle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(...)
    payload: ResponseGetArticlePayload = Field(...)
    message: str = Field(...)

    @field_validator('code')
    @classmethod
    def force_x_positive_01(cls, v):
        assert v == "0"
        return v

    @field_validator('message')
    @classmethod
    def force_x_positive_02(cls, v):
        assert v == 'Success'
        return v


class ParamsGetArticle:

    @staticmethod
    def request_params(element=None):
        dict_params = {
            'limit': random.randint(1, 10),
            'offset': random.randint(0, 5),
            'isActive': fake.pybool(),
            'sortField': random.choice(list(["isActive", "title"])),
            'sortDirection': random.choice(list(["asc", "desc"]))
        }
        return dict_params

    @staticmethod
    def request_filter(element=None):
        dict_params = {
            'isContainsDownloadMaterial': random.choice(list(["true", "false"])),
            'isContainsVideo': random.choice(list(["true", "false"]))
        }
        if element:
            param = dict_params[element]
            return list([element, '=', param])
        else:
            return dict_params


    @staticmethod
    def request_sorts(select=None, field=None, value=None):
        sort_selection = ["asc", "desc"]

        if select == 'queue':
            return sort_selection

        elif value == 'asc':
            if field == 'isActive':
                return ['sortField', '=', 'isActive', '&', 'sortDirection', '=', 'asc']
            elif field == 'title':
                return ['sortField', '=', 'title', '&', 'sortDirection', '=', 'asc']
        elif value == 'desc':
            if field == 'isActive':
                return ['sortField', '=', 'isActive', '&', 'sortDirection', '=', 'desc']
            elif field == 'title':
                return ['sortField', '=', 'title', '&', 'sortDirection', '=', 'desc']
        else:
            return False



class ValidateGetArticle:

    @staticmethod
    def response_default(data):
        try:
            return ResponseGetArticle.model_validate(data)
        except ValidationError as e:
            PydanticResponseError.print_error(e)