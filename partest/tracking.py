"""Created resource registry + TrackingApiClient for session cleanup."""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence, Tuple, Union

import httpx

from partest.client import ApiClient

IdExtractor = Callable[[Any, str, str], Optional[Tuple[str, Any]]]


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
    """Stores (collection_endpoint, id) pairs for LIFO multi-pass DELETE cleanup."""

    def __init__(self):
        self._items: List[Tuple[str, Any]] = []

    def track(self, endpoint: str, resource_id: Any) -> None:
        if resource_id is not None:
            self._items.append((endpoint, resource_id))

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def items(self) -> Sequence[Tuple[str, Any]]:
        return tuple(self._items)

    def clear(self) -> None:
        self._items.clear()

    def snapshot(self) -> int:
        """Current size, to be paired with :meth:`since` or :meth:`cleanup_since`.

        Lets a function-scoped fixture drain only what its own test created, without
        each project re-implementing the same autouse bookkeeping.
        """
        return len(self._items)

    def since(self, mark: int) -> "CreatedRegistry":
        """New registry holding everything tracked after ``mark``."""
        drained = CreatedRegistry()
        drained._items = list(self._items[mark:])
        return drained

    async def cleanup_since(self, mark: int, domain: str, token: str, **kwargs) -> None:
        """Clean up only resources tracked after ``mark``, then forget them.

        The tail is removed from this registry whether cleanup succeeded or not — a
        failed delete is reported by :meth:`cleanup` itself, and keeping the entry
        would make the session pass try it again for every later test.
        """
        tail = self.since(mark)
        del self._items[mark:]
        await tail.cleanup(domain, token, **kwargs)

    async def cleanup(
        self,
        domain: str,
        token: str,
        *,
        max_passes: int = 4,
        delete_builder: Optional[Callable[[str, Any], str]] = None,
        auth_header: str = "Authorization",
        auth_scheme: str = "Bearer",
        verify: bool = False,
        timeout: float = 40.0,
    ) -> None:
        """DELETE tracked resources LIFO; 409 retries across passes; 404/204 OK."""
        if not self._items:
            return

        def _url(endpoint: str, rid: Any) -> str:
            if delete_builder:
                return delete_builder(endpoint, rid)
            return f"{endpoint.rstrip('/')}/{rid}"

        headers = {auth_header: f"{auth_scheme} {token}".strip()}
        pending = list(reversed(self._items))
        async with httpx.AsyncClient(
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
        verify: bool = False,
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
