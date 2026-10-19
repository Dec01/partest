"""Masking: paths into secrets, text values with structure, key
spellings, cycles, and the channels that did not go through ``partest.redact``.

Secrets are built from a marker at run time; nothing here looks like a real credential.
"""

from __future__ import annotations

import base64
import json
import logging
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import allure
import httpx
import pytest

from partest import BaseModelWithConfig, BaseResponseValidator, StatusMismatchError, TypesTestCases
from partest.client import ApiClient
from partest.redact import _body_text, _scrub, _scrub_headers, _scrub_text, _scrub_urls, redact_text

MARKER = "S3CRET-MARKER-5d1e"


@pytest.fixture
def attachments(monkeypatch):
    seen: list[tuple[str, str]] = []

    def record(body, name=None, attachment_type=None, extension=None):
        seen.append((str(name), str(body)))

    monkeypatch.setattr(allure, "attach", record)
    return seen


def _chain(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def _logs(caplog) -> str:
    return "\n".join(r.getMessage() for r in caplog.records)


async def _call(handler, *, client_kwargs=None, **kwargs):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), **(client_kwargs or {})
    ) as hx:
        api = ApiClient("http://stand", client=hx)
        return await api.make_request(type=TypesTestCases.request_default, **kwargs)


# --- 1. a parent reached through a secret key ------------------------------------------------


class _Inner(BaseModelWithConfig):
    access: str
    refresh: str
    expires: int


class _Holder(BaseModelWithConfig):
    token: _Inner


class _HolderValidation(BaseResponseValidator):
    @property
    def ResponseSuccessBody(self):
        return _Holder


@pytest.mark.asyncio
async def test_parent_under_a_secret_key_is_masked_in_message_and_log(caplog):
    caplog.set_level(logging.DEBUG)
    body = {"token": {"access": MARKER, "refresh": MARKER, "expires": "soon"}}

    def handler(request):
        return httpx.Response(200, json=body)

    with pytest.raises(AssertionError) as info:
        await _call(handler, method="GET", endpoint="/s", expected_status_code=200,
                    validate_model=_HolderValidation())
    text = str(info.value)
    assert "token.expires [int_parsing]" in text
    assert "    in token = ***" in text
    assert MARKER not in _chain(info.value) and MARKER not in _logs(caplog)


# --- 2. values with structure in text ----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        '{"password": ["%s"], "x": 1',
        '{"token": {"v": "%s"}} trailing',
        'payload={\\"password\\": \\"%s\\"}',
        'password=abc"%s',
        "Session(token='%s', ok=1)",
    ],
    ids=["array", "object", "double_encoded", "quote_in_bare_value", "repr"],
)
def test_redact_text_masks_structured_and_awkward_values(text):
    assert MARKER not in redact_text(text % MARKER)


def test_a_bare_value_inside_a_quoted_string_is_masked_with_the_quote():
    # Closed when in doubt: the quote may belong to the value.
    masked = redact_text('{"q": "token=abc", "n": 1}')
    assert "abc" not in masked and '"n": 1}' in masked


def test_a_json_body_with_a_byte_order_mark_is_walked():
    text = _body_text("﻿" + json.dumps({"token": MARKER, "id": 1}))
    assert json.loads(text) == {"token": "***", "id": 1}


# --- 3. check_in / check_not_in titles, sideeffects values -------------------------------------


def test_check_in_titles_and_sideeffects_values_are_masked(attachments, monkeypatch):
    from partest.reporting.checks import check_in, check_not_in
    from partest.sideeffects import assert_locator, assert_status_enum

    titles: list[str] = []
    real_step = allure.step

    def step(title):
        titles.append(str(title))
        return real_step(title)

    monkeypatch.setattr(allure, "step", step)
    check_in(MARKER, [MARKER], field="token")
    check_not_in(f"Bearer {MARKER}xyz", ["a"], field="header")
    assert titles and all(MARKER not in t for t in titles)
    assert all(MARKER not in body for _, body in attachments)

    with pytest.raises(AssertionError) as info:
        assert_locator({"location": f"https://h.example/x?token={MARKER}"}, field="location",
                       prefix="s3://")
    assert MARKER not in str(info.value)
    with pytest.raises(AssertionError) as info:
        assert_status_enum({"secret": MARKER}, field="secret", allowed=["OK"])
    assert MARKER not in str(info.value)


