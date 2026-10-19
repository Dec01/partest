"""Every channel that shows what went over the wire masks it (proposals §E2).

One walker serves every channel (`partest.redact._scrub`): a value under a secret key is
`***` whole — no prefix kept, headers included; any other string gets only narrow patterns
(URL credentials and secret query values, Bearer/Basic, a JWT), so a body that merely *names*
a secret field stays readable and stays valid JSON. Text that is not JSON gets the full
`redact_text`.

Each test sends a secret through one input (body, header, cookie, query, URL userinfo) and
looks for it in every output a failed run produces: log records (httpx's own line included),
stdout, the exception text with its whole chain (`traceback.format_exception`), and every
Allure attachment.
"""

from __future__ import annotations

import json
import logging
import pickle
import traceback
from dataclasses import dataclass

import allure
import httpx
import pytest

from partest import (
    BaseModelWithConfig,
    BaseResponseValidator,
    StatusMismatchError,
    TypesTestCases,
)
from partest.client import ApiClient, format_status_mismatch
from partest.redact import _body_text, _scrub, redact_text
from partest.reporting import attach as attach_mod
from partest.reporting.templates import ErrorTemplates, StepTemplates, format_http_status_failure
from partest.utils import ErrorDesc, Logger, PydanticResponseError

MARKER = "S3CRET-MARKER-7f3a9c"
# A mask that keeps a prefix would still show this.
PREFIX = MARKER[:8]


@pytest.fixture
def attachments(monkeypatch):
    """Every Allure attachment made during the test, as text."""
    seen: list[tuple[str, str]] = []

    def record(body, name=None, attachment_type=None, extension=None):
        seen.append((str(name), str(body)))

    monkeypatch.setattr(allure, "attach", record)
    return seen


def _chain(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def _logs(caplog) -> str:
    return "\n".join(r.getMessage() for r in caplog.records)


def _assert_nowhere(secret: str, *, caplog=None, capsys=None, exc=None, attachments=None):
    if caplog is not None:
        assert secret not in _logs(caplog)
    if capsys is not None:
        out, err = capsys.readouterr()
        assert secret not in out
        assert secret not in err
    if exc is not None:
        assert secret not in _chain(exc)
    if attachments is not None:
        for name, body in attachments:
            assert secret not in body, name


async def _call(handler, *, client_kwargs=None, **kwargs):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), **(client_kwargs or {})
    ) as hx:
        api = ApiClient("http://stand", client=hx)
        return await api.make_request(type=TypesTestCases.request_default, **kwargs)


def _nested(depth: int, leaf) -> dict:
    node = leaf
    for i in range(depth):
        node = {f"level{i}": node}
    return node


# --- the walker -----------------------------------------------------------------------------


def test_a_body_that_names_a_secret_field_stays_readable_and_valid_json():
    body = {
        "missing": ["password", "email"],
        "errors": [{"field": "password", "message": "too short"}],
        "detail": "token: expired",
        "token": MARKER,
    }
    text = _body_text(body)
    assert json.loads(text) == {
        "missing": ["password", "email"],
        "errors": [{"field": "password", "message": "too short"}],
        "detail": "token: expired",
        "token": "***",
    }


def test_secret_keys_are_masked_whole_at_any_depth_and_beyond_it():
    deep = _nested(10, {"password": MARKER})
    text = _body_text(deep)
    assert MARKER not in text and PREFIX not in text
    assert json.loads(text)  # still JSON
    beyond = _body_text(_nested(60, MARKER))
    assert MARKER not in beyond  # past the walker's depth the value is replaced whole


