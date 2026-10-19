"""Build a structured coverage model from OpenAPI + runtime call storage."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from partest.call_storage import call_count, call_meta, call_type, endpoint_subtype
from partest.methodology.api.classifier import classify_path_object
from partest.methodology.api.matrix import (
    CoveragePriority,
    applicable_test_cases,
    p1_test_cases,
    required_test_cases,
)
from partest.methodology.api.steps import call_depth
from partest.methodology.api.subtypes import SUBTYPE_LABELS, MethodSubtype
from partest.reports._rules import is_exception_row
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


def _depth_of(
    metas: Sequence[Any], present: Sequence[str], *, is_exception: bool
) -> Optional[Dict[str, Any]]:
    """Axis C as far as the call records show it, for the required cells this run filled.

    Per filled cell, the deepest check any call of that type *asked for*
    (:func:`~partest.methodology.api.steps.call_depth`): a status check
    (``expected_status_code`` passed) or a schema check on top of it (``validate_model``
    passed as well). The flags are the call's arguments, recorded before the request is
    sent — what was asked, not what passed. ``values`` is ``None``: value asserts live in
    the suite's code, and the call does not see them.

    ``None`` — not measured: an ``exception`` row (outside depth, as it is outside the
    average), no filled cell, or no call record carrying the two flags (storage loaded from
    an older dump, a call recorded by hand).
    """
    if is_exception or not present:
        return None
    wanted = set(present)
    reached: Dict[str, int] = {}
    for meta in metas or ():
        if not isinstance(meta, dict) or "has_status_check" not in meta or not meta.get("type"):
            continue
        cell = canonicalize_type(meta.get("type"))
        if cell not in wanted:
            continue
        level = call_depth(bool(meta.get("has_status_check")), bool(meta.get("has_validate_model")))
        reached[cell] = max(reached.get(cell, 0), level)
    if not reached:
        return None
    return {
        "cells": len(reached),
        "status": sum(1 for level in reached.values() if level >= 1),
        "schema": sum(1 for level in reached.values() if level >= 2),
        "values": None,
    }


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
    # Axis C, apart from the percentage: see ``_depth_of``. ``None`` — not measured.
    depth: Optional[Dict[str, Any]] = None

    def label_types(self, types: Sequence[str]) -> List[str]:
        return [TYPE_LABELS.get(t, t) for t in types]


@dataclass
class CoverageReport:
    endpoints: List[EndpointCoverage]
    # Over the rows that are not ``exception``; ``0.0`` when there are none — the type stays
    # ``float`` here (``scored_count`` says whether anything was averaged), ``coverage.json``
    # writes ``null``.
    average_pct: float
    total_calls: int
    full_count: int
    partial_count: int
    empty_count: int
    exception_count: int
    by_subtype: Dict[str, Dict[str, Any]]
    by_swagger: Dict[str, Dict[str, Any]]

    @property
    def scored_count(self) -> int:
        """The rows ``average_pct`` is taken from — all but ``exception``, counted from
        ``endpoints`` each time it is read, so it cannot go stale after ``endpoints`` change.
        ``0`` means nothing was averaged: ``average_pct``'s ``0.0`` is then "not measured"."""
        return sum(1 for ep in self.endpoints or () if not is_exception_row(ep))


def _conf_list(name: str) -> Optional[list]:
    """A list from confpartest, found the way every other setting is (``conf_attr``).

    A report must still be written when the project file is broken: the reason is already
    in the coverage state (:func:`partest.coverage._coverage_unavailable_reason`), so a
    failure here is the library default, not a second error.
    """
    from partest.conf import ConfpartestError, conf_attr

    try:
        value = conf_attr(name)
    except ConfpartestError:
        return None
    if value is None or isinstance(value, (str, bytes)):
        return None
    try:
        return list(value)
    except TypeError:
        return None


