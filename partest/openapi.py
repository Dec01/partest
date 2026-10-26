"""Resolve OpenAPI / swagger specs from local path or URL (project-agnostic)."""

from __future__ import annotations

import json
import logging
import time
import zlib
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Union

import httpx
import yaml

from partest.conf import ConfpartestError, parse_swagger_entry
from partest.http.client import httpx_client
from partest.tls import (
    VerifySetting,
    certificate_error,
    is_certificate_error,
    resolve_verify,
)

__all__ = [
    "resolve_swagger",
    "resolve_from_confpartest",
    "OpenApiResolveError",
    "SpecSource",
    "DEFAULT_MAX_SPEC_BYTES",
]

SpecSource = Union[str, Path, Tuple[str, str], Sequence[str]]

#: The largest OpenAPI document :func:`resolve_swagger` reads, in bytes (64 MiB). The
#: largest public specifications are a few tens of megabytes; past this a document is an
#: error, not a reason to keep reading.
DEFAULT_MAX_SPEC_BYTES = 64 * 1024 * 1024

# The C parser when PyYAML has it: a 64 MiB document takes the pure-Python one minutes and
# gigabytes. Both are the safe loader.
_HAS_C_YAML = hasattr(yaml, "CSafeLoader")
# What a fetched body may be encoded with: none, or one layer that is decoded here, within
# `max_bytes` — `br` and `zstd` are not, and neither are layers on layers (a decompression
# bomb of a few hundred bytes otherwise fills hundreds of megabytes before a limit sees it).
_ACCEPT_ENCODING = "gzip, deflate"
_DECODED_ENCODINGS = frozenset({"gzip", "x-gzip", "deflate"})


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
    line cannot be avoided without bypassing the client (and with it the TLS policy).
    Installed on the ``httpx`` logger only for the duration of the request, it touches only
    arguments that contain this URL's query; the consumer's logging setup is unchanged.
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
        if _HAS_C_YAML:
            data = yaml.load(text, Loader=yaml.CSafeLoader)
        else:
            data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except yaml.YAMLError as e:
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
    max_bytes: Optional[int] = DEFAULT_MAX_SPEC_BYTES,
    total_timeout: Optional[float] = None,
    max_redirects: int = 20,
) -> Dict[str, Any]:
    """Load OpenAPI dict from local file, URL, or confpartest entry.

    Accepts::

        resolve_swagger("docs/openapi.yaml")
        resolve_swagger("https://api.example/v3/api-docs")   # the scheme in any case
        resolve_swagger(["local", "docs/openapi.yaml"])
        resolve_swagger(["url", "https://…"])
        resolve_swagger(("file", Path("…")))

    A pair is read by :func:`partest.conf.parse_swagger_entry` — the grammar of
    ``confpartest.swagger_files``. A relative local path is taken from *project_root*, or
    from the current directory.

    For a URL:

    * ``user:password@`` is sent as basic ``auth=`` and never logged (a caller's own
      ``Authorization`` header wins); the query string is kept out of httpx's INFO
      ``HTTP Request:`` line;
    * redirects are followed up to *max_redirects*; one to another origin (scheme, host or
      port) drops the caller's *headers* and the credentials, and one from ``https`` to
      ``http`` is refused;
    * the body may be plain or one layer of ``gzip`` / ``deflate`` — decoded here, never past
      *max_bytes*; ``br``, ``zstd`` and several layers are refused;
    * *timeout* bounds each step (connect, each read). *total_timeout*, when set, is checked
      before each request and between the chunks of the body, and each step's timeout is cut
      to what is left of it: past the headers, the body and the redirects overrun it by at
      most one *timeout*. While the headers arrive it does not apply — a server that sends
      them a byte at a time, each within *timeout*, holds the call as long as it keeps
      sending — and resolving the host name (DNS) is bounded by neither;
    * a ``url`` must start with ``http://`` or ``https://``; one whose password holds a raw
      ``/``, ``?``, ``#`` or ``@``, or whose "port" is not a number, is refused before any
      request;
    * every message names the location the way :func:`partest.redact.redact_url` shows it.

    *max_bytes* bounds the document, local or fetched (decoded); ``None`` lifts it. Every
    failure is :class:`OpenApiResolveError`, its text without URL credentials or the query
    string and without a chained exception — except a YAML parse error, which keeps the
    parser's exception chained.
    """
    try:
        return _resolve(
            source,
            project_root=project_root,
            timeout=timeout,
            verify=verify,
            headers=headers,
            max_bytes=max_bytes,
            total_timeout=total_timeout,
            max_redirects=max_redirects,
        )
    except OpenApiResolveError:
        raise
    except Exception as exc:  # anything else may quote the address: httpx, IDNA, urlsplit
        from partest.conf import _safe_text

        location = source[1] if isinstance(source, (list, tuple)) and len(source) > 1 else source
        try:
            raw: Optional[str] = str(location)
        except Exception:
            raw = None
        text = f"{type(exc).__name__}: {exc}"
        raise OpenApiResolveError(f"Cannot load OpenAPI: {_shown_error(text, raw)}") from None


