"""poll_until / poll_until_sync: terminal detection, history, timeout, and the clock.

The timing cases run on a fake monotonic clock — sleeping advances it — so they assert
exact numbers instead of hoping a CI machine is fast enough.
"""

from __future__ import annotations

import asyncio

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
    assert isinstance(err, TimeoutError)
    assert isinstance(err, AssertionError)  # a failed test, like sideeffects.wait_for
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


@pytest.mark.parametrize("timeout, interval", [(-1, 1), (10, 0), (10, -1)])
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


@pytest.mark.asyncio
async def test_real_clock_smoke():
    """No fake clock: the defaults really are monotonic time and a real sleep."""
    fetch = sequence("RUNNING", "DONE")
    result = await poll_until(fetch, lambda s: s in TERMINAL, timeout=2, interval=0.01)
    assert result.value == "DONE"
    assert 0 < result.elapsed < 2
