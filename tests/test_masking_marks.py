"""Which exceptions count as already masked, and the remaining check_* and text channels.

Only the package marks an exception it raises with a masked message; a suite's exception of
the same class — or one that merely carries ``validation_errors`` — is masked like any text.
"""

from __future__ import annotations

import pickle

import allure
import httpx
import pytest

from partest import StatusMismatchError, TypesTestCases
from partest.client import ApiClient
from partest.redact import _already_masked, redact_text

MARKER = "S3CRET-MARKER-ab12"


@pytest.fixture
def attachments(monkeypatch):
    seen: list[tuple[str, str]] = []

    def record(body, name=None, attachment_type=None, extension=None):
        seen.append((str(name), str(body)))

    monkeypatch.setattr(allure, "attach", record)
    return seen


def _summary(exc, attachments, monkeypatch) -> str:
    from partest import pytest_plugin

    monkeypatch.setattr(pytest_plugin, "plugin_enabled", lambda: True)

    class Call:
        when = "call"

        class excinfo:
            value = exc

    attachments.clear()
    pytest_plugin.pytest_runtest_makereport(None, Call())
    return dict(attachments)["failure_summary"]


# --- 1. the mark --------------------------------------------------------------------------


def test_a_suites_own_exceptions_are_masked_in_failure_summary(attachments, monkeypatch):
    own = StatusMismatchError(f"got 500 with password={MARKER}", status_code=500)
    assert MARKER not in _summary(own, attachments, monkeypatch)

    carrier = AssertionError(f"token={MARKER}")
    carrier.validation_errors = []
    assert MARKER not in _summary(carrier, attachments, monkeypatch)

    class Sub(StatusMismatchError):
        _partest_masked = True  # a class attribute is not the mark

    assert not _already_masked(Sub(f"token={MARKER}"))


@pytest.mark.asyncio
async def test_the_packages_own_errors_are_not_masked_again(attachments, monkeypatch):
    def handler(request):
        return httpx.Response(401, json={"detail": "token: expired", "code": 7})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as hx:
        with pytest.raises(StatusMismatchError) as info:
            await ApiClient("http://stand", client=hx).make_request(
                "GET", "/x", expected_status_code=200, type=TypesTestCases.request_default
            )
    exc = info.value
    assert _already_masked(exc)
    assert _already_masked(pickle.loads(pickle.dumps(exc)))
    assert '"detail": "token: expired"' in _summary(exc, attachments, monkeypatch)


def test_check_errors_are_marked_and_kept_as_built(attachments, monkeypatch):
    from partest.reporting.checks import check_eq

    with pytest.raises(AssertionError) as info:
        check_eq({"detail": "token: expired"}, {"detail": "ok"}, field="body")
    assert _already_masked(info.value)
    # A check value is free text, so `token: expired` is masked once — and only once.
    summary = _summary(info.value, attachments, monkeypatch)
    assert "'detail': 'token: ***'" in summary and str(info.value) in summary


# --- 2. check_* contexts and values -------------------------------------------------------


def test_check_contexts_and_unexpected_values_are_masked(attachments):
    from partest.reporting.checks import check_ne, check_not_empty, check_status_in

    with pytest.raises(AssertionError) as info:
        check_ne({"token": MARKER}, {"token": MARKER}, field="body", context=f"password={MARKER}")
    assert MARKER not in str(info.value)
    with pytest.raises(AssertionError) as info:
        check_status_in(500, (200,), method="GET", path=f"/x?token={MARKER}")
    assert MARKER not in str(info.value)
    with pytest.raises(AssertionError) as info:
        check_not_empty([], field="items", context=f"secret={MARKER}")
    assert MARKER not in str(info.value)
    check_ne(1, {"token": MARKER}, field="body")  # a pass attaches the expectation too
    assert all(MARKER not in body for _, body in attachments)


# --- 3. the traceback in failure_details ----------------------------------------------------


@pytest.mark.asyncio
async def test_failure_details_mask_frames_and_chain(attachments):
    from partest.reporting.attach import _attach_failure_masked
    from partest.redact import _mark_masked

    def call_with_secret():
        json_data = {"password": MARKER}  # a source line the traceback quotes
        raise ValueError(f"upstream refused https://h.example/x?token={MARKER}") from KeyError(json_data)

    try:
        try:
            call_with_secret()
        except ValueError as cause:
            raise _mark_masked(AssertionError("status mismatch (masked)")) from cause
    except AssertionError as exc:
        _attach_failure_masked("message", exc)
    (_, text), = attachments
    assert MARKER not in text
    assert "AssertionError: status mismatch (masked)" in text


# --- 4. known_defect notes reach JUnit XML ---------------------------------------------------


pytest_plugins = ["pytester"]


def test_known_defect_note_is_a_junit_property(pytester):
    pytester.makepyfile(
        test_suite=(
            "import pytest\n\n"
            "@pytest.mark.known_defect('BUG-5')\n"
            "def test_network():\n"
            "    raise ConnectionError('down')\n"
        )
    )
    xml = pytester.path / "junit.xml"
    pytester.runpytest(f"--junitxml={xml}", "-p", "no:randomly", "-p", "no:cacheprovider",
                       "-p", "no:asyncio", "-o", "addopts=")
    text = xml.read_text(encoding="utf-8")
    assert 'name="known_defect_note"' in text and "not a reproduction" in text


# --- 5. Bearer challenge parameters ----------------------------------------------------------


def test_a_bearer_challenge_keeps_its_parameters():
    challenge = 'WWW-Authenticate: Bearer realm="api", error="invalid_token"'
    assert redact_text(challenge) == challenge
    assert MARKER not in redact_text(f"Authorization: Bearer {MARKER}")


# --- 6. PollTimeout's description ------------------------------------------------------------


def test_poll_timeout_masks_its_description():
    from partest.polling import PollTimeout, poll_until_sync

    with pytest.raises(PollTimeout) as caught:
        poll_until_sync(lambda: 1, lambda v: False, timeout=0, interval=1,
                        what=f"job with token={MARKER}")
    assert MARKER not in str(caught.value)
    assert _already_masked(caught.value)


# --- 7. optin_comparable on something that is not a payload --------------------------------


def test_optin_comparable_without_a_payload():
    from partest.reports import optin_comparable

    payload = {"meta": {"selection": {"optin": {"slow": {"state": "off"}}}}}
    assert optin_comparable(None, payload) == (None, [])
    assert optin_comparable(payload, []) == (None, [])
    assert optin_comparable({"meta": None}, payload) == (None, [])
