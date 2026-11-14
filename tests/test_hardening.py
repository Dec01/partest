"""Small invariants that belong to no wave: things that must not break silently.

Each case here replaces a defect that could only be seen by reading the source — a
``__str__`` that raised instead of returning a string, a network call with no deadline.
Neither showed up as a red test, which is exactly why they are pinned.
"""

from __future__ import annotations

import logging

import pytest

from partest import parparser
from partest.utils.logger import Logger


def test_logger_str_describes_name_and_level():
    """``str(Logger())`` is a description, not a raise.

    It used to reference a module-level ``logger`` that does not exist, so ``str(log)``
    — or any f-string interpolating one — died with ``NameError``. ``repr`` was never
    affected: the class defines no ``__repr__`` and ``repr()`` does not fall back to
    ``__str__``.
    """
    log = Logger()
    text = str(log)
    assert isinstance(text, str)
    assert log.get_log().name in text
    assert logging.getLevelName(log.get_log().getEffectiveLevel()) in text


class _FakeGet:
    """Stand-in for ``requests.get``: records the call, returns an empty spec."""

    class _Resp:
        text = "openapi: 3.0.0\npaths: {}\n"

        def raise_for_status(self):
            return None

    def __init__(self):
        self.calls = []
        self.kwargs = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs.get("timeout")))
        self.kwargs.append(kwargs)
        return self._Resp()


def test_load_swagger_yaml_url_passes_a_timeout(monkeypatch):
    """An unreachable stand must fail, not hang the import of the whole suite."""
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)
    parser = parparser.OpenAPIParser.load_swagger_yaml(
        "url", "https://example.invalid/openapi.yaml"
    )

    assert fake_get.calls == [
        ("https://example.invalid/openapi.yaml", parparser.SWAGGER_FETCH_TIMEOUT)
    ]
    assert isinstance(parparser.SWAGGER_FETCH_TIMEOUT, (int, float))
    # Only that a limit exists. Any ceiling here would be a number nobody can justify,
    # and would break a considered decision to raise the default.
    assert parparser.SWAGGER_FETCH_TIMEOUT > 0
    assert parser.swagger_dict["paths"] == {}
    assert "auth" not in fake_get.kwargs[0]


def test_load_swagger_yaml_takes_a_timeout_override(monkeypatch):
    """The default is a module constant, not a hard-coded value: callers may override."""
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)

    parparser.OpenAPIParser.load_swagger_yaml(
        "url", "https://example.invalid/openapi.yaml", timeout=0.25
    )

    assert fake_get.calls == [("https://example.invalid/openapi.yaml", 0.25)]


def test_load_swagger_yaml_passes_basic_auth(monkeypatch):
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)

    parparser.OpenAPIParser.load_swagger_yaml(
        "url",
        "https://example.invalid/openapi.yaml",
        auth=("swagger-user", "s3cr3t"),
    )

    assert fake_get.kwargs == [{
        "timeout": parparser.SWAGGER_FETCH_TIMEOUT,
        "verify": True,
        "auth": ("swagger-user", "s3cr3t"),
    }]


def test_load_swagger_yaml_local_ignores_auth(monkeypatch, tmp_path):
    spec = tmp_path / "openapi.yaml"
    spec.write_text("openapi: 3.0.0\npaths: {}\n", encoding="utf-8")
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)

    parser = parparser.OpenAPIParser.load_swagger_yaml(
        "local", str(spec), auth=("swagger-user", "s3cr3t")
    )

    assert parser.swagger_dict["paths"] == {}
    assert fake_get.calls == []


def test_swagger_settings_passes_its_timeout_down(monkeypatch):
    """``SwaggerSettings`` is how the package fetches specs; the override must survive it."""
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)

    settings = parparser.SwaggerSettings(
        {"api": ("url", "https://example.invalid/openapi.yaml")}, timeout=1.5
    )
    settings.load_swagger()

    assert fake_get.calls == [("https://example.invalid/openapi.yaml", 1.5)]
    # Default unchanged for everyone who does not ask.
    assert parparser.SwaggerSettings({}).timeout == parparser.SWAGGER_FETCH_TIMEOUT


