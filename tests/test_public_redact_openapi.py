"""The public surface consumers build on: ``partest.redact``, ``partest.openapi`` and the
grammar of a ``swagger_files`` entry (``partest.conf``).

partest-atlas and veha kept copies of these; the copies are to go, so what they rely on is
pinned here: the names, the one URL core behind ``redact_url``, ``redact_text`` and the
output channels, and the closed-on-doubt rule for an address that cannot be read. Fetching a
spec is ``test_openapi_fetch.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import partest.conf as conf
import partest.openapi as openapi
import partest.redact as redact
from partest.conf import (
    SWAGGER_SOURCE_KINDS,
    ConfpartestError,
    SwaggerEntry,
    _resolve_relative,
    _safe_text,
    parse_swagger_entry,
    resolve_entry_location,
    validate_confpartest,
)
from partest.redact import REDACTED, _scrub_text, _scrub_urls, redact_text, redact_url

# A raw `/`, `?` or `#` in a password cuts the authority short: the parser that follows RFC
# 3986 reads `user:pa` as host and port and the rest as path, query or fragment.
CUT_PASSWORDS = [
    "https://user:pa/ss@h.example/x",
    "https://user:pa#ss@h.example/x",
    "https://user:pa?ss@h.example/x",
    "https://user:pa/s?s@h.example/x",
    "https://user:1234?ss@h.example/x",  # a password that starts like a port
]


def _no_part_of(secret_parts, text):
    for part in secret_parts:
        assert part not in text, (part, text)


# --- the names ------------------------------------------------------------------------


def test_redact_declares_its_public_names():
    assert sorted(redact.__all__) == sorted(
        [
            "DEFAULT_SENSITIVE_HEADERS",
            "DEFAULT_SENSITIVE_BODY_KEYS",
            "mask_secret",
            "redact_text",
            "redact_headers",
            "redact_mapping",
            "redact_url",
            "REDACTED",
        ]
    )
    assert REDACTED == "<redacted>"
    for name in redact.__all__:
        assert getattr(redact, name) is not None


def test_openapi_declares_its_public_names():
    assert sorted(openapi.__all__) == sorted(
        [
            "resolve_swagger",
            "resolve_from_confpartest",
            "OpenApiResolveError",
            "SpecSource",
            "DEFAULT_MAX_SPEC_BYTES",
        ]
    )
    for name in openapi.__all__:
        assert hasattr(openapi, name), name


def test_the_grammar_has_one_home():
    for name in (
        "ConfpartestError",
        "load_confpartest",
        "require_confpartest",
        "validate_confpartest",
        "confpartest_snapshot",
        "conf_attr",
        "SWAGGER_SOURCE_KINDS",
        "SwaggerEntry",
        "parse_swagger_entry",
        "resolve_entry_location",
    ):
        assert name in conf.__all__, name
        assert hasattr(conf, name), name
    for name in ("SWAGGER_SOURCE_KINDS", "SwaggerEntry", "parse_swagger_entry"):
        assert name not in openapi.__all__
    assert not hasattr(conf, "LOCAL_SOURCE_KINDS")


# --- redact_url -----------------------------------------------------------------------

CLEAN = [
    (
        "https://user:s3cr3t@h.example:8443/v3/api-docs?token=abc#frag",
        "https://h.example:8443/v3/api-docs",
    ),
    ("HTTPS://user:s3cr3t@h.example/x", "HTTPS://h.example/x"),
    ("https://u:p@ss@h.example/x", "https://h.example/x"),  # raw `@` in the password
    ("https://u:p%2Fss@h.example/x", "https://h.example/x"),  # an encoded one
    ("https://:s3cr3t@h.example/x", "https://h.example/x"),
    ("https://tok3n@h.example/x", "https://h.example/x"),
    ("http://[::1]:8080/openapi.json", "http://[::1]:8080/openapi.json"),
    ("https://u:p@[::1]:8443/openapi.json", "https://[::1]:8443/openapi.json"),
    ("https://h.example/openapi.json", "https://h.example/openapi.json"),
    ("  https://h.example/x?a=1  ", "https://h.example/x"),
    ("//user:s3cr3t@h.example/x?y=1", "//h.example/x"),
    ("https://h.example/app;jsessionid=ABC123?x=1", "https://h.example/app;jsessionid=***"),
    ("https://h.example/k/password=s3cr3t", "https://h.example/k/password=***"),
    ("https://h.example/My%20Specs/openapi.yaml", "https://h.example/My%20Specs/openapi.yaml"),
    ("file:///srv/specs/openapi.yaml", "file:///srv/specs/openapi.yaml"),
    ("docs/openapi.yaml", "docs/openapi.yaml"),
    ("docs/openapi.yaml?v=2#x", "docs/openapi.yaml"),
    ("app:s3cr3t@db.internal/prod", "***@db.internal/prod"),
    ("", ""),
    (None, ""),
]

CLOSED = [
    *CUT_PASSWORDS,
    "https://tok?en@h.example/x",  # a token alone, cut by `?`
    "https://tok#en@h.example/x",
    "https://tok/en@h.example/x",
    "https://h.example/users/@me",  # ambiguous too: the userinfo cannot be told apart
    "https://h.example/x?email=a@b.example",
    "https://u:p@h.example/users/a@b.example",
    "http://[::1]:8080/@scope/openapi.json",  # a working address, but an `@` all the same
    "https://admin:hunter2/api",  # a password without its `@`: the "port" is not a number
    "https://h.example:notaport/x",
    "https://user:PW＠h.example/x",  # U+FF20, read as `@` by urlsplit and IDNA
    "https://tok＠h.example/x",
    "https://h.example/My Specs/openapi.yaml",  # past whitespace: not one address
    "https://user:pa'PW@h.example/x",  # past a quote
    'https://user:pa"PW@h.example/x',
    "https://user:pa<PW@h.example/x",
    "https://h.example/a b@c",
]


@pytest.mark.parametrize("url, expected", CLEAN)
def test_redact_url(url, expected):
    assert redact_url(url) == expected


@pytest.mark.parametrize("url", CLOSED)
def test_redact_url_is_closed_on_doubt(url):
    out = redact_url(url)
    assert out == url.split("://", 1)[0] + "://" + REDACTED
    _no_part_of(["user", "pa", "PW", "ss", "hunter2", "tok", "1234"], out)


def test_redact_url_closes_a_scheme_relative_or_broken_address_too():
    assert redact_url("//user:pa?ss@h.example/x") == "//" + REDACTED
    assert redact_url("h.example/x?ss@y") == REDACTED
    assert redact_url("https:/user:s3cr3t@h.example/x") == "https:/" + REDACTED
    assert redact_url("C:/specs/team@corp/openapi.yaml") == "C:/specs/team@corp/openapi.yaml"


@pytest.mark.parametrize(
    "url", [u for u, _ in CLEAN] + CLOSED + [REDACTED, "https://" + REDACTED, "//" + REDACTED]
)
def test_redact_url_is_idempotent(url):
    once = redact_url(url)
    assert redact_url(once) == once


# --- redact_text: credentials of an address -------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        # psycopg puts the DSN into the exception text whole
        (
            'connection to server failed: invalid dsn "app:S3cr3tPass@db.internal/prod"',
            'connection to server failed: invalid dsn "***@db.internal/prod"',
        ),
        (
            "could not connect to app:S3cr3tPass@db.internal:5432/prod: timeout",
            "could not connect to ***@db.internal:5432/prod: timeout",
        ),
        ("app:S3cr3tPass@db_internal/prod", "***@db_internal/prod"),
        ("app:S3cr3tPass@[::1]:5432/prod", "***@[::1]:5432/prod"),
        ("app:S3cr3tPass@бд.пример/prod", "***@бд.пример/prod"),
        ("app:S3cr3tPass@db.internal: refused", "***@db.internal: refused"),
        ("app:S3cr3tPass@db.internal, retrying", "***@db.internal, retrying"),
        ("app:S3cr3tPass@db.internal?sslmode=require", "***@db.internal?sslmode=require"),
        ("dsn=app:p@ss@db.internal/prod", "dsn=***@db.internal/prod"),
        ("email:alice@example.com", "***@example.com"),  # not a secret, but the word stays
        (
            "OperationalError: postgresql://app:S3cr3tPass@db.internal:5432/prod refused",
            "OperationalError: postgresql://db.internal:5432/prod refused",
        ),
        ("amqp://guest:guest@mq.internal:5672/", "amqp://mq.internal:5672/"),
        ("see https://h.example/app;jsessionid=ABC123 now", "see https://h.example/app;jsessionid=*** now"),
    ],
)
def test_redact_text_removes_the_credentials_of_a_dsn(text, expected):
    out = redact_text(text)
    assert out == expected
    _no_part_of(["S3cr3tPass", "p@ss", "ABC123"], out)


@pytest.mark.parametrize(
    "text",
    [
        "write to a@b.example",
        "contact: first.last+tag@b.example, cc a@b.example",
        "mailto:a@b.example",
        "<a href='mailto:A.B@b.example'>mail</a>",
        "git@github.example:org/repo.git",
        "user a@b.example logged in at 12:30",
        "https://h.example/x?email=a@b.example",
    ],
)
def test_redact_text_keeps_mail_addresses(text):
    assert redact_text(text) == text


@pytest.mark.parametrize(
    "url, shown",
    [
        # free text reads `user:pa/ss@` as userinfo, as the channels always have: the colon
        # is not followed by a port, so the host after the `@` is shown
        (CUT_PASSWORDS[0], "https://h.example/x"),
        (CUT_PASSWORDS[1], "https://" + REDACTED),
        (CUT_PASSWORDS[2], "https://" + REDACTED),
        (CUT_PASSWORDS[3], "https://" + REDACTED),
        (CUT_PASSWORDS[4], "https://" + REDACTED),
        ("https://user:pa'PW@h.example/x", "https://" + REDACTED),  # an apostrophe, RFC-legal
    ],
)
def test_redact_text_closes_an_address_with_a_cut_password(url, shown):
    out = redact_text(f"cannot fetch {url} (refused)")
    assert out == f"cannot fetch {shown} (refused)"
    _no_part_of(["user", "pa", "ss", "PW"], out)


def test_redact_text_leaves_the_query_to_the_key_rules():
    out = redact_text("GET https://u:p@h.example/x?token=abc&page=2")
    assert out == "GET https://h.example/x?token=***&page=2"


# --- the output channels share the core -----------------------------------------------


@pytest.mark.parametrize("url", CUT_PASSWORDS + ["https://user:pa'PW@h.example/x"])
def test_channels_close_an_address_with_a_cut_password(url):
    for out in (
        _scrub_urls(f"GET {url}"),
        _scrub_urls(f"GET {url}", drop_query=True),
        _scrub_text(f"GET {url} failed"),
        _safe_text(f"Failed to fetch OpenAPI URL {url}: boom", secrets_of=url),
    ):
        _no_part_of(["user", "pa", "ss", "PW"], out)


def test_channels_keep_a_mail_address_in_a_query():
    """Request URLs in the log are real requests: an `@` in a value is not a credential."""
    assert _scrub_urls("GET https://h.example/x?email=a@b.example&token=t") == (
        "GET https://h.example/x?email=a@b.example&token=***"
    )
    assert _scrub_urls("GET https://h.example/users/a@b.example") == (
        "GET https://h.example/users/a@b.example"
    )
    assert _scrub_urls("GET http://[::1]:8080/@scope/openapi.json") == (
        "GET http://[::1]:8080/@scope/openapi.json"
    )


@pytest.mark.parametrize(
    "text",
    [
        "bad spec https://tok/en@h.example/x",
        'bad spec https://user:pa"PW@h.example/x',
        "bad spec https://user:pa<PW@h.example/x",
        "bad spec https://user:pa>PW@h.example/x",
        "bad spec https://admin:hunter2/api",
        "bad spec https://user:PW＠h.example/x",
    ],
)
def test_configuration_errors_close_on_doubt(text):
    """Errors about the project's configuration read an address the way redact_url does."""
    out = _safe_text(text)
    assert out == "bad spec https://" + REDACTED
    _no_part_of(["tok", "PW", "hunter2"], out)


