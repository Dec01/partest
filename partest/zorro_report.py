import allure

from partest.test_types import TypesTestCases
from partest.allure_graph import create_chart
from partest.call_storage import call_count, call_type
from confpartest import test_types_coverage


types = TypesTestCases
required_types = test_types_coverage

def zorro():
    """Function for displaying the total number of API calls and test types."""
    report_lines = []
    total_coverage_percentage = 0
    total_endpoints = 0
    total_calls_excluding_generation = 0

    for (method, endpoint, description), count in call_count.items():
        types = set(call_type[(method, endpoint, description)])
        total_endpoints += 1

        if 'generation_data' not in types:
            total_calls_excluding_generation += count

        coverage_status = "Недостаточное покрытие ❌"
        present_types = [test_type for test_type in required_types if test_type in types]
        coverage_count = len(present_types)
        required_count = len(required_types)

        # Logic for determining the coverage status and calculating the percentage
        if coverage_count == required_count:
            coverage_percentage = 100
            coverage_status = "Покрытие выполнено ✅"
        elif coverage_count > 0:
            coverage_percentage = (coverage_count / required_count) * 100
            coverage_status = f"Покрытие выполнено на {coverage_percentage:.2f}% 🔔"
        else:
            coverage_percentage = 0

        total_coverage_percentage += coverage_percentage

        report_line = (
            f"\n{description}\nЭндпоинт: {endpoint}\nМетод: {method} | "
            f"Обращений: {count}, Типы тестов: {', '.join(types)}\n{coverage_status}\n"
        )
        report_lines.append(report_line)

    # Calculation of the total coverage percentage
    if total_endpoints > 0:
        average_coverage_percentage = total_coverage_percentage / total_endpoints
    else:
        average_coverage_percentage = 0

    border = "*" * 50
    summary = f"{border}\nОбщий процент покрытия: {average_coverage_percentage:.2f}%\nОбщее количество вызовов (исключая 'generation_data'): {total_calls_excluding_generation}\n{border}\n"
    report_lines.insert(0, summary)
    create_chart(call_count)

    with open('api_call_counts.png', 'rb') as f:
        allure.attach(f.read(), name='Оценка покрытия', attachment_type=allure.attachment_type.PNG)

    allure.attach("\n".join(report_lines), name='Отчет по вызовам API', attachment_type=allure.attachment_type.TEXT)