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
    ):
        self._client = client or ApiClient(
            domain=domain, verify=verify, follow_redirects=follow_redirects
        )
        self._registry = registry
        self.domain = domain
        self._id_extractors: List[IdExtractor] = list(id_extractors or [default_id_extractor])
        self._instrument = instrument

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

        for extractor in self._id_extractors:
            tracked = extractor(result, str(method), str(endpoint))
            if tracked:
                ep, rid = tracked
                self._registry.track(ep, rid)
                break
        return result

    def __getattr__(self, name):
        return getattr(self._client, name)
