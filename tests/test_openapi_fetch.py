"""``partest.openapi.resolve_swagger`` fetching a spec on someone else's behalf.

partest-atlas calls it for a project's ``swagger_files``: the address is the project's, the
server may be anyone's. Pinned here: the limits (size — compressed bodies included —, time,
redirects), what crosses a redirect, what reaches a log or an error, and that every failure
is an ``OpenApiResolveError`` without a chained exception.
"""

from __future__ import annotations

import base64
import gzip
import http.server
import logging
import threading
import time
import tracemalloc
import zlib
from pathlib import Path

import httpx
import pytest

import partest.openapi as openapi
from partest.openapi import OpenApiResolveError, _normalize_source, resolve_swagger

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"
SPEC = (
    "openapi: 3.0.0\n"
    "info: {title: probe, version: '1'}\n"
    "paths:\n"
    "  /items:\n"
    "    get:\n"
    "      responses: {'200': {description: ok}}\n"
)
SECRETS = ["s3cr3tpw", "t0k3nvalue", "alice"]


def _no_part_of(secret_parts, text):
    for part in secret_parts:
        assert part not in text, (part, text)


def _assert_unchained(err):
    assert err.__cause__ is None and err.__suppress_context__


# --- sources --------------------------------------------------------------------------


def test_a_pair_is_read_by_the_grammar():
    assert "paths" in resolve_swagger([" File ", str(FIXTURE)])
    with pytest.raises(OpenApiResolveError, match="source_type must be one of"):
        resolve_swagger(["svn", str(FIXTURE)])


def test_a_string_is_a_url_whatever_the_case_of_its_scheme():
    assert _normalize_source("HTTP://h.example/x") == ("url", "HTTP://h.example/x")
    assert _normalize_source("Https://h.example/x") == ("url", "Https://h.example/x")
    assert _normalize_source("docs/openapi.yaml") == ("local", "docs/openapi.yaml")


def test_a_missing_file_is_named_without_credentials():
    with pytest.raises(OpenApiResolveError, match="not found") as caught:
        resolve_swagger("specs/alice:s3cr3tpw@host/spec.json")
    _no_part_of(SECRETS, str(caught.value))


def test_a_local_file_is_bounded():
    with pytest.raises(OpenApiResolveError, match="max_bytes=10"):
        resolve_swagger(FIXTURE, max_bytes=10)
    assert "paths" in resolve_swagger(FIXTURE, max_bytes=None)


def test_a_deep_document_is_an_open_api_error(tmp_path):
    """`json` gives up with RecursionError — not an OpenApiResolveError until now."""
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 200_000, encoding="utf-8")
    with pytest.raises(OpenApiResolveError) as caught:
        resolve_swagger(deep)
    assert caught.value.__cause__ is None


# --- a local server -------------------------------------------------------------------

SEEN: list = []


@pytest.fixture
def server():
    """``/spec`` — the spec with a length; ``/chunked`` — without one; ``/slow`` — a line at
    a time; ``/loop`` — a redirect to itself; ``/hop`` — a redirect to ``/spec``;
    ``/undefined`` — the spec with ``charset=undefined``."""

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):  # noqa: N802 - the stdlib's name
            SEEN.append((self.path, dict(self.headers)))
            path = self.path.split("?", 1)[0]
            body = SPEC.encode("utf-8")
            if path in ("/spec", "/undefined"):
                self.send_response(200)
                if path == "/undefined":
                    self.send_header("Content-Type", "application/yaml; charset=undefined")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path in ("/chunked", "/slow"):
                self.send_response(200)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for line in body.splitlines(keepends=True):
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(line), line))
                    self.wfile.flush()
                    if path == "/slow":
                        time.sleep(0.3)
                self.wfile.write(b"0\r\n\r\n")
            elif path in ("/loop", "/hop"):
                self.send_response(302)
                self.send_header("Location", "/loop" if path == "/loop" else "/spec")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self.send_error(404)

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    SEEN.clear()
    try:
        yield f"127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_fetches_within_the_defaults(server):
    for path in ("/spec", "/chunked", "/hop", "/undefined"):
        assert "/items" in resolve_swagger(f"http://{server}{path}", timeout=5)["paths"], path
    assert SEEN[0][1]["Accept-Encoding"] == "gzip, deflate"  # never br, zstd


