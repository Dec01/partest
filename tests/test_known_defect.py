"""``@pytest.mark.known_defect``: only an ``AssertionError`` from the body reproduces the defect.

Each case is a real pytest session (``pytester``, in process — the partest plugin is the one
this test session loaded). Plain ``xfail`` would report the setup failure, the network error
and the passing body all as XFAIL or XPASS; here they are error, failed and failed.
"""

from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]

SUITE = '''
import pytest

@pytest.fixture
def stand():
    raise ConnectionError("ssh tunnel is down")

@pytest.fixture
def broken_teardown():
    yield
    raise RuntimeError("cleanup failed")

@pytest.mark.known_defect("BUG-1", reason="total ignores the discount")
def test_body_asserts():
    assert 1 == 2

@pytest.mark.known_defect("BUG-2")
def test_setup_fails(stand):
    assert False

@pytest.mark.known_defect("BUG-3")
def test_body_raises_something_else():
    raise ConnectionError("reset by peer")

@pytest.mark.known_defect("BUG-4", reason="fixed?")
def test_body_passes():
    pass

@pytest.mark.known_defect("BUG-5")
def test_reproduces_but_teardown_fails(broken_teardown):
    assert 1 == 2

def test_unmarked_assertion():
    assert 1 == 2

@pytest.mark.known_defect("BUG-6")
def test_body_skips():
    pytest.skip("not today")

@pytest.mark.known_defect()
def test_marker_without_id():
    assert 1 == 2
'''


@pytest.fixture
def session(pytester):
    pytester.makepyfile(test_suite=SUITE)
    result = pytester.runpytest("-rxXfE", "-p", "no:randomly", "-p", "no:cacheprovider", "-p", "no:asyncio",
                                "--strict-markers", "-o", "addopts=")
    return result


def _outcome(result, name):
    for report in result.reprec.getreports("pytest_runtest_logreport"):
        if report.nodeid.endswith(f"::{name}") and report.when == "call":
            return report
    return None


def test_outcomes(session):
    session.assert_outcomes(passed=0, failed=3, xfailed=2, errors=3, skipped=1)


def test_assertion_in_the_body_is_xfail_with_the_id(session):
    session.stdout.fnmatch_lines(["XFAIL test_suite.py::test_body_asserts - BUG-1: total ignores the discount"])
    report = _outcome(session, "test_body_asserts")
    assert report.skipped and report.wasxfail == "BUG-1: total ignores the discount"
    assert ("known_defect", "BUG-1") in report.user_properties


def test_setup_failure_is_an_error_not_a_reproduction(session):
    session.stdout.fnmatch_lines(["ERROR test_suite.py::test_setup_fails - ConnectionError*"])
    reports = [
        r for r in session.reprec.getreports("pytest_runtest_logreport")
        if r.nodeid.endswith("::test_setup_fails") and r.when == "setup"
    ]
    assert reports and reports[0].failed and not hasattr(reports[0], "wasxfail")
    assert any(
        "an error in setup is not a reproduction" in text
        for name, text in reports[0].sections if name == "known_defect"
    )
    assert ("known_defect", "BUG-2") in reports[0].user_properties


def test_another_exception_in_the_body_is_a_failure(session):
    report = _outcome(session, "test_body_raises_something_else")
    assert report.failed and not hasattr(report, "wasxfail")
    assert any("ConnectionError is not a reproduction" in text for _, text in report.sections)


def test_a_passing_body_is_a_strict_xpass_failure(session):
    report = _outcome(session, "test_body_passes")
    assert report.failed
    assert str(report.longrepr).startswith("[XPASS(strict)] BUG-4: fixed?")


def test_teardown_error_after_a_reproduction_is_still_an_error(session):
    assert _outcome(session, "test_reproduces_but_teardown_fails").skipped
    session.stdout.fnmatch_lines(["ERROR test_suite.py::test_reproduces_but_teardown_fails*"])


def test_unmarked_and_skipped_tests_are_untouched(session):
    assert _outcome(session, "test_unmarked_assertion").failed
    report = _outcome(session, "test_body_skips")
    assert report.skipped and not hasattr(report, "wasxfail")


def test_a_marker_without_an_id_is_a_setup_error(session):
    session.stdout.fnmatch_lines(["ERROR test_suite.py::test_marker_without_id - TypeError*"])


def test_runxfail_turns_the_marker_off(pytester):
    pytester.makepyfile(test_suite=SUITE)
    result = pytester.runpytest("--runxfail", "-p", "no:randomly", "-p", "no:cacheprovider", "-p", "no:asyncio",
                                "-o", "addopts=", "-k", "body_asserts or body_passes")
    result.assert_outcomes(failed=1, passed=1)


ARGS = ("-p", "no:randomly", "-p", "no:cacheprovider", "-p", "no:asyncio", "-o", "addopts=")

