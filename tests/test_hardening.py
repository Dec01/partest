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

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs.get("timeout")))
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


def test_load_swagger_yaml_takes_a_timeout_override(monkeypatch):
    """The default is a module constant, not a hard-coded value: callers may override."""
    fake_get = _FakeGet()
    monkeypatch.setattr(parparser.requests, "get", fake_get)

    parparser.OpenAPIParser.load_swagger_yaml(
        "url", "https://example.invalid/openapi.yaml", timeout=0.25
    )

    assert fake_get.calls == [("https://example.invalid/openapi.yaml", 0.25)]


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


def test_load_swagger_yaml_rejects_unknown_source_type():
    with pytest.raises(ValueError):
        parparser.OpenAPIParser.load_swagger_yaml("ftp", "somewhere")
