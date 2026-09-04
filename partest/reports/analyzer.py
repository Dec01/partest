"""Build a structured coverage model from OpenAPI + runtime call storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from partest.call_storage import call_count, call_meta, call_type, endpoint_subtype
from partest.methodology.classifier import classify_path_object
from partest.methodology.matrix import (
    CoveragePriority,
    applicable_test_cases,
    p1_test_cases,
    required_test_cases,
)
from partest.methodology.subtypes import SUBTYPE_LABELS, MethodSubtype
from partest.test_types import (
    EXCEPTION_TYPES,
    TYPE_LABELS,
    TypesTestCases,
    canonicalize_type,
)



def _kind_for(*, count: int, present: Sequence[str], required: Sequence[str], is_exception: bool) -> str:
    """Classify what this run actually observed for one endpoint.

    ``unseen`` says nothing about whether tests exist — only that none of them hit
    this operation in this run. A partial selection (``-k``, a marker filter, a failed
    fixture) or an unmerged xdist run produces it in bulk.
    """
    if is_exception:
        return "exception"
    if count == 0:
        return "unseen"
    if not required:
        return "full"
    if not present:
        return "empty"
    return "full" if len(present) >= len(required) else "partial"


@dataclass
class EndpointCoverage:
    method: str
    path: str
    description: str
    subtype: MethodSubtype
    subtype_label: str
    calls: int
    executed_types: Set[str]
    required_p1: List[str]
    required_all: List[str]
    missing_p1: List[str]
    missing_all: List[str]
    present_required: List[str]
    coverage_pct: float
    status: str  # full | partial | empty | exception | deprecated
    # Run-level classification, kept separate from the legacy ``status``:
    # unseen (no call in THIS run) is not the same claim as empty (called, no
    # required cell executed). Conflating them is how a filtered or unmerged
    # parallel run reads as "these endpoints have no tests".
    kind: str = "unseen"
    is_exception: bool = False
    priority_cells: Dict[str, int] = field(default_factory=dict)
    depth_hints: List[Dict[str, Any]] = field(default_factory=list)

    def label_types(self, types: Sequence[str]) -> List[str]:
        return [TYPE_LABELS.get(t, t) for t in types]


@dataclass
class CoverageReport:
    endpoints: List[EndpointCoverage]
    average_pct: float
    total_calls: int
    full_count: int
    partial_count: int
    empty_count: int
    exception_count: int
    by_subtype: Dict[str, Dict[str, Any]]
    by_swagger: Dict[str, Dict[str, Any]]


def _load_required_from_conf() -> Optional[List[str]]:
    """Optional flat list from confpartest (legacy mode)."""
    try:
        from confpartest import test_types_coverage

        return [canonicalize_type(t) for t in test_types_coverage]
    except Exception:
        return None


def _load_exceptions_from_conf() -> Set[str]:
    try:
        from confpartest import test_types_exception

        return {canonicalize_type(t) for t in test_types_exception} | set(EXCEPTION_TYPES)
    except Exception:
        return set(EXCEPTION_TYPES)


class CoverageAnalyzer:
    """Merge swagger paths with runtime counters into EndpointCoverage rows."""

    def __init__(
        self,
        paths_info: Sequence[Any],
        *,
        use_matrix: bool = True,
        max_priority: CoveragePriority = CoveragePriority.P1,
        legacy_required: Optional[List[str]] = None,
    ):
        self.paths_info = list(paths_info or [])
        self.use_matrix = use_matrix
        self.max_priority = max_priority
        self.legacy_required = legacy_required if legacy_required is not None else _load_required_from_conf()
        self.exception_types = _load_exceptions_from_conf()

    def _subtype_for(self, method: str, path: str, path_obj: Any = None) -> MethodSubtype:
        cached = endpoint_subtype.get((method, path))
        if cached:
            try:
                return MethodSubtype(cached)
            except ValueError:
                pass
        if path_obj is not None:
            return classify_path_object(path_obj)
        return MethodSubtype.UNKNOWN

    def _required_for(self, subtype: MethodSubtype) -> Tuple[List[str], List[str]]:
        if self.use_matrix:
            p1 = p1_test_cases(subtype)
            all_req = required_test_cases(subtype, self.max_priority)
            return p1, all_req
        if self.legacy_required:
            return list(self.legacy_required), list(self.legacy_required)
        return [TypesTestCases.request_default], [TypesTestCases.request_default]

    def analyze(self) -> CoverageReport:
        rows: List[EndpointCoverage] = []
        seen_keys = set()

        # Prefer swagger as full universe
        for path_obj in self.paths_info:
            if getattr(path_obj, "deprecated", False):
                continue
            method = path_obj.method
            path = path_obj.path
            description = path_obj.description or ""
            key = (method, path, description)
            seen_keys.add(key)
            rows.append(self._row_for_key(key, path_obj=path_obj))

        # Calls that didn't match description exactly
        for key, count in list(call_count.items()):
            if key in seen_keys:
                continue
            if count <= 0:
                continue
            rows.append(self._row_for_key(key, path_obj=None))

        total_pct = 0.0
        total_calls = 0
        full = partial = empty = exc = 0
        by_subtype: Dict[str, Dict[str, Any]] = {}
        by_swagger: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            total_pct += row.coverage_pct
            total_calls += row.calls
            if row.is_exception or row.status == "exception":
                exc += 1
            elif row.status == "full":
                full += 1
            elif row.status == "partial":
                partial += 1
            else:
                empty += 1

            sl = row.subtype.value
            bucket = by_subtype.setdefault(
                sl, {"count": 0, "pct_sum": 0.0, "label": row.subtype_label}
            )
            bucket["count"] += 1
            bucket["pct_sum"] += row.coverage_pct

            # source_type is used as swagger bucket key when available
            src = "API"
            for p in self.paths_info:
                if p.method == row.method and p.path == row.path:
                    src = getattr(p, "source_type", None) or "API"
                    break
            sb = by_swagger.setdefault(str(src), {"count": 0, "pct_sum": 0.0})
            sb["count"] += 1
            sb["pct_sum"] += row.coverage_pct

        n = len(rows) or 1
        for b in by_subtype.values():
            b["avg_pct"] = b["pct_sum"] / b["count"] if b["count"] else 0.0
        for b in by_swagger.values():
            b["avg_pct"] = b["pct_sum"] / b["count"] if b["count"] else 0.0

        return CoverageReport(
            endpoints=rows,
            average_pct=total_pct / n if rows else 0.0,
            total_calls=total_calls,
            full_count=full,
            partial_count=partial,
            empty_count=empty,
            exception_count=exc,
            by_subtype=by_subtype,
            by_swagger=by_swagger,
        )

    def _row_for_key(self, key: Tuple[str, str, str], path_obj: Any) -> EndpointCoverage:
        method, path, description = key
        count = call_count.get(key, 0)
        raw_types = call_type.get(key, [])
        executed = {canonicalize_type(t) for t in raw_types if t}
        subtype = self._subtype_for(method, path, path_obj)
        p1, all_req = self._required_for(subtype)

        is_exc = bool(executed & self.exception_types)
        cells = {
            tc: int(prio)
            for tc, prio in applicable_test_cases(subtype).items()
            if prio != CoveragePriority.NA
        }

        if is_exc:
            pct = 100.0
            status = "exception"
            missing_p1: List[str] = []
            missing_all: List[str] = []
            present = list(executed)
        else:
            required = all_req or p1
            present = [t for t in required if t in executed]
            missing_all = [t for t in required if t not in executed]
            missing_p1 = [t for t in p1 if t not in executed]
            if not required:
                pct = 100.0 if count > 0 else 0.0
            else:
                pct = (len(present) / len(required)) * 100.0
            if pct >= 100.0 and required:
                status = "full"
            elif present or count > 0:
                status = "partial" if present else "empty"
                if not present and count > 0:
                    # calls without matching required types
                    status = "partial"
                    pct = max(pct, 5.0)  # show activity
            else:
                status = "empty"

        kind = _kind_for(count=count, present=present, required=(all_req or p1), is_exception=is_exc)

        metas = call_meta.get(key, [])
        return EndpointCoverage(
            method=method,
            path=path,
            description=description,
            subtype=subtype,
            subtype_label=SUBTYPE_LABELS.get(subtype, subtype.value),
            calls=count,
            executed_types=executed,
            required_p1=p1,
            required_all=all_req,
            missing_p1=missing_p1,
            missing_all=missing_all,
            present_required=present,
            coverage_pct=pct,
            status=status,
            kind=kind,
            is_exception=is_exc,
            priority_cells=cells,
            depth_hints=list(metas),
        )


def analyze_coverage(
    paths_info: Sequence[Any] = None,
    *,
    use_matrix: bool = True,
    max_priority: CoveragePriority = CoveragePriority.P1,
) -> CoverageReport:
    if paths_info is None:
        try:
            from partest.coverage import get_paths_info

            paths_info = get_paths_info()
        except Exception:
            paths_info = []
    return CoverageAnalyzer(
        paths_info,
        use_matrix=use_matrix,
        max_priority=max_priority,
    ).analyze()