@pytest.mark.parametrize("path", ["/spec", "/chunked"])
def test_a_document_past_max_bytes_is_refused(server, path):
    url = f"http://{server}{path}?token=t0k3nvalue"
    with pytest.raises(OpenApiResolveError, match="max_bytes=40") as caught:
        resolve_swagger(url, timeout=5, max_bytes=40)
    _assert_unchained(caught.value)
    _no_part_of(SECRETS, str(caught.value))


def test_total_timeout_bounds_the_fetch(server):
    with pytest.raises(OpenApiResolveError, match="total_timeout=0.5"):
        resolve_swagger(f"http://{server}/slow", timeout=5, total_timeout=0.5)
    assert "/items" in resolve_swagger(f"http://{server}/slow", timeout=5)["paths"]


def test_redirects_are_bounded(server):
    with pytest.raises(OpenApiResolveError, match="max_redirects=3"):
        resolve_swagger(f"http://{server}/loop", timeout=5, max_redirects=3)
    assert len(SEEN) == 4  # the first request and three redirects


@pytest.mark.parametrize(
    "password, encoded",
    [("pa/ss", "pa%2Fss"), ("pa?ss", "pa%3Fss"), ("pa#ss", "pa%23ss"), ("pa＠ss", "pa%40ss")],
)
def test_an_unreadable_address_is_refused_before_any_request(server, password, encoded, mock):
    with pytest.raises(OpenApiResolveError, match="percent-encode") as caught:
        resolve_swagger(["url", f"http://user:{password}@{server}/spec"], timeout=5)
    assert SEEN == []
    _no_part_of(["user", password], str(caught.value))
    # Percent-encoded, the same password reaches an HTTPS server as basic auth.
    mock["handler"] = lambda r: _body(SPEC.encode())
    assert "/items" in resolve_swagger(f"https://user:{encoded}@h.example/spec")["paths"]
    assert mock["seen"][-1].headers["Authorization"].startswith("Basic ")


def test_a_password_without_its_at_is_refused_before_any_request(server):
    """httpx would answer `Invalid port: 'hunter2'`."""
    for url in ("http://admin:hunter2/api", f"http://{server.split(':')[0]}:notaport/x"):
        with pytest.raises(OpenApiResolveError, match="percent-encode") as caught:
            resolve_swagger(url, timeout=5)
        _no_part_of(["hunter2", "notaport"], str(caught.value))
    assert SEEN == []


def test_the_query_stays_out_of_the_log_and_userinfo_goes_as_auth(mock, caplog):
    url = "https://alice:s3cr3tpw@h.example/spec?token=t0k3nvalue&v=1"
    mock["handler"] = lambda r: _body(SPEC.encode())
    with caplog.at_level(logging.INFO):
        assert "/items" in resolve_swagger(url, timeout=5)["paths"]
    assert any("HTTP Request" in r.getMessage() for r in caplog.records)
    _no_part_of(SECRETS, caplog.text)
    request = mock["seen"][-1]
    assert request.headers["Authorization"] == "Basic " + base64.b64encode(
        b"alice:s3cr3tpw"
    ).decode()
    assert request.url.query == b"token=t0k3nvalue&v=1"  # the query still reaches the server


# --- a mock transport: bodies and redirects the stdlib server cannot easily give -----------


@pytest.fixture
def mock(monkeypatch):
    """Route resolve_swagger's client through ``httpx.MockTransport(handler)``."""
    state = {"handler": None, "seen": []}

    def factory(**kwargs):
        kwargs.pop("verify", None)

        def handler(request):
            state["seen"].append(request)
            return state["handler"](request)

        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(openapi, "httpx_client", factory)
    return state


