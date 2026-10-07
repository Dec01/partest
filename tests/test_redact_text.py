"""partest.redact.redact_text: secrets inside text whose structure is gone."""

from __future__ import annotations

import time

import pytest

from partest.redact import redact_text


@pytest.mark.parametrize(
    "text, secret",
    [
        ('{"status": "RUNNING", "token": "abc.def"}', "abc.def"),
        ("{'access_token': 'xyz', 'n': 1}", "xyz"),
        ("Session(access_token='s3cr3t', status='OK')", "s3cr3t"),
        ("a=1&password=hunter2&b=2", "hunter2"),
        ("Authorization: Bearer eyJhbGc.x.y", "eyJhbGc.x.y"),
        ("seen header Bearer abc123 in the log", "abc123"),
        ("OrderedDict([('status', 'OK'), ('client_secret', 'cs-1')])", "cs-1"),
        ('{"token": "a\\"b-tail"}', "b-tail"),
    ],
)
def test_secrets_are_masked(text, secret):
    masked = redact_text(text)
    assert secret not in masked
    assert "***" in masked


@pytest.mark.parametrize("text", ["RUNNING", "tokenize=fine", "status: DONE", ""])
def test_ordinary_text_is_untouched(text):
    assert redact_text(text) == text


def test_pathological_input_is_linear():
    hostile = 'token: "' + "\\" * 50000 + " " + "token=" + "a" * 200000
    started = time.perf_counter()
    redact_text(hostile)
    assert time.perf_counter() - started < 2.0
