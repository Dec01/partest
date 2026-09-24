"""The third outcome of a check: «not measured».

The returned defect these tests guard against was caught four times in one day, in four
unrelated checks, and every time it looked like a pass: a comparison ran over data nobody
had collected. The worst shape is an aggregate — a difference, a share or a mean over an
empty sample is a constant by construction, so the assertion cannot fail even in
principle.

``test_the_old_form_is_green_on_data_that_was_never_collected`` is that defect, kept alive
on purpose: it passes, and it proves nothing. The test right below it puts the same
comparison through :func:`partest.reporting.check_measured` and shows the run refusing to
call it a pass.
"""

from __future__ import annotations

import types
from contextlib import contextmanager

import pytest

from partest import pytest_plugin as pp
from partest.reporting import (
    NotMeasured,
    NotMeasuredWarning,
    Premise,
    check_eq,
    check_measured,
    mark_not_measured,
    measurable,
    not_measured_records,
    reset_not_measured,
)
from partest.reporting import attach as attach_mod
from partest.reporting import measured as measured_mod


@pytest.fixture(autouse=True)
def clean_ledger():
    """The ledger is per-process; these tests must not leak into the run's summary."""
    reset_not_measured()
    yield
    reset_not_measured()


def growth(before: dict, after: dict) -> int:
    """A difference of two samples: zero when both are empty, zero when all is well."""
    return sum(after.values()) - sum(before.values())


# --- the defect, and its return -------------------------------------------


def test_the_old_form_is_green_on_data_that_was_never_collected():
    """Two plain checks over samples that were never taken. Both pass. Nothing was tested."""
    before, after = {}, {}  # the source was unreachable, so nothing got sampled
    check_eq(growth(before, after), 0, field="growth")
    assert not_measured_records() == ()


def test_the_same_comparison_is_not_measured_when_the_sample_is_empty():
    before, after = {}, {}
    ran = []

    with pytest.warns(NotMeasuredWarning) as warned:
        measured = check_measured(
            measurable(before, what="baseline") & measurable(after, what="current"),
            lambda: ran.append(check_eq(growth(before, after), 0, field="growth")),
            what="growth of the sampled counters",
        )

    assert measured is False
    assert ran == [], "the assertion must not run on data that was never collected"
    record = not_measured_records()[-1]
    assert record.what == "growth of the sampled counters"
    assert "baseline" in record.reason and "construction" in record.reason
    assert "NOT MEASURED" in str(warned[0].message)


def test_the_same_comparison_is_measured_once_the_sample_exists():
    before, after = {"q": 1}, {"q": 1}
    measured = check_measured(
        measurable(before, what="baseline") & measurable(after, what="current"),
        lambda: check_eq(growth(before, after), 0, field="growth"),
        what="growth of the sampled counters",
    )
    assert measured is True
    assert not_measured_records() == ()


def test_a_real_regression_still_fails_under_the_same_premise():
    before, after = {"q": 1}, {"q": 5}
    with pytest.raises(AssertionError):
        check_measured(
            measurable(before, what="baseline") & measurable(after, what="current"),
            lambda: check_eq(growth(before, after), 0, field="growth"),
            what="growth of the sampled counters",
        )
    assert not_measured_records() == (), "a failure is not an unmeasured assertion"


# --- the premise cannot be forgotten --------------------------------------


def test_a_plain_premise_without_a_reason_is_refused_even_when_it_holds():
    """Eagerly, on the green path: otherwise the gap ships and shows up only on a bad day."""
    with pytest.raises(ValueError) as err:
        check_measured(True, lambda: None, what="anything")
    assert "reason=" in str(err.value)


def test_a_plain_premise_with_a_reason_is_enough():
    with pytest.warns(NotMeasuredWarning):
        measured = check_measured(
            False,
            lambda: None,
            what="queue drain",
            reason="the broker was not reachable from this runner",
        )
    assert measured is False
    assert not_measured_records()[-1].reason.startswith("the broker")


def test_what_is_mandatory_too():
    for bad in ("", "   ", None):
        with pytest.raises(ValueError):
            check_measured(True, lambda: None, what=bad, reason="r")


def test_the_assertion_must_be_callable():
    with pytest.raises(TypeError):
        check_measured(True, "check_eq(a, b)", what="x", reason="r")


# --- premises --------------------------------------------------------------


def test_measurable_tells_a_missing_sample_from_an_empty_one():
    missing = measurable(None, what="vendored bundle")
    empty = measurable([], what="vendored bundle")
    assert not missing and not empty
    assert "never collected" in missing.reason
    assert "0 item(s)" in empty.reason
    assert "construction" in empty.reason


def test_measurable_can_demand_more_than_one_observation():
    assert measurable([1], what="samples", min_size=2).ok is False
    assert measurable([1, 2], what="samples", min_size=2).ok is True


def test_measurable_does_not_consume_what_it_cannot_count():
    stream = iter([1, 2, 3])
    assert measurable(stream, what="stream").ok is True
    assert list(stream) == [1, 2, 3]