def _load_required_from_conf() -> Optional[List[str]]:
    """Optional flat list from confpartest (legacy mode)."""
    values = _conf_list("test_types_coverage")
    return None if values is None else [canonicalize_type(t) for t in values]


def _load_exceptions_from_conf() -> Set[str]:
    values = _conf_list("test_types_exception") or []
    return {canonicalize_type(t) for t in values} | set(EXCEPTION_TYPES)


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

        scored = 0
        for row in rows:
            # An `exception` row is counted, but outside every average: its 100 %
            # says "not scored by the matrix", not "fully covered".
            counts = not is_exception_row(row)
            if counts:
                total_pct += row.coverage_pct
                scored += 1
            total_calls += row.calls
            if not counts:
                exc += 1
            elif row.status == "full":
                full += 1
            elif row.status == "partial":
                partial += 1
            else:
                empty += 1

            sl = row.subtype.value
            bucket = by_subtype.setdefault(
                sl, {"count": 0, "scored": 0, "pct_sum": 0.0, "label": row.subtype_label}
            )
            bucket["count"] += 1
            if counts:
                bucket["scored"] += 1
                bucket["pct_sum"] += row.coverage_pct

            # source_type is used as swagger bucket key when available
            src = "API"
            for p in self.paths_info:
                if p.method == row.method and p.path == row.path:
                    src = getattr(p, "source_type", None) or "API"
                    break
            sb = by_swagger.setdefault(str(src), {"count": 0, "scored": 0, "pct_sum": 0.0})
            sb["count"] += 1
            if counts:
                sb["scored"] += 1
                sb["pct_sum"] += row.coverage_pct

        # `avg_pct` stays a float: `0.0` when nothing in the bucket was scored, and
        # `scored == 0` says so — as `average_pct` does for the whole report.
        for b in list(by_subtype.values()) + list(by_swagger.values()):
            b["avg_pct"] = b["pct_sum"] / b["scored"] if b["scored"] else 0.0

        return CoverageReport(
            endpoints=rows,
            average_pct=total_pct / scored if scored else 0.0,
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
            depth=_depth_of(metas, present, is_exception=is_exc),
        )


def _say_what_was_not_counted(report: CoverageReport) -> None:
    """A report with nothing behind it is a finding, not a result: say so where it is read.

    Under pytest with the partest plugin: a line in the ``partest: coverage NOT COUNTED``
    section of the terminal summary — not a warning, because reports are written from
    ``pytest_sessionfinish`` too, where ``filterwarnings = error`` would turn a warning into
    a lost ``coverage.json``. Without the plugin there is no such section, so a
    ``UserWarning``.

    Checked even when the report has rows: under pytest-xdist the controller merges the
    workers' counters but loads the specification itself, and when that fails the merged
    calls alone produce a report whose percentage nobody can trust.
    """
    from partest import conf as _conf
    from partest.coverage import _coverage_unavailable_reason

    reason = _coverage_unavailable_reason()
    if reason:
        what = "has no endpoints" if not report.endpoints else "was built without the specification"
        message = f"the coverage report {what} — {reason}"
    elif not report.endpoints:
        message = "the coverage report has no endpoints — no OpenAPI operations are loaded"
    else:
        return
    if _conf._project_roots:
        _conf._note(_conf.NOTES_COVERAGE, message)
    else:
        warnings.warn(f"partest: {message}", UserWarning, stacklevel=3)


def analyze_coverage(
    paths_info: Sequence[Any] = None,
    *,
    use_matrix: bool = True,
    max_priority: CoveragePriority = CoveragePriority.P1,
) -> CoverageReport:
    from_project = paths_info is None
    if from_project:
        try:
            from partest.coverage import get_paths_info

            paths_info = get_paths_info()
        except Exception:
            paths_info = []
    report = CoverageAnalyzer(
        paths_info,
        use_matrix=use_matrix,
        max_priority=max_priority,
    ).analyze()
    if from_project:
        _say_what_was_not_counted(report)
    return report