def test_channels_and_redact_url_remove_the_same_userinfo():
    url = "https://alice:s3cr3t@h.example/v1/openapi.json"
    assert _scrub_urls(url) == redact_url(url) == redact_text(url)


# --- the grammar of a swagger_files entry ----------------------------------------------


class _PathLike(os.PathLike):
    def __init__(self, path):
        self.path = path

    def __fspath__(self):
        return self.path


def test_source_kinds():
    assert SWAGGER_SOURCE_KINDS == {"local", "file", "path", "url"}


@pytest.mark.parametrize(
    "entry, expected",
    [
        (["local", "docs/openapi.yaml"], ("local", "docs/openapi.yaml")),
        ([" File ", "docs/openapi.yaml"], ("local", "docs/openapi.yaml")),
        (("PATH", Path("docs") / "openapi.yaml"), ("local", str(Path("docs") / "openapi.yaml"))),
        (("local", _PathLike(" docs/openapi.yaml ")), ("local", "docs/openapi.yaml")),
        (["URL", " https://h.example/v3/api-docs \n"], ("url", "https://h.example/v3/api-docs")),
        (["url", "https://h.example/x", "reserved"], ("url", "https://h.example/x")),
        (["url", "http://[::1]:8080/@scope/openapi.json"], ("url", "http://[::1]:8080/@scope/openapi.json")),
    ],
)
def test_parse_swagger_entry(entry, expected):
    parsed = parse_swagger_entry(entry)
    assert parsed == expected
    assert isinstance(parsed, SwaggerEntry)
    assert (parsed.kind, parsed.location) == expected


