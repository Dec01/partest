import random

from faker import Faker
from urllib.parse import urlencode
from src.models.endpoints.configs import config as endpoint_config

class ParamsManager:
    def __init__(self, locale="ru_RU"):
        self._faker = Faker(locale=locale)
        self._config = endpoint_config
        self._param_generators = self._config.param_generators

    def configure_generator(self, param, generator=None, values=None, fixed_value=None):
        if param not in self._param_generators:
            raise ValueError(f"Неизвестный параметр: {param}")
        if fixed_value is not None:
            self._param_generators[param] = lambda: fixed_value
        elif values is not None:
            if not values:
                raise ValueError(f"Список значений для {param} не может быть пустым")
            self._param_generators[param] = lambda: random.choice(values)
        elif generator is not None:
            self._param_generators[param] = generator
        return self

    def get_endpoint_config(self, service, endpoint):
        return self._config.get_endpoint_config(service, endpoint)

    def generate_params(self, service, endpoint, dynamic_values=None):
        dynamic_values = dynamic_values or {}
        config = self.get_endpoint_config(service, endpoint)
        params = config.params
        param_config = config.param_config

        for param, conf in param_config.items():
            self.configure_generator(
                param,
                generator=conf.get("generator"),
                values=conf.get("values"),
                fixed_value=conf.get("fixed_value")
            )

        if not params:
            return {}
        unknown_keys = [key for key in params if key not in self._param_generators]
        if unknown_keys:
            raise ValueError(f"Неизвестные параметры: {unknown_keys}")

        result = {}
        for key in params:
            if key in dynamic_values:
                result[key] = dynamic_values[key]
            else:
                result[key] = self._param_generators[key]()
        return result

    def get_params_missing(self, service, endpoint, missing_param, dynamic_values=None):
        config = self.get_endpoint_config(service, endpoint)
        params = config.params
        param_config = config.param_config

        if missing_param not in params:
            raise ValueError(f"Параметр {missing_param} отсутствует в списке параметров")

        for param, conf in param_config.items():
            self.configure_generator(
                param,
                generator=conf.get("generator"),
                values=conf.get("values"),
                fixed_value=conf.get("fixed_value")
            )

        dynamic_values = dynamic_values or {}
        result = {}
        for key in params:
            if key != missing_param:
                if key in dynamic_values:
                    result[key] = dynamic_values[key]
                else:
                    result[key] = self._param_generators[key]()
        return result

    def to_query_string(self, service, endpoint, dynamic_values=None):
        params = self.generate_params(service, endpoint, dynamic_values)
        return "?" + urlencode(params) if params else ""

    def __str__(self):
        return f"Params: {list(self._param_generators.keys())}"