import allure
import httpx
from typing import Optional, Dict, Any, Type

from pydantic import BaseModel, ValidationError
from partest import track_api_calls
from partest.utils import Logger, errordesc, StatusCode


class ApiClient:
    """
    ApiClient serves not only as a client for making requests for endpoints, but also for processing these requests.

    Attributes
    ----------
    :param domain:
    :param verify:
    :param follow_redirects:

    """


    def __init__(self, domain, verify=False, follow_redirects=True):
        self.domain = domain
        self.verify = verify
        self.follow_redirects = follow_redirects
        self.logger = Logger()

    @track_api_calls
    async def make_request(
        self,
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
        type: Optional[str] = None

    ) -> Optional[Dict[str, Any]]:

        url = f"{self.domain}{endpoint}{add_url1}{add_url2}{add_url3}"
        self.logger.log_request(method, url, params=params, headers=headers, data=data)

        async with httpx.AsyncClient(verify=self.verify, follow_redirects=self.follow_redirects) as client:
            try:
                response = await self._perform_request(client, method, url, params, headers, data)

                self.logger.log_response(response)

                if expected_status_code is not None:
                    with allure.step("Валидация ответа"):
                        self._check_status_code(response.status_code, expected_status_code, response, data, validate_model)
                return response.json()

            except httpx.HTTPStatusError as err:
                return self._handle_http_error(err, data)

            except httpx.RequestError as e:
                self.logger.error(f"An error occurred: {e}")
                return None

    async def _perform_request(self, client, method: str, url: str, params: Optional[Dict[str, Any]],
                               headers: Optional[Dict[str, str]], data: Optional[Dict[str, Any]]) -> httpx.Response:
        if method == "GET":
            return await client.get(url, params=params, headers=headers)
        elif method == "POST":
            return await client.post(url, json=data, params=params, headers=headers)
        elif method == "PUT":
            return await client.put(url, json=data, params=params, headers=headers)
        elif method == "PATCH":
            return await client.patch(url, json=data, params=params, headers=headers)
        elif method == "DELETE":
            return await client.delete(url, params=params, headers=headers)
        else:
            raise ValueError("Unsupported HTTP method")

    def _check_status_code(self, actual_code: int, expected_code: int, response: httpx.Response,
                           request_data: Optional[Dict[str, Any]], validate_model: Optional[Type[BaseModel]]):
        """ We check whether the actual status code corresponds to the expected status code. """
        with allure.step(f"Проверка статус-кода ответа: ожидали {expected_code}, получили {actual_code}"):
            if actual_code != expected_code:
                error_description = errordesc()
                error_description.codeExpected = expected_code
                error_description.codeActual = actual_code
                error_description.responseBody = response
                error_description.requestBody = request_data
                self.logger.error(errordesc.status(
                    codeExpected=expected_code,
                    codeActual=error_description.codeActual,
                    responseBody=error_description.responseBody
                ))
                raise AssertionError(f"Expected status code {expected_code}, but got {actual_code}")
        with allure.step(f"Проверка тела ответа"):
            if validate_model:
                    try:
                        data = response.json()
                        assert validate_model.response_default(data)
                    except ValidationError as e:
                        self.logger.error(errordesc.validate(
                            validateModel=validate_model,
                            validateData=data,
                            error=str(e)
                        ))
                        raise AssertionError(f"Response data validation failed: {e}")

    def _handle_http_error(self, err: httpx.HTTPStatusError, request_data: Optional[Dict[str, Any]]):
        """ Exception handling. """
        error_description = errordesc()
        error_description.codeExpected = StatusCode.ok
        error_description.codeActual = err.response.status_code
        error_description.responseBody = err.response
        error_description.requestBody = request_data
        self.logger.error(errordesc.status(
            codeExpected=StatusCode.ok,
            codeActual=error_description.codeActual,
            responseBody=error_description.responseBody
        ))
        return None

class Get(ApiClient):
    async def get(self, endpoint, add_url1=None, add_url2=None, add_url3=None, params=None, headers=None, data=None, expected_status_code=None, validate_model=None):
        return await self.make_request("GET", endpoint, add_url1=add_url1, add_url2=add_url2, add_url3=add_url3, params=params, data=data, headers=headers,
                                       expected_status_code=expected_status_code, validate_model=validate_model)

class Post(ApiClient):
    async def post(self, endpoint, add_url1=None, add_url2=None, add_url3=None, params=None, data=None, headers=None, expected_status_code=None, validate_model=None):
        return await self.make_request("POST", endpoint, add_url1=add_url1, add_url2=add_url2, add_url3=add_url3, params=params, data=data, headers=headers,
                                       expected_status_code=expected_status_code, validate_model=validate_model)

class Patch(ApiClient):
    async def patch(self, endpoint, add_url1=None, add_url2=None, add_url3=None, params=None, data=None, headers=None, expected_status_code=None, validate_model=None):
        return await self.make_request("PATCH", endpoint, add_url1=add_url1, add_url2=add_url2, add_url3=add_url3, params=params, data=data, headers=headers,
                                       expected_status_code=expected_status_code, validate_model=validate_model)

class Put(ApiClient):
    async def put(self, endpoint, add_url1=None, add_url2=None, add_url3=None, params=None, data=None, headers=None, expected_status_code=None, validate_model=None):
        return await self.make_request("PUT", endpoint, add_url1=add_url1, add_url2=add_url2, add_url3=add_url3, params=params, data=data, headers=headers,
                                       expected_status_code=expected_status_code, validate_model=validate_model)

class Delete(ApiClient):
    async def delete(self, endpoint, add_url1=None, add_url2=None, add_url3=None, params=None, data=None, headers=None, expected_status_code=None, validate_model=None):
        return await self.make_request("DELETE", endpoint, add_url1=add_url1, add_url2=add_url2, add_url3=add_url3, params=params, data=data, headers=headers,
                                       expected_status_code=expected_status_code, validate_model=validate_model)