def _shown_error(text: str, location: Optional[str], *also: str) -> str:
    """*text* safe to show: the location — and *also*, other spellings of it, such as the
    URL without its credentials that httpx quotes —, wherever quoted whole, as
    :func:`redact_url` shows it (closed on doubt); then the configuration-error rule over the
    rest."""
    from partest.conf import _safe_text
    from partest.redact import redact_url

    for spelling in sorted({s for s in (location, *also) if s}, key=len, reverse=True):
        text = text.replace(spelling, redact_url(spelling))
    return _safe_text(text, secrets_of=location)


def _resolve(
    source: SpecSource,
    *,
    project_root: Optional[Union[str, Path]],
    timeout: float,
    verify: Optional[VerifySetting],
    headers: Optional[Mapping[str, str]],
    max_bytes: Optional[int],
    total_timeout: Optional[float],
    max_redirects: int,
) -> Dict[str, Any]:
    from partest.conf import _safe_text
    from partest.redact import redact_url

    kind, location = _normalize_source(source)
    # The location as written, the way redact_url shows one address: no credentials, no
    # query string or fragment (`s3://bucket/spec.yaml?X-Amz-Signature=…` read as a path),
    # closed on doubt (`https:/user:pw@host` with a slash lost).
    shown = redact_url(location)
    if kind == "local":
        root = Path(project_root).resolve() if project_root else Path.cwd()
        path = Path(location)
        where = shown
        if not path.is_absolute():
            path = (root / path).resolve()
            where = f"{shown} (relative to {_safe_text(str(root))})"
        if not path.is_file():
            raise OpenApiResolveError(f"OpenAPI file not found: {where}")
        if max_bytes is not None and path.stat().st_size > max_bytes:
            raise OpenApiResolveError(f"OpenAPI file {where} is larger than max_bytes={max_bytes}")
        return _parse_spec_text(path.read_text(encoding="utf-8"), hint=shown)

    from partest.redact import _unreadable_address

    if _unreadable_address(location):
        # httpx would read `user:pa` as host and port, and quote the "port" back.
        raise OpenApiResolveError(
            f"OpenAPI URL {shown} cannot be read as an address — a password with a raw '/', "
            "'?', '#' or '@', or a port that is not a number; percent-encode them (%2F, %3F, "
            "%23, %40)"
        )
    # Settled here rather than left to the factory only because the failure message
    # below has to quote the value that was used.
    settled = resolve_verify(verify)
    url, auth = _split_credentials(location)
    request_headers = dict(headers or {})
    if any(k.lower() == "authorization" for k in request_headers):
        auth = None  # the caller's header wins
    if not any(k.lower() == "accept-encoding" for k in request_headers):
        request_headers["Accept-Encoding"] = _ACCEPT_ENCODING
    query = url.split("?", 1)[1].split("#", 1)[0] if "?" in url else ""
    quiet = _HideQuery(query) if query else None
    httpx_logger = logging.getLogger("httpx")
    failure = None
    if quiet is not None:
        httpx_logger.addFilter(quiet)
    try:
        with httpx_client(timeout=timeout, verify=settled, follow_redirects=False) as client:
            text = _fetch(
                client,
                client.build_request("GET", url, headers=request_headers),
                auth=auth,
                caller_headers=list(headers or {}),
                timeout=timeout,
                max_bytes=max_bytes,
                total_timeout=total_timeout,
                max_redirects=max_redirects,
            )
    except httpx.HTTPError as e:
        # Messages are sanitised and not chained: a traceback would print the original
        # exception, and with it credentials or a token in the URL.
        if is_certificate_error(e):
            # A specification usually lives on a different host from the stand, and
            # this failure happens while tests are being collected, not while one
            # runs — so the message has to carry the whole answer on its own.
            failure = str(certificate_error(e, url=shown, verify=settled))
        else:
            failure = f"Failed to fetch OpenAPI URL {shown}: {e}"
    except _FetchRefused as e:
        failure = f"Failed to fetch OpenAPI URL {shown}: {e}"
    finally:
        if quiet is not None:
            httpx_logger.removeFilter(quiet)
    if failure is not None:
        raise OpenApiResolveError(_shown_error(failure, location, url)) from None
    return _parse_spec_text(text, hint=shown)