def test_swagger_settings_scopes_auth_to_the_named_source(monkeypatch):
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)
    settings = parparser.SwaggerSettings(
        {
            "private": ("url", "https://private.example.invalid/openapi.yaml"),
            "public": ("url", "https://public.example.invalid/openapi.yaml"),
        },
        auth={"private": ("swagger-user", "s3cr3t")},
    )

    settings.load_swagger()

    assert fake_get.kwargs[0]["auth"] == ("swagger-user", "s3cr3t")
    assert "auth" not in fake_get.kwargs[1]
    # The pre-existing public attribute keeps its (source_type, path) shape.
    assert settings.swaggers == [
        ("url", "https://private.example.invalid/openapi.yaml"),
        ("url", "https://public.example.invalid/openapi.yaml"),
    ]


def test_swagger_auth_validation_never_quotes_credentials():
    from partest.conf import validate_confpartest

    class Conf:
        swagger_files = {"api": ["url", "https://example.invalid/openapi.yaml"]}
        swagger_auth = {
            "api": ("swagger-user", "s3cr3t", "extra"),
            "other": ("swagger-user", "another-secret"),
        }

    errors = validate_confpartest(Conf)

    assert len(errors) == 2, errors
    text = " ".join(errors)
    assert "s3cr3t" not in text and "another-secret" not in text
    assert "swagger-user" not in text and "extra" not in text


def test_load_swagger_yaml_rejects_unknown_source_type():
    with pytest.raises(ValueError):
        parparser.OpenAPIParser.load_swagger_yaml("ftp", "somewhere")


def test_swagger_settings_loads_a_manually_appended_source_without_auth(monkeypatch):
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)
    settings = parparser.SwaggerSettings({})
    settings.swaggers.append(("url", "https://manual.example.invalid/openapi.yaml"))

    settings.load_swagger()

    assert fake_get.calls == [
        ("https://manual.example.invalid/openapi.yaml", parparser.SWAGGER_FETCH_TIMEOUT)
    ]
    assert "auth" not in fake_get.kwargs[0]


def test_swagger_settings_manual_public_append_never_gets_private_auth(monkeypatch):
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)
    settings = parparser.SwaggerSettings(
        {}, auth={"private": ("private-user", "private-secret")}
    )
    settings.swaggers.append(("url", "https://public.example.invalid/openapi.yaml"))
    settings.add_swagger(
        {"private": ("url", "https://private.example.invalid/openapi.yaml")}
    )

    settings.load_swagger()

    assert fake_get.kwargs[0].get("auth") is None
    assert "auth" not in fake_get.kwargs[0]
    assert fake_get.kwargs[1]["auth"] == ("private-user", "private-secret")
    assert len(fake_get.calls) == 2


def test_swagger_settings_two_protected_sources_get_their_own_credentials(monkeypatch):
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)
    settings = parparser.SwaggerSettings(
        {
            "one": ("url", "https://one.example.invalid/openapi.yaml"),
            "two": ("url", "https://two.example.invalid/openapi.yaml"),
        },
        auth={"one": ("one-user", "one-secret"), "two": ("two-user", "two-secret")},
    )

    settings.load_swagger()

    assert [call["auth"] for call in fake_get.kwargs] == [
        ("one-user", "one-secret"),
        ("two-user", "two-secret"),
    ]


def test_swagger_settings_reordering_does_not_move_credentials(monkeypatch):
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)
    settings = parparser.SwaggerSettings(
        {
            "one": ("url", "https://one.example.invalid/openapi.yaml"),
            "two": ("url", "https://two.example.invalid/openapi.yaml"),
        },
        auth={"one": ("one-user", "one-secret"), "two": ("two-user", "two-secret")},
    )
    settings.swaggers.reverse()

    settings.load_swagger()

    assert [(url, kwargs["auth"]) for (url, _), kwargs in zip(
        fake_get.calls, fake_get.kwargs
    )] == [
        ("https://two.example.invalid/openapi.yaml", ("two-user", "two-secret")),
        ("https://one.example.invalid/openapi.yaml", ("one-user", "one-secret")),
    ]


