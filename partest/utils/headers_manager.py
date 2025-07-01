import random

from faker import Faker
from src.models.endpoints.configs import config as endpoint_config

class HeadersManager:
    def __init__(self, locale="ru_RU"):
        self._faker = Faker(locale=locale)
        self._config = endpoint_config
        self._header_generators = self._config.header_generators

    def configure_generator(self, header, generator=None, values=None, fixed_value=None):
        if header not in self._header_generators:
            raise ValueError(f"Неизвестный заголовок: {header}")
        if fixed_value is not None:
            self._header_generators[header] = lambda: fixed_value
        elif values is not None:
            if not values:
                raise ValueError(f"Список значений для {header} не может быть пустым")
            self._header_generators[header] = lambda: random.choice(values)
        elif generator is not None:
            self._header_generators[header] = generator
        return self

    def get_endpoint_config(self, service, endpoint):
        return self._config.get_endpoint_config(service, endpoint)

    def generate_headers(self, service, endpoint, dynamic_values=None):
        dynamic_values = dynamic_values or {}
        config = self.get_endpoint_config(service, endpoint)
        headers = config.headers
        header_config = config.header_config

        for header, conf in header_config.items():
            self.configure_generator(
                header,
                generator=conf.get("generator"),
                values=conf.get("values"),
                fixed_value=conf.get("fixed_value")
            )

        if not headers:
            raise ValueError("Список заголовков не может быть пустым")
        unknown_headers = [header for header in headers if header not in self._header_generators]
        if unknown_headers:
            raise ValueError(f"Неизвестные заголовки: {unknown_headers}")

        result = {}
        for header in headers:
            if header in dynamic_values:
                result[header] = dynamic_values[header]
            else:
                result[header] = self._header_generators[header]()
        return result

    def get_headers_missing(self, service, endpoint, missing_header, dynamic_values=None):
        config = self.get_endpoint_config(service, endpoint)
        headers = config.headers
        header_config = config.header_config

        if missing_header not in headers:
            raise ValueError(f"Заголовок {missing_header} отсутствует в списке заголовков")

        for header, conf in header_config.items():
            self.configure_generator(
                header,
                generator=conf.get("generator"),
                values=conf.get("values"),
                fixed_value=conf.get("fixed_value")
            )

        dynamic_values = dynamic_values or {}
        result = {}
        for header in headers:
            if header != missing_header:
                if header in dynamic_values:
                    result[header] = dynamic_values[header]
                else:
                    result[header] = self._header_generators[header]()
        return result

    def __str__(self):
        return f"Headers: {list(self._header_generators.keys())}"