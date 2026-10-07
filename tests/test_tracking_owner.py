"""Ownership in CreatedRegistry: a resource created during a test may belong to a wider area.

The case that asked for it: a session-scoped cache filled lazily, by whichever test needs
it first. The object is created inside that test, so per-test cleanup used to delete it —
and every later test got a cached id that no longer existed. Claiming it for the session
keeps it out of per-test cleanup and leaves it to the pass that owns it.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from partest import tracking
from partest.tracking import TEST_OWNER, CreatedRegistry, TrackingApiClient


@pytest.fixture
def deletes(monkeypatch):
    """Every DELETE cleanup sends, as a path, answered with 204."""
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        return httpx.Response(204)

    real = tracking.httpx_async_client

    def factory(**kwargs):
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(tracking, "httpx_async_client", factory)
    return sent


def clean_since(registry, mark):
    asyncio.run(registry.cleanup_since(mark, "http://stand", "t"))


def test_default_behaviour_is_unchanged(deletes):
    registry = CreatedRegistry()
    registry.track("/items", 1)
    mark = registry.snapshot()
    registry.track("/items", 2)
    registry.track("/items", 3)

    clean_since(registry, mark)

    assert deletes == ["/items/3", "/items/2"]
    assert registry.items == (("/items", 1),)
    assert registry.owner_of("/items", 1) is TEST_OWNER


def test_a_claimed_resource_survives_per_test_cleanup(deletes):
    registry = CreatedRegistry()
    mark = registry.snapshot()
    registry.track("/items", 1)
    with registry.owned_by("session"):
        registry.track("/items", 2)
    registry.track("/items", 3)

    clean_since(registry, mark)

    assert deletes == ["/items/3", "/items/1"]
    assert registry.items == (("/items", 2),)
    assert registry.owner_of("/items", 2) == "session"


def test_the_session_pass_still_removes_everything(deletes):
    registry = CreatedRegistry()
    with registry.owned_by("session"):
        registry.track("/items", 1)
    registry.track("/items", 2)

    asyncio.run(registry.cleanup("http://stand", "t"))

    assert deletes == ["/items/2", "/items/1"]
    assert registry.count == 0


def test_cleanup_owned_removes_one_area_and_nothing_else(deletes):
    registry = CreatedRegistry()
    module_a, module_b = ("module", "a"), ("module", "b")
    registry.track("/items", 1, owner=module_a)
    registry.track("/items", 2, owner=module_b)
    registry.track("/items", 3, owner="session")
    registry.track("/items", 4, owner=module_a)

    asyncio.run(registry.cleanup_owned(module_a, "http://stand", "t"))

    assert deletes == ["/items/4", "/items/1"]
    assert registry.items == (("/items", 2), ("/items", 3))


def test_adopt_claims_after_the_fact():
    registry = CreatedRegistry()
    registry.track("/items", 7)
    registry.track("/other", 7)

    assert registry.adopt(7, "session", endpoint="/items") == 1
    assert registry.owner_of("/items", 7) == "session"
    assert registry.owner_of("/other", 7) is TEST_OWNER

    assert registry.adopt(7, "session") == 2
    assert registry.adopt(7, None) == 2  # handed back to the test


def test_adopt_refuses_to_claim_nothing_silently():
    registry = CreatedRegistry()
    with pytest.raises(LookupError, match="not tracked"):
        registry.adopt(99, "session")
    assert registry.adopt(99, "session", endpoint="/items") == 1
    assert registry.items == (("/items", 99),)
    assert registry.owner_of("/items", 99) == "session"


def test_owned_by_none_is_refused():
    with pytest.raises(ValueError):
        with CreatedRegistry().owned_by(None):
            pass


def test_a_claim_is_per_registry_and_ends_with_the_block():
    first, second = CreatedRegistry(), CreatedRegistry()
    with first.owned_by("session"):
        first.track("/a", 1)
        second.track("/b", 1)
    first.track("/a", 2)
    assert first.owner_of("/a", 1) == "session"
    assert second.owner_of("/b", 1) is TEST_OWNER
    assert first.owner_of("/a", 2) is TEST_OWNER


def test_a_claim_does_not_leak_into_a_concurrent_task():
    registry = CreatedRegistry()

    async def claimed():
        with registry.owned_by("session"):
            await asyncio.sleep(0.01)
            registry.track("/items", "claimed")

    async def unclaimed():
        await asyncio.sleep(0.005)
        registry.track("/items", "plain")

    async def main():
        await asyncio.gather(claimed(), unclaimed())

    asyncio.run(main())
    assert registry.owner_of("/items", "claimed") == "session"
    assert registry.owner_of("/items", "plain") is TEST_OWNER


def test_since_carries_owners_and_still_returns_everything():
    registry = CreatedRegistry()
    registry.track("/items", 1, owner="session")
    registry.track("/items", 2)
    tail = registry.since(0)
    assert tail.items == (("/items", 1), ("/items", 2))
    assert tail.owner_of("/items", 1) == "session"


def test_a_legacy_subclass_without_owners_keeps_working(deletes):
    """Built ``_items`` itself and never called ``super().__init__()``."""

    class Legacy(CreatedRegistry):
        def __init__(self):
            self._items = []

    registry = Legacy()
    registry._items.append(("/items", 1))
    registry.track("/items", 2)
    assert registry.owner_of("/items", 1) is TEST_OWNER

    clean_since(registry, 0)
    assert deletes == ["/items/2", "/items/1"]


class _Client:
    """Stand-in ApiClient: fires the response hook the way the real one does."""

    def __init__(self, ids):
        self._ids = iter(ids)
        self._hooks = []

    def add_response_hook(self, hook):
        self._hooks.append(hook)

    async def make_request(self, method, endpoint, *args, **kwargs):
        body = {"id": next(self._ids)}
        response = httpx.Response(201)
        for hook in self._hooks:
            hook(method, endpoint, body, response)
        return body


def test_tracking_client_creates_under_the_claim(deletes):
    registry = CreatedRegistry()
    api = TrackingApiClient("http://stand", registry, client=_Client([1, 2]), instrument=False)

    async def scenario():
        mark = registry.snapshot()
        with api.owned_by("session"):
            await api.make_request("POST", "/items")  # the lazy cache, filled mid-test
        await api.make_request("POST", "/items")  # the test's own object
        await registry.cleanup_since(mark, "http://stand", "t")

    asyncio.run(scenario())
    assert deletes == ["/items/2"]
    assert registry.items == (("/items", 1),)
    assert registry.owner_of("/items", 1) == "session"


def test_test_owner_is_public_at_the_top_level():
    import partest

    assert partest.TEST_OWNER is TEST_OWNER is None
    assert "TEST_OWNER" in partest.__all__


def test_leaving_a_claim_in_another_context_is_a_clear_error():
    """What an async fixture holding owned_by across its yield runs into."""
    import contextvars

    registry = CreatedRegistry()
    block = registry.owned_by("session")
    contextvars.copy_context().run(block.__enter__)
    with pytest.raises(RuntimeError, match="different context"):
        block.__exit__(None, None, None)
