"""poll_until / poll_until_sync: terminal detection, history, timeout, and the clock.

The timing cases run on a fake monotonic clock — sleeping advances it — so they assert
exact numbers instead of hoping a CI machine is fast enough.
"""

from __future__ import annotations

import asyncio
import pickle
import sys
import time

import pytest

from partest import polling
from partest.polling import PollResult, PollTick, PollTimeout, poll_until, poll_until_sync


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    async def async_sleep(self, seconds: float) -> None:
        self.sleep(seconds)


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(polling, "_monotonic", fake.monotonic)
    monkeypatch.setattr(polling, "_sleep", fake.sleep)
    monkeypatch.setattr(polling, "_async_sleep", fake.async_sleep)
    return fake


def sequence(*values):
    """A fetch that returns the given values, then repeats the last one."""
    it = iter(values)
    last = [None]

    def fetch():
        try:
            last[0] = next(it)
        except StopIteration:
            pass
        return last[0]

    return fetch


TERMINAL = {"DONE", "FAILED"}


@pytest.mark.asyncio
async def test_returns_the_terminal_value_with_the_states_seen(clock):
    fetch = sequence("QUEUED", "QUEUED", "RUNNING", "RUNNING", "DONE")
    result = await poll_until(fetch, lambda s: s in TERMINAL, timeout=60, interval=2)
    assert isinstance(result, PollResult)
    assert result.value == "DONE"
    assert result.history == ("QUEUED", "RUNNING", "DONE")
    assert result.state == "DONE"
    assert result.attempts == 5
    assert result.elapsed == pytest.approx(8.0)
    assert clock.sleeps == [2, 2, 2, 2]


@pytest.mark.asyncio
async def test_a_terminal_first_answer_does_not_sleep(clock):
    result = await poll_until(lambda: "DONE", lambda s: s in TERMINAL, timeout=10, interval=1)
    assert result.attempts == 1
    assert clock.sleeps == []


@pytest.mark.asyncio
async def test_state_maps_values_for_history_and_the_value_is_kept_whole(clock):
    fetch = sequence({"status": "RUNNING", "p": 1}, {"status": "RUNNING", "p": 2}, {"status": "DONE", "p": 3})
    result = await poll_until(
        fetch,
        lambda job: job["status"] in TERMINAL,
        timeout=60,
        interval=1,
        state=lambda job: job["status"],
    )
    assert result.history == ("RUNNING", "DONE")
    assert result.value == {"status": "DONE", "p": 3}


@pytest.mark.asyncio
async def test_timeout_carries_the_last_value_and_the_history(clock):
    fetch = sequence({"status": "QUEUED"}, {"status": "RUNNING"})
    with pytest.raises(PollTimeout) as caught:
        await poll_until(
            fetch,
            lambda job: job["status"] in TERMINAL,
            timeout=5,
            interval=2,
            state=lambda job: job["status"],
            what="job 7",
        )
    err = caught.value
    assert isinstance(err, AssertionError)  # a failed test, like sideeffects.wait_for
    # Not a TimeoutError: that is an OSError, and `except OSError` around network code
    # would swallow the poll's verdict.
    assert not isinstance(err, OSError)
    assert err.last == {"status": "RUNNING"}
    assert err.history == ("QUEUED", "RUNNING")
    assert err.timeout == 5
    message = str(err)
    assert "job 7" in message and "QUEUED → RUNNING" in message and "last state RUNNING" in message


@pytest.mark.asyncio
async def test_the_last_sleep_is_cut_to_the_deadline_and_one_fetch_happens_there(clock):
    calls = []

    def fetch():
        calls.append(clock.now)
        return "RUNNING"

    with pytest.raises(PollTimeout) as caught:
        await poll_until(fetch, lambda s: s in TERMINAL, timeout=5, interval=2)
    # 0, 2, 4, then a sleep of 1 (not 2) and a last look at exactly the deadline.
    assert clock.sleeps == [2, 2, 1]
    assert [t - 1000.0 for t in calls] == [0, 2, 4, 5]
    assert caught.value.attempts == 4
    assert caught.value.elapsed == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_a_job_finishing_in_the_final_sleep_is_not_reported_as_stuck(clock):
    def fetch():
        return "DONE" if clock.now - 1000.0 >= 5 else "RUNNING"

    result = await poll_until(fetch, lambda s: s in TERMINAL, timeout=5, interval=2)
    assert result.value == "DONE"