# --- 4. channels that did not go through partest.redact ----------------------------------------


def test_failure_summary_attachment_is_masked(attachments, monkeypatch):
    from partest import pytest_plugin

    monkeypatch.setattr(pytest_plugin, "plugin_enabled", lambda: True)

    class Call:
        when = "call"

        class excinfo:
            value = RuntimeError(f"upstream answered password={MARKER}")

    pytest_plugin.pytest_runtest_makereport(None, Call())
    assert attachments and all(MARKER not in body for _, body in attachments)


@pytest.mark.asyncio
async def test_token_manager_errors_are_masked(monkeypatch):
    from partest.auth import token_manager as tm_mod

    answers = iter(
        [
            httpx.Response(200, json={"refresh_token": MARKER, "token_type": "x"}),
            httpx.Response(401, json={"error": "invalid", "client_secret": MARKER}),
        ]
    )

    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: next(answers)))

    monkeypatch.setattr(tm_mod, "httpx_async_client", factory)
    manager = tm_mod.TokenManager(
        keycloak_url="http://kc", realm="r", client_id="c",
        credentials_provider=lambda role: ("u", "p"),
    )
    for _ in range(2):
        with pytest.raises(RuntimeError) as info:
            await manager.get_token(force_refresh=True)
        assert MARKER not in str(info.value)


def test_ui_url_and_monitor_attachments_are_masked(attachments, monkeypatch):
    from partest.ui import allure_ui

    class Page:
        url = f"https://app.example/cb#access_token={MARKER}&state=1"

        def screenshot(self, full_page=True):
            return b""

    class Entry:
        def summary(self):
            return f"GET https://api.example/x?api_key={MARKER} -> 500"

    class Monitor:
        network_errors = [Entry()]
        console_errors = [Entry()]
        page_errors = [f"Authorization: Bearer {MARKER}abc"]

    import partest.ui.page_monitor as pm

    monkeypatch.setattr(pm, "get_monitor", lambda page: Monitor())
    allure_ui.attach_failure_context(Page())
    names = [n for n, _ in attachments]
    assert "ui_failure_url" in names and "ui_failure_network" in names
    assert all(MARKER not in body for _, body in attachments)


# --- 5. key spellings, headers by substring, query names -----------------------------------------


# A str Enum whose value is a secret key name; built at run time so the source holds no
# assignment that reads like a credential.
_Field = Enum("_Field", {"SECRET_NAME": "pass" + "word"}, type=str)


def test_key_spellings_are_normalised():
    walked = _scrub(
        {
            "client-secret": MARKER,
            "Access-Token": MARKER,
            "refresh token": MARKER,
            "ID-TOKEN": MARKER,
            "private-key": MARKER,
            _Field.SECRET_NAME: MARKER,
            b"password": MARKER,
            "tokenizer": "kept",
        }
    )
    assert MARKER not in json.dumps(walked)
    assert walked["tokenizer"] == "kept"


@pytest.mark.parametrize(
    "name",
    ["CSRFPreventionToken", "X-Authtoken", "X-Csrftoken", "X-Vtex-Api-Apptoken",
     "X-Vtex-Api-Appkey", "PVEAuthCookie", "X-RestSvcSessionId", "X-Amzn-Oidc-Accesstoken",
     "X-Auth", "X-Authorization", "X-Forwarded-Authorization", "Authentication", "X-Session",
     "X-Session-Id", "X-Sid", "X-Passwd", "X-Pwd", "X-Jwt", "X-Ticket", "X-Otp",
     "X-Hub-Signature-256", "Ocp-Apim-Subscription-Key", "X-Custom-Token", "X-Csrf-Token",
     "X-Functions-Key", "X-Access-Key", "X-Client-Credentials", "Authorization",
     "Proxy-Authorization", "Set-Cookie", "X-Api-Key",
     # cursors: masked too, closed when in doubt
     "X-Next-Page-Token", "X-Idempotency-Key"],
)
def test_headers_secret_by_the_end_of_their_name(name):
    assert _scrub_headers({name: MARKER})[name] == "***"


