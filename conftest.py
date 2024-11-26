import time
import pytest
from partest import ApiClient, api_call_storage



def pytest_addoption(parser):
    parser.addoption("--domain", action="store", default="url.com")

@pytest.fixture(scope="session")
def domain(request):
    return request.config.getoption("--domain")

@pytest.fixture(scope="session")
def api_client(domain):
    return ApiClient(domain=domain, verify=False)

def pytest_make_parametrize_id(config, val):
    return repr(val)

@pytest.fixture(autouse=True)
def slow_down_tests():
    yield
    time.sleep(0)


@pytest.fixture(scope='session', autouse=True)
def clear_call_data():
    """Фикстура для очистки данных перед запуском тестов."""
    global call_count, call_type
    api_call_storage.call_count.clear()
    api_call_storage.call_type.clear()
    yield