def _body(body: bytes, headers=None) -> httpx.Response:
    """A 200 whose body is streamed: `Response(content=...)` would decode it at once."""
    return httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))


def _encoded(body: bytes, *layers: str) -> bytes:
    for layer in layers:
        body = gzip.compress(body) if layer == "gzip" else zlib.compress(body)
    return body


@pytest.mark.parametrize(
    "encoding, body",
    [
        ("gzip", _encoded(SPEC.encode(), "gzip")),
        ("x-gzip", _encoded(SPEC.encode(), "gzip")),
        ("deflate", zlib.compress(SPEC.encode())),  # zlib-wrapped, as the standard says
        ("deflate", zlib.compress(SPEC.encode())[2:-4]),  # raw, as some servers send it
        ("identity", SPEC.encode()),
    ],
)
def test_one_layer_of_gzip_or_deflate_is_decoded(mock, encoding, body):
    mock["handler"] = lambda r: _body(body, {"Content-Encoding": encoding})
    assert "/items" in resolve_swagger("https://h.example/spec")["paths"]


def test_a_decompression_bomb_stops_at_max_bytes(mock):
    """A gzip body of ~50 KB that inflates to 50 MB: read raw, inflated here to the limit."""
    bomb = gzip.compress(b"\0" * (50 * 1024 * 1024), compresslevel=9)
    mock["handler"] = lambda r: _body(bomb, {"Content-Encoding": "gzip"})
    tracemalloc.start()
    try:
        with pytest.raises(OpenApiResolveError, match="max_bytes=1048576"):
            resolve_swagger("https://h.example/spec", max_bytes=1024 * 1024)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8 * 1024 * 1024, peak


@pytest.mark.parametrize("encoding", ["gzip, gzip", "deflate, gzip", "br", "zstd", "compress"])
def test_other_encodings_and_layers_are_refused(mock, encoding):
    """`gzip, gzip` of 645 bytes inflated to 595 MiB in httpx's own decoder; `br` of 455 bytes
    to 293 MiB. Neither is decoded here."""
    body = _encoded(SPEC.encode(), "gzip", "gzip")
    mock["handler"] = lambda r: _body(body, {"Content-Encoding": encoding})
    with pytest.raises(OpenApiResolveError, match="Content-Encoding .* is not accepted") as caught:
        resolve_swagger("https://h.example/spec")
    _assert_unchained(caught.value)


def test_a_corrupt_body_is_an_open_api_error(mock):
    mock["handler"] = lambda r: _body(b"\x1f\x8bnot gzip at all", {"Content-Encoding": "gzip"})
    with pytest.raises(OpenApiResolveError, match="not valid gzip"):
        resolve_swagger("https://h.example/spec")


def test_a_redirect_to_another_origin_drops_the_callers_headers(mock):
    def handler(request):
        if request.url.host == "h.example":
            if request.url.path == "/same":
                return httpx.Response(302, headers={"Location": "/spec"})
            if request.url.path == "/away":
                return httpx.Response(302, headers={"Location": "https://cdn.example/spec"})
        return _body(SPEC.encode())

    mock["handler"] = handler
    headers = {"X-Api-Key": "k3yvalue", "X-Tenant": "t1"}
    resolve_swagger("https://alice:s3cr3tpw@h.example/same", headers=headers)
    same = mock["seen"][-1]
    assert same.headers["X-Api-Key"] == "k3yvalue" and "Authorization" in same.headers

    resolve_swagger("https://alice:s3cr3tpw@h.example/away", headers=headers)
    first, away = mock["seen"][-2], mock["seen"][-1]
    assert first.headers["X-Api-Key"] == "k3yvalue" and "Authorization" in first.headers
    assert away.url.host == "cdn.example"
    for name in ("X-Api-Key", "X-Tenant", "Authorization"):
        assert name not in away.headers, name