STATUS_SUITE = '''
import pytest
from partest import StatusMismatchError

@pytest.mark.known_defect("BUG-7")
@pytest.mark.parametrize("status", [500, 429, 502, 503, 504, 404])
def test_status(status):
    raise StatusMismatchError("status mismatch", status_code=status, expected=(200,))

@pytest.mark.known_defect("BUG-8")
def test_imperative_xfail():
    pytest.xfail("decided in the body")

@pytest.mark.known_defect("BUG-9")
@pytest.mark.xfail(reason="both")
def test_both_markers():
    assert False

@pytest.fixture
def adds_xfail(request):
    request.applymarker(pytest.mark.xfail(reason="added by a fixture"))

@pytest.mark.known_defect("BUG-11")
def test_xfail_added_at_run_time(adds_xfail):
    assert False

@pytest.mark.known_defect("BUG-12")
def test_xfail_added_at_run_time_body_passes(adds_xfail):
    pass

@pytest.fixture
def adds_xfail_not_run(request):
    request.applymarker(pytest.mark.xfail(run=False, reason="not run"))

@pytest.mark.known_defect("BUG-13")
def test_xfail_not_run_added_at_run_time(adds_xfail_not_run):
    assert False
'''


def test_a_gateway_status_is_not_a_reproduction_but_500_is(pytester):
    pytester.makepyfile(test_suite=STATUS_SUITE)
    result = pytester.runpytest(*ARGS, "-rE")
    reports = {
        r.nodeid.split("::", 1)[1]: r
        for r in result.reprec.getreports("pytest_runtest_logreport") if r.when == "call"
    }
    for status in (500, 404, 429):  # 429: throttling is the service's own behaviour
        assert reports[f"test_status[{status}]"].wasxfail == "BUG-7"
    for status in (502, 503, 504):
        report = reports[f"test_status[{status}]"]
        assert report.failed and not hasattr(report, "wasxfail")
        assert any("a gateway did not let the request through" in t for _, t in report.sections)
    # pytest.xfail() in the body is pytest's own xfail, not turned into a failure
    assert reports["test_imperative_xfail"].wasxfail == "decided in the body"
    result.stdout.fnmatch_lines(["ERROR test_suite.py::test_both_markers - TypeError*"])
    # the same pair, xfail added by a fixture: refused at call, never an XFAIL or XPASS
    for name in (
        "test_xfail_added_at_run_time",
        "test_xfail_added_at_run_time_body_passes",
        # run=False: pytest would not run the body and call it an XFAIL "[NOTRUN]"
        "test_xfail_not_run_added_at_run_time",
    ):
        report = reports[name]
        assert report.failed and not hasattr(report, "wasxfail"), name
        assert "xfail was added to this test at run time" in str(report.longrepr)
    assert "use one of them" in result.stdout.str()


def _allure_statuses(pytester, *args):
    import json

    pytest.importorskip("allure_pytest")
    results = pytester.path / "allure-results"
    pytester.runpytest(*ARGS, f"--alluredir={results}", *args)
    statuses = {}
    for path in results.glob("*-result.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        statuses[data["fullName"].rsplit("#", 1)[-1]] = data["status"]
    return statuses


def test_allure_sees_the_final_verdict(pytester):
    """allure-pytest wraps the report hook; it must read the report after the verdict."""
    pytester.makepyfile(test_suite=SUITE)
    statuses = _allure_statuses(pytester)
    assert statuses["test_body_asserts"] == "skipped"  # XFAIL, not "failed"
    assert statuses["test_body_passes"] == "failed"     # XPASS(strict), not "passed"
    assert statuses["test_body_raises_something_else"] == "broken"
    assert statuses["test_setup_fails"] == "broken"


RERUN_A = '''
import pytest

@pytest.fixture(scope="module")
def resource():
    print("SETUP-A")
    yield
    with open("order.log", "a") as fh:
        fh.write("teardown-A\\n")

@pytest.mark.known_defect("BUG-10")
def test_reproduces(resource):
    with open("order.log", "a") as fh:
        fh.write("call-A\\n")
    assert 1 == 2
'''

RERUN_B = '''
def test_next():
    with open("order.log", "a") as fh:
        fh.write("call-B\\n")
'''


def test_rerunfailures_does_not_rerun_a_reproduction(pytester):
    """A reproduced defect is an xfail to pytest-rerunfailures: no re-run, and the module
    fixture of its module is finalized in its own module, before the next module runs."""
    pytest.importorskip("pytest_rerunfailures")
    pytester.makepyfile(test_a=RERUN_A, test_b=RERUN_B)
    result = pytester.runpytest(*ARGS, "--reruns", "1")
    result.assert_outcomes(xfailed=1, passed=1)
    assert "rerun" not in result.parseoutcomes()
    order = (pytester.path / "order.log").read_text().split()
    assert order == ["call-A", "teardown-A", "call-B"]


def test_the_marker_is_registered(pytester):
    result = pytester.runpytest("--markers", "-p", "no:asyncio", "-o", "addopts=")
    result.stdout.fnmatch_lines(["@pytest.mark.known_defect(id, reason=''):*"])
