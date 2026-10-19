import configparser
import json
import logging
from partest.redact import (
    _body_text,
    _dumps,
    _files_summary,
    _scrub_cookies,
    _scrub_headers,
    _scrub_params,
    _scrub_text,
)

# How much of a body the INFO request/response log shows, after masking.
_LOG_BODY_LIMIT = 8000


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
    warning(message)
        Logs a warning, masked like the request log
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
        # Nothing is computed when INFO is off: masking a large body costs time.
        if not self.logger.isEnabledFor(logging.INFO):
            return
        # Headers whole-masked by name, `params` and the body walked (secret keys masked, the
        # body serialised as JSON and shortened), URL credentials and secret query values
        # removed, files shown as name, size and content type only.
        safe_params = None if params is None else _dumps(_scrub_params(params))
        self.logger.info(
            f'{"=" * 14}REQUEST INFO{"=" * 14}\nRequest Method: {method} \nURL: {_scrub_text(url)} \nParams: {safe_params} \nHeaders: {_scrub_headers(headers)} \nData: {_body_text(data, limit=_LOG_BODY_LIMIT)}\nDataType: {data_type}\nFiles: {_files_summary(files)}\n{"=" * 13}↓RESPONSE INFO↓{"=" * 13}')

    def log_response(self, response):
        """
        Logs the response information.

        Headers, cookies (``Set-Cookie`` included) and the body are masked, and the body is
        shortened to ``_LOG_BODY_LIMIT`` characters.

        Parameters
        ----------
        response : Response
            the response object
        """
        if not self.logger.isEnabledFor(logging.INFO):
            return
        try:
            data = response.json()
        except Exception:
            try:
                text = response.text
            except Exception:
                text = None
            self.logger.info(
                f'Response (non-JSON): {_body_text(text, limit=_LOG_BODY_LIMIT)}\n'
            )
            return
        try:
            # httpx raises RuntimeError here for a response built without a request.
            cookies = _scrub_cookies(response.cookies)
        except Exception:
            cookies = None
        self.logger.info(
            f'Response StatusCode: {response.status_code}\nCookies: {cookies}\nHeaders: {_scrub_headers(getattr(response, "headers", None))}, \nData: {_body_text(data, limit=_LOG_BODY_LIMIT, indent=4)}')

    def error(self, message):
        """
        Logs an error message.

        Parameters
        ----------
        message : str
            the error message
        """
        self.logger.error(_scrub_text(message))

    def _error_masked(self, message):
        """An ERROR line the package built from already masked parts (``ErrorDesc``).

        Masking it again would read its JSON as free text: ``"detail": "token: expired"``
        would lose its value and its closing quote, ``"password": ""`` would turn into
        ``"***"``.
        """
        self.logger.error(message)

    def warning(self, message):
        """
        Logs a warning: a call that works but is probably not what was meant.

        The text is masked like the request log (``user:password@`` in a URL, secret
        values by key, bearer tokens): a warning tends to quote what the caller passed.

        Parameters
        ----------
        message : str
            the warning message
        """
        self.logger.warning(_scrub_text(message))

    def log_str(self, str):
        """
        Logs a string.

        Parameters
        ----------
        str : str
            the string to log
        """
        return self.logger.info(_scrub_text(str))

    def __str__(self):
        """
         Returns the logger info.

         Returns
         -------
         str
             the logger name and its effective level, e.g.
             ``Logger(name=partest.utils.logger, level=WARNING)``
         """
        level = logging.getLevelName(self.logger.getEffectiveLevel())
        return f"Logger(name={self.logger.name}, level={level})"