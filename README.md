## Partest
Pypi: https://pypi.org/project/partest/

This is a framework for API autotests with coverage assessment. Detailed instructions in the process of writing. It is better to check with the author how to use it. Tools are used:

* pytest
* httpx
* allure

Files are required for specific work:

**conftest.py** - it must have a fixture's inside:

```commandline
def pytest_addoption(parser):
    parser.addoption("--domain", action="store", default="http://url.ru")

@pytest.fixture(scope="session")
def domain(request):
    return request.config.getoption("--domain")
    
@pytest.fixture(scope="session")
def api_client(domain):
    return ApiClient(domain=domain)

@pytest.fixture(scope='session', autouse=True)
def clear_call_data():
    global call_count, call_type
    api_call_storage.call_count.clear()
    api_call_storage.call_type.clear()
    yield
```

**confpartest.py** - It must have variables inside:

```
swagger_files = {
    'test1': ['local', '../docs/openapi.yaml']
}

test_types_coverage = ['default', '405', 'param']
test_types_exception = ['health']

    """ swagger_files
    
        The **swagger_files** directory can have many items. The item key is the name of the swagger. Next, let's analyze the value
        in which the list with certain data is stored:
            0: 'local' or 'url'
            1: 'path'
            
        Example:
        
        swagger_files = {
            'test1': ['url', 'https://petstore.swagger.io/v2/swagger.json'],
            'test2': ['local', '../docs/openapi.yaml']
        }

    """
    """ test_types_coverage
    
        The **test_types_coverage** a list of test types, the amount of which is 100% coverage. List of available types:

        'default': The default type of test case.
        '405': The type of test case for 405 error.
        'params': The type of test case for parameters.
        'elem': The type of test case for elements.
        'generation_data': The type of test case for generation data.
        'health': The type of test case for health.
        'env': The type of test case for environment.
        
    """
        """ test_types_exception
    
        The **test_types_exception** contains a list of test types that are an exception. Applying this type of test to 
        an endpoint automatically counts as 100% coverage.
        
    """
```

The project must have a test that displays information about the coverage in allure. The name of it **test_zorro.py**:

```commandline
import allure
import pytest

from partest.zorro_report import zorro

@pytest.mark.asyncio
class TestCoverAge:

    async def test_display_final_call_counts(self):
        zorro()
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
        Parameters
        ----------
        :param method: HTTP method to use.
        :param endpoint: The endpoint to make the request to.
        :param add_url1: Additional URL part 1.
        :param add_url2: Additional URL part 2.
        :param add_url3: Additional URL part 3.
        :param after_url: Additional URL part after the endpoint.
        :param defining_url: Defining URL.
        :param params: Query parameters.
        :param headers: Request headers.
        :param data: Request data.
        :param data_type: Request data type.
        :param files: Request files.
        :param expected_status_code: Expected status code.
        :param validate_model: Model to validate the response.
        :param type: Request type.
```