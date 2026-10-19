"""Masking with simple rules — header names by their last segment, query names that
mean one thing only — the value scanner's edges, and two client defects found on the way.

Secrets are built from a marker at run time; nothing here looks like a real credential.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from partest import StatusMismatchError, TypesTestCases
from partest.client import ApiClient, format_status_mismatch
from partest.redact import _scrub, _scrub_params, _scrub_urls, redact_text

MARKER = "S3CRET-MARKER-c0de"


async def _call(handler, *, client_kwargs=None, api_kwargs=None, **kwargs):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), **(client_kwargs or {})
    ) as hx:
        api = ApiClient("http://stand", client=hx, **(api_kwargs or {}))
        return await api.make_request(type=TypesTestCases.request_default, **kwargs)


# --- 4. a hook that rejects the expected status -------------------------------------------------


@pytest.mark.asyncio
async def test_a_hook_rejecting_the_expected_status_is_not_an_assertion():
    async def raise_for_status(response):
        await response.aread()
        response.raise_for_status()

    def handler(request):
        return httpx.Response(404, json={"detail": "not found"})

    with pytest.raises(RuntimeError, match="rejected the expected status 404") as info:
        await _call(handler, client_kwargs={"event_hooks": {"response": [raise_for_status]}},
                    method="GET", endpoint="/x", expected_status_code=404)
    assert not isinstance(info.value, AssertionError)


@pytest.mark.asyncio
async def test_instrumented_hook_rejection_is_not_reported_as_expected_404_got_404():
    from partest.tracking import CreatedRegistry, TrackingApiClient

    async def raise_for_status(response):
        await response.aread()
        response.raise_for_status()

    def handler(request):
        return httpx.Response(404, json={})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), event_hooks={"response": [raise_for_status]}
    ) as hx:
        tracked = TrackingApiClient(
            "http://stand", CreatedRegistry(), client=ApiClient("http://stand", client=hx)
        )
        with pytest.raises(RuntimeError) as info:
            await tracked.make_request("GET", "/x", expected_status_code=404,
                                       type=TypesTestCases.request_default)
    assert "expected 404, got 404" not in str(info.value)


# --- 5. an expected status is not retried -----------------------------------------------------


@pytest.mark.asyncio
async def test_an_expected_429_is_not_retried():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(429, json={})

    await _call(handler, api_kwargs={"max_retries": 3, "retry_backoff": 0.0},
                method="POST", endpoint="/login", json_data={}, expected_status_code=429)
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_an_unexpected_429_is_still_retried():
    answers = iter([429, 200])
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(next(answers), json={})

    await _call(handler, api_kwargs={"max_retries": 3, "retry_backoff": 0.0},
                method="GET", endpoint="/x", expected_status_code=200)
    assert len(seen) == 2


# --- 7. query names that mean one thing only -----------------------------------------------------


def test_ambiguous_query_names_are_not_masked():
    assert _scrub_urls("https://h.example/x?code=RU&key=name&sig=1") == (
        "https://h.example/x?code=RU&key=name&sig=***"  # an Azure SAS signature is access
    )
    signed = _scrub_urls(
        f"https://s.example/o?X-Goog-Signature={MARKER}&auth_token={MARKER}&session_id={MARKER}"
    )
    assert MARKER not in signed
    assert _scrub_params({"code": 200, "token": MARKER}) == {"code": 200, "token": "***"}


# --- 8. the value scanner -------------------------------------------------------------------


def test_status_message_keeps_its_tail_after_a_bracketed_comment():
    response = httpx.Response(
        400, text='{"comment": "password: [can' + "'" + 't be empty]", "id": 7}'
    )
    msg = format_status_mismatch(method="POST", url="http://stand/x", expected=201,
                                 actual=400, response=response)
    masked = redact_text(msg)  # free-text masking of the whole message
    # The apostrophe may open a string: the pair is not trusted, the value runs to the end of
    # its line — the rest of the line goes, the next lines stay.
    assert "response body:" in masked and "hint: Bad Request" in masked
    assert "can't be empty" not in masked


def test_a_traceback_with_an_open_bracket_keeps_its_other_frames():
    text = (
        "Traceback (most recent call last):\n"
        '  File "a.py", line 3, in f\n'
        f"    token = {{'value': '{MARKER}',\n"
        '  File "b.py", line 9, in g\n'
        "    other()\n"
        "ValueError: boom"
    )
    masked = redact_text(text)
    assert MARKER not in masked
    assert 'File "b.py", line 9, in g' in masked and "ValueError: boom" in masked


def test_a_validation_message_keeps_the_next_error():
    # With an apostrophe inside, the bracket's pair is not trusted: closed when in doubt.
    text = "Validation failed: password: [can't be blank], email: [is invalid]"
    assert "can't be blank" not in redact_text(text)
    secret = redact_text(f"Validation failed: password: [{MARKER}], email: [is invalid]")
    assert MARKER not in secret and "email: [is invalid]" in secret


def test_json_encoded_in_a_string_is_scanned_with_its_escapes():
    text = 'body={\\"token\\": {\\"a\\": \\"' + MARKER + '\\"}, \\"z\\": 1}'
    masked = redact_text(text)
    assert MARKER not in masked
    assert masked.endswith(', \\"z\\": 1}')


def test_an_unbalanced_value_is_masked_to_the_end_of_its_line():
    masked = redact_text('{"note": "token: [' + MARKER + '", "next": "x"}\nsecond line')
    assert MARKER not in masked and masked.endswith("\nsecond line")


def test_an_unbalanced_value_stops_at_the_truncation_marker():
    masked = redact_text(f"password: [{MARKER} ... [truncated, 9000 chars total]")
    assert MARKER not in masked and "[truncated, 9000 chars total]" in masked


# --- 9. print_error keeps the path ------------------------------------------------------------


def test_print_error_does_not_mask_a_path_that_names_a_secret(capsys):
    from pydantic import BaseModel, ValidationError

    from partest.utils import PydanticResponseError

    class Inner(BaseModel):
        b: int

    class Outer(BaseModel):
        Token: Inner

    try:
        Outer.model_validate({"Token": {"b": MARKER}})
    except ValidationError as e:
        PydanticResponseError.print_error(e)
    out, _ = capsys.readouterr()
    assert "('Token', 'b')" in out
    assert MARKER not in out


# --- 6. headers in a whole request log ---------------------------------------------------------


def test_request_log_header_rule(caplog):
    from partest.utils import Logger

    caplog.set_level(logging.INFO)
    Logger().log_request(
        "GET", "http://stand/x",
        headers={"X-Csrf-Token": MARKER, "X-Request-Id": "s-42", "WWW-Authenticate": "Bearer"},
    )
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert MARKER not in text and "s-42" in text and "'WWW-Authenticate': 'Bearer'" in text


def test_status_mismatch_error_is_still_raised_for_an_unexpected_status():
    async def run():
        async def raise_for_status(response):
            await response.aread()
            response.raise_for_status()

        def handler(request):
            return httpx.Response(500, json={})

        return await _call(handler, client_kwargs={"event_hooks": {"response": [raise_for_status]}},
                           method="GET", endpoint="/x", expected_status_code=404)

    import asyncio

    with pytest.raises(StatusMismatchError) as info:
        asyncio.run(run())
    assert info.value.status_code == 500


def test_scrub_does_not_touch_a_field_that_only_names_a_secret():
    assert _scrub({"missing": ["password"], "field": "token"}) == {
        "missing": ["password"], "field": "token"
    }


# --- free text: closed when in doubt ---------------------------------------------------------


@pytest.mark.parametrize(
    "template",
    [
        "Creds(raw=b'x', token='{s}')",
        "rotating the users' token: '{s}'",
        "{{'msg': \"users' data\", 'password': '{s}'}}",
        'Unexpected token " in JSON: {{"password": "{s}"}}',
        '{{"login": "admin"--", "password": "{s}"}}',
        "N'adm', password = '{s}'",
        "token: {{\n    'raw': b'x',\n    'v': '{s}'\n}}",
        "token=b'{s}'",
        "password: 'it''s-{s}'",
    ],
    ids=["bytes_before", "apostrophe_before", "apostrophe_in_other_value", "lone_quote",
         "sql_injection_quote", "sql_literal", "pprint_block", "bytes_value", "apostrophe_inside"],
)
def test_free_text_leaks_are_closed(template):
    assert MARKER not in redact_text(template.format(s=MARKER))


def test_an_open_value_is_masked_as_its_indented_block():
    text = (
        "Data: {\n"
        ' "token": {\n'
        f'  "a": "{MARKER}",\n'
        f'  "b": "{MARKER}"\n'
        "... [truncated, 9000 chars total]"
    )
    masked = redact_text(text)
    assert MARKER not in masked
    assert masked.endswith("... [truncated, 9000 chars total]")


@pytest.mark.parametrize(
    "chunk", ["token: {\n", "x\ntoken: [a\n", "token={", '"token: [a ', "password: 'a\n"]
)
def test_many_open_values_take_linear_time(chunk):
    import time

    text = chunk * (65536 // len(chunk))
    started = time.perf_counter()
    redact_text(text)
    assert time.perf_counter() - started < 2.0


def test_known_defect_survives_a_session_without_the_skipping_plugin(pytester):
    pytester.makepyfile(
        test_suite=(
            "import pytest\n\n"
            "@pytest.mark.known_defect('BUG-1')\n"
            "def test_reproduces():\n"
            "    assert False\n\n"
            "def test_plain():\n"
            "    pass\n"
        )
    )
    result = pytester.runpytest("-p", "no:skipping", "-ra", "-p", "no:randomly", "-p", "no:cacheprovider",
                                "-p", "no:asyncio", "-o", "addopts=")
    assert "AttributeError" not in result.stdout.str()
    assert "INTERNALERROR" not in result.stdout.str()
    result.stdout.fnmatch_lines(["*XFAIL BUG-1*"])
    result.assert_outcomes(passed=1, skipped=1)  # an XFAIL without the skipping plugin


pytest_plugins = ["pytester"]
