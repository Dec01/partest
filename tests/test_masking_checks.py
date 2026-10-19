"""check_* show each value masked once; notes, poll notes and the classifier's former branch.

Secrets are built from a marker at run time.
"""

from __future__ import annotations

import json

import allure
import pytest

MARKER = "S3CRET-MARKER-9f01"


@pytest.fixture
def attachments(monkeypatch):
    seen: list[tuple[str, str]] = []

    def record(body, name=None, attachment_type=None, extension=None):
        seen.append((str(name), str(body)))

    monkeypatch.setattr(allure, "attach", record)
    return seen


@pytest.fixture
def titles(monkeypatch):
    seen: list[str] = []
    real = allure.step

    def step(title):
        seen.append(str(title))
        return real(title)

    monkeypatch.setattr(allure, "step", step)
    return seen


VALUE = {"detail": "token: expired", "password": ""}


@pytest.mark.parametrize("check", ["check_ne", "check_in", "check_not_in"])
def test_a_check_value_is_masked_once_as_free_text(check, attachments):
    from partest.reporting import checks

    with pytest.raises(AssertionError) as info:
        if check == "check_ne":
            checks.check_ne(dict(VALUE), dict(VALUE), field="body")
        elif check == "check_in":
            checks.check_in(dict(VALUE), [{"other": 1}], field="body")
        else:
            checks.check_not_in(dict(VALUE), [dict(VALUE)], field="body")
    message = str(info.value)
    attachment = dict(attachments)["check:body"]
    json.loads(attachment)
    # Closed when in doubt: the prose loses its value — once, with its quotes intact.
    assert "'detail': 'token: ***'" in message
    assert '"detail": "token: ***"' in attachment
    assert "'password': ''" in message and '"password": ""' in attachment


def test_step_titles_of_bounds_and_prefixes_are_masked(titles, attachments):
    from partest.reporting.checks import check_between, check_lt, check_not_startswith

    check_not_startswith("value", f"token={MARKER}", field="text")
    check_between("token=m", f"token={MARKER}", "token=z", field="text")
    with pytest.raises(TypeError):
        check_lt(1, f"secret={MARKER}", field="n")
    assert titles and all(MARKER not in t for t in titles)
    assert all(MARKER not in body for _, body in attachments)


def test_notes_of_a_marked_exception_are_masked(attachments):
    from partest.redact import _mark_masked
    from partest.reporting.attach import _attach_failure_masked

    exc = _mark_masked(AssertionError('status mismatch: {"detail": "token: expired"}'))
    if not hasattr(exc, "add_note"):
        pytest.skip("exception notes are Python 3.11+")
    exc.add_note(f"retry with password={MARKER}")
    _attach_failure_masked("message", exc)
    (_, text), = attachments
    assert MARKER not in text
    assert 'status mismatch: {"detail": "token: expired"}' in text


def test_a_poll_note_masks_its_description():
    from partest.polling import poll_until_sync

    def fetch():
        raise ConnectionError("down")

    with pytest.raises(ConnectionError) as info:
        poll_until_sync(fetch, lambda v: True, timeout=1, interval=0,
                        what=f"job token={MARKER}")
    notes = getattr(info.value, "__notes__", [])
    if not notes:
        pytest.skip("exception notes are Python 3.11+")
    assert all(MARKER not in note for note in notes)


@pytest.mark.parametrize(
    "path, description, expected",
    [
        ("/a/b/{x/y/z}", "", "GET_DYNAMIC"),
        ("/orders/status/{a/b/c}", "List statuses", "GET_STATIC"),
    ],
)
def test_a_former_by_parent_template_reads_by_the_general_rules(path, description, expected):
    from partest.methodology import classify_endpoint

    assert classify_endpoint("GET", path, description).name == expected


# --- check values are free text at every level -------------------------------------------------


SECRET_LINE = f"password: {MARKER}"