def test_a_redirect_from_https_to_http_is_refused(mock):
    mock["handler"] = lambda r: (
        httpx.Response(302, headers={"Location": "http://h.example/spec"})
        if r.url.scheme == "https"
        else _body(SPEC.encode())
    )
    with pytest.raises(OpenApiResolveError, match="https to http"):
        resolve_swagger("https://h.example/spec")
    assert [r.url.scheme for r in mock["seen"]] == ["https"]


def test_each_step_gets_what_is_left_of_total_timeout(mock):
    def handler(request):
        time.sleep(0.2)
        return httpx.Response(302, headers={"Location": "/again"})

    mock["handler"] = handler
    with pytest.raises(OpenApiResolveError, match="total_timeout=0.5"):
        resolve_swagger("https://h.example/spec", timeout=60, total_timeout=0.5)
    steps = [r.extensions["timeout"]["read"] for r in mock["seen"]]
    assert 2 <= len(steps) <= 4, steps
    assert all(s <= 0.5 for s in steps), steps
    assert steps == sorted(steps, reverse=True), steps


@pytest.mark.parametrize(
    "exc",
    [
        httpx.InvalidURL("Invalid port: 's3cr3tpw'"),
        UnicodeError("encoding with 'idna' codec failed (alice:s3cr3tpw@h)"),
        ValueError("netloc 'alice:s3cr3tpw@h' contains invalid characters"),
        RecursionError("maximum recursion depth exceeded"),
    ],
)
def test_any_failure_is_an_open_api_error_without_the_secret(monkeypatch, exc):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(openapi, "_fetch", boom)
    with pytest.raises(OpenApiResolveError) as caught:
        resolve_swagger("https://alice:s3cr3tpw@h.example/spec")
    _assert_unchained(caught.value)
    _no_part_of(SECRETS, str(caught.value))


# --- a mistyped scheme, a path with a query, a cut stream, the C loader -------------------

MISTYPED = [
    "https:/alice:PWSECRET@h.example/x?k=KSECRET",
    "https//alice:PWSECRET@h.example/x?k=KSECRET",
    "ｈttps://alice:PWSECRET@h.example/x?k=KSECRET",  # a full-width `h`
]


@pytest.mark.parametrize("url", MISTYPED + ["ftp://alice:PWSECRET@h.example/x?k=KSECRET"])
def test_a_url_entry_must_be_http_and_is_never_quoted(url):
    with pytest.raises(OpenApiResolveError, match="must start with http") as caught:
        resolve_swagger(["url", url])
    _no_part_of(["PWSECRET", "KSECRET", "alice"], str(caught.value))


@pytest.mark.parametrize(
    "source",
    MISTYPED
    + [
        "s3://bucket/spec.yaml?X-Amz-Signature=KSECRET",
        "ftp://h.example/spec.yaml?t=KSECRET#PWSECRET",
    ],
)
def test_a_string_read_as_a_path_is_named_without_secrets(source):
    with pytest.raises(OpenApiResolveError, match="not found") as caught:
        resolve_swagger(source)
    _no_part_of(["PWSECRET", "KSECRET", "alice"], str(caught.value))


def test_a_failure_names_the_url_as_redact_url_shows_it(mock):
    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")

    mock["handler"] = handler
    with pytest.raises(OpenApiResolveError) as caught:
        resolve_swagger("https://alice:s3cr3tpw@h.example/spec?token=t0k3nvalue#frag")
    text = str(caught.value)
    assert "Failed to fetch OpenAPI URL https://h.example/spec:" in text
    _no_part_of(SECRETS + ["frag"], text)


