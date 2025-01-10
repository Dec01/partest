## HI!

This is a framework for API autotests with coverage assessment. Detailed instructions in the process of writing. It is better to check with the author how to use it. Tools are used:

* pytest
* httpx
* allure

Files are required for specific work:

**conftest.py** - it must have a fixture's inside:

```commandline
@pytest.fixture(scope="session")
def api_client(domain):
    return ApiClient(domain=domain)
```
```commandline
@pytest.fixture(scope='session', autouse=True)
def clear_call_data():
    """Фикстура для очистки данных перед запуском тестов."""
    global call_count, call_type
    api_call_storage.call_count.clear()
    api_call_storage.call_type.clear()
    yield
```

**confpartest.py** - It must have variables inside:

```
swagger_files = {
    'test1': ['local', '../public/swagger/app-openapi.yaml'],
    'test2': ['local', '../public/swagger/app-openapi2.yaml'],
    'test3': ['url', 'https://url.ru']
}

test_types_coverage = ['default', '405', 'param']
```

The project must have a test that displays information about the coverage in allure. The name of it **test_zorro.py**:

```commandline

    async def test_display_final_call_counts(self):
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
            matched_types = set(types).intersection(types)  
            count_matched = len(matched_types)

            # Логика для определения статуса покрытия и расчета процента
            if count_matched == len(types):  # Все типы присутствуют
                coverage_status = "Покрытие выполнено ✅"
                total_coverage_percentage += 100
            elif count_matched == 2:  
                coverage_status = "Покрытие выполнено на 66% 🔔"
                total_coverage_percentage += 66
            elif count_matched == 1:  
                coverage_status = "Покрытие выполнено на 33% ❌"
                total_coverage_percentage += 33
            else: 
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

```


What does the test look like:

```commandline
    async def test_get(self, api_client):
        endpoint = 'https://ya.ru'
        response = await api_client.make_request(
            'GET',
            endpoint,
            params='limit=1',
            expected_status_code=200,
            validate_model=Models.ValidateGet,
            type=types.type_default
        )
        assert response is not None
        assert isinstance(response, dict)
```

All available data that the client can accept:
```
method: str,
endpoint: str,
add_url1: Optional[str] = '',
add_url2: Optional[str] = '',
add_url3: Optional[str] = '',
params: Optional[Dict[str, Any]] = None,
headers: Optional[Dict[str, str]] = None,
data: Optional[Dict[str, Any]] = None,
expected_status_code: Optional[int] = None,
validate_model: Optional[Type[BaseModel]] = None,
type: Optional[str] = None```