@pytest.mark.asyncio
async def test_async_fetch_and_async_on_tick_are_awaited(clock):
    ticks = []

    values = iter(["RUNNING", "DONE"])

    async def fetch():
        await asyncio.sleep(0)
        return next(values)

    async def on_tick(tick: PollTick):
        ticks.append((tick.attempt, tick.state, tick.elapsed))

    await poll_until(fetch, lambda s: s in TERMINAL, timeout=10, interval=3, on_tick=on_tick)
    assert ticks == [(1, "RUNNING", 0.0), (2, "DONE", 3.0)]


@pytest.mark.asyncio
async def test_an_error_from_fetch_is_not_swallowed(clock):
    def fetch():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await poll_until(fetch, lambda s: True, timeout=10, interval=1)


@pytest.mark.parametrize("timeout, interval", [(-1, 1), (10, -1), (-1, -1)])
def test_nonsense_timing_is_refused(timeout, interval):
    with pytest.raises(ValueError):
        poll_until_sync(lambda: 1, lambda v: True, timeout=timeout, interval=interval)


def test_sync_variant_has_the_same_contract(clock):
    ticks = []
    fetch = sequence(1, 1, 2, 3)
    result = poll_until_sync(fetch, lambda v: v == 3, timeout=60, interval=1.5, on_tick=ticks.append)
    assert result.value == 3
    assert result.history == (1, 2, 3)
    assert [t.attempt for t in ticks] == [1, 2, 3, 4]
    assert clock.sleeps == [1.5, 1.5, 1.5]

    with pytest.raises(PollTimeout) as caught:
        poll_until_sync(lambda: "x" * 500, lambda v: False, timeout=1, interval=1)
    assert len(str(caught.value)) < 1000  # a huge value is shortened, not dumped


def test_the_default_clock_is_monotonic():
    """Wall-clock time jumps with NTP and DST; a poll timed on it can end early or never."""
    assert polling._monotonic is time.monotonic
    assert polling._sleep is time.sleep
    assert polling._async_sleep is asyncio.sleep


@pytest.mark.asyncio
async def test_real_clock_smoke():
    """No fake clock: the defaults really are monotonic time and a real sleep."""
    fetch = sequence("RUNNING", "DONE")
    result = await poll_until(fetch, lambda s: s in TERMINAL, timeout=5, interval=0.05)
    assert result.value == "DONE"
    assert result.attempts == 2
    # One real 50 ms sleep: more than three ticks of the coarsest monotonic clock around
    # (about 16 ms on Windows), so time must have moved.
    assert 0 < result.elapsed < 5


@pytest.mark.parametrize("where", ["fetch", "state", "is_terminal", "on_tick"])
def test_an_error_propagates_unchanged_and_carries_the_poll_so_far(clock, where):
    calls = {"n": 0}

    def boom_on_third(stage):
        if where == stage and calls["n"] == 3:
            raise RuntimeError(f"boom in {stage}")

    def fetch():
        calls["n"] += 1
        boom_on_third("fetch")
        return f"S{calls['n']}"

    def state(value):
        boom_on_third("state")
        return value

    def is_terminal(value):
        boom_on_third("is_terminal")
        return False

    def on_tick(tick):
        boom_on_third("on_tick")

    with pytest.raises(RuntimeError, match=f"boom in {where}") as caught:
        poll_until_sync(
            fetch, is_terminal, timeout=60, interval=1, state=state, on_tick=on_tick, what="job 9"
        )
    exc = caught.value
    assert exc.poll_attempts == 3
    expected = ("S1", "S2") if where in ("fetch", "state") else ("S1", "S2", "S3")
    assert exc.poll_history == expected
    assert exc.poll_elapsed == pytest.approx(2.0)
    if sys.version_info >= (3, 11):
        assert any("while polling job 9: attempt 3" in note for note in exc.__notes__)


@pytest.mark.asyncio
async def test_async_errors_carry_the_poll_too(clock):
    async def fetch():
        raise ConnectionError("down")

    with pytest.raises(ConnectionError) as caught:
        await poll_until(fetch, lambda v: True, timeout=10, interval=1)
    assert caught.value.poll_attempts == 1
    assert caught.value.poll_history == ()


@pytest.mark.asyncio
async def test_async_is_terminal_and_state_are_awaited(clock):
    async def is_terminal(job):
        await asyncio.sleep(0)
        return job["status"] in TERMINAL

    async def state(job):
        return job["status"]

    fetch = sequence({"status": "RUNNING"}, {"status": "DONE"})
    result = await poll_until(fetch, is_terminal, timeout=10, interval=1, state=state)
    assert result.history == ("RUNNING", "DONE")
    assert result.attempts == 2