def _b64url(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_string_leaves_get_only_narrow_patterns():
    # Built at run time: the source tree must hold nothing that looks like a token.
    jwt_payload = _b64url(b'{"sub":"123"}')
    jwt = ".".join([_b64url(b'{"alg":"HS256"}'), jwt_payload, _b64url(b"signature")])
    walked = _scrub(
        {
            "next": f"https://u:{MARKER}@h.example/x?access_token={MARKER}&page=2",
            "auth": f"Bearer {MARKER}abcdef",
            "jwt": jwt,
            "query": f"a=1&password={MARKER}",
            "text": "the password is required",
        }
    )
    dumped = json.dumps(walked)
    assert MARKER not in dumped
    assert jwt_payload not in dumped
    assert walked["text"] == "the password is required"
    assert walked["next"] == "https://h.example/x?access_token=***&page=2"


def test_a_json_string_leaf_is_walked_too():
    walked = _scrub({"payload": json.dumps({"client_secret": MARKER, "id": 1})})
    assert json.loads(walked["payload"]) == {"client_secret": "***", "id": 1}


def test_models_dataclasses_bytes_and_sets_are_walked():
    class Login(BaseModelWithConfig):
        user: str
        password: str

    @dataclass
    class Creds:
        api_key: str
        name: str

    text = _body_text(
        [Login(user="u", password=MARKER), Creds(api_key=MARKER, name="n"),
         json.dumps({"token": MARKER}).encode(), {MARKER + "-not-a-key"}]
    )
    assert '"password": "***"' in text and '"api_key": "***"' in text
    assert MARKER + "-not-a-key" in text  # a set member under no key is not a secret


def test_text_that_is_not_json_gets_the_full_redact_text():
    assert MARKER not in _body_text(f"login failed: password={MARKER}; user=bob")


def test_a_body_too_deep_to_parse_is_not_shown_raw():
    hostile = "[" * 200000 + "]" * 200000
    text = _body_text(hostile, limit=50)
    assert len(text) < 200  # no RecursionError, shortened


# --- redact_text --------------------------------------------------------------------------


def test_redact_text_masks_basic_credentials_and_whole_cookie_lines():
    import base64

    basic = base64.b64encode(f"alice:{MARKER}".encode()).decode()
    text = redact_text(f"Authorization: Basic {basic}\nCookie: a=1; session={MARKER}; theme=dark")
    assert basic not in text and MARKER not in text
    assert redact_text("basic information") == "basic information"


def test_redact_text_masks_closed_when_in_doubt():
    # In free text a quote cannot be told apart reliably: masking more is the safe side, even
    # when the JSON then no longer parses.
    masked = redact_text('{"q": "token=abc", "token": "x\\"y"}')
    assert "abc" not in masked and '"token": "***"' in masked
    assert redact_text('["password", "email"]') == '["password", "email"]'
    assert redact_text('{"field": "password", "message": "m"}') == '{"field": "password", "message": "m"}'


# --- URLs ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        f"https://u:p@ss{MARKER}@h.example/x",
        f"https://u:pa/ss{MARKER}@h.example/x",
        f"u:{MARKER}@db.example:5432/x",
    ],
    ids=["at_in_password", "slash_in_password", "no_scheme"],
)
def test_userinfo_is_removed_wherever_it_is(url):
    from partest.conf import _strip_url_secrets
    from partest.redact import _scrub_urls

    assert MARKER not in _scrub_urls(url)
    assert MARKER not in _strip_url_secrets(url)


def test_a_port_is_not_taken_for_a_password():
    from partest.redact import _scrub_urls

    assert _scrub_urls("https://h.example:8080/users/a@b.example") == (
        "https://h.example:8080/users/a@b.example"
    )


# --- the INFO request / response log -------------------------------------------------------


def test_request_log_masks_body_params_url_headers_and_shows_files_by_name(caplog):
    caplog.set_level(logging.INFO)
    Logger().log_request(
        "POST",
        f"http://user:{MARKER}@stand/items?token={MARKER}&page=2",
        params={"access_token": MARKER, "page": 2},
        headers={"Authorization": f"Bearer {MARKER}", "Accept": "application/json",
                 "Referer": f"https://h.example/back?api_key={MARKER}"},
        data={"name": "x", "nested": {"password": MARKER}},
        files={"upload": ("report.csv", MARKER.encode() * 3, "text/csv")},
    )
    text = _logs(caplog)
    assert MARKER not in text and PREFIX not in text
    assert "page=2" in text and '"page": 2' in text
    assert '"name": "x"' in text  # the body is JSON now, not a Python repr
    assert "'Authorization': '***'" in text
    assert "'filename': 'report.csv'" in text and "'size': 60" in text
    assert "'content_type': 'text/csv'" in text


def test_request_log_computes_nothing_when_info_is_off(caplog, monkeypatch):
    import partest.utils.logger as logger_mod

    def boom(*args, **kwargs):
        raise AssertionError("masked a body that nobody would see")

    monkeypatch.setattr(logger_mod, "_body_text", boom)
    caplog.set_level(logging.WARNING)
    Logger().log_request("POST", "http://stand/x", data={"a": 1})
    Logger().log_response(httpx.Response(200, json={"a": 1}))


