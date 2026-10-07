"""Created resource registry + TrackingApiClient for session cleanup."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any, Callable, Dict, Hashable, Iterator, List, Optional, Sequence, Tuple, Union

from partest.client import ApiClient
from partest.http.client import httpx_async_client
from partest.tls import VerifySetting, resolve_verify

IdExtractor = Callable[[Any, str, str], Optional[Tuple[str, Any]]]

_UNSET: Any = object()

#: Owner of a resource nobody claimed: the test that created it. Per-test cleanup
#: (:meth:`CreatedRegistry.cleanup_since`) removes exactly these.
TEST_OWNER = None

# The owner a registry stamps on what it tracks, per async task / thread. A mapping keyed
# by ``id(registry)`` so two registries in one context do not share a claim.
_CURRENT_OWNER: "contextvars.ContextVar[Dict[int, Hashable]]" = contextvars.ContextVar(
    "partest_tracking_owner", default={}
)


def _dig(data: Any, path: Sequence[str]) -> Any:
    cur = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def default_id_extractor(result: Any, method: str, endpoint: str) -> Optional[Tuple[str, Any]]:
    """Track POST responses that return a top-level ``id``."""
    if method.upper() != "POST":
        return None
    if isinstance(result, dict) and result.get("id") is not None:
        return endpoint, result["id"]
    return None


def nested_id_extractor(
    *path: str,
    methods: Sequence[str] = ("POST",),
    collection_endpoint: Optional[str] = None,
) -> IdExtractor:
    """Build extractor for nested ids, e.g. ``data.id`` or ``result.item.id``.

    Example::

        TrackingApiClient(
            domain, registry,
            id_extractors=[
                nested_id_extractor("data", "id"),
                default_id_extractor,
            ],
        )
    """
    methods_u = {m.upper() for m in methods}

    def _extract(result: Any, method: str, endpoint: str) -> Optional[Tuple[str, Any]]:
        if method.upper() not in methods_u:
            return None
        rid = _dig(result, path)
        if rid is None:
            return None
        return (collection_endpoint or endpoint), rid

    return _extract


def field_id_extractor(
    field: str = "id",
    *,
    methods: Sequence[str] = ("POST",),
    collection_endpoint: Optional[str] = None,
) -> IdExtractor:
    """Top-level field extractor (default ``id``; also useful for ``uuid``)."""
    methods_u = {m.upper() for m in methods}

    def _extract(result: Any, method: str, endpoint: str) -> Optional[Tuple[str, Any]]:
        if method.upper() not in methods_u:
            return None
        if isinstance(result, dict) and result.get(field) is not None:
            return (collection_endpoint or endpoint), result[field]
        return None

    return _extract


def chain_extractors(*extractors: IdExtractor) -> IdExtractor:
    """Try extractors in order; first non-None wins."""

    def _extract(result: Any, method: str, endpoint: str) -> Optional[Tuple[str, Any]]:
        for ex in extractors:
            tracked = ex(result, method, endpoint)
            if tracked:
                return tracked
        return None

    return _extract


class CreatedRegistry:
    """Stores (collection_endpoint, id) pairs for LIFO multi-pass DELETE cleanup.

    Every entry has an **owner**. By default it is :data:`TEST_OWNER` (``None``) — the test
    that was running — and per-test cleanup removes it. A resource created *during* a test
    but meant to outlive it — a lazily filled session cache, a module-level object created
    on first use — is claimed by a wider owner (any hashable: ``"session"``,
    ``("module", request.module.__name__)``) with :meth:`owned_by` or :meth:`adopt`.
    :meth:`cleanup_since` then leaves it alone, :meth:`cleanup_owned` removes it when that
    area ends, and :meth:`cleanup` — the session pass — still removes everything.
    """

    def __init__(self):
        self._items: List[Tuple[str, Any]] = []
        # Parallel to ``_items``, index for index; every mutation below touches both.
        # ``items`` keeps returning bare pairs, so nothing that unpacks them changes.
        self._owners: List[Hashable] = []

    def _owner_list(self) -> List[Hashable]:
        """``_owners``, brought level with ``_items`` first.

        A subclass that builds ``_items`` itself, or code that appends to it directly,
        predates owners; whatever it added belongs to the test, as everything did then.
        """
        owners = self.__dict__.setdefault("_owners", [])
        missing = len(self._items) - len(owners)
        if missing > 0:
            owners.extend([TEST_OWNER] * missing)
        elif missing < 0:
            del owners[len(self._items):]
        return owners

    def track(self, endpoint: str, resource_id: Any, *, owner: Hashable = _UNSET) -> None:
        """Register a created resource.

        ``owner`` defaults to the one set by an enclosing :meth:`owned_by`, else
        :data:`TEST_OWNER`.
        """
        if resource_id is not None:
            if owner is _UNSET:
                owner = _CURRENT_OWNER.get().get(id(self), TEST_OWNER)
            owners = self._owner_list()
            self._items.append((endpoint, resource_id))
            owners.append(owner)

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def items(self) -> Sequence[Tuple[str, Any]]:
        return tuple(self._items)

    def owner_of(self, endpoint: str, resource_id: Any) -> Hashable:
        """Owner of the latest entry for this resource; ``KeyError`` if it is not tracked."""
        owners = self._owner_list()
        for index in range(len(self._items) - 1, -1, -1):
            if self._items[index] == (endpoint, resource_id):
                return owners[index]
        raise KeyError((endpoint, resource_id))

    def clear(self) -> None:
        self._items.clear()
        self._owner_list().clear()

    @contextmanager
    def owned_by(self, owner: Hashable) -> Iterator["CreatedRegistry"]:
        """Within the block, everything this registry tracks belongs to ``owner``.

        Covers ids registered by :class:`TrackingApiClient` too, in sync and async code.
        The claim lives in a context variable, so a concurrent task outside the block is
        not affected::

            async def shared_item(api, registry):
                if cache.item is None:            # the first test to need it pays for it
                    with registry.owned_by("session"):
                        folder = await api.make_request("POST", "/folders", ...)
                        cache.item = await api.make_request("POST", "/items", ...)
                return cache.item

        **Claim the parents together with the resource** — wrap the whole chain of creates
        in the block, not only the last one. A claimed child under a test-owned parent is
        not protected: per-test cleanup deletes the parent, and the service either cascades
        the delete to the child (the cache now holds an id that is gone) or refuses it with
        409 because a child exists (the delete is retried, then given up, and the parent is
        left on the stand). The other way round is safe: a claimed parent with test-owned
        children loses the children after each test and keeps itself.

        Enter and leave the block in the same context. Holding it across the ``yield`` of an
        async fixture does not work: pytest-asyncio may run the teardown half in another
        context, where the claim cannot be undone — that is reported as ``RuntimeError``
        here. Claim inside the fixture's setup instead, or use :meth:`adopt` /
        ``track(..., owner=...)``.
        """
        if owner is TEST_OWNER:
            raise ValueError("owned_by(None) would claim nothing; None is the per-test owner")
        current = _CURRENT_OWNER.get()
        token = _CURRENT_OWNER.set({**current, id(self): owner})
        try:
            yield self
        finally:
            try:
                _CURRENT_OWNER.reset(token)
            except ValueError as exc:  # token created in a different Context
                raise RuntimeError(
                    "CreatedRegistry.owned_by() was left in a different context than it was "
                    "entered in — typically a `with` held across the `yield` of an async "
                    "fixture. Claim around the creating calls only, or use adopt() / "
                    "track(..., owner=...)."
                ) from exc

    def adopt(self, resource_id: Any, owner: Hashable, *, endpoint: Optional[str] = None) -> int:
        """Hand an already tracked resource to ``owner``; return how many entries moved.

        For a claim that can only be made after the fact — the id is known once the create
        returned. Matches by id, and by ``endpoint`` as well when it is given. If nothing
        under that id is tracked: with ``endpoint`` it is tracked now, under ``owner``;
        without one ``LookupError`` is raised — a claim that silently did nothing would let
        per-test cleanup delete a resource its caller believes is protected.
        ``owner=None`` hands the resource back to the test.

        Adopt the parents as well (each with its own call, or by wrapping the creation in
        :meth:`owned_by`, which is preferable because it cannot miss one): a claimed child
        whose parent stays with the test is deleted by the cascade, or keeps the parent's
        delete failing with 409 — see :meth:`owned_by`.
        """
        moved = 0
        owners = self._owner_list()
        for index, (ep, rid) in enumerate(self._items):
            if rid == resource_id and (endpoint is None or ep == endpoint):
                owners[index] = owner
                moved += 1
        if moved:
            return moved
        if endpoint is None:
            raise LookupError(
                f"resource {resource_id!r} is not tracked; pass endpoint= to track it "
                f"under {owner!r}"
            )
        self.track(endpoint, resource_id, owner=owner)
        return 1

    def owned(self, owner: Hashable) -> "CreatedRegistry":
        """New registry holding only what ``owner`` owns, in tracking order."""
        selected = CreatedRegistry()
        for item, who in zip(self._items, self._owner_list()):
            if who == owner:
                selected._items.append(item)
                selected._owners.append(who)
        return selected

    def snapshot(self) -> int:
        """Current size, to be paired with :meth:`since` or :meth:`cleanup_since`.

        Lets a function-scoped fixture drain only what its own test created, without
        each project re-implementing the same autouse bookkeeping.
        """
        return len(self._items)

    def since(self, mark: int) -> "CreatedRegistry":
        """New registry holding everything tracked after ``mark``, whoever owns it."""
        drained = CreatedRegistry()
        drained._items = list(self._items[mark:])
        drained._owners = list(self._owner_list()[mark:])
        return drained

    async def cleanup_since(self, mark: int, domain: str, token: str, **kwargs) -> None:
        """Clean up the resources the test tracked after ``mark``, then forget them.

        Entries claimed by a wider owner (:meth:`owned_by`, :meth:`adopt`) are skipped and
        stay in the registry, in order, for :meth:`cleanup_owned` or the session pass.
        Without claims this is everything after ``mark``, as it always was.

        The removed part leaves this registry whether cleanup succeeded or not — a
        failed delete is reported by :meth:`cleanup` itself, and keeping the entry
        would make the session pass try it again for every later test.
        """
        tail = CreatedRegistry()
        kept_items: List[Tuple[str, Any]] = []
        kept_owners: List[Hashable] = []
        owners = self._owner_list()
        for item, who in zip(self._items[mark:], owners[mark:]):
            if who is TEST_OWNER:
                tail._items.append(item)
                tail._owners.append(who)
            else:
                kept_items.append(item)
                kept_owners.append(who)
        self._items[mark:] = kept_items
        owners[mark:] = kept_owners
        await tail.cleanup(domain, token, **kwargs)

    async def cleanup_owned(self, owner: Hashable, domain: str, token: str, **kwargs) -> None:
        """Clean up everything ``owner`` owns, wherever it sits, then forget it.

        The teardown of a module- or class-level area::

            await registry.cleanup_owned(("module", request.module.__name__), domain, token)

        Same delete rules as :meth:`cleanup`; forgotten whether the delete succeeded or
        not, like :meth:`cleanup_since`.
        """
        selected = self.owned(owner)
        keep = [i for i, who in enumerate(self._owner_list()) if who != owner]
        self._items = [self._items[i] for i in keep]
        self._owners = [self._owners[i] for i in keep]
        await selected.cleanup(domain, token, **kwargs)

    async def cleanup(
        self,
        domain: str,
        token: str,
        *,
        max_passes: int = 4,
        delete_builder: Optional[Callable[[str, Any], str]] = None,
        auth_header: str = "Authorization",
        auth_scheme: str = "Bearer",
        verify: Optional[VerifySetting] = None,
        timeout: float = 40.0,
    ) -> None:
        """DELETE tracked resources LIFO; 409 retries across passes; 404/204 OK.

        ``verify`` follows :mod:`partest.tls`; cleanup carries a bearer token like any
        other call and has no reason to trust a certificate the suite would not.
        """
        if not self._items:
            return
        verify = resolve_verify(verify)

        def _url(endpoint: str, rid: Any) -> str:
            if delete_builder:
                return delete_builder(endpoint, rid)
            return f"{endpoint.rstrip('/')}/{rid}"

        headers = {auth_header: f"{auth_scheme} {token}".strip()}
        pending = list(reversed(self._items))
        async with httpx_async_client(
            base_url=domain,
            verify=verify,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            for _ in range(max_passes):
                if not pending:
                    break
                still = []
                for endpoint, rid in pending:
                    try:
                        response = await client.delete(_url(endpoint, rid), headers=headers)
                    except Exception:
                        continue
                    if response.status_code == 409:
                        still.append((endpoint, rid))
                pending = still
        self._items.clear()
        self._owner_list().clear()


class TrackingApiClient:
    """Transparent wrapper over :class:`partest.client.ApiClient`.

    After successful create (POST → body with id), registers the resource for
    session cleanup. Optionally instruments each call for Allure.
    """

    def __init__(
        self,
        domain: str,
        registry: CreatedRegistry,
        *,
        client: Optional[ApiClient] = None,
        id_extractors: Optional[Sequence[IdExtractor]] = None,
        instrument: bool = True,
        verify: Optional[VerifySetting] = None,
        follow_redirects: bool = True,
        track_before_validate: bool = True,
    ):
        self._client = client or ApiClient(
            domain=domain, verify=verify, follow_redirects=follow_redirects
        )
        self._registry = registry
        self.domain = domain
        self._id_extractors: List[IdExtractor] = list(id_extractors or [default_id_extractor])
        self._instrument = instrument
        self._track_before_validate = bool(track_before_validate)
        if self._track_before_validate and hasattr(self._client, "add_response_hook"):
            self._client.add_response_hook(self._on_response)
        else:
            self._track_before_validate = False

    def _track_from(self, body: Any, method: Any, endpoint: Any) -> bool:
        for extractor in self._id_extractors:
            tracked = extractor(body, str(method), str(endpoint))
            if tracked:
                ep, rid = tracked
                self._registry.track(ep, rid)
                return True
        return False

    def _on_response(self, method: str, endpoint: str, body: Any, response: Any) -> None:
        """Register a created id as soon as the status is 2xx.

        Runs before ``validate_model``, so a 201 whose body fails schema validation
        still leaves the resource in the registry and the session cleanup can delete
        it. The test still fails — only the leftover is prevented.
        """
        status = getattr(response, "status_code", 0)
        if not (200 <= int(status or 0) < 300):
            return
        self._track_from(body, method, endpoint)

    @property
    def registry(self) -> CreatedRegistry:
        return self._registry

    @property
    def client(self) -> ApiClient:
        return self._client

    def add_id_extractor(self, extractor: IdExtractor) -> None:
        self._id_extractors.append(extractor)

    def owned_by(self, owner: Hashable):
        """What this client creates inside the block belongs to ``owner``.

        Shorthand for ``client.registry.owned_by(owner)`` — see
        :meth:`CreatedRegistry.owned_by`.
        """
        return self._registry.owned_by(owner)

    async def make_request(self, method, endpoint, *args, **kwargs):
        call = self._client.make_request
        if self._instrument:
            try:
                from partest.reporting.instrument import instrumented_make_request

                result = await instrumented_make_request(
                    call, method, endpoint, *args, **kwargs
                )
            except ImportError:
                result = await call(method, endpoint, *args, **kwargs)
        else:
            result = await call(method, endpoint, *args, **kwargs)

        # With the hook installed the id is already registered; extracting again here
        # would double-track it. This path stays for clients without hook support.
        if not self._track_before_validate:
            self._track_from(result, method, endpoint)
        return result

    def __getattr__(self, name: str) -> Any:
        """Delegate anything this wrapper does not define to the wrapped client.

        A deliberate hole in the type coverage the package advertises with ``py.typed``:
        every unknown attribute types as ``Any``, so a typo here is caught at runtime
        rather than by a checker. Prefer ``client`` for anything you need statically.
        """
        return getattr(self._client, name)
