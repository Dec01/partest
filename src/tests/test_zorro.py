import allure
import pytest

from confpartest import test_types_coverage
from partest.allure_graph import create_chart
from partest.api_call_storage import call_count, call_type

types = test_types_coverage

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
            coverage_status = "Недостаточное покрытие ❌"
            matched_types = set(types).intersection(types)  # Находим совпадения
            count_matched = len(matched_types)

            # Логика для определения статуса покрытия и расчета процента
            if count_matched == len(types):  # Все типы присутствуют
                coverage_status = "Покрытие выполнено ✅"
                total_coverage_percentage += 100
            elif count_matched == 2:  # Два типа присутствуют
                coverage_status = "Покрытие выполнено на 66% 🔔"
                total_coverage_percentage += 66
            elif count_matched == 1:  # Один тип присутствует
                coverage_status = "Покрытие выполнено на 33% ❌"
                total_coverage_percentage += 33
            else:  # Нет типов
                coverage_status = "Недостаточное покрытие ❌"
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

        create_chart(call_count)

        with open('api_call_counts.png', 'rb') as f:
            allure.attach(f.read(), name='Оценка покрытия', attachment_type=allure.attachment_type.PNG)

        allure.attach("\n".join(report_lines), name='Отчет по вызовам API', attachment_type=allure.attachment_type.TEXT)

        assert True