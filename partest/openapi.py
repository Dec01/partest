"""Resolve OpenAPI / swagger specs from local path or URL (project-agnostic)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Union

import httpx
import yaml

from partest.tls import (
    VerifySetting,
    certificate_error,
    is_certificate_error,
    resolve_verify,
    verify_for_httpx,
)

SpecSource = Union[str, Path, Tuple[str, str], Sequence[str]]


class OpenApiResolveError(RuntimeError):
    """Failed to load or parse an OpenAPI document."""


def _parse_spec_text(text: str, *, hint: str = "") -> Dict[str, Any]:
    text = text.lstrip("\ufeff")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception as e:
        raise OpenApiResolveError(f"Cannot parse OpenAPI ({hint}): {e}") from e
    raise OpenApiResolveError(f"OpenAPI root must be a mapping ({hint})")


def resolve_swagger(
    source: SpecSource,
    *,
    project_root: Optional[Union[str, Path]] = None,
    timeout: float = 60.0,
    # ``None`` means "caller did not say" and defers to the package-wide switch, so a
    # stand with a self-signed certificate is turned off in one place instead of here
    # separately. An explicit value still wins.
    verify: Optional[VerifySetting] = None,
    headers: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Load OpenAPI dict from local file, URL, or confpartest entry.

    Accepts::

        resolve_swagger("docs/openapi.yaml")
        resolve_swagger("https://api.example/v3/api-docs")
        resolve_swagger(["local", "docs/openapi.yaml"])
        resolve_swagger(["url", "https://…"])
        resolve_swagger(("file", Path("…")))
    """
    kind, location = _normalize_source(source)
    root = Path(project_root).resolve() if project_root else Path.cwd()

    if kind in {"local", "file", "path"}:
        path = Path(location)
        if not path.is_absolute():
            path = (root / path).resolve()
        if not path.is_file():
            raise OpenApiResolveError(f"OpenAPI file not found: {path}")
        return _parse_spec_text(path.read_text(encoding="utf-8"), hint=str(path))

    if kind == "url":
        settled = resolve_verify(verify)
        try:
            with httpx.Client(timeout=timeout, verify=verify_for_httpx(settled),
                              follow_redirects=True) as client:
                resp = client.get(location, headers=dict(headers or {}))
                resp.raise_for_status()
                return _parse_spec_text(resp.text, hint=location)
        except httpx.HTTPError as e:
            if is_certificate_error(e):
                # A specification usually lives on a different host from the stand, and
                # this failure happens while tests are being collected, not while one
                # runs — so the message has to carry the whole answer on its own.
                raise OpenApiResolveError(
                    str(certificate_error(e, url=location, verify=settled))
                ) from e
            raise OpenApiResolveError(f"Failed to fetch OpenAPI URL {location}: {e}") from e

    raise OpenApiResolveError(f"Unknown OpenAPI source kind {kind!r}")


def resolve_from_confpartest(
    conf: Any = None,
    *,
    service: Optional[str] = None,
    project_root: Optional[Union[str, Path]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Resolve first (or named) entry from ``confpartest.swagger_files``."""
    if conf is None:
        from partest.conf import require_confpartest

        conf = require_confpartest(project_root=project_root)
    swagger = getattr(conf, "swagger_files", None) or {}
    if not isinstance(swagger, Mapping) or not swagger:
        raise OpenApiResolveError("confpartest.swagger_files is empty or invalid")
    if service is not None:
        if service not in swagger:
            raise OpenApiResolveError(
                f"service {service!r} not in swagger_files; known={list(swagger)}"
            )
        return resolve_swagger(swagger[service], project_root=project_root, **kwargs)
    # first entry
    name = next(iter(swagger))
    return resolve_swagger(swagger[name], project_root=project_root, **kwargs)


def _normalize_source(source: SpecSource) -> Tuple[str, str]:
    if isinstance(source, (list, tuple)):
        if len(source) < 2:
            raise OpenApiResolveError(f"source pair needs [kind, location], got {source!r}")
        return str(source[0]).lower(), str(source[1])
    text = str(source).strip()
    if text.startswith("http://") or text.startswith("https://"):
        return "url", text
    return "local", text
