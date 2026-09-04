"""Generic headers/params Config builder (project-agnostic)."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional, Union


class HeaderSpec(dict):
    """Optional typed-ish dict: default, generator, allowed_values."""


class Config:
    """Build request headers and query params from named registries.

    Consumer projects can subclass or mutate ``GLOBAL_HEADERS`` / ``GLOBAL_PARAMS``.
    """

    def __init__(self):
        self.GLOBAL_HEADERS: Dict[str, dict] = {
            "Accept": {
                "default": "application/json",
                "allowed_values": ["application/json", "*/*"],
            },
            "Content-Type": {
                "default": "application/json",
                "allowed_values": [
                    "application/json",
                    "multipart/form-data",
                    "application/x-www-form-urlencoded",
                    "text/plain",
                ],
            },
            "X-Request-ID": {
                "default": None,
                "generator": lambda: str(uuid.uuid4()),
            },
        }
        self.GLOBAL_PARAMS: Dict[str, dict] = {}

    def register_header(
        self,
        name: str,
        *,
        default: Any = None,
        generator: Optional[Callable[[], Any]] = None,
        allowed_values: Optional[List[str]] = None,
    ) -> "Config":
        spec: dict = {"default": default}
        if generator is not None:
            spec["generator"] = generator
        if allowed_values is not None:
            spec["allowed_values"] = allowed_values
        self.GLOBAL_HEADERS[name] = spec
        return self

    def get_headers(
        self,
        headers: List[str],
        custom_values: Optional[Dict[str, Union[str, int, bool]]] = None,
        token: Optional[str] = None,
        *,
        auth_scheme: str = "Bearer",
    ) -> Dict[str, str]:
        custom_values = custom_values or {}
        result: Dict[str, str] = {}

        for header in headers:
            header_config = self.GLOBAL_HEADERS.get(header, {})
            value = custom_values.get(header, header_config.get("default"))

            allowed = header_config.get("allowed_values")
            if allowed and value is not None and value not in allowed:
                raise ValueError(
                    f"Header {header} must be one of {allowed}, got {value}"
                )

            if value is None and header_config.get("generator"):
                value = header_config["generator"]()

            if value is not None:
                result[header] = str(value)

        if token:
            result["Authorization"] = f"{auth_scheme} {token}".strip()

        return result

    def get_params(
        self,
        params: List[str],
        custom_values: Optional[Dict[str, Union[str, int, bool]]] = None,
    ) -> Dict[str, Union[str, int, bool]]:
        custom_values = custom_values or {}
        result: Dict[str, Union[str, int, bool]] = {}

        for param in params:
            param_config = self.GLOBAL_PARAMS.get(param, {})
            value = custom_values.get(param, param_config.get("default"))

            allowed = param_config.get("allowed_values")
            if allowed and value is not None and value not in allowed:
                raise ValueError(
                    f"Parameter {param} must be one of {allowed}, got {value}"
                )

            if value is not None or param_config.get("required"):
                result[param] = value  # type: ignore[assignment]

        return result

    @staticmethod
    def apply_token(
        headers: Dict[str, str],
        token: Optional[str],
        *,
        auth_scheme: str = "Bearer",
    ) -> Dict[str, str]:
        """Return a copy of ``headers`` with Authorization set/cleared (LIB-14)."""
        out = dict(headers or {})
        if not token:
            out.pop("Authorization", None)
            return out
        out["Authorization"] = f"{auth_scheme} {token}".strip()
        return out

    def headers_bind(
        self,
        names: List[str],
        *,
        token: Optional[str] = None,
        custom_values: Optional[Dict[str, Union[str, int, bool]]] = None,
        auth_scheme: str = "Bearer",
    ) -> "HeadersBind":
        """Build a re-bindable headers holder for collection façades."""
        return HeadersBind(
            self,
            names,
            token=token,
            custom_values=custom_values,
            auth_scheme=auth_scheme,
        )


class HeadersBind:
    """Mutable headers view: ``apply_token`` rebuilds the dict without recreating Config.

    Typical consumer::

        class ModelsHeaders:
            def __init__(self, token=None):
                cfg = Config()
                self._read = cfg.headers_bind(["Accept", "X-Request-ID"], token=token)
                self._write = cfg.headers_bind(
                    ["Accept", "Content-Type", "X-Request-ID"], token=token
                )

            @property
            def read(self):
                return self._read.headers

            @property
            def write(self):
                return self._write.headers

            def apply_token(self, token: str):
                self._read.apply_token(token)
                self._write.apply_token(token)
    """

    def __init__(
        self,
        config: Config,
        names: List[str],
        *,
        token: Optional[str] = None,
        custom_values: Optional[Dict[str, Union[str, int, bool]]] = None,
        auth_scheme: str = "Bearer",
    ):
        self._config = config
        self._names = list(names)
        self.token = token
        self._custom_values = dict(custom_values or {})
        self._auth_scheme = auth_scheme
        self.headers: Dict[str, str] = {}
        self.refresh()

    def refresh(self) -> Dict[str, str]:
        self.headers = self._config.get_headers(
            self._names,
            custom_values=self._custom_values,
            token=self.token,
            auth_scheme=self._auth_scheme,
        )
        return self.headers

    def apply_token(self, token: Optional[str]) -> Dict[str, str]:
        self.token = token
        return self.refresh()

    def __getitem__(self, key: str) -> str:
        return self.headers[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.headers.get(key, default)

    def as_dict(self) -> Dict[str, str]:
        return dict(self.headers)

