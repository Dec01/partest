import allure
import pytest

from partest.zorro_report import zorro


@allure.epic("Coverage")
@allure.feature("Final report")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.asyncio
class TestCoverage:

    async def test_display_final_call_counts(self):
        report = zorro()
        assert report is not None
        assert report.average_pct >= 0