@pytest.mark.parametrize(
    "entry, words",
    [
        ("https://u:s3cr3t@h.example/x", "got a str"),
        (["url"], "got a list of 1"),
        (["ftp", "https://u:s3cr3t@h.example/x"], "source_type must be one of"),
        (["local", "   "], "non-empty"),
        (["local", None], "non-empty"),
        (["local", b"docs/openapi.yaml"], "non-empty"),
        (["url", "https://user:s3/cr3t@h.example/x"], "percent-encode"),
        (["url", "https://user:s3?cr3t@h.example/x"], "percent-encode"),
        (["url", "https://user:s3cr3t/api"], "percent-encode"),
        (["url", "https://user:s3cr3t＠h.example/x"], "percent-encode"),
    ],
)
def test_parse_swagger_entry_refuses_without_quoting_the_location(entry, words):
    with pytest.raises(ConfpartestError) as caught:
        parse_swagger_entry(entry)
    assert words in str(caught.value)
    _no_part_of(["s3cr3t", "cr3t", "user"], str(caught.value))


def test_validation_reads_the_same_grammar():
    class Conf:
        swagger_files = {
            "a": [" URL ", "https://h.example/x"],  # kind with spaces: accepted everywhere now
            "b": ["svn", "x"],
            "c": ["url", "https://user:pa?ss@h.example/x"],
        }

    errors = validate_confpartest(Conf)
    assert len(errors) == 2, errors
    assert errors[0].startswith("swagger_files['b'] source_type must be one of file|local|path|url")
    assert errors[1].startswith("swagger_files['c'] the URL cannot be read")
    _no_part_of(["pa?ss", "user"], " ".join(errors))


