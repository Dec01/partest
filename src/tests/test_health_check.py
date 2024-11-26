import allure
import pytest

from src.models.user_paths import PathsServices
from src.models.payloads.model_health import HealthValidate

health_check_path = PathsServices.services_paths.get('health_check').get('service_path_v1')

@allure.epic('Сводка')
@allure.feature('Health Check')
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.dev
@pytest.mark.asyncio
class TestHealthCheck:

    async def test_case_health_check(self, api_client):
        endpoint = health_check_path
        response = await api_client.make_request(
            'GET',
            endpoint,
            expected_status_code=200,
            validate_model=HealthValidate
        )
        assert response is not None
        assert isinstance(response, dict)

