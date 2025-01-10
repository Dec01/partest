import allure
import httpx
from typing import Optional, Dict, Any, Type

from pydantic import BaseModel, ValidationError
from partest import track_api_calls
from partest.utils import Logger, errordesc, StatusCode


class ApiClient:
    """
    A class used to represent an API client.

    ...

    Attributes
    ----------
    domain : str
        The domain to make the requests to.
    verify : bool
        Whether to verify the SSL certificate.
    follow_redirects : bool
        Whether to follow redirects.
    logger : Logger
        The logger to use.

    Methods
    -------
    make_request(method, endpoint, add_url1, add_url2, add_url3, after_url, defining_url, params, headers, data, data_type, files, expected_status_code, validate_model, type)
        Make a request to the specified endpoint.
    _perform_request(client, method, url, params, headers, data, data_type, files)
        Perform the actual HTTP request.
    _check_status_code(actual_code, expected_code, response, request_data, validate_model)
        Check if the actual status code corresponds to the expected status code.
    _handle_http_error(err, request_data)
        Handle HTTP error.
    """

    def __init__(self, domain, verify=False, follow_redirects=True):
        """
        Constructs all the necessary attributes for the ApiClient object.

        Parameters
        ----------
            domain : str
                The domain to make the requests to.
            verify : bool, optional
                Whether to verify the SSL certificate (default is False).
            follow_redirects : bool, optional
                Whether to follow redirects (default is True).
        """
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
            after_url: Optional[str] = '',
            defining_url: Optional[str] = '',
            params: Optional[Dict[str, Any]] = None,
            headers: Optional[Dict[str, str]] = None,
            data: Optional[Dict[str, Any]] = None,
            data_type: Optional[Dict[str, Any]] = None,
            files: Optional[Dict[str, Any]] = None,
            expected_status_code: Optional[int] = None,
            validate_model: Optional[Type[BaseModel]] = None,
            type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:

        """
        Make a request to the specified endpoint.

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

        Returns
        -------
        :return: Response data.
        """

        url = f"{self.domain}{endpoint}{add_url1}{add_url2}{add_url3}{after_url}"
        self.logger.log_request(method, url, params=params, headers=headers, data=data, data_type=data_type,
                                files=files)

        async with httpx.AsyncClient(verify=self.verify, follow_redirects=self.follow_redirects) as client:
            try:
                response = await self._perform_request(client, method, url, params, headers, data, data_type, files)

                self.logger.log_response(response)

                if expected_status_code is not None:
                    with allure.step("Валидация ответа"):
                        self._check_status_code(response.status_code, expected_status_code, response, data,
                                                validate_model)

                try:
                    return response.json()
                except ValueError:
                    return response.text

            except httpx.HTTPStatusError as err:
                return self._handle_http_error(err, data)

            except httpx.RequestError as e:
                self.logger.error(f"An error occurred: {e}")
                return None

    async def _perform_request(self, client, method: str, url: str, params: Optional[Dict[str, Any]],
                               headers: Optional[Dict[str, str]], data: Optional[Dict[str, Any]], data_type: Optional[Dict[str, Any]],files: Optional[Dict[str, Any]]) -> httpx.Response:
        """
        Perform the actual HTTP request.

        Parameters
        ----------
        :param client: HTTP client.
        :param method: HTTP method to use.
        :param url: The URL to make the request to.
        :param params: Query parameters.
        :param headers: Request headers.
        :param data: Request data.
        :param data_type: Request data type.
        :param files: Request files.

        Returns
        -------
        :return: HTTP response.
        """
        if method == "GET":
            return await client.get(url, params=params, headers=headers)
        elif method == "POST":
            return await client.post(url, json=data, data=data_type, params=params, headers=headers, files=files)
        elif method == "PUT":
            return await client.put(url, json=data, data=data_type, params=params, headers=headers)
        elif method == "PATCH":
            return await client.patch(url, json=data, data=data_type, params=params, headers=headers)
        elif method == "DELETE":
            return await client.delete(url, params=params, headers=headers)
        else:
            raise ValueError("Unsupported HTTP method")

    def _check_status_code(self, actual_code: int, expected_code: int, response: httpx.Response,
                           request_data: Optional[Dict[str, Any]], validate_model: Optional[Type[BaseModel]]):
        """
        Check if the actual status code corresponds to the expected status code.

        Parameters
        ----------
        :param actual_code: Actual status code.
        :param expected_code: Expected status code.
        :param response: HTTP response.
        :param request_data: Request data.
        :param validate_model: Model to validate the response.

        Returns
        -------
        :return: None
        """
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
        """
        Handle HTTP error.

        Parameters
        ----------
        :param err: HTTP error.
        :param request_data: Request data.

        Returns
        -------
        :return: None
        """
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
    async def get(self, endpoint, add_url1=None, add_url2=None, add_url3=None, after_url=None, params=None, headers=None, data=None, data_type=None, expected_status_code=None, validate_model=None):
        return await self.make_request("GET", endpoint, add_url1=add_url1, add_url2=add_url2, add_url3=add_url3, after_url=after_url, params=params, data=data, data_type=data_type, headers=headers,
                                       expected_status_code=expected_status_code, validate_model=validate_model)

class Post(ApiClient):
    async def post(self, endpoint, add_url1=None, add_url2=None, add_url3=None, after_url=None, params=None, data=None, data_type=None, headers=None, expected_status_code=None, validate_model=None):
        return await self.make_request("POST", endpoint, add_url1=add_url1, add_url2=add_url2, add_url3=add_url3, after_url=after_url, params=params, data=data, data_type=data_type, headers=headers,
                                       expected_status_code=expected_status_code, validate_model=validate_model)

class Patch(ApiClient):
    async def patch(self, endpoint, add_url1=None, add_url2=None, add_url3=None, after_url=None, params=None, data=None, data_type=None, headers=None, expected_status_code=None, validate_model=None):
        return await self.make_request("PATCH", endpoint, add_url1=add_url1, add_url2=add_url2, add_url3=add_url3, after_url=after_url, params=params, data=data, data_type=data_type, headers=headers,
                                       expected_status_code=expected_status_code, validate_model=validate_model)

class Put(ApiClient):
    async def put(self, endpoint, add_url1=None, add_url2=None, add_url3=None, after_url=None, params=None, data=None, data_type=None, headers=None, expected_status_code=None, validate_model=None):
        return await self.make_request("PUT", endpoint, add_url1=add_url1, add_url2=add_url2, add_url3=add_url3, after_url=after_url, params=params, data=data, data_type=data_type, headers=headers,
                                       expected_status_code=expected_status_code, validate_model=validate_model)

class Delete(ApiClient):
    async def delete(self, endpoint, add_url1=None, add_url2=None, add_url3=None, after_url=None, params=None, data=None, data_type=None, headers=None, expected_status_code=None, validate_model=None):
        return await self.make_request("DELETE", endpoint, add_url1=add_url1, add_url2=add_url2, add_url3=add_url3, after_url=after_url, params=params, data=data, data_type=data_type, headers=headers,
                                       expected_status_code=expected_status_code, validate_model=validate_model)