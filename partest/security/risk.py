"""Risk profile model — entity registry stays in the consumer.

Aligned with multi-project security planning (critical/high/medium/low).
Legacy 1.3.0 field names remain available via properties and ``from_legacy``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Mapping, Sequence, Union


@dataclass(init=False)
class RiskProfile:
    """Per-entity risk flags for security / coverage planning.

    Primary fields (stable multi-project API)::

        RiskProfile("clients", writes=True, fk_traversal=True)
        RiskProfile(entity="users", writes=True, authz=True, pii=True)

    Level rules (aggregate depth of security coverage)::

        critical — authz **or** (pii and writes)
        high     — writes and fk_traversal
        medium   — writes (without the above)
        low      — read-oriented / no write flags
    """

    entity: str
    writes: bool = False
    authz: bool = False
    pii: bool = False
    fk_traversal: bool = False
    money: bool = False
    notes: str = ""
    tags: List[str] = field(default_factory=list)

    def __init__(
        self,
        entity: str = "",
        writes: bool = False,
        authz: bool = False,
        pii: bool = False,
        fk_traversal: bool = False,
        *,
        money: bool = False,
        notes: str = "",
        tags: Sequence[str] | None = None,
        # legacy 1.3.0 kwargs (LIB-01 dual API)
        name: str | None = None,
        has_writes: bool | None = None,
        has_authz: bool | None = None,
        has_pii: bool | None = None,
        has_fk: bool | None = None,
        has_money: bool | None = None,
    ):
        ent = entity or name or ""
        if not ent:
            raise TypeError("RiskProfile requires entity= or name=")
        object.__setattr__(self, "entity", ent)
        object.__setattr__(
            self, "writes", bool(writes if has_writes is None else has_writes)
        )
        object.__setattr__(
            self, "authz", bool(authz if has_authz is None else has_authz)
        )
        object.__setattr__(self, "pii", bool(pii if has_pii is None else has_pii))
        object.__setattr__(
            self,
            "fk_traversal",
            bool(fk_traversal if has_fk is None else has_fk),
        )
        object.__setattr__(
            self, "money", bool(money if has_money is None else has_money)
        )
        object.__setattr__(self, "notes", notes or "")
        object.__setattr__(self, "tags", list(tags or []))

    # --- legacy aliases (read-only) ---
    @property
    def name(self) -> str:
        return self.entity

    @property
    def has_writes(self) -> bool:
        return self.writes

    @property
    def has_authz(self) -> bool:
        return self.authz

    @property
    def has_pii(self) -> bool:
        return self.pii

    @property
    def has_fk(self) -> bool:
        return self.fk_traversal

    @property
    def has_money(self) -> bool:
        return self.money

    @property
    def level(self) -> str:
        """critical | high | medium | low."""
        if self.authz or (self.pii and self.writes):
            return "critical"
        if self.writes and self.fk_traversal:
            return "high"
        if self.money and self.writes:
            return "high"
        if self.writes:
            return "medium"
        return "low"

    @classmethod
    def from_legacy(
        cls,
        name: str,
        *,
        has_writes: bool = False,
        has_authz: bool = False,
        has_pii: bool = False,
        has_fk: bool = False,
        has_money: bool = False,
        notes: str = "",
        tags: Sequence[str] | None = None,
    ) -> "RiskProfile":
        """Build from 1.3.0-style field names."""
        return cls(
            entity=name,
            writes=has_writes,
            authz=has_authz,
            pii=has_pii,
            fk_traversal=has_fk,
            money=has_money,
            notes=notes,
            tags=tags,
        )


ProfileSource = Union[Sequence[RiskProfile], Mapping[str, RiskProfile], Iterable[RiskProfile]]


def _iter_profiles(profiles: ProfileSource) -> List[RiskProfile]:
    if isinstance(profiles, Mapping):
        return list(profiles.values())
    return list(profiles)


def by_level(profiles: ProfileSource, level: str) -> List[RiskProfile]:
    """Filter profiles by ``level`` (accepts list or consumer registry dict)."""
    want = (level or "").lower()
    return [p for p in _iter_profiles(profiles) if p.level == want]


def writable(profiles: ProfileSource) -> List[RiskProfile]:
    """Profiles with ``writes=True`` (list or registry dict)."""
    return [p for p in _iter_profiles(profiles) if p.writes]


def level_of(profiles: Mapping[str, RiskProfile], entity: str) -> str:
    """Lookup level from a consumer ``PROFILES`` mapping."""
    return profiles[entity].level