def test_response_log_masks_body_headers_and_cookies(caplog):
    caplog.set_level(logging.INFO)
    response = httpx.Response(
        302,
        json={"id": 1, "token": MARKER},
        headers=[
            ("Set-Cookie", f"sid={MARKER}; Path=/"),
            ("X-Auth-Token", MARKER),
            ("Location", f"https://u:{MARKER}@h.example/next?token={MARKER}"),
            ("X-Request-Id", "req-1"),
        ],
        request=httpx.Request("GET", "http://stand/items"),
    )
    Logger().log_response(response)
    text = _logs(caplog)
    assert MARKER not in text and PREFIX not in text
    assert "'sid': '***'" in text and "req-1" in text and '"id": 1' in text
    assert "https://h.example/next?token=***" in text


def test_response_log_masks_a_non_json_body(caplog):
    caplog.set_level(logging.INFO)
    Logger().log_response(httpx.Response(200, text=f"access_token={MARKER}&expires=60"))
    text = _logs(caplog)
    assert MARKER not in text and "expires=60" in text


def test_logger_error_warning_and_log_str_are_masked(caplog):
    caplog.set_level(logging.INFO)
    log = Logger()
    log.error(f"failed for http://u:{MARKER}@h/x")
    log.warning(f"password={MARKER}")
    log.log_str(f"Authorization: Bearer {MARKER}")
    assert MARKER not in _logs(caplog)


@pytest.mark.asyncio
async def test_httpx_request_line_is_masked(caplog):
    caplog.set_level(logging.INFO)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    await _call(handler, method="GET", endpoint=f"/items?access_token={MARKER}&page=1")
    lines = [r.getMessage() for r in caplog.records if r.name.startswith("httpx")]
    assert lines and all(MARKER not in line for line in lines)
    assert any("access_token=***&page=1" in line for line in lines)
    filters = logging.getLogger("httpx").filters
    ApiClient("http://stand")
    assert logging.getLogger("httpx").filters == filters  # installed once


# --- status mismatch: message, its attachment, the ERROR line -------------------------------


@pytest.mark.asyncio
async def test_status_mismatch_masks_every_channel_and_carries_the_status(
    caplog, capsys, attachments
):
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"error": "boom", "refresh_token": MARKER, "missing": ["password"]},
            headers={"Set-Cookie": f"sid={MARKER}"},
        )

    with pytest.raises(StatusMismatchError) as info:
        await _call(
            handler,
            method="POST",
            endpoint="/items",
            params={"token": MARKER},
            headers={"Authorization": f"Bearer {MARKER}"},
            json_data={"name": "x", "password": MARKER},
            expected_status_code=(201, 202),
        )
    exc = info.value
    assert isinstance(exc, AssertionError)
    assert exc.status_code == 500 and exc.expected == (201, 202)
    text = str(exc)
    assert text.startswith("HTTP status mismatch: expected {201, 202}, got 500")
    assert '"missing": ["password"]' in text and '"name": "x"' in text
    assert any(name == "status_mismatch" for name, _ in attachments)
    assert [r for r in caplog.records if r.levelno >= logging.ERROR]  # ErrorDesc.status
    _assert_nowhere(MARKER, caplog=caplog, capsys=capsys, exc=exc, attachments=attachments)
    _assert_nowhere(PREFIX, caplog=caplog, exc=exc, attachments=attachments)
    copy = pickle.loads(pickle.dumps(exc))
    assert (copy.status_code, copy.expected, str(copy)) == (500, (201, 202), text)


def test_format_status_mismatch_masks_url_and_bodies():
    response = httpx.Response(
        400,
        text=f'{{"client_secret": "{MARKER}"}}',
        request=httpx.Request("GET", f"http://stand/x?api_key={MARKER}"),
    )
    msg = format_status_mismatch(
        method="GET",
        url=f"http://u:{MARKER}@stand/x?api_key={MARKER}&page=3",
        expected=200,
        actual=400,
        request_body=f"token={MARKER}",
        response=response,
    )
    assert MARKER not in msg
    assert "http://stand/x?api_key=***&page=3" in msg


def test_error_desc_never_shows_raw_and_never_fails():
    assert MARKER not in ErrorDesc.status(
        codeExpected=200, codeActual=500, responseBody=httpx.Response(500, json={"secret": MARKER})
    )
    assert MARKER not in ErrorDesc.status(
        codeExpected=200, codeActual=500, responseBody=httpx.Response(500, text=f"password={MARKER}")
    )

    class Unreadable:
        def json(self):
            raise ValueError("no")

        @property
        def text(self):
            raise RuntimeError(MARKER)

    text = ErrorDesc.status(codeExpected=200, codeActual=500, responseBody=Unreadable())
    assert "not shown" in text and MARKER not in text
    element = ErrorDesc.element(
        payloadElement={"token": MARKER}, dataElement="x",
        requestBody=httpx.Response(200, json={"password": MARKER}),
        responseBody=httpx.Response(200, json={"token": MARKER}),
    )
    assert MARKER not in element