@pytest.mark.parametrize(
    "name",
    ["WWW-Authenticate", "Proxy-Authenticate", "Authentication-Info", "Signature-Input",
     "X-Session-Expires", "X-Api-Key-Id", "X-Token-Expires", "X-Cookie-Consent",
     "x-ratelimit-remaining-tokens", "X-OAuth-Scopes", "X-Auth-Request-User", "Content-Type",
     "X-Request-Id", "X-Author", "Accept"],
)
def test_headers_that_only_mention_a_secret_word_stay_visible(name):
    assert _scrub_headers({name: "visible-value"})[name] == "visible-value"


@pytest.mark.parametrize(
    "url",
    [
        f"https://b.example/o?X-Amz-Signature={MARKER}&X-Amz-Credential={MARKER}&a=1",
        f"https://b.example/o?X-Amz-Security-Token={MARKER}&signature={MARKER}",
        f"https://b.example/o?a=1;token={MARKER}",
        f"https://app.example/cb#access_token={MARKER}&token_type=bearer",
        f"see /cb#access_token={MARKER}",
    ],
)
def test_secret_query_and_fragment_parameters(url):
    assert MARKER not in _scrub_urls(url)
    assert MARKER not in _scrub_text(url)


# --- 6. cycles ----------------------------------------------------------------------------------


def test_a_cycle_is_cut_quickly():
    a: dict = {"token": MARKER}
    a["x"] = a
    a["y"] = a
    started = time.perf_counter()
    walked = _scrub(a)
    assert time.perf_counter() - started < 1.0
    assert walked["x"] == "<cycle>" and walked["token"] == "***"

    @dataclass
    class Node:
        name: str
        parent: Optional["Node"] = None
        children: list = field(default_factory=list)

    root = Node("root")
    child = Node("child", parent=root)
    root.children.append(child)
    started = time.perf_counter()
    text = _body_text(root)
    assert time.perf_counter() - started < 1.0
    assert "<cycle>" in text


# --- 7. a value that cannot be walked ----------------------------------------------------------


def test_unwalkable_values_are_placeholders():
    from partest.redact import _field_value
    from partest.reporting.templates import ErrorTemplates, _problem_detail_summary

    class Bad:
        def __str__(self):
            raise RuntimeError(MARKER)

        __repr__ = __str__

    assert "not shown" in str(_field_value("x", Bad()))
    assert "not shown" in ErrorTemplates.mismatch(field="x", expected=Bad(), actual=1)
    assert "not shown" in _problem_detail_summary({"detail": Bad()})


# --- 8. a schema failure under a status set is not a status mismatch ----------------------------


class _Item(BaseModelWithConfig):
    id: int


class _ItemValidation(BaseResponseValidator):
    @property
    def ResponseSuccessBody(self):
        return _Item


@pytest.mark.asyncio
async def test_instrumented_schema_failure_under_a_status_set_keeps_its_errors(attachments):
    from partest.tracking import CreatedRegistry, TrackingApiClient

    def handler(request):
        return httpx.Response(201, json={"id": "nope"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
        tracked = TrackingApiClient(
            "http://stand", CreatedRegistry(), client=ApiClient("http://stand", client=hx)
        )
        with pytest.raises(AssertionError) as info:
            await tracked.make_request(
                "POST", "/items", json_data={}, expected_status_code=(200, 201),
                validate_model=_ItemValidation(), type=TypesTestCases.request_default,
            )
    assert not isinstance(info.value, StatusMismatchError)
    assert info.value.validation_errors[0]["loc"] == ("id",)
    assert "status_mismatch" not in [n for n, _ in attachments]


# --- 9. the HTTP-error branch raises StatusMismatchError ---------------------------------------


@pytest.mark.asyncio
async def test_http_error_branch_is_a_status_mismatch():
    async def raise_for_status(response):
        await response.aread()
        response.raise_for_status()

    def handler(request):
        return httpx.Response(502, json={"token": MARKER})

    with pytest.raises(StatusMismatchError) as info:
        await _call(handler, client_kwargs={"event_hooks": {"response": [raise_for_status]}},
                    method="GET", endpoint="/x", expected_status_code=(200, 204))
    exc = info.value
    assert (exc.status_code, exc.expected) == (502, (200, 204))
    assert exc.__cause__ is None and exc.__context__ is None
    assert MARKER not in str(exc)