@pytest.mark.parametrize(
    "value",
    [
        SECRET_LINE,
        SECRET_LINE.encode(),
        bytearray(SECRET_LINE.encode()),
        [SECRET_LINE],
        (SECRET_LINE,),
        {SECRET_LINE},
        {"log": [SECRET_LINE]},
        f"api_key: {MARKER}",
    ],
    ids=["str", "bytes", "bytearray", "list", "tuple", "set", "nested", "api_key"],
)
@pytest.mark.parametrize("check", ["check_eq", "check_ne", "check_in", "check_not_in"])
def test_no_check_shows_a_secret_line(check, value, attachments, titles):
    from partest.reporting import checks

    with pytest.raises(AssertionError) as info:
        if check == "check_eq":
            checks.check_eq(value, "other", field="log")
        elif check == "check_ne":
            checks.check_ne(value, value, field="log")
        elif check == "check_in":
            checks.check_in(value, ["other"], field="log")
        else:
            checks.check_not_in(value if isinstance(value, str) else "x", [value, "x"], field="log")
    assert MARKER not in str(info.value)
    assert all(MARKER not in t for t in titles)
    for name, body in attachments:
        assert MARKER not in body, name
        if name.startswith("check:"):
            json.loads(body)


def test_a_bytes_container_is_free_text_too(attachments):
    from partest.reporting.checks import check_in, check_not_in

    log = f"error: password: {MARKER}".encode()
    check_in(b"error", log, field="log")
    with pytest.raises(AssertionError):
        check_not_in(b"error", bytearray(log), field="log")
    with pytest.raises(AssertionError):  # a memoryview does not support `in`: not found
        check_in(b"error", memoryview(log), field="log")
    assert all(MARKER not in body for _, body in attachments)


def test_bounds_and_prefixes_are_free_text(attachments, titles):
    from partest.reporting.checks import check_between, check_lt, check_not_startswith

    with pytest.raises(AssertionError) as first:
        check_not_startswith(f"password: {MARKER}", "password", field="line")
    with pytest.raises(AssertionError) as second:
        check_between("z", f"api_key: {MARKER}", "token: y", field="line")
    with pytest.raises(AssertionError) as third:
        check_lt("z", f"secret: {MARKER}", field="line")
    for exc in (first.value, second.value, third.value):
        assert MARKER not in str(exc)
    assert all(MARKER not in t for t in titles)
    for name, body in attachments:
        assert MARKER not in body, name


# --- shorten after masking, context, keys, statuses, shared references -----------------------


