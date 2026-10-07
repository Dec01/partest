"""Poll until something reaches a terminal state — and say what was seen on the way.

Every suite that starts a background job ends up writing the same loop: fetch, compare
with a set of terminal states, sleep, give up after a while. Each copy gets one detail
wrong — wall-clock time instead of a monotonic clock, a sleep that overshoots the
deadline, a timeout that returns the last non-terminal value as if it were the answer, or
a message that says "timed out" and nothing about where the job got stuck. The last one
is the expensive one: "did not finish in 300 s" and "sat in QUEUED for 300 s" are two
different findings, and only the history tells them apart.

::

    from partest.polling import poll_until

    result = await poll_until(
        lambda: api.make_request("GET", "/jobs", add_url1=f"/{job_id}",
                                 expected_status_code=200, type=types.request_default),
        lambda job: job["status"] in {"DONE", "FAILED"},
        timeout=300, interval=2,
        state=lambda job: job["status"],
        what=f"job {job_id}",
    )
    assert result.value["status"] == "DONE", result.history

On timeout :class:`PollTimeout` is raised with the last value, the states seen and the
time spent. :func:`partest.sideeffects.wait_for` stays the small form — one synchronous
probe, "truthy means done"; this is the form for a state machine you need the path of. An exception from ``fetch`` is not swallowed: a failing request is a failure
of its own, not a reason to keep waiting.

Timing: the clock is :func:`time.monotonic`; between two fetches the loop sleeps
``interval`` and never past the deadline, and one last fetch is made *at* the deadline,
so a job that finishes during the final sleep is not reported as stuck. Nothing else
waits — the total is ``timeout`` plus however long the last fetch takes.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, List, Optional, Tuple, TypeVar, Union

T = TypeVar("T")

_REPR_LIMIT = 200

# Indirections, so a test can drive the loop on a fake clock without patching the
# event loop's own time source.
_monotonic = time.monotonic
_sleep = time.sleep
_async_sleep = asyncio.sleep


@dataclass(frozen=True)
class PollTick:
    """One observation, as handed to ``on_tick``.

    ``attempt`` counts from 1; ``elapsed`` is seconds since polling began, measured on the
    monotonic clock; ``state`` is ``state(value)``, or the value itself without ``state=``.
    """

    attempt: int
    value: Any
    state: Any
    elapsed: float


@dataclass(frozen=True)
class PollResult(Generic[T]):
    """What :func:`poll_until` saw before the condition held.

    ``history`` is the sequence of states observed, with consecutive repeats collapsed:
    ``("QUEUED", "RUNNING", "DONE")`` after forty fetches. ``attempts`` is how many
    fetches it took, ``elapsed`` the seconds spent.
    """

    value: T
    history: Tuple[Any, ...]
    elapsed: float
    attempts: int

    @property
    def state(self) -> Any:
        """The terminal state — the last entry of ``history``."""
        return self.history[-1] if self.history else None


class PollTimeout(AssertionError, TimeoutError):
    """The condition did not hold within ``timeout``.

    An ``AssertionError``, so pytest reports a failed test — as it does for
    :func:`partest.sideeffects.wait_for` — and a ``TimeoutError``, so code that waits on
    several things can catch the timeout by what it is.

    Carries what a reader needs to tell "slow" from "stuck": ``last`` (the last value
    fetched), ``history`` (states seen, repeats collapsed), ``elapsed``, ``attempts`` and
    the ``timeout`` that was set.
    """

    def __init__(
        self,
        *,
        what: str,
        last: Any,
        history: Tuple[Any, ...],
        elapsed: float,
        attempts: int,
        timeout: float,
    ) -> None:
        self.what = what
        self.last = last
        self.history = history
        self.elapsed = elapsed
        self.attempts = attempts
        self.timeout = timeout
        seen = " → ".join(_short(s) for s in history) if history else "nothing"
        super().__init__(
            f"{what} did not reach a terminal state within {timeout:g} s "
            f"({elapsed:.1f} s, {attempts} attempt{'s' if attempts != 1 else ''}); "
            f"last state {_short(history[-1]) if history else _short(None)}; seen: {seen}; "
            f"last value: {_short(last)}"
        )


def _short(value: Any) -> str:
    text = value if isinstance(value, str) else repr(value)
    if len(text) > _REPR_LIMIT:
        return text[: _REPR_LIMIT - 3] + "..."
    return text


def _validate(timeout: float, interval: float) -> None:
    if timeout < 0:
        raise ValueError(f"timeout must be >= 0, got {timeout!r}")
    if interval <= 0:
        raise ValueError(f"interval must be > 0, got {interval!r}")


class _Tracker:
    """The bookkeeping shared by the async and the sync loop."""

    def __init__(self, state: Optional[Callable[[Any], Any]]) -> None:
        self._state = state
        self.started = _monotonic()
        self.history: List[Any] = []
        self.attempts = 0
        self.last: Any = None

    def observe(self, value: Any) -> PollTick:
        self.attempts += 1
        self.last = value
        current = self._state(value) if self._state is not None else value
        if not self.history or not _same(self.history[-1], current):
            self.history.append(current)
        return PollTick(self.attempts, value, current, self.elapsed())

    def elapsed(self) -> float:
        return _monotonic() - self.started

    def result(self) -> PollResult:
        return PollResult(self.last, tuple(self.history), self.elapsed(), self.attempts)

    def timeout(self, what: str, timeout: float) -> PollTimeout:
        return PollTimeout(
            what=what,
            last=self.last,
            history=tuple(self.history),
            elapsed=self.elapsed(),
            attempts=self.attempts,
            timeout=timeout,
        )


def _same(a: Any, b: Any) -> bool:
    try:
        return bool(a == b)
    except Exception:
        return a is b


async def poll_until(
    fetch: Callable[[], Union[T, Awaitable[T]]],
    is_terminal: Callable[[T], bool],
    *,
    timeout: float,
    interval: float,
    on_tick: Optional[Callable[[PollTick], Any]] = None,
    state: Optional[Callable[[T], Any]] = None,
    what: str = "polled value",
) -> PollResult[T]:
    """Call ``fetch`` until ``is_terminal(value)`` holds; raise :class:`PollTimeout` if it never does.

    ``fetch`` takes no arguments and may be a coroutine function or a plain one.
    ``on_tick`` (plain or async) receives a :class:`PollTick` after every fetch — log it,
    attach it, refresh a token there. ``state`` maps a value to what ``history`` records;
    without it the value itself is recorded. ``what`` names the thing in the timeout
    message.
    """
    _validate(timeout, interval)
    tracker = _Tracker(state)
    deadline = tracker.started + timeout
    while True:
        value = fetch()
        if inspect.isawaitable(value):
            value = await value
        tick = tracker.observe(value)
        if on_tick is not None:
            outcome = on_tick(tick)
            if inspect.isawaitable(outcome):
                await outcome
        if is_terminal(value):
            return tracker.result()
        remaining = deadline - _monotonic()
        if remaining <= 0:
            raise tracker.timeout(what, timeout)
        await _async_sleep(min(interval, remaining))


def poll_until_sync(
    fetch: Callable[[], T],
    is_terminal: Callable[[T], bool],
    *,
    timeout: float,
    interval: float,
    on_tick: Optional[Callable[[PollTick], Any]] = None,
    state: Optional[Callable[[T], Any]] = None,
    what: str = "polled value",
) -> PollResult[T]:
    """:func:`poll_until` for synchronous code — same contract, ``time.sleep`` between fetches."""
    _validate(timeout, interval)
    tracker = _Tracker(state)
    deadline = tracker.started + timeout
    while True:
        value = fetch()
        tick = tracker.observe(value)
        if on_tick is not None:
            on_tick(tick)
        if is_terminal(value):
            return tracker.result()
        remaining = deadline - _monotonic()
        if remaining <= 0:
            raise tracker.timeout(what, timeout)
        _sleep(min(interval, remaining))


__all__ = [
    "PollResult",
    "PollTick",
    "PollTimeout",
    "poll_until",
    "poll_until_sync",
]