def test_load_swagger_yaml_refuses_basic_auth_over_http_before_requests(monkeypatch):
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)

    with pytest.raises(RuntimeError, match="requires an https:// URL") as caught:
        parparser.OpenAPIParser.load_swagger_yaml(
            "url", "http://example.invalid/openapi.yaml", auth=("user", "s3cr3t")
        )

    assert fake_get.calls == []
    assert "s3cr3t" not in str(caught.value) and "user" not in str(caught.value)


def test_load_swagger_yaml_public_http_still_works_without_auth(monkeypatch):
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)

    parser = parparser.OpenAPIParser.load_swagger_yaml(
        "url", "http://example.invalid/openapi.yaml"
    )

    assert parser.swagger_dict["paths"] == {}
    assert fake_get.calls == [
        ("http://example.invalid/openapi.yaml", parparser.SWAGGER_FETCH_TIMEOUT)
    ]
    assert "auth" not in fake_get.kwargs[0]


def _failing_get(url, **kwargs):
    raise parparser.requests.ConnectionError(f"cannot send {kwargs.get('auth')} to {url}")


def _assert_clean_auth_traceback(error, *secrets, detached=False):
    assert error.__cause__ is None and error.__suppress_context__
    if detached:
        assert error.__context__ is None
    text = str(error)
    for secret in secrets:
        assert secret not in text
    library_frames = []
    tb = error.__traceback__
    while tb is not None:
        filename = tb.tb_frame.f_code.co_filename
        assert f"{__import__('os').sep}requests{__import__('os').sep}" not in filename
        if filename == parparser.__file__:
            library_frames.append(tb.tb_frame)
        tb = tb.tb_next
    assert library_frames
    for frame in library_frames:
        shown_locals = repr(frame.f_locals)
        for secret in secrets:
            assert secret not in shown_locals, (frame.f_code.co_name, shown_locals)
        if "auth" in frame.f_locals:
            assert frame.f_locals["auth"] is None
        if "self" in frame.f_locals:
            for secret in secrets:
                assert secret not in repr(frame.f_locals["self"])


def test_direct_load_swagger_yaml_clears_auth_from_traceback_frames(monkeypatch):
    monkeypatch.setattr(parparser.requests, "get", _failing_get)

    with pytest.raises(RuntimeError) as caught:
        parparser.OpenAPIParser.load_swagger_yaml(
            "url",
            "https://example.invalid/openapi.yaml",
            auth=("trace-user", "trace-secret"),
        )

    _assert_clean_auth_traceback(caught.value, "trace-user", "trace-secret")


def test_direct_load_swagger_yaml_clears_userinfo_from_traceback_frames(monkeypatch):
    monkeypatch.setattr(parparser.requests, "get", _failing_get)

    with pytest.raises(Exception) as caught:
        parparser.OpenAPIParser.load_swagger_yaml(
            "url", "https://userinfo-user:userinfo-secret@example.invalid/openapi.yaml"
        )

    _assert_clean_auth_traceback(
        caught.value, "userinfo-user", "userinfo-secret", detached=True
    )


def test_swagger_settings_load_clears_auth_from_traceback_frames(monkeypatch):
    monkeypatch.setattr(parparser.requests, "get", _failing_get)
    settings = parparser.SwaggerSettings(
        {"api": ("url", "https://example.invalid/openapi.yaml")},
        auth={"api": ("settings-user", "settings-secret")},
    )

    with pytest.raises(RuntimeError) as caught:
        settings.load_swagger()

    assert "settings-user" not in repr(settings)
    assert "settings-secret" not in repr(settings)
    _assert_clean_auth_traceback(caught.value, "settings-user", "settings-secret")
