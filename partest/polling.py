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

    async def fetch_job():
        await tokens.refresh_if_needed()          # a long poll outlives a token: refresh HERE
        return await api.make_request("GET", "/jobs", add_url1=f"/{job_id}",
                                      expected_status_code=200, type=types.request_default)

    result = await poll_until(
        fetch_job,
        lambda job: job["status"] in {"DONE", "FAILED"},
        timeout=300, interval=2,
        state=lambda job: job["status"],
        on_tick=lambda tick: log.info("job %s: %s", job_id, tick.state),
        what=f"job {job_id}",
    )
    assert result.value["status"] == "DONE", result.history

**Anything the next fetch needs belongs in** ``fetch``. ``on_tick`` runs *after* a fetch
has succeeded, so a token refreshed there arrives one request too late: the first fetch
after expiry fails with 401 before ``on_tick`` ever sees it. ``on_tick`` is for observing —
logging, attaching, counting.

On timeout :class:`PollTimeout` is raised with the last value, the states seen and the
time spent. :func:`partest.sideeffects.wait_for` is the small form built on the same loop —
one synchronous probe, "truthy means done"; this is the form for a state machine you need
the path of.

An exception from ``fetch``, ``state``, ``is_terminal`` or ``on_tick`` is not swallowed: a
failing request is a finding of its own, not a reason to keep waiting. It propagates
unchanged, carrying the poll so far — ``poll_history``, ``poll_attempts``,
``poll_elapsed`` as attributes, and on Python 3.11+ a note shown under the traceback.

``is_terminal``, ``state`` and ``on_tick`` may each be plain or async in
:func:`poll_until`; so may ``fetch``.

Timing: the clock is :func:`time.monotonic`; between two fetches the loop sleeps
``interval`` and never past the deadline, and one last fetch is made *at* the deadline,
so a job that finishes during the final sleep is not reported as stuck. Nothing else
waits — the total is ``timeout`` plus however long the last fetch takes.

Messages carry values a test fetched, and values fetched from an API can carry tokens.
Everything put into a message is redacted by the rule of every other channel of the package
(see the enterprise notes) — dicts and lists by key, a string leaf by the narrow patterns,
anything else by masking its ``repr`` as free text — followed no deeper than
:data:`MESSAGE_DEPTH` levels, and shortened. The attributes (``last``, ``history``,
``poll_history``) keep the originals: reporting them is the caller's responsibility.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, List, Optional, Tuple, TypeVar, Union

from partest.redact import _is_blank, _is_secret_key, _mark_masked, _scrub, _scrub_text

T = TypeVar("T")

_REPR_LIMIT = 200
#: How many states from each end of the history a timeout message shows.
MESSAGE_HISTORY_EDGE = 5

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


class PollTimeout(AssertionError):
    """The condition did not hold within ``timeout``.

    An ``AssertionError``, so pytest reports a failed test — as it does for
    :func:`partest.sideeffects.wait_for`. Deliberately *not* a ``TimeoutError``: that is an
    ``OSError``, and a network ``except OSError`` around the poll would swallow it.

    Carries what a reader needs to tell "slow" from "stuck": ``last`` (the last value
    fetched), ``history`` (states seen, repeats collapsed), ``elapsed``, ``attempts`` and
    the ``timeout`` that was set. The message shows a shortened, redacted history.

    **The attributes are not redacted.** ``last`` is the value as fetched, and without
    ``state=`` every entry of ``history`` is a whole response body — tokens included, if
    the API returns them. Putting the attributes into a report or an attachment is the
    caller's decision and the caller's responsibility; the message is the safe part.
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
        self.history = tuple(history)
        self.elapsed = elapsed
        self.attempts = attempts
        self.timeout = timeout
        last_state = history[-1] if history else None
        super().__init__(
            f"{_scrub_text(what)} did not reach a terminal state within {timeout:g} s "
            f"({elapsed:.1f} s, {attempts} attempt{'s' if attempts != 1 else ''}); "
            f"last state {_short(last_state)}; seen: {_history_text(self.history)}; "
            f"last value: {_short(last)}"
        )
        _mark_masked(self)  # every part of the message above is masked

    def __reduce__(self):
        return (
            _rebuild_timeout,
            (self.what, self.last, self.history, self.elapsed, self.attempts, self.timeout),
        )


def _rebuild_timeout(what, last, history, elapsed, attempts, timeout) -> PollTimeout:
    return PollTimeout(
        what=what, last=last, history=history, elapsed=elapsed, attempts=attempts, timeout=timeout
    )


#: How deep a message follows nested dicts and lists before printing ``…`` instead.
MESSAGE_DEPTH = 6



class _Shown:
    """A leaf already turned into safe text; its repr is that text."""

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text

    def __repr__(self) -> str:
        return self.text


def _sanitize(value: Any, depth: int, *, top: bool = True) -> Any:
    """A copy safe to print: secrets masked, depth bounded, nothing echoed raw.

    The package's one rule (``partest.redact``): plain ``dict`` and ``list`` (and a plain
    ``tuple``) are walked, a value under a secret key — in any spelling, ``client-secret``
    too — is ``***``; a string inside them gets the narrow patterns (URL credentials, signed
    query values, Bearer/Basic, a JWT); a string on its own is free text. Everything else — a
    ``Mapping`` subclass, a namedtuple, a model, a dataclass — keeps its own ``repr``, masked
    as free text, so its type stays visible and its secrets do not.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _scrub_text(value) if top else _scrub(value)
    if depth <= 0:
        return _Shown("…")
    if type(value) is dict:
        return {
            k: ("***" if _is_secret_key(k) and not _is_blank(value[k])
                else _sanitize(value[k], depth - 1, top=False))
            for k in value
        }
    if type(value) is list:
        return [_sanitize(v, depth - 1, top=False) for v in value]
    if type(value) is tuple:
        return tuple(_sanitize(v, depth - 1, top=False) for v in value)
    return _Shown(_scrub_text(repr(value)))