def test_resolve_entry_location(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / "specs").mkdir(parents=True)
    (project / "specs" / "api.yaml").write_text("openapi: 3.0.0\n", encoding="utf-8")
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "specs").mkdir()
    (tmp_path / "elsewhere" / "specs" / "api.yaml").write_text("x", encoding="utf-8")

    # 3. not from the current directory, but under the directory of confpartest.py
    monkeypatch.chdir(tmp_path)
    found = resolve_entry_location(["local", "specs/api.yaml"], project)
    assert found == ("local", str(project / "specs" / "api.yaml"))
    # 2. the current directory wins when the file is there
    monkeypatch.chdir(tmp_path / "elsewhere")
    found = resolve_entry_location([" File ", "specs/api.yaml"], project)
    assert Path(found.location) == (tmp_path / "elsewhere" / "specs" / "api.yaml").resolve()
    # 1. absolute; 4. neither — as written
    absolute = str(project / "specs" / "api.yaml")
    assert resolve_entry_location(["local", absolute], None).location == absolute
    assert resolve_entry_location(["local", "nope.yaml"], project).location == "nope.yaml"
    # a URL as parsed
    assert resolve_entry_location(["url", "https://h/x"], project) == ("url", "https://h/x")


def test_resolve_entry_location_agrees_with_coverage(tmp_path, monkeypatch):
    """Coverage uses the private `_resolve_relative`; both apply the same rule."""
    import types

    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "api.yaml").write_text("x", encoding="utf-8")
    module = types.SimpleNamespace(__file__=str(tmp_path / "confpartest.py"))
    elsewhere = tmp_path / "sub"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    for written in ("specs/api.yaml", "nope.yaml", str(tmp_path / "specs" / "api.yaml")):
        public = resolve_entry_location(["local", written], tmp_path).location
        private = _resolve_relative(written, module)
        assert Path(public).resolve() == Path(private).resolve(), written


def test_redact_url_closes_on_an_object_it_cannot_read():
    class Broken:
        def __str__(self):
            raise RuntimeError("s3cr3t")

    assert redact_url(Broken()) == REDACTED


@pytest.mark.parametrize(
    "url",
    [
        "https:/alice:s3cr3t@h.example/x",
        "https//alice:s3cr3t@h.example/x",
        "ｈttps://alice:s3cr3t@h.example/x",
        "ftp://h.example/spec.yaml",
    ],
)
def test_a_url_entry_must_start_with_http(url):
    with pytest.raises(ConfpartestError, match="must start with http:// or https://") as caught:
        parse_swagger_entry(["url", url])
    _no_part_of(["s3cr3t", "alice"], str(caught.value))


def test_validation_does_not_quote_a_secret_key():
    class Conf:
        swagger_files = {"https://alice:s3cr3t@h.example/x": ["svn", "x"]}

    errors = validate_confpartest(Conf)
    assert len(errors) == 1
    _no_part_of(["s3cr3t", "alice"], errors[0])