# --- schema failure: the chain, validation_errors, print_error ------------------------------


class _Item(BaseModelWithConfig):
    id: int


class _ItemValidation(BaseResponseValidator):
    @property
    def ResponseSuccessBody(self):
        return _Item


class _Session(BaseModelWithConfig):
    token: int


class _SessionValidation(BaseResponseValidator):
    @property
    def ResponseSuccessBody(self):
        return _Session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body, model, where",
    [
        ({"token": MARKER}, _SessionValidation(), ("token", "int_parsing")),
        ({"id": 1, "token": MARKER}, _ItemValidation(), ("token", "extra_forbidden")),
    ],
    ids=["rejected_value", "extra_secret_member"],
)
async def test_schema_failure_chain_and_stdout_carry_no_values(
    body, model, where, caplog, capsys, attachments
):
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with pytest.raises(AssertionError) as info:
        await _call(
            handler, method="GET", endpoint="/items", expected_status_code=200,
            validate_model=model,
        )
    exc = info.value
    assert exc.__cause__ is None and exc.__context__ is None
    chain = _chain(exc)
    assert "input_value" not in chain
    assert f"{where[0]} [{where[1]}]" in chain
    assert [(e["loc"], e["type"]) for e in exc.validation_errors] == [((where[0],), where[1])]
    assert all(set(e) == {"loc", "type", "msg"} for e in exc.validation_errors)
    out, _ = capsys.readouterr()
    assert "Проблемный ключ:" in out and MARKER not in out
    _assert_nowhere(MARKER, caplog=caplog, exc=exc, attachments=attachments)


@pytest.mark.asyncio
async def test_schema_failure_error_line_is_text_not_a_tuple_repr(caplog):
    """`ErrorDesc.validate` returned a tuple; its repr went to the log with literal `\\n` on
    one line, and the mask after `token = ***` swallowed the text that followed."""
    caplog.set_level(logging.ERROR)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token": MARKER})

    with pytest.raises(AssertionError):
        await _call(
            handler, method="GET", endpoint="/items", expected_status_code=200,
            validate_model=_SessionValidation(),
        )
    lines = [r.getMessage() for r in caplog.records if "Ошибка валидации" in r.getMessage()]
    assert lines, _logs(caplog)
    text = lines[0]
    assert "\\n" not in text and "('" not in text  # a string, not the repr of a tuple
    # the line after the masked value survives: "token" did not eat "Response body"
    assert "Подробнее в принт-логах." in text and "\nResponse body: " in text
    assert MARKER not in text


def test_error_desc_validate_is_one_string():
    text = ErrorDesc.validate(validateModel="M", validateData={"a": 1}, error="token = x")
    assert isinstance(text, str)
    assert text.index("token = x") < text.index("M") < text.index("{'a': 1}")


def test_print_error_shows_the_type_not_the_value(capsys):
    from pydantic import ValidationError

    try:
        _Item.model_validate({"id": MARKER})
    except ValidationError as e:
        PydanticResponseError.print_error(e)
    out, _ = capsys.readouterr()
    assert MARKER not in out
    assert "<str, значение не показывается>" in out


# --- the HTTP-error and network-error branches of make_request -----------------------------


@pytest.mark.asyncio
async def test_http_status_error_branch_is_masked_and_not_chained(caplog, attachments):
    caplog.set_level(logging.DEBUG)

    async def raise_for_status(response: httpx.Response) -> None:
        await response.aread()
        response.raise_for_status()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"token": MARKER})

    with pytest.raises(AssertionError) as info:
        await _call(
            handler,
            client_kwargs={"event_hooks": {"response": [raise_for_status]}},
            method="GET",
            endpoint=f"/items?token={MARKER}",
        )
    assert str(info.value).startswith("Server returned 503: ")
    assert info.value.__cause__ is None and info.value.__context__ is None
    _assert_nowhere(MARKER, caplog=caplog, exc=info.value, attachments=attachments)


@pytest.mark.asyncio
async def test_network_error_and_hook_failure_log_lines_are_masked(caplog):
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach http://u:{MARKER}@stand/?token={MARKER}")

    with pytest.raises(httpx.ConnectError):
        await _call(handler, method="GET", endpoint="/items")

    api = ApiClient("http://stand")

    def hook(*args):
        raise RuntimeError(f"password={MARKER}")

    api.add_response_hook(hook)
    api._emit_response("GET", "/x", {}, None)
    text = _logs(caplog)
    assert "Network/request error:" in text and "response hook failed" in text
    assert MARKER not in text


