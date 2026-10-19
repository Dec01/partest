"""Masking free text: linear time, quotes of both kinds, the shortening marker, query names
outside a URL, PEM keys, and no second pass over what the package already masked.

Secrets and anything shaped like one are built at run time.
"""

from __future__ import annotations

import base64
import json
import logging
import time

import allure
import httpx
import pytest

from partest import StatusMismatchError, TypesTestCases
from partest.client import ApiClient
from partest.redact import _scrub, _scrub_headers, _scrub_params, _scrub_text, redact_text

MARKER = "S3CRET-MARKER-7e47"


@pytest.fixture
def attachments(monkeypatch):
    seen: list[tuple[str, str]] = []

    def record(body, name=None, attachment_type=None, extension=None):
        seen.append((str(name), str(body)))

    monkeypatch.setattr(allure, "attach", record)
    return seen


def _best_time(text: str) -> float:
    best = float("inf")
    for _ in range(3):
        started = time.perf_counter()
        redact_text(text)
        best = min(best, time.perf_counter() - started)
    return best


@pytest.mark.parametrize(
    "build",
    [
        lambda n: '{"token":{"a":1, ' * n,  # invalid JSON on one line, nothing closes
        lambda n: "password: {} " * (n // 5) + "\n" + "    x\n" * n,
    ],
    ids=["open_values_on_one_line", "closed_values_then_indented_lines"],
)
def test_time_grows_linearly(build):
    small, large = build(4000), build(8000)
    t_small, t_large = _best_time(small), _best_time(large)
    assert t_large < 2.0
    assert t_large <= max(t_small, 0.005) * 2.5


@pytest.mark.parametrize(
    "template",
    [
        "{{'token': {{'a': '}}', 'b': '{s}'}}, 'z': 1}}",
        "{{'secret': ['a]', '{s}'], 'z': 1}}",
    ],
)
def test_a_bracket_inside_single_quotes_does_not_close_the_value(template):
    assert MARKER not in redact_text(template.format(s=MARKER))


def test_a_forged_shortening_marker_does_not_end_a_value():
    text = f"password: [x ... [truncated, 3 chars total] {MARKER}]  and more"
    assert MARKER not in redact_text(text)
    real = f"password: [{MARKER} ... [truncated, 9000 chars total]"
    masked = redact_text(real)
    assert MARKER not in masked and masked.endswith("[truncated, 9000 chars total]")


def test_query_names_outside_a_url_and_jsessionid():
    assert MARKER not in json.dumps(_scrub_params(f"sv=1&sig={MARKER}"))
    assert MARKER not in _scrub_text(f"retry with sv=2020&sig={MARKER}&se=1")
    assert MARKER not in _scrub_text(f"Location: https://h.example/app;jsessionid={MARKER}?x=1")


@pytest.mark.parametrize(
    "name", ["X-Pass", "X-Cred", "X-Saml-Assertion", "X-Request-Hmac", "X-Signature-V2"]
)
def test_more_header_endings_are_secret(name):
    assert _scrub_headers({name: MARKER})[name] == "***"


def test_access_control_allow_credentials_stays_visible():
    headers = {"Access-Control-Allow-Credentials": "true"}
    assert _scrub_headers(headers) == headers


def _pem(body: str) -> str:
    kind = "RSA " + "PRIV" + "ATE KEY"
    return f"-----BEGIN {kind}-----\n{body}\n-----END {kind}-----"


def test_a_pem_key_is_masked_whatever_key_it_sits_under():
    text = f"config loaded: cert={_pem(MARKER)} done"
    masked = redact_text(text)
    assert MARKER not in masked and masked.endswith(" done")
    assert MARKER not in json.dumps(_scrub({"cert": _pem(MARKER)}))
    unterminated = "-----BEGIN " + "PRIV" + "ATE KEY-----\n" + MARKER
    assert MARKER not in redact_text(unterminated)


@pytest.mark.parametrize("template", ["token=u'{s}'", 'token=f"{s}"', "password=N'{s}'"])
def test_more_string_prefixes(template):
    assert MARKER not in redact_text(template.format(s=MARKER))


def test_poll_messages_use_the_same_rule():
    from partest.polling import PollTimeout, poll_until_sync

    def part(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    jwt = ".".join([part(b'{"alg":"HS256"}'), part(b'{"sub":"1"}'), part(b"sig")])
    value = {
        "client-secret": MARKER,
        "next": f"https://u:{MARKER}@h.example/x?sig={MARKER}",
        "jwt": jwt,
    }
    with pytest.raises(PollTimeout) as caught:
        poll_until_sync(lambda: value, lambda v: False, timeout=0, interval=1)
    message = str(caught.value)
    assert MARKER not in message and part(b'{"sub":"1"}') not in message


# --- no second pass over what the package masked ---------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, body, kept",
    [
        (401, {"detail": "token: expired", "code": 7}, '"detail": "token: expired"'),
        (400, {"password": "", "error": "bad"}, '"password": ""'),
    ],
    ids=["value_naming_a_key", "empty_secret"],
)
async def test_masked_text_is_not_masked_again(status, body, kept, caplog, attachments, monkeypatch):
    from partest import pytest_plugin
    from partest.tracking import CreatedRegistry, TrackingApiClient

    caplog.set_level(logging.DEBUG)

    def handler(request):
        return httpx.Response(status, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
        tracked = TrackingApiClient(
            "http://stand", CreatedRegistry(), client=ApiClient("http://stand", client=hx)
        )
        with pytest.raises(StatusMismatchError) as info:
            await tracked.make_request("GET", "/x", expected_status_code=200,
                                       type=TypesTestCases.request_default)

    error_lines = "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)
    details = dict(attachments)["failure_details"]

    monkeypatch.setattr(pytest_plugin, "plugin_enabled", lambda: True)

    class Call:
        when = "call"

        class excinfo:
            value = info.value

    attachments.clear()
    pytest_plugin.pytest_runtest_makereport(None, Call())
    summary = dict(attachments)["failure_summary"]

    for channel in (error_lines, details, summary):
        assert kept in channel
        assert "token: ***" not in channel and '"***"' not in channel
    assert "Original error:" in details
    # The response body in the message is still the JSON the walker produced.
    original = str(info.value)
    assert kept in original