class _FetchRefused(Exception):
    """The fetch stopped on a limit or a rule of :func:`resolve_swagger`."""


def _origin(url: httpx.URL) -> Tuple[str, str, Optional[int]]:
    default = {"http": 80, "https": 443}.get(url.scheme)
    return url.scheme, url.host, url.port or default


def _fetch(
    client: httpx.Client,
    request: httpx.Request,
    *,
    auth: Optional[Tuple[str, str]],
    caller_headers: Sequence[str],
    timeout: float,
    max_bytes: Optional[int],
    total_timeout: Optional[float],
    max_redirects: int,
) -> str:
    """GET *request*, following redirects by hand: each step gets what is left of
    *total_timeout*, and a step to another origin goes without the caller's headers."""
    started = time.monotonic()
    origin = _origin(request.url)
    redirects = 0
    while True:
        step = timeout
        if total_timeout is not None:
            left = total_timeout - (time.monotonic() - started)
            if left <= 0:
                raise _FetchRefused(f"not answered within total_timeout={total_timeout}s")
            step = min(timeout, left)
        request.extensions["timeout"] = httpx.Timeout(step).as_dict()
        response = client.send(request, auth=auth, stream=True)
        try:
            following = response.next_request
            if following is None:
                response.raise_for_status()
                return _read_body(response, max_bytes, total_timeout, started)
        finally:
            response.close()
        redirects += 1
        if redirects > max_redirects:
            raise _FetchRefused(f"more than max_redirects={max_redirects} redirects")
        if request.url.scheme == "https" and following.url.scheme != "https":
            raise _FetchRefused("a redirect from https to http is refused")
        if _origin(following.url) != origin:
            # httpx drops `Authorization` alone, and keeps it on an http → https step.
            for name in [*caller_headers, "Authorization", "Cookie"]:
                following.headers.pop(name, None)
            auth = None
        request = following


def _encodings(response: httpx.Response) -> list:
    tokens = response.headers.get_list("content-encoding", split_commas=True)
    return [t.strip().lower() for t in tokens if t.strip() and t.strip().lower() != "identity"]


def _decoder(head: bytes) -> Any:
    """A ``zlib`` decoder for a ``gzip`` or ``deflate`` body; ``deflate`` is zlib-wrapped by
    the standard and raw in the wild — told apart by the zlib header."""
    return zlib.decompressobj(
        zlib.MAX_WBITS
        if len(head) >= 2 and head[0] & 0x0F == 8 and (head[0] << 8 | head[1]) % 31 == 0
        else -zlib.MAX_WBITS
    )