# --- Allure: attach_* and instrumentation ---------------------------------------------------


def test_attach_response_default_is_unchanged_and_true_masks(attachments):
    attach_mod.attach_response(status=200, body={"token": MARKER})
    assert MARKER in attachments[-1][1]  # the public default stays: as received
    attach_mod.attach_response(status=200, body=_nested(10, {"token": MARKER}), redact_body=True)
    attach_mod.attach_response(status=200, body=f"password={MARKER}", redact_body=True)
    for _, text in attachments[1:]:
        assert MARKER not in text


def test_attach_request_masks_params_path_headers_and_deep_bodies(attachments):
    attach_mod.attach_request(
        method="GET",
        path=f"/items?token={MARKER}",
        params={"api_key": MARKER, "page": 1},
        headers={"Cookie": f"sid={MARKER}"},
        body=_nested(10, {"secret": MARKER}),
    )
    (_, text), = attachments
    assert MARKER not in text and PREFIX not in text
    assert '"page": 1' in text
    json.loads(text)


def test_attach_check_and_mismatch_mask_a_secret_field(attachments):
    attach_mod.attach_check(field="token", expected=MARKER, actual=MARKER + "x", ok=False)
    msg = ErrorTemplates.mismatch(field="password", expected=MARKER, actual="other")
    typed = ErrorTemplates.type_mismatch(field="token", expected_type="int", actual=MARKER)
    title = StepTemplates.assert_field("access_token", MARKER)
    for text in (attachments[0][1], msg, typed, title):
        assert MARKER not in text
    plain = ErrorTemplates.mismatch(field="status", expected="OK", actual="FAILED")
    assert "'OK'" in plain and "'FAILED'" in plain


def test_checks_attachments_are_masked(attachments):
    from partest.reporting.checks import check_in

    check_in("id", {"id": 1, "token": MARKER})
    _assert_nowhere(MARKER, attachments=attachments)


def test_sideeffects_messages_are_masked():
    from partest.sideeffects import Observation, assert_locator

    with pytest.raises(AssertionError) as info:
        assert_locator({"token": MARKER}, field="location")
    assert MARKER not in str(info.value)
    with pytest.raises(AssertionError) as info:
        Observation("bus", found=False, detail={"password": MARKER}).require()
    assert MARKER not in str(info.value)


def test_attach_failure_masks_the_text(attachments):
    try:
        raise RuntimeError(f"upstream said password={MARKER}")
    except RuntimeError as exc:
        attach_mod.attach_failure(f"failed with token={MARKER}", exc)
    _assert_nowhere(MARKER, attachments=attachments)


def test_format_http_status_failure_masks_bodies_path_and_original_message():
    msg = format_http_status_failure(
        method="POST",
        path=f"/items?token={MARKER}",
        expected=201,
        actual=409,
        request_body={"password": MARKER},
        response_body={"title": "conflict", "detail": f"Bearer {MARKER}xyz"},
        original_message=f"HTTP status mismatch ... secret={MARKER}",
    )
    assert MARKER not in msg


@pytest.mark.asyncio
async def test_instrumented_tracking_client_masks_attachments_titles_and_failure(
    attachments, caplog, monkeypatch
):
    from partest.reporting import templates
    from partest.tracking import CreatedRegistry, TrackingApiClient

    caplog.set_level(logging.DEBUG)
    titles: list[str] = []
    real_step = allure.step

    def step(title):
        titles.append(str(title))
        return real_step(title)

    monkeypatch.setattr(allure, "step", step)
    monkeypatch.setattr(templates, "_conflict_hint_provider", lambda path, body: f"token={MARKER}")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_nested(10, {"access_token": MARKER}))
        return httpx.Response(409, json={"error": "taken", "client_secret": MARKER})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
        api = ApiClient("http://stand", client=hx)
        tracked = TrackingApiClient("http://stand", CreatedRegistry(), client=api)
        await tracked.make_request(
            "GET", f"/items?token={MARKER}", expected_status_code=200,
            type=TypesTestCases.request_default,
        )
        with pytest.raises(StatusMismatchError) as info:
            await tracked.make_request(
                "POST",
                "/items",
                json_data={"password": MARKER},
                expected_status_code=201,
                type=TypesTestCases.request_default,
            )
    assert info.value.status_code == 409 and info.value.expected == (201,)
    names = [name for name, _ in attachments]
    assert "response" in names and "status_mismatch" in names and "failure_details" in names
    _assert_nowhere(MARKER, caplog=caplog, exc=info.value, attachments=attachments)
    assert titles and all(MARKER not in t for t in titles)