def test_a_long_history_is_shortened_in_the_message_and_kept_whole(clock):
    counter = iter(range(1000))
    with pytest.raises(PollTimeout) as caught:
        poll_until_sync(lambda: f"S{next(counter)}", lambda v: False, timeout=29, interval=1)
    err = caught.value
    assert len(err.history) == 30
    message = str(err)
    assert "S0 → S1 → S2 → S3 → S4 → … 20 more … → S25" in message
    assert "S12" not in message


def test_the_message_is_redacted_and_the_attributes_are_not(clock):
    value = {"status": "RUNNING", "token": "eyJhbGciOiJIUzI1NiJ9.secret-part"}
    with pytest.raises(PollTimeout) as caught:
        poll_until_sync(lambda: value, lambda v: False, timeout=1, interval=1)
    assert "secret-part" not in str(caught.value)
    assert caught.value.last == value


def test_poll_timeout_survives_pickling(clock):
    with pytest.raises(PollTimeout) as caught:
        poll_until_sync(sequence("A", "B"), lambda v: False, timeout=2, interval=1, what="job 3")
    copy = pickle.loads(pickle.dumps(caught.value))
    assert isinstance(copy, PollTimeout)
    assert copy.history == ("A", "B") and copy.attempts == 3
    assert str(copy) == str(caught.value)


def test_wait_for_now_looks_once_more_at_the_deadline(clock):
    """The fix that came with moving wait_for onto the shared loop."""
    from partest.sideeffects import wait_for

    looks = []

    def probe():
        looks.append(clock.now - 1000.0)
        return None

    with pytest.raises(AssertionError, match="import did not happen within 5s"):
        wait_for(probe, timeout=5, interval=2, description="import")
    assert looks == [0, 2, 4, 5]
    assert clock.sleeps == [2, 2, 1]


# --- what a message may show -------------------------------------------------------


def _timeout_message(value):
    with pytest.raises(PollTimeout) as caught:
        poll_until_sync(lambda: value, lambda v: False, timeout=0, interval=1)
    return str(caught.value)


def test_a_model_with_a_token_is_shown_by_its_repr_masked():
    from dataclasses import dataclass

    from pydantic import BaseModel

    class Session(BaseModel):
        access_token: str
        status: str

    @dataclass
    class Job:
        status: str
        token: str

    model = _timeout_message(Session(access_token="SECRET-1", status="RUNNING"))
    assert "SECRET-1" not in model
    assert "Session(" in model and "RUNNING" in model
    record = _timeout_message(Job(status="RUNNING", token="SECRET-2"))
    assert "SECRET-2" not in record and "Job(" in record


def test_a_body_kept_as_a_string_is_masked():
    message = _timeout_message('{"status": "RUNNING", "token": "SECRET-3"}')
    assert "SECRET-3" not in message and "RUNNING" in message


def test_nesting_deeper_than_the_limit_is_not_printed():
    deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"secretish": "DEEP-VALUE"}}}}}}}}
    message = _timeout_message(deep)
    assert "DEEP-VALUE" not in message and "…" in message


def test_mapping_subclasses_and_namedtuples_keep_their_type_in_the_message():
    import collections

    Point = collections.namedtuple("Point", "status token")
    ordered = collections.OrderedDict(status="RUNNING", token="SECRET-4")
    message = _timeout_message([Point("RUNNING", "SECRET-5"), ordered])
    assert "Point(" in message and "OrderedDict" in message
    assert "SECRET-4" not in message and "SECRET-5" not in message


def test_wait_for_with_a_negative_timeout_looks_once(clock):
    from partest.sideeffects import wait_for

    looks = []
    with pytest.raises(AssertionError, match=r"import did not happen within -1s"):
        wait_for(lambda: looks.append(1), timeout=-1, interval=1, description="import")
    assert looks == [1]


def test_wait_for_masks_its_message_and_keeps_repr_form(clock):
    from partest.sideeffects import wait_for

    with pytest.raises(AssertionError) as caught:
        wait_for(lambda: {"token": "SECRET-6", "ok": False} and "", timeout=0, interval=1)
    assert "last observation: ''" in str(caught.value)
    with pytest.raises(AssertionError) as caught:
        wait_for(lambda: [{"token": "SECRET-7"}][:0] or None, timeout=0, interval=1)
    assert "last observation: None" in str(caught.value)


def test_wait_for_probe_errors_carry_the_poll(clock):
    from partest.sideeffects import wait_for

    calls = {"n": 0}

    def probe():
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConnectionError("down")
        return None

    with pytest.raises(ConnectionError) as caught:
        wait_for(probe, timeout=10, interval=1, description="import")
    assert caught.value.poll_attempts == 2
    assert caught.value.poll_history == (None,)