def _read_body(
    response: httpx.Response,
    max_bytes: Optional[int],
    total_timeout: Optional[float],
    started: float,
) -> str:
    """The body of a streamed response as text, within *max_bytes* and *total_timeout*.

    Read raw and decoded here, so a compressed body is stopped at *max_bytes* of output, not
    after a whole decompressed chunk. Decoded the way ``Response.text`` decodes: the charset
    of ``Content-Type``, else UTF-8, undecodable bytes replaced.
    """
    too_large = f"the document is larger than max_bytes={max_bytes}"
    encodings = _encodings(response)
    if len(encodings) > 1 or (encodings and encodings[0] not in _DECODED_ENCODINGS):
        raise _FetchRefused(
            f"Content-Encoding {', '.join(encodings)} is not accepted: identity, or one layer "
            "of gzip or deflate"
        )
    declared = response.headers.get("content-length", "")
    if max_bytes is not None and declared.isdigit() and int(declared) > max_bytes:
        raise _FetchRefused(too_large)
    gzip = encodings and encodings[0] in ("gzip", "x-gzip")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if gzip else None
    head = b""
    out = bytearray()

    def take(data: bytes) -> None:
        nonlocal decoder
        if not encodings:
            out.extend(data)
        else:
            if decoder is None:  # deflate: which kind shows in the first two bytes
                decoder = _decoder(data[:2])
            while data and not decoder.eof:
                budget = 0 if max_bytes is None else max_bytes - len(out) + 1
                try:
                    out.extend(decoder.decompress(data, budget))
                except zlib.error:
                    raise _FetchRefused(f"the body is not valid {encodings[0]}") from None
                if max_bytes is not None and len(out) > max_bytes:
                    break
                data = decoder.unconsumed_tail
        if max_bytes is not None and len(out) > max_bytes:
            raise _FetchRefused(too_large)

    for raw in response.iter_raw():
        if total_timeout is not None and time.monotonic() - started > total_timeout:
            raise _FetchRefused(f"the document did not arrive within total_timeout={total_timeout}s")
        if encodings and decoder is None and len(head) + len(raw) < 2:
            head += raw
            continue
        take(head + raw)
        head = b""
    if head:
        take(head)
    if encodings and decoder is None:  # an empty compressed body
        raise _FetchRefused(f"the body is not valid {encodings[0]}")
    if decoder is not None:
        out.extend(decoder.flush())
        if max_bytes is not None and len(out) > max_bytes:
            raise _FetchRefused(too_large)
        if not decoder.eof:
            # A cut connection or a cut file: what arrived may still parse, as half a spec.
            raise _FetchRefused(f"the body ends before its {encodings[0]} stream does")
    body = bytes(out)
    try:
        return body.decode(response.charset_encoding or "utf-8", errors="replace")
    except (LookupError, UnicodeError):  # a charset Python does not know, or `undefined`
        return body.decode("utf-8", errors="replace")


def resolve_from_confpartest(
    conf: Any = None,
    *,
    service: Optional[str] = None,
    project_root: Optional[Union[str, Path]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Resolve first (or named) entry from ``confpartest.swagger_files``.

    Without *project_root*, a relative local path that does not exist from the current
    directory is taken from the directory of ``confpartest.py`` — the rule of
    :func:`partest.conf.resolve_entry_location`.
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
            kind == "local"
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
    """``("local" | "url", location)``: a pair by the ``swagger_files`` grammar; a string or
    a path — ``url`` when it starts with ``http://`` or ``https://`` in any case."""
    if isinstance(source, (list, tuple)):
        try:
            return parse_swagger_entry(source)
        except ConfpartestError as exc:
            raise OpenApiResolveError(f"OpenAPI source pair: {exc}") from None
    text = str(source).strip()
    if text.lower().startswith(("http://", "https://")):
        return "url", text
    return "local", text
