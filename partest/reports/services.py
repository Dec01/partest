"""Resolve OpenAPI path (+ optional swagger tag) → service key/label.

Consumer supplies YAML / dict. Library never hardcodes product prefixes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


def _norm_path(path: str) -> str:
    text = (path or "").strip()
    if not text:
        return "/"
    if not text.startswith("/"):
        text = "/" + text
    return text.rstrip("/") or "/"


def _title_from_key(key: str) -> str:
    return key.replace("-", " ").replace("_", " ").strip().title() or "Unknown"


@dataclass(frozen=True)
class ServiceRef:
    key: str
    label: str


@dataclass
class ServiceMap:
    """Prefix / tag map. Longest matching prefix wins."""

    prefixes: list[tuple[str, str, str]] = field(default_factory=list)
    tags: dict[str, tuple[str, str]] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    api_prefixes: tuple[str, ...] = ("/api/v1/", "/api/")
    default_excluded: tuple[str, ...] = ()

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ServiceMap":
        if path is None:
            return cls()
        src = Path(path)
        if not src.is_file():
            return cls()
        import yaml

        raw = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ServiceMap":
        api_prefixes = tuple(raw.get("api_prefixes") or ["/api/v1/", "/api/"])
        default_excluded = tuple(raw.get("default_excluded") or [])
        labels: dict[str, str] = {}
        prefixes: list[tuple[str, str, str]] = []
        services = raw.get("services") or {}
        for key, spec in services.items():
            spec = spec or {}
            label = spec.get("label") or _title_from_key(str(key))
            labels[str(key)] = label
            for prefix in spec.get("prefixes") or []:
                prefixes.append((_norm_path(str(prefix)), str(key), label))
        prefixes.sort(key=lambda item: len(item[0]), reverse=True)

        tags: dict[str, tuple[str, str]] = {}
        for tag, key in (raw.get("tags") or {}).items():
            key_s = str(key)
            tags[str(tag).strip().lower()] = (key_s, labels.get(key_s, _title_from_key(key_s)))

        return cls(
            prefixes=prefixes,
            tags=tags,
            labels=labels,
            api_prefixes=tuple(str(p) for p in api_prefixes),
            default_excluded=default_excluded,
        )

    def label_for(self, key: str) -> str:
        return self.labels.get(key) or _title_from_key(key)

    def resolve(
        self,
        path: str,
        *,
        swagger_tags: Optional[Sequence[str]] = None,
    ) -> ServiceRef:
        for tag in swagger_tags or ():
            hit = self.tags.get(str(tag).strip().lower())
            if hit:
                return ServiceRef(key=hit[0], label=hit[1])

        norm = _norm_path(path)
        for prefix, key, label in self.prefixes:
            if norm == prefix or norm.startswith(prefix + "/"):
                return ServiceRef(key=key, label=label)

        return self._fallback(norm)

    def _fallback(self, norm_path: str) -> ServiceRef:
        rest = norm_path
        for api_prefix in sorted(self.api_prefixes, key=len, reverse=True):
            pref = _norm_path(api_prefix)
            if rest == pref:
                return ServiceRef(key="root", label="Root")
            token = pref if pref.endswith("/") else pref + "/"
            if rest.startswith(token):
                rest = rest[len(token) :]
                break
        segment = rest.split("/", 1)[0].strip() or "unknown"
        key = segment.lower()
        return ServiceRef(key=key, label=self.label_for(key))

    def known_keys(self) -> list[str]:
        return list(self.labels.keys())


def resolve_service(
    path: str,
    *,
    method: str = "",
    swagger_tags: Optional[Iterable[str]] = None,
    service_map: Optional[ServiceMap] = None,
) -> ServiceRef:
    """Public helper: path (+ optional tags) → ServiceRef."""
    del method
    smap = service_map or ServiceMap()
    tags = list(swagger_tags) if swagger_tags is not None else None
    return smap.resolve(path, swagger_tags=tags)
