"""Headers builder. Config is injected by the consumer (no domain hardcode)."""

from __future__ import annotations

import random
from typing import Any, Callable, Dict, List, Optional


class HeadersManager:
    """Generate headers from a consumer-provided endpoint config object.

    Expected config shape (duck-typed):
      - header_generators: dict[str, Callable[[], Any]]
      - get_endpoint_config(service, endpoint) -> object with
            .headers: list[str]
            .header_config: dict[str, dict]
    """

    def __init__(self, config: Any, locale: str = "en_US"):
        self._config = config
        self._header_generators: Dict[str, Callable[[], Any]] = dict(
            getattr(config, "header_generators", {}) or {}
        )
        try:
            from faker import Faker

            self._faker = Faker(locale=locale)
        except ImportError:
            self._faker = None

    def configure_generator(
        self,
        header: str,
        generator: Optional[Callable] = None,
        values: Optional[List[Any]] = None,
        fixed_value: Any = None,
    ):
        if fixed_value is not None:
            self._header_generators[header] = lambda: fixed_value
        elif values is not None:
            if not values:
                raise ValueError(f"Value list for {header} cannot be empty")
            self._header_generators[header] = lambda: random.choice(values)
        elif generator is not None:
            self._header_generators[header] = generator
        else:
            raise ValueError(f"No generator configured for header: {header}")
        return self

    def get_endpoint_config(self, service, endpoint):
        return self._config.get_endpoint_config(service, endpoint)

    def generate_headers(self, service, endpoint, dynamic_values=None):
        dynamic_values = dynamic_values or {}
        config = self.get_endpoint_config(service, endpoint)
        headers = config.headers
        header_config = getattr(config, "header_config", {}) or {}

        for header, conf in header_config.items():
            self.configure_generator(
                header,
                generator=conf.get("generator"),
                values=conf.get("values"),
                fixed_value=conf.get("fixed_value"),
            )

        if not headers:
            raise ValueError("Header list cannot be empty")
        unknown_headers = [h for h in headers if h not in self._header_generators]
        if unknown_headers:
            raise ValueError(f"Unknown headers: {unknown_headers}")

        result = {}
        for header in headers:
            if header in dynamic_values:
                result[header] = dynamic_values[header]
            else:
                result[header] = self._header_generators[header]()
        return result

    def get_headers_missing(self, service, endpoint, missing_header, dynamic_values=None):
        result = self.generate_headers(service, endpoint, dynamic_values)
        result.pop(missing_header, None)
        return result

    def __str__(self):
        return f"Headers: {list(self._header_generators.keys())}"