def _masked(value: Any, *, quote_strings: bool) -> str:
    try:
        safe = _sanitize(value, MESSAGE_DEPTH)
        if isinstance(safe, str) and not quote_strings:
            return safe
        return repr(safe)
    except Exception:  # an odd value must not turn a timeout into a different error
        return f"<{type(value).__name__}>"


def _shorten(text: str) -> str:
    if len(text) > _REPR_LIMIT:
        return text[: _REPR_LIMIT - 3] + "..."
    return text


def _short(value: Any) -> str:
    """Redacted and shortened text of a value, for a message; a string is shown bare."""
    return _shorten(_masked(value, quote_strings=False))


def _short_repr(value: Any) -> str:
    """Like :func:`_short`, but in ``repr`` form: a string keeps its quotes."""
    return _shorten(_masked(value, quote_strings=True))


def _history_text(history: Tuple[Any, ...], edge: int = MESSAGE_HISTORY_EDGE) -> str:
    if not history:
        return "nothing"
    if len(history) <= 2 * edge + 1:
        shown = [_short(s) for s in history]
    else:
        hidden = len(history) - 2 * edge
        shown = (
            [_short(s) for s in history[:edge]]
            + [f"… {hidden} more …"]
            + [_short(s) for s in history[-edge:]]
        )
    return " → ".join(shown)


def _validate(timeout: float, interval: float) -> None:
    if timeout < 0:
        raise ValueError(f"timeout must be >= 0, got {timeout!r}")
    if interval < 0:
        raise ValueError(f"interval must be >= 0, got {interval!r}")


class _Tracker:
    """The bookkeeping shared by the async and the sync loop."""

    def __init__(self) -> None:
        self.started = _monotonic()
        self.history: List[Any] = []
        self.attempts = 0
        self.last: Any = None

    def observe(self, value: Any, state: Any) -> PollTick:
        self.last = value
        if not self.history or not _same(self.history[-1], state):
            self.history.append(state)
        return PollTick(self.attempts, value, state, self.elapsed())

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

    def annotate(self, exc: BaseException, what: str) -> None:
        """Attach the poll so far to an exception that is about to propagate.

        ``poll_history`` holds the states as recorded — unredacted, and whole response
        bodies when no ``state=`` was given; the note shows the redacted, shortened form.
        """
        history = tuple(self.history)
        elapsed = self.elapsed()
        for name, value in (
            ("poll_history", history),
            ("poll_attempts", self.attempts),
            ("poll_elapsed", elapsed),
        ):
            try:
                setattr(exc, name, value)
            except Exception:  # exceptions with __slots__ or read-only attributes
                pass
        add_note = getattr(exc, "add_note", None)
        if add_note is not None:  # Python 3.11+
            try:
                add_note(
                    f"while polling {_scrub_text(what)}: attempt {self.attempts}, "
                    f"{elapsed:.1f} s in; "
                    f"seen: {_history_text(history)}"
                )
            except Exception:
                pass


def _same(a: Any, b: Any) -> bool:
    try:
        return bool(a == b)
    except Exception:
        return a is b


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def poll_until(
    fetch: Callable[[], Union[T, Awaitable[T]]],
    is_terminal: Callable[[T], Union[bool, Awaitable[bool]]],
    *,
    timeout: float,
    interval: float,
    on_tick: Optional[Callable[[PollTick], Any]] = None,
    state: Optional[Callable[[T], Any]] = None,
    what: str = "polled value",
) -> PollResult[T]:
    """Call ``fetch`` until ``is_terminal(value)`` holds; raise :class:`PollTimeout` if it never does.

    ``fetch`` takes no arguments. ``fetch``, ``is_terminal``, ``state`` and ``on_tick`` may
    each be a plain or an async callable. ``state`` maps a value to what ``history``
    records; without it the value itself is recorded. ``on_tick`` receives a
    :class:`PollTick` after every successful fetch — for observing; anything the *next*
    fetch needs, such as a fresh token, belongs inside ``fetch``. ``what`` names the thing
    in messages.
    """
    _validate(timeout, interval)
    tracker = _Tracker()
    deadline = tracker.started + timeout
    while True:
        try:
            tracker.attempts += 1
            value = await _maybe_await(fetch())
            current = value if state is None else await _maybe_await(state(value))
            tick = tracker.observe(value, current)
            if on_tick is not None:
                await _maybe_await(on_tick(tick))
            done = bool(await _maybe_await(is_terminal(value)))
        except Exception as exc:
            tracker.annotate(exc, what)
            raise
        if done:
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
    tracker = _Tracker()
    deadline = tracker.started + timeout
    while True:
        try:
            tracker.attempts += 1
            value = fetch()
            current = value if state is None else state(value)
            tick = tracker.observe(value, current)
            if on_tick is not None:
                on_tick(tick)
            done = bool(is_terminal(value))
        except Exception as exc:
            tracker.annotate(exc, what)
            raise
        if done:
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
