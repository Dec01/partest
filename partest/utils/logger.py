import configparser
import json
import logging

from faker.providers.bank.en_PH import logger


class Logger:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.setup_logger()

    def setup_logger(self):
        parser = configparser.ConfigParser()
        parser.read('pytest.ini')

    def get_log(self):
        return self.logger

    def log_request(self, method, url, params=None, headers=None, data=None):
        self.logger.info(
            f'{"=" * 14}REQUEST INFO{"=" * 14}\nRequest Method: {method} \nURL: {url} \nParams: {params} \nHeaders: {headers} \nData: {data}\n{"=" * 13}↓RESPONSE INFO↓{"=" * 13}')

    def log_response(self, response):
        try:
            self.logger.info(
                f'Response StatusCode: {response.status_code}\nCookies: {response.cookies}\nHeaders: {response.headers}, \nData: {json.dumps(response.json(), indent=4, ensure_ascii=False)}')
        except json.JSONDecodeError:
            self.logger.info(f'Response (non-JSON): {response.text}\n')

    def error(self, message):
        self.logger.error(message)

    def log_str(self, str):
        return self.logger.info(str)

    def __str__(self):
        return logger.info()