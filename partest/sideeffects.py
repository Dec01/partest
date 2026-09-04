"""Observing what a write left outside the HTTP response.

A 2xx says the request was accepted. It does not say a file reached the object store,
an event reached the broker, or a row reached the database. Checking those means
reaching for a surface the API does not expose, and that raises two problems this
module exists to solve.

**The first is honesty.** A suite that cannot reach the object store usually skips the
whole test, which quietly deletes the HTTP assertions too. Here an unreachable surface
is *held*: the response contract is still asserted, and the missing observation is
recorded and reported. A held surface is a visible gap, not a green test.

**The second is pretending.** An in-memory fake proves nothing about a real broker, so
:class:`InMemoryObjectStore` and :class:`InMemoryBus` deliberately refuse to look like
the real thing: anything observed through them is reported as ``simulated``. Develop the
test against a fake, swap in a real probe when credentials arrive, and the report tells
you which one ran.

Read-only by construction. The database probe rejects anything that is not a single
SELECT, brokers are polled without committing an offset, and object stores are only
ever read. Cleanup belongs to the API and the tracking registry, never here.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

# --- Held surfaces --------------------------------------------------------


@dataclass
class Held:
    """A surface that could not be observed, and why."""

    surface: str
    reason: str

    def __str__(self) -> str:
        return f"{self.surface}: {self.reason}"


_held: List[Held] = []


def hold(surface: str, reason: str) -> Held:
    """Record that a surface could not be checked, and carry on.

    Use instead of skipping the test: the HTTP contract assertions before this point
    keep their value, and the gap stays visible in the report rather than vanishing.
    """
    entry = Held(surface, reason)
    _held.append(entry)
    try:
        import allure

        with allure.step(f"HOLD {surface} — {reason}"):
            pass
    except Exception:
        pass
    return entry


def held_surfaces() -> List[Held]:
    return list(_held)


def reset_held() -> None:
    _held.clear()


# --- Response contract (surface I1) ---------------------------------------


def assert_locator(
    body: Any,
    *,
    field: str,
    prefix: Optional[str] = None,
    pattern: Optional[str] = None,
) -> str:
    """Check the locator an async create returns, before chasing the artefact itself.

    This is the cheapest real evidence available and it needs no credentials: the API
    told you where it put the thing. Assert that before deciding whether an object
    store check is even worth holding for.
    """
    if not isinstance(body, dict) or field not in body:
        raise AssertionError(f"response has no locator field {field!r}: {body!r}")
    value = body[field]
    if not isinstance(value, str) or not value:
        raise AssertionError(f"locator {field!r} is not a non-empty string: {value!r}")
    if prefix is not None and not value.startswith(prefix):
        raise AssertionError(f"locator {value!r} does not start with {prefix!r}")
    if pattern is not None and not re.search(pattern, value):
        raise AssertionError(f"locator {value!r} does not match {pattern!r}")
    return value


def assert_status_enum(body: Any, *, field: str, allowed: Sequence[str]) -> str:
    """A status that is not in its own enum is a contract break, not a slow pipeline."""
    if not isinstance(body, dict) or field not in body:
        raise AssertionError(f"response has no status field {field!r}: {body!r}")
    value = body[field]
    if value not in allowed:
        raise AssertionError(f"status {value!r} not in {list(allowed)}")
    return value


# --- Polling (surface I5) -------------------------------------------------


def wait_for(
    probe: Callable[[], Any],
    *,
    timeout: float = 30.0,
    interval: float = 1.0,
    description: str = "condition",
) -> Any:
    """Poll until ``probe`` returns something truthy, or fail with what was seen last.

    Asynchronous pipelines need a wait, and a bare ``sleep`` makes a suite slow when it
    passes and confusing when it fails. The timeout message carries the last value so
    the failure says what actually happened.
    """
    deadline = time.monotonic() + timeout
    last: Any = None
    while True:
        last = probe()
        if last:
            return last
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"{description} did not happen within {timeout:g}s; last observation: {last!r}"
            )
        time.sleep(interval)


# --- Probes ---------------------------------------------------------------


@dataclass
class Observation:
    """What a probe saw, and whether it was the real system."""

    surface: str
    found: bool
    detail: Any = None
    simulated: bool = False

    def require(self, what: str = "side effect") -> "Observation":
        """Fail unless the effect was observed; say so loudly when it was simulated."""
        if not self.found:
            raise AssertionError(f"{what} not observed on {self.surface}: {self.detail!r}")
        if self.simulated:
            raise AssertionError(
                f"{what} was only observed on a simulated {self.surface}. "
                f"A fake proves the test wiring, never the system — point the probe at "
                f"the real surface or hold it."
            )
        return self


class ObjectStoreProbe:
    """Read-only view of an object store (surface I2).

    Implement with whatever client the project has. Never write or delete through it:
    artefacts are removed by the API and the tracking registry.
    """

    surface = "object-store"
    simulated = False

    def head(self, key: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def observe(self, key: str) -> Observation:
        meta = self.head(key)
        return Observation(self.surface, meta is not None, meta, self.simulated)


class BusProbe:
    """Read-only view of a message broker (surface I3).

    Poll without committing an offset — a test that commits steals messages from the
    application and turns an intermittent bug into someone else's incident.
    """

    surface = "bus"
    simulated = False

    def poll(self, predicate: Callable[[Any], bool], *, limit: int = 100) -> Optional[Any]:
        raise NotImplementedError

    def observe(self, predicate: Callable[[Any], bool], *, limit: int = 100) -> Observation:
        message = self.poll(predicate, limit=limit)
        return Observation(self.surface, message is not None, message, self.simulated)


_SELECT_ONLY = re.compile(r"^\s*(select|with)\b", re.I)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|truncate|alter|create|grant|revoke|merge|call)\b", re.I
)


def assert_read_only_sql(query: str) -> str:
    """Reject anything that is not a single read.

    The library never mutates a database. This is enforced rather than documented
    because the failure mode — a test quietly deleting production-adjacent rows — is not
    one to leave to discipline.

    Starting with SELECT is not sufficient on its own: PostgreSQL happily runs
    ``WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x``. Hence the keyword check
    as well.

    It errs towards refusing: a query whose *string literal* contains a word like
    "delete" is rejected even though it is harmless. Blocking a legitimate read costs a
    rephrasing; letting a write through costs data.
    """
    text = (query or "").strip().rstrip(";")
    if ";" in text:
        raise ValueError("only a single statement is allowed")
    if not _SELECT_ONLY.match(text):
        raise ValueError("only SELECT (or WITH ... SELECT) queries are allowed")
    if _FORBIDDEN.search(text):
        raise ValueError("query contains a data-modifying keyword")
    return text


class DbProbe:
    """SELECT-only view of a database (surface I4).

    The connection, the driver and the schema stay in the project. Route every query
    through :meth:`select` so the read-only guard applies.
    """

    surface = "database"
    simulated = False

    def run_select(self, query: str, params: Optional[Sequence[Any]] = None) -> List[Any]:
        raise NotImplementedError

    def select(self, query: str, params: Optional[Sequence[Any]] = None) -> List[Any]:
        return self.run_select(assert_read_only_sql(query), params)

    def observe(self, query: str, params: Optional[Sequence[Any]] = None) -> Observation:
        rows = self.select(query, params)
        return Observation(self.surface, bool(rows), rows, self.simulated)


# --- Fakes, for building the test before the credentials exist ------------


@dataclass
class InMemoryObjectStore(ObjectStoreProbe):
    """Fake store. Everything it reports is marked simulated on purpose."""

    objects: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    surface: str = "object-store"
    simulated: bool = True

    def put(self, key: str, size: int = 0, **meta: Any) -> None:
        """Seed the fake. Not part of the probe contract — real probes never write."""
        self.objects[key] = {"key": key, "size": size, **meta}

    def head(self, key: str) -> Optional[Dict[str, Any]]:
        return self.objects.get(key)


@dataclass
class InMemoryBus(BusProbe):
    """Fake broker. Polling never removes a message, mirroring a non-committing read."""

    messages: List[Any] = field(default_factory=list)
    surface: str = "bus"
    simulated: bool = True

    def publish(self, message: Any) -> None:
        self.messages.append(message)

    def poll(self, predicate: Callable[[Any], bool], *, limit: int = 100) -> Optional[Any]:
        for message in self.messages[-limit:]:
            if predicate(message):
                return message
        return None


def observe_or_hold(
    probe: Optional[Any],
    surface: str,
    reason: str,
    observe: Callable[[Any], Observation],
) -> Optional[Observation]:
    """Observe through ``probe``, or record a hold when there is none.

    The shape an integration test wants: the HTTP assertions already ran and keep their
    value, and the surface that could not be reached is reported instead of dragging the
    whole test into a skip.
    """
    if probe is None:
        hold(surface, reason)
        return None
    return observe(probe)


__all__ = [
    "BusProbe",
    "DbProbe",
    "Held",
    "InMemoryBus",
    "InMemoryObjectStore",
    "Observation",
    "ObjectStoreProbe",
    "assert_locator",
    "assert_read_only_sql",
    "assert_status_enum",
    "held_surfaces",
    "hold",
    "observe_or_hold",
    "reset_held",
    "wait_for",
]