def test_a_premise_that_does_not_hold_cannot_be_built_without_a_reason():
    with pytest.raises(ValueError):
        Premise(False)
    assert Premise(True).reason == ""


def test_premises_combine_and_the_failing_one_explains_itself():
    good = measurable([1], what="baseline")
    bad = measurable([], what="current")
    assert (good & bad).reason == bad.reason
    assert (bad & good).reason == bad.reason
    assert bool(good & measurable([2], what="current")) is True
    assert isinstance(good & True, Premise)


# --- what the report shows -------------------------------------------------


class _FakeAllure:
    """Enough of allure to see what a report reader would see."""

    def __init__(self):
        self.steps = []
        self.attachments = []
        self.tags = []
        self.dynamic = types.SimpleNamespace(tag=self.tags.append)

    @contextmanager
    def step(self, title):
        self.steps.append(title)
        yield

    def attach(self, body, name=None, attachment_type=None):
        self.attachments.append((name, body))


@pytest.fixture
def fake_allure(monkeypatch):
    fake = _FakeAllure()
    monkeypatch.setattr(measured_mod, "allure", fake)
    monkeypatch.setattr(attach_mod, "allure", fake)
    monkeypatch.setattr(attach_mod, "AttachmentType", types.SimpleNamespace(JSON="json", TEXT="text"))
    return fake


def test_the_report_tells_the_three_outcomes_apart(fake_allure):
    check_measured(True, lambda: None, what="a measurable thing", reason="unused")
    measured_titles = list(fake_allure.steps)

    with pytest.warns(NotMeasuredWarning):
        check_measured(False, lambda: None, what="an unmeasurable thing", reason="no data")

    assert measured_titles == ["Measured: a measurable thing"]
    assert fake_allure.steps[-1] == "NOT MEASURED: an unmeasurable thing — no data"

    name, body = fake_allure.attachments[-1]
    assert name == "not_measured:an unmeasurable thing"
    assert '"passed": null' in body, "a missing measurement must not read as passed"
    assert '"outcome": "not_measured"' in body
    assert "no data" in body
    assert fake_allure.tags == ["not-measured"], "the test itself is flagged, not only a step"


def test_a_measured_failure_keeps_the_ordinary_check_attachment(fake_allure):
    with pytest.raises(AssertionError):
        check_measured(True, lambda: check_eq(1, 2, field="growth"), what="growth", reason="x")
    names = [name for name, _ in fake_allure.attachments]
    assert "check:growth" in names
    assert not any(name.startswith("not_measured:") for name in names)


def test_mark_not_measured_stands_on_its_own(fake_allure):
    with pytest.warns(NotMeasuredWarning):
        mark_not_measured(what="dependency audit", reason="the audited file was not found")
    assert not_measured_records() == (
        NotMeasured(what="dependency audit", reason="the audited file was not found"),
    )
    assert fake_allure.steps[-1].startswith("NOT MEASURED: dependency audit")


def test_mark_not_measured_demands_a_reason():
    with pytest.raises(ValueError):
        mark_not_measured(what="dependency audit", reason="")


def test_the_primitive_survives_without_allure(monkeypatch):
    monkeypatch.setattr(measured_mod, "allure", None)
    monkeypatch.setattr(attach_mod, "allure", None)
    with pytest.warns(NotMeasuredWarning):
        assert check_measured(False, lambda: None, what="x", reason="no allure here") is False
    assert not_measured_records()[-1].what == "x"


# --- the run says it out loud ----------------------------------------------


class _FakeTerminal:
    def __init__(self):
        self.lines = []

    def write_sep(self, sep, title):
        self.lines.append(f"{sep} {title}")

    def write_line(self, line):
        self.lines.append(line)


def test_the_terminal_summary_is_silent_when_everything_was_measured():
    term = _FakeTerminal()
    pp.pytest_terminal_summary(term, 0, None)
    assert term.lines == []


def test_the_terminal_summary_names_what_was_not_measured():
    with pytest.warns(NotMeasuredWarning):
        mark_not_measured(what="dead letters", reason="bus unavailable")
        mark_not_measured(what="dead letters", reason="bus unavailable")
    term = _FakeTerminal()
    pp.pytest_terminal_summary(term, 0, None)
    text = "\n".join(term.lines)
    assert "NOT MEASURED" in text
    assert "dead letters (x2): bus unavailable" in text


def test_the_session_starts_with_an_empty_ledger():
    with pytest.warns(NotMeasuredWarning):
        mark_not_measured(what="leftover", reason="from a previous session")
    session = types.SimpleNamespace(config=types.SimpleNamespace())
    pp.pytest_sessionstart(session)
    assert not_measured_records() == ()


def test_the_new_names_are_exported():
    import partest.reporting as ah

    for name in (
        "check_measured",
        "measurable",
        "mark_not_measured",
        "not_measured_records",
        "reset_not_measured",
        "attach_not_measured",
        "Premise",
        "NotMeasured",
        "NotMeasuredWarning",
    ):
        assert name in ah.__all__
        assert getattr(ah, name, None) is not None
