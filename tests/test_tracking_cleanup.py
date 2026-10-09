"""CreatedRegistry.cleanup: ids stay inside their path segment, credentials stay at their origin."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from partest import tracking
from partest.tracking import CreatedRegistry


@pytest.fixture
def transport(monkeypatch):
    """Route cleanup through a handler set per test; record every request it sees."""
    state = {"handler": lambda request: httpx.Response(204), "seen": []}

    def dispatch(request: httpx.Request) -> httpx.Response:
        state["seen"].append(request)
        return state["handler"](request)

    real = tracking.httpx_async_client

    def factory(**kwargs):
        return real(transport=httpx.MockTransport(dispatch), **kwargs)

    monkeypatch.setattr(tracking, "httpx_async_client", factory)
    return state


def _clean(registry, **kwargs):
    asyncio.run(registry.cleanup("http://stand/api", "tok", **kwargs))


@pytest.mark.parametrize(
    "rid, raw_path",
    [
        ("../x", b"/api/items/..%2Fx"),
        ("a/b", b"/api/items/a%2Fb"),
        ("a?b=c", b"/api/items/a%3Fb%3Dc"),
        ("a#frag", b"/api/items/a%23frag"),
        ("..", b"/api/items/%2E%2E"),
        (".", b"/api/items/%2E"),
        (42, b"/api/items/42"),
        ("3f2c-uuid", b"/api/items/3f2c-uuid"),
    ],
)
def test_an_id_is_one_path_segment(transport, rid, raw_path):
    registry = CreatedRegistry()
    registry.track("/items", rid)
    _clean(registry)
    [request] = transport["seen"]
    assert request.method == "DELETE"
    assert request.url.raw_path == raw_path
    assert request.url.host == "stand"


def test_a_delete_builder_still_builds_the_url_itself(transport):
    registry = CreatedRegistry()
    registry.track("/items", "a/b")
    _clean(registry, delete_builder=lambda endpoint, rid: f"{endpoint}/{rid}")
    assert transport["seen"][0].url.raw_path == b"/api/items/a/b"


@pytest.mark.parametrize(
    "location",
    ["http://elsewhere.example/api/items/1", "https://stand/api/items/1", "http://stand:8080/x"],
    ids=["other_host", "other_scheme", "other_port"],
)
@pytest.mark.parametrize("auth_header", ["Authorization", "X-Api-Token"])
def test_a_redirect_to_another_origin_is_not_followed(transport, location, auth_header):
    transport["handler"] = lambda request: httpx.Response(307, headers={"location": location})
    registry = CreatedRegistry()
    registry.track("/items", 1)
    _clean(registry, auth_header=auth_header, max_passes=1)
    assert [str(r.url) for r in transport["seen"]] == ["http://stand/api/items/1"]
    assert all(r.headers[auth_header] == "Bearer tok" for r in transport["seen"])
    assert registry.count == 0


def test_a_same_origin_redirect_is_followed_with_the_header(transport):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/"):
            return httpx.Response(308, headers={"location": request.url.path + "/"})
        return httpx.Response(204)

    transport["handler"] = handler
    registry = CreatedRegistry()
    registry.track("/items", 1)
    _clean(registry, auth_header="X-Api-Token")
    seen = transport["seen"]
    assert [(r.method, r.url.path) for r in seen] == [
        ("DELETE", "/api/items/1"),
        ("DELETE", "/api/items/1/"),
    ]
    assert seen[1].headers["X-Api-Token"] == "Bearer tok"


def test_a_see_other_redirect_is_not_turned_into_another_delete(transport):
    transport["handler"] = lambda request: httpx.Response(
        303, headers={"location": "/api/items/1/status"}
    )
    registry = CreatedRegistry()
    registry.track("/items", 1)
    _clean(registry, max_passes=1)
    assert len(transport["seen"]) == 1


def test_a_redirect_loop_stops(transport):
    transport["handler"] = lambda request: httpx.Response(
        307, headers={"location": "/api/items/1"}
    )
    registry = CreatedRegistry()
    registry.track("/items", 1)
    _clean(registry, max_passes=1)
    assert len(transport["seen"]) == 1 + tracking._CLEANUP_REDIRECTS


@pytest.mark.parametrize("rid", ["", "  ", "\t\n", None])
def test_a_blank_id_is_not_tracked(rid):
    registry = CreatedRegistry()
    registry.track("/items", rid)
    assert registry.count == 0
    assert registry.adopt(rid, "session", endpoint="/items") == 0
    assert registry.count == 0


@pytest.mark.parametrize("rid", ["", "  "])
@pytest.mark.parametrize("builder", [None, lambda endpoint, rid: f"{endpoint}/{rid}"])
def test_a_blank_id_that_got_in_anyway_sends_no_delete(transport, caplog, rid, builder):
    registry = CreatedRegistry()
    registry.track("/items", 1)
    registry._items.append(("/items", rid))  # past track(): a subclass filling _items
    registry._owners.append(tracking.TEST_OWNER)
    with caplog.at_level("WARNING", logger="partest.tracking"):
        _clean(registry, delete_builder=builder)
    assert [r.url.path for r in transport["seen"]] == ["/api/items/1"]
    assert "blank id" in caplog.text
    assert registry.count == 0


def test_the_segment_helper_refuses_a_blank_id():
    with pytest.raises(ValueError):
        tracking._id_segment(" ")
