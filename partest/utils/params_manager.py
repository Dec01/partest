"""Query-params builder. Config is injected by the consumer (no domain hardcode)."""

from __future__ import annotations

import random
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode


class ParamsManager:
    """Generate query params from a consumer-provided endpoint config object.

    Expected config shape (duck-typed):
      - param_generators: dict[str, Callable[[], Any]]
      - get_endpoint_config(service, endpoint) -> object with
            .params: list[str]
            .param_config: dict[str, dict]
    """

    def __init__(self, config: Any, locale: str = "en_US"):
        self._config = config
        self._param_generators: Dict[str, Callable[[], Any]] = dict(
            getattr(config, "param_generators", {}) or {}
        )
        try:
            from faker import Faker

            self._faker = Faker(locale=locale)
        except ImportError:
            self._faker = None

    def configure_generator(
        self,
        param: str,
        generator: Optional[Callable] = None,
        values: Optional[List[Any]] = None,
        fixed_value: Any = None,
    ):
        if fixed_value is not None:
            self._param_generators[param] = lambda: fixed_value
        elif values is not None:
            if not values:
                raise ValueError(f"Value list for {param} cannot be empty")
            self._param_generators[param] = lambda: random.choice(values)
        elif generator is not None:
            self._param_generators[param] = generator
        else:
            raise ValueError(f"No generator configured for param: {param}")
        return self

    def get_endpoint_config(self, service, endpoint):
        return self._config.get_endpoint_config(service, endpoint)

    def generate_params(self, service, endpoint, dynamic_values=None):
        dynamic_values = dynamic_values or {}
        config = self.get_endpoint_config(service, endpoint)
        params = config.params
        param_config = getattr(config, "param_config", {}) or {}

        for param, conf in param_config.items():
            self.configure_generator(
                param,
                generator=conf.get("generator"),
                values=conf.get("values"),
                fixed_value=conf.get("fixed_value"),
            )

        if not params:
            return {}
        unknown_keys = [key for key in params if key not in self._param_generators]
        if unknown_keys:
            raise ValueError(f"Unknown params: {unknown_keys}")

        result = {}
        for key in params:
            if key in dynamic_values:
                result[key] = dynamic_values[key]
            else:
                result[key] = self._param_generators[key]()
        return result

    def get_params_missing(self, service, endpoint, missing_param, dynamic_values=None):
        params = self.generate_params(service, endpoint, dynamic_values)
        params.pop(missing_param, None)
        return params

    def to_query_string(self, service, endpoint, dynamic_values=None):
        params = self.generate_params(service, endpoint, dynamic_values)
        return "?" + urlencode(params) if params else ""

    def __str__(self):
        return f"Params: {list(self._param_generators.keys())}"
