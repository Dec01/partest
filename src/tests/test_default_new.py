import allure
import pytest

from src.models.payloads.aggregator_model_objects import Models
from src.models.user_paths import PathsServices
from partest.test_types import TypesTestCases

types = TypesTestCases
service = PathsServices.services_paths.get('article')

@allure.epic('Микросервис "Article"')
@allure.feature('Стандартная проверка')
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.dev
@pytest.mark.asyncio
class TestArticleDefault:
    _article_uuid_list = []
    _article_uuid = None
    _article_uuid_main = None
    _article_urlcode = None
    _article_urlcode_main = None
    _article_source = None
    _article_source_main = None

    async def test_get_article(self, api_client):
        endpoint = service.get('service_endpoints_path').get('general_path').get('url')
        response = await api_client.make_request(
            'GET',
            service.get('service_path_v1')[0] + endpoint,
            params='limit=1',
            expected_status_code=200,
            validate_model=Models.ValidateGetArticle,
            type=types.type_default
        )
        assert response is not None
        assert isinstance(response, dict)
