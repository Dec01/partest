import allure
import pytest

from partest.zorro_report import zorro


@allure.epic('Сводка')
@allure.feature('Оценка покрытия')
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.dev
@pytest.mark.asyncio
class TestCoverAge:

    async def test_display_final_call_counts(self):
        zorro()
        assert True