def test_not_startswith_masks_before_it_shortens(attachments):
    from partest.reporting.checks import check_not_startswith

    import base64

    def part(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    payload = part(b'{"sub":"someone-quite-long"}')
    jwt = ".".join([part(b'{"alg":"HS256"}'), payload, part(b"signature")])
    text = "x" * 50 + " " + jwt  # cut at 80 before the second dot, the JWT would not match
    check_not_startswith(text, "y", field="line")
    (_, body), = attachments
    assert payload[:5] not in body


@pytest.mark.parametrize(
    "context", ['{"log": "password: %s"}' % MARKER, '["api_key: %s"]' % MARKER]
)
def test_a_context_is_masked_like_a_check_value(context):
    from partest.reporting.checks import check_eq, check_not_empty

    with pytest.raises(AssertionError) as first:
        check_eq(1, 2, field="n", context=context)
    with pytest.raises(AssertionError) as second:
        check_not_empty([], field="items", context=context)
    assert MARKER not in str(first.value) and MARKER not in str(second.value)


def test_text_keys_of_a_check_value_are_masked(attachments):
    import enum

    from partest.reporting.checks import check_eq

    Kind = enum.Enum("Kind", {"LINE": f"secret: {MARKER}"})
    value = {
        f"password: {MARKER}": 1,
        f"api_key: {MARKER}".encode(): 2,
        ("tok" + "en:", MARKER): 3,
        Kind.LINE: 4,
    }
    with pytest.raises(AssertionError) as info:
        check_eq(value, {}, field="map")
    assert MARKER not in str(info.value)
    assert all(MARKER not in body for _, body in attachments)


def test_a_status_is_shown_as_a_number_and_anything_else_masked(titles):
    from partest.reporting.checks import check_status, check_status_in

    with pytest.raises(AssertionError) as info:
        check_status(500, 200)
    assert "Expected: 200" in str(info.value) and "Actual: 500" in str(info.value)
    with pytest.raises(AssertionError) as info:
        check_status({"token": MARKER}, f"password: {MARKER}")
    with pytest.raises(AssertionError) as other:
        check_status_in(f"api_key: {MARKER}", (200, 201))
    assert MARKER not in str(info.value) and MARKER not in str(other.value)
    assert all(MARKER not in t for t in titles)
    assert any("(200, 201)" in t for t in titles)


def test_shared_references_are_walked_in_bounded_time():
    import time

    from partest.redact import _field_value, _scrub

    node: object = {"leaf": "x"}
    for _ in range(25):
        node = {"a": node, "b": node}  # a DAG: 2**25 paths, 26 objects
    for walk in (_scrub, lambda v: _field_value("v", v)):
        started = time.perf_counter()
        walk(node)
        assert time.perf_counter() - started < 3.0


# --- statuses as codes, a prefix kept as typed, the walk budget marker ----------------------


def test_an_int_enum_status_reads_as_its_code():
    from http import HTTPStatus

    from partest.reporting.templates import ErrorTemplates, StepTemplates, _status_shown

    assert _status_shown(HTTPStatus.CREATED) == "201"
    assert _status_shown((HTTPStatus.OK, 201)) == "(200, 201)"
    assert "Expected: 201" in ErrorTemplates.status(expected=HTTPStatus.CREATED, actual=500)
    assert StepTemplates.http("GET", "/x", HTTPStatus.OK).endswith("expect status=200")
    huge = 10**5000
    assert _status_shown(huge)  # too long to print: shown some other way, no ValueError


def test_status_in_the_other_templates_is_masked_when_not_a_number():
    from partest.reporting.templates import ErrorTemplates

    texts = [
        ErrorTemplates.forbidden_access(role="r", method="GET", path="/x", actual=f"token: {MARKER}"),
        ErrorTemplates.unexpected_allow(role="r", method="GET", path="/x", actual=f"token: {MARKER}"),
        ErrorTemplates.conflict_409(method="POST", path="/x", expected=f"token: {MARKER}"),
    ]
    assert all(MARKER not in t for t in texts)
    assert "Actual status: 403" in ErrorTemplates.forbidden_access(
        role="r", method="GET", path="/x", actual=403
    )


def test_not_startswith_shows_the_prefix_it_checks(attachments):
    import json as _json

    from partest.reporting.checks import check_not_startswith

    bom = "﻿"
    with pytest.raises(AssertionError) as info:
        check_not_startswith(bom + '{"a":1}', bom, field="body")
    assert repr(bom) in str(info.value) or bom in str(info.value)
    attached = _json.loads(dict(attachments)["check:body"])
    assert attached["actual"].startswith(bom) and attached["expected"]["not startswith"] == bom


def test_the_walk_budget_has_its_own_marker():
    from partest import redact

    wide = [{"i": i} for i in range(redact._MAX_NODES + 10)]
    walked = redact._scrub(wide)
    assert walked[-1] == "<too large>" and walked[0] == {"i": 0}
    assert redact._scrub_check(wide)[-1] == "<too large>"


def test_check_status_in_shows_http_status_as_codes(attachments):
    from http import HTTPStatus

    from partest.reporting.checks import check_status_in

    with pytest.raises(AssertionError) as info:
        check_status_in(HTTPStatus.NOT_FOUND, (HTTPStatus.OK, HTTPStatus.CREATED))
    message = str(info.value)
    assert "one of (200, 201)" in message and "Actual: 404" in message
    assert "HTTPStatus" not in message
    attached = dict(attachments)["check:status"]
    assert "in (200, 201)" in attached and "HTTPStatus" not in attached
