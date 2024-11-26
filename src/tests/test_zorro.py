import allure
import pytest

from partest.allure_graph import create_chart
from partest.api_call_storage import call_count, call_type
from partest.test_types import TypesTestCases
from src.models.user_paths import PathsServices

types = TypesTestCases
service = PathsServices.services_paths.get('article')


@allure.epic('Сводка')
@allure.feature('Оценка покрытия')
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.dev
@pytest.mark.asyncio
class TestCoverAge:

    async def test_display_final_call_counts(self):
        """Функция для отображения итогового количества вызовов API и типов тестов."""
        report_lines = []
        total_coverage_percentage = 0
        total_endpoints = 0
        total_calls_excluding_generation = 0

        for (method, endpoint, description), count in call_count.items():
            types = set(call_type[(method, endpoint, description)])
            total_endpoints += 1

            # Подсчет вызовов, исключая тип 'generation_data'
            if 'generation_data' not in types:
                total_calls_excluding_generation += count

            # Проверка на наличие обязательных типов тестов
            type_default = 'default'
            type_405 = '405'
            coverage_status = "Недостаточное покрытие ❌"

            # Логика для определения статуса покрытия и расчета процента
            if count >= 2:
                coverage_status = "Покрытие выполнено ✅"
                total_coverage_percentage += 100
            elif type_default in types and type_405 in types:
                coverage_status = "Покрытие выполнено ✅"
                total_coverage_percentage += 100
            elif count < 2:
                if type_default in types or type_405 in types:
                    coverage_status = "Покрытие выполнено на 50% 🔔"
                    total_coverage_percentage += 50
                else:
                    total_coverage_percentage += 0

            report_line = (
                f"\n{description}\nЭндпоинт: {endpoint}\nМетод: {method} | "
                f"Обращений: {count}, Типы тестов: {', '.join(types)}\n{coverage_status}\n"
            )
            report_lines.append(report_line)

        # Вычисление общего процента покрытия
        if total_endpoints > 0:
            average_coverage_percentage = total_coverage_percentage / total_endpoints
        else:
            average_coverage_percentage = 0


        border = "*" * 50
        summary = f"{border}\nОбщий процент покрытия: {average_coverage_percentage:.2f}%\nОбщее количество вызовов (исключая 'generation_data'): {total_calls_excluding_generation}\n{border}\n"

        # Добавляем сводку в начало отчета
        report_lines.insert(0, summary)

        # print(summary)

        create_chart(call_count)

        with open('api_call_counts.png', 'rb') as f:
            allure.attach(f.read(), name='Оценка покрытия', attachment_type=allure.attachment_type.PNG)

        allure.attach("\n".join(report_lines), name='Отчет по вызовам API', attachment_type=allure.attachment_type.TEXT)

        assert True