def test_a_cut_compressed_stream_is_refused(mock):
    """A cut connection or file: half a gzip stream can still decode to valid YAML."""
    whole = gzip.compress((SPEC + "# " + "x" * 5000 + "\n").encode())
    mock["handler"] = lambda r: _body(whole[: len(whole) // 2], {"Content-Encoding": "gzip"})
    with pytest.raises(OpenApiResolveError, match="ends before its gzip stream"):
        resolve_swagger("https://h.example/spec")
    mock["handler"] = lambda r: _body(b"", {"Content-Encoding": "gzip"})
    with pytest.raises(OpenApiResolveError, match="gzip stream"):  # an empty one too
        resolve_swagger("https://h.example/spec")


@pytest.mark.skipif(not hasattr(__import__("yaml"), "CSafeLoader"), reason="PyYAML without libyaml")
def test_yaml_goes_through_the_c_loader(monkeypatch):
    import yaml

    seen = []
    real = yaml.load

    def spy(stream, Loader):  # noqa: N803 - PyYAML's name
        seen.append(Loader)
        return real(stream, Loader=Loader)

    monkeypatch.setattr(openapi.yaml, "load", spy)
    assert "paths" in resolve_swagger(FIXTURE)
    assert seen == [yaml.CSafeLoader]


def test_explicit_basic_auth_uses_the_existing_https_fetch(mock):
    mock["handler"] = lambda r: _body(SPEC.encode())

    assert "/items" in resolve_swagger(
        "https://h.example/spec", auth=("explicit-user", "explicit-secret")
    )["paths"]

    expected = "Basic " + base64.b64encode(b"explicit-user:explicit-secret").decode()
    assert mock["seen"][-1].headers["Authorization"] == expected


def test_explicit_basic_auth_over_http_is_refused_before_the_client(mock):
    with pytest.raises(OpenApiResolveError, match="requires an https:// URL") as caught:
        resolve_swagger("http://h.example/spec", auth=("http-user", "http-secret"))

    assert mock["seen"] == []
    _no_part_of(["http-user", "http-secret"], str(caught.value))
    _assert_unchained(caught.value)


def test_resolve_from_confpartest_selects_only_the_named_services_auth(mock):
    from partest.openapi import resolve_from_confpartest

    class Conf:
        swagger_files = {
            "public": ["url", "https://public.example/spec"],
            "private": ["url", "https://private.example/spec"],
        }
        swagger_auth = {"private": ("private-user", "private-secret")}

    mock["handler"] = lambda r: _body(SPEC.encode())
    assert "/items" in resolve_from_confpartest(Conf)["paths"]
    assert "Authorization" not in mock["seen"][-1].headers
    assert "/items" in resolve_from_confpartest(Conf, service="private")["paths"]
    expected = "Basic " + base64.b64encode(b"private-user:private-secret").decode()
    assert mock["seen"][-1].headers["Authorization"] == expected


def test_explicit_auth_and_authorization_header_keep_their_priority(mock):
    from partest.openapi import resolve_from_confpartest

    class Conf:
        swagger_files = {"api": ["url", "https://h.example/spec"]}
        swagger_auth = {"api": ("configured-user", "configured-secret")}

    mock["handler"] = lambda r: _body(SPEC.encode())
    resolve_from_confpartest(Conf, auth=("explicit-user", "explicit-secret"))
    expected = "Basic " + base64.b64encode(b"explicit-user:explicit-secret").decode()
    assert mock["seen"][-1].headers["Authorization"] == expected

    resolve_from_confpartest(Conf, headers={"Authorization": "Bearer caller-token"})
    assert mock["seen"][-1].headers["Authorization"] == "Bearer caller-token"

    resolve_from_confpartest(Conf, auth=None)
    assert "Authorization" not in mock["seen"][-1].headers


def test_resolve_from_confpartest_rejects_http_auth_before_the_client(mock):
    from partest.openapi import resolve_from_confpartest

    class Conf:
        swagger_files = {"api": ["url", "http://h.example/spec"]}
        swagger_auth = {"api": ("configured-user", "configured-secret")}

    with pytest.raises(OpenApiResolveError, match="requires an https:// URL") as caught:
        resolve_from_confpartest(Conf)

    assert mock["seen"] == []
    _no_part_of(["configured-user", "configured-secret"], str(caught.value))


def test_resolve_from_confpartest_validates_auth_names_before_the_client(mock):
    from partest.openapi import resolve_from_confpartest

    class Conf:
        swagger_files = {"api": ["url", "https://h.example/spec"]}
        swagger_auth = {"ap1": ("configured-user", "configured-secret")}

    with pytest.raises(OpenApiResolveError, match="no matching swagger_files") as caught:
        resolve_from_confpartest(Conf)

    assert mock["seen"] == []
    _no_part_of(["configured-user", "configured-secret"], str(caught.value))


def test_explicit_auth_is_dropped_on_a_cross_origin_redirect(mock):
    def handler(request):
        if request.url.host == "h.example":
            return httpx.Response(302, headers={"Location": "https://cdn.example/spec"})
        return _body(SPEC.encode())

    mock["handler"] = handler
    resolve_swagger("https://h.example/spec", auth=("redirect-user", "redirect-secret"))

    first, away = mock["seen"]
    assert "Authorization" in first.headers
    assert "Authorization" not in away.headers


def test_explicit_auth_is_cleared_from_resolve_traceback_frames(mock):
    def handler(request):
        raise httpx.ConnectError("cannot send trace-user:trace-secret")

    mock["handler"] = handler
    with pytest.raises(OpenApiResolveError) as caught:
        resolve_swagger(
            "https://h.example/spec", auth=("trace-user", "trace-secret")
        )

    error = caught.value
    _assert_unchained(error)
    _no_part_of(["trace-user", "trace-secret"], str(error))
    library_frames = []
    tb = error.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == openapi.__file__:
            library_frames.append(tb.tb_frame)
        tb = tb.tb_next
    assert library_frames
    for frame in library_frames:
        shown_locals = repr(frame.f_locals)
        _no_part_of(["trace-user", "trace-secret"], shown_locals)
        if "auth" in frame.f_locals:
            assert frame.f_locals["auth"] is None


def _assert_clean_openapi_traceback(error, *secrets):
    _assert_unchained(error)
    assert error.__context__ is None
    _no_part_of(secrets, str(error))
    library_frames = []
    tb = error.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == openapi.__file__:
            library_frames.append(tb.tb_frame)
        tb = tb.tb_next
    assert library_frames
    for frame in library_frames:
        _no_part_of(secrets, repr(frame.f_locals))
        if frame.f_code.co_name == "resolve_from_confpartest":
            assert frame.f_locals["kwargs"] is None
            for name in (
                "conf", "configured_auth", "swagger", "entry", "location",
                "source_entry", "source_location", "raw", "url_auth", "auth_errors",
            ):
                assert frame.f_locals[name] is None, name
        if frame.f_code.co_name == "resolve_swagger":
            for name in ("source", "location", "raw", "url_auth", "hidden_auth"):
                assert frame.f_locals[name] is None, name


@pytest.mark.parametrize("failure", ["http", "validation", "network"])
def test_resolve_from_confpartest_clears_its_own_traceback(mock, failure):
    from partest.openapi import resolve_from_confpartest

    class Conf:
        swagger_auth = {"ap1" if failure == "validation" else "api": (
            "wrapper-user", "wrapper-secret"
        )}

    Conf.swagger_files = {
        "api": ["url", f"http{'s' if failure != 'http' else ''}://h.example/spec"]
    }
    if failure == "network":
        def handler(request):
            raise httpx.ConnectError("cannot send wrapper-user:wrapper-secret")

        mock["handler"] = handler
    with pytest.raises(OpenApiResolveError) as caught:
        resolve_from_confpartest(Conf)

    _assert_clean_openapi_traceback(caught.value, "wrapper-user", "wrapper-secret")


def test_userinfo_is_cleared_from_resolve_traceback_and_parser_chain(mock):
    mock["handler"] = lambda request: _body(b"openapi: [")

    with pytest.raises(OpenApiResolveError) as caught:
        resolve_swagger("https://userinfo-user:userinfo-secret@h.example/spec")

    _assert_clean_openapi_traceback(caught.value, "userinfo-user", "userinfo-secret")
