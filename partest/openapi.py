"""Resolve OpenAPI / swagger specs from local path or URL (project-agnostic)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Union

import httpx
import yaml

from partest.http.client import httpx_client
from partest.tls import (
    VerifySetting,
    certificate_error,
    is_certificate_error,
    resolve_verify,
)

SpecSource = Union[str, Path, Tuple[str, str], Sequence[str]]


class OpenApiResolveError(RuntimeError):
    """Failed to load or parse an OpenAPI document."""


def _split_credentials(location: str) -> Tuple[str, Optional[Tuple[str, str]]]:
    """``user:password@`` out of the URL and into ``auth=``, so no log line carries it."""
    from urllib.parse import unquote, urlsplit, urlunsplit

    try:
        parts = urlsplit(location)
    except ValueError:
        return location, None
    if "@" not in parts.netloc:
        return location, None
    userinfo, host = parts.netloc.rsplit("@", 1)
    user, _, password = userinfo.partition(":")
    return urlunsplit(parts._replace(netloc=host)), (unquote(user), unquote(password))


class _HideQuery(logging.Filter):
    """Rewrites httpx's ``HTTP Request: GET <url> ...`` line for one URL with a query string.

    httpx logs every request at INFO from inside ``Client``, whatever the transport, so the
    line cannot be avoided without bypassing the client (and with it redirects and the TLS
    policy). Installed on the ``httpx`` logger only for the duration of the request, it touches
    only arguments that contain this URL's query; the consumer's logging setup is unchanged.
    """

    def __init__(self, query: str):
        super().__init__()
        self.query = query

    def filter(self, record: logging.LogRecord) -> bool:
        from partest.conf import _safe_text

        if isinstance(record.args, tuple):
            record.args = tuple(
                _safe_text(arg) if self.query in str(arg) else arg for arg in record.args
            )
        return True


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
        # Settled here rather than left to the factory only because the failure message
        # below has to quote the value that was used.
        from partest.conf import _safe_text

        settled = resolve_verify(verify)
        shown = _safe_text(location, secrets_of=location)
        url, auth = _split_credentials(location)
        request_headers = dict(headers or {})
        if any(k.lower() == "authorization" for k in request_headers):
            auth = None  # the caller's header wins
        query = url.split("?", 1)[1].split("#", 1)[0] if "?" in url else ""
        quiet = _HideQuery(query) if query else None
        httpx_logger = logging.getLogger("httpx")
        failure = None
        if quiet is not None:
            httpx_logger.addFilter(quiet)
        try:
            with httpx_client(timeout=timeout, verify=settled,
                              follow_redirects=True) as client:
                resp = client.get(url, headers=request_headers, auth=auth)
                resp.raise_for_status()
                text = resp.text
        except httpx.HTTPError as e:
            # Messages are sanitised and not chained: a traceback would print the original
            # exception, and with it credentials or a token in the URL.
            if is_certificate_error(e):
                # A specification usually lives on a different host from the stand, and
                # this failure happens while tests are being collected, not while one
                # runs — so the message has to carry the whole answer on its own.
                failure = str(certificate_error(e, url=location, verify=settled))
            else:
                failure = f"Failed to fetch OpenAPI URL {location}: {e}"
        finally:
            if quiet is not None:
                httpx_logger.removeFilter(quiet)
        if failure is not None:
            raise OpenApiResolveError(_safe_text(failure, secrets_of=location)) from None
        return _parse_spec_text(text, hint=shown)

    raise OpenApiResolveError(f"Unknown OpenAPI source kind {kind!r}")


def resolve_from_confpartest(
    conf: Any = None,
    *,
    service: Optional[str] = None,
    project_root: Optional[Union[str, Path]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Resolve first (or named) entry from ``confpartest.swagger_files``.

    Without *project_root*, a relative local path that does not exist from the current
    directory is taken from the directory of ``confpartest.py``.
    """
    if conf is None:
        from partest.conf import require_confpartest

        conf = require_confpartest(project_root=project_root)
    swagger = getattr(conf, "swagger_files", None) or {}
    if project_root is None and isinstance(swagger, Mapping) and swagger:
        from partest.conf import _module_dir

        entry = swagger[service] if service in swagger else next(iter(swagger.values()))
        try:
            kind, location = _normalize_source(entry)
        except OpenApiResolveError:
            kind, location = "", ""
        base = _module_dir(conf)
        if (
            kind in {"local", "file", "path"}
            and base is not None
            and not Path(location).is_absolute()
            and not Path(location).exists()
            and (base / location).exists()
        ):
            project_root = base
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
