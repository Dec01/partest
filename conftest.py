import time

import pytest

from partest import ApiClient, reset_storage


def pytest_addoption(parser):
    parser.addoption("--domain", action="store", default="http://127.0.0.1:8000")


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


@pytest.fixture(scope="session", autouse=True)
def clear_call_data():
    reset_storage()
    yield
    reset_storage()
