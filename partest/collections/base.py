"""Thin collection façade + manager skeleton (no product entities)."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Union


class BaseCollection:
    """Façade: ``paths`` + ``headers`` + ``payload`` + ``validate``.

    Reference layout (consumer, not library entities)::

        class ClientCollection(BaseCollection):
            def __init__(self, token: str | None = None):
                self.validate = ModelsValidations()
                self.payload = ModelsPayloads()
                self.paths = ModelsPaths()
                self.headers = ModelsHeaders(token)

    Domain collections stay in the consumer project.
    """

    validate: Any = None
    payload: Any = None
    paths: Any = None
    headers: Any = None

    def apply_token(self, token: Optional[str]) -> "BaseCollection":
        """Re-bind Authorization on headers helper if supported."""
        if self.headers is None or token is None:
            return self
        if hasattr(self.headers, "apply_token"):
            self.headers.apply_token(token)
        elif hasattr(self.headers, "token"):
            self.headers.token = token
            # common pattern: rebuild read/write dicts from Config
            if hasattr(self.headers, "refresh"):
                self.headers.refresh()
            elif hasattr(self.headers, "rebuild"):
                self.headers.rebuild()
        return self


class CollectionsManager:
    """Generic name → collection map with bulk ``apply_token``.

    Consumer wires factories / instances — **no entity names in the library**::

        mgr = CollectionsManager(
            items=ItemsCollection(token=None),
            health=HealthCollection(token=None),
        )
        mgr.apply_token(access_token)
        path = mgr.items.paths.list_items
    """

    def __init__(
        self,
        collections: Optional[Mapping[str, Any]] = None,
        **named: Any,
    ):
        self._collections: Dict[str, Any] = {}
        if collections:
            for name, coll in collections.items():
                self._register(name, coll)
        for name, coll in named.items():
            self._register(name, coll)

    def _register(self, name: str, coll: Any) -> None:
        self._collections[name] = coll
        setattr(self, name, coll)

    def get(self, name: str) -> Any:
        return self._collections[name]

    def names(self) -> Iterable[str]:
        return self._collections.keys()

    def values(self) -> Iterable[Any]:
        return self._collections.values()

    def items(self) -> Iterable[tuple]:
        return self._collections.items()

    def __iter__(self) -> Iterator[str]:
        return iter(self._collections)

    def __contains__(self, name: object) -> bool:
        return name in self._collections

    def __len__(self) -> int:
        return len(self._collections)

    def apply_token(self, token: Optional[str]) -> "CollectionsManager":
        """Apply token to every collection that supports ``apply_token``."""
        for coll in self._collections.values():
            if coll is None:
                continue
            if hasattr(coll, "apply_token"):
                coll.apply_token(token)
        return self

    def add(self, name: str, collection: Any) -> "CollectionsManager":
        self._register(name, collection)
        return self
