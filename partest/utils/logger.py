import configparser
import json
import logging

from faker.providers.bank.en_PH import logger


class Logger:
    """
    A class used to represent a Logger

    ...

    Attributes
    ----------
    logger : Logger
        a logger object

    Methods
    -------
    setup_logger()
        Sets up the logger
    get_log()
        Returns the logger
    log_request(method, url, params=None, headers=None, data=None, data_type=None, files=None)
        Logs the request information
    log_response(response)
        Logs the response information
    error(message)
        Logs an error message
    log_str(str)
        Logs a string
    __str__()
        Returns the logger info
    """
    def __init__(self):
        """
        Constructs all the necessary attributes for the logger object.
        """
        self.logger = logging.getLogger(__name__)
        self.setup_logger()

    def setup_logger(self):
        """
         Sets up the logger by reading the configuration from 'pytest.ini'.
         """
        parser = configparser.ConfigParser()
        parser.read('pytest.ini')

    def get_log(self):
        """
        Returns the logger object.

        Returns
        -------
        Logger
            a logger object
        """
        return self.logger

    def log_request(self, method, url, params=None, headers=None, data=None, data_type=None, files=None):
        """
        Logs the request information.

        Parameters
        ----------
        method : str
            the request method
        url : str
            the request url
        params : dict, optional
            the request parameters (default is None)
        headers : dict, optional
            the request headers (default is None)
        data : dict, optional
            the request data (default is None)
        data_type : str, optional
            the data type (default is None)
        files : dict, optional
            the request files (default is None)
        """
        self.logger.info(
            f'{"=" * 14}REQUEST INFO{"=" * 14}\nRequest Method: {method} \nURL: {url} \nParams: {params} \nHeaders: {headers} \nData: {data}\nDataType: {data_type}\nFiles: {files}\n{"=" * 13}↓RESPONSE INFO↓{"=" * 13}')

    def log_response(self, response):
        """
        Logs the response information.

        Parameters
        ----------
        response : Response
            the response object
        """
        try:
            self.logger.info(
                f'Response StatusCode: {response.status_code}\nCookies: {response.cookies}\nHeaders: {response.headers}, \nData: {json.dumps(response.json(), indent=4, ensure_ascii=False)}')
        except json.JSONDecodeError:
            self.logger.info(f'Response (non-JSON): {response.text}\n')

    def error(self, message):
        """
        Logs an error message.

        Parameters
        ----------
        message : str
            the error message
        """
        self.logger.error(message)

    def log_str(self, str):
        """
        Logs a string.

        Parameters
        ----------
        str : str
            the string to log
        """
        return self.logger.info(str)

    def __str__(self):
        """
         Returns the logger info.

         Returns
         -------
         str
             the logger info
         """
        return logger.info()