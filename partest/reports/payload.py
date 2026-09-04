"""CoverageReport → JSON payload + aggregates (service map is injected)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

from partest.reports.analyzer import CoverageReport, EndpointCoverage
from partest.reports.services import ServiceMap
from partest.test_types import TYPE_LABELS

COVERAGE_PRESETS = {
    "0": (0.0, 0.0),
    "1-33": (0.0001, 33.0),
    "34-66": (34.0, 66.0),
    "67-99": (67.0, 99.9999),
    "100": (100.0, 100.0),
}


def _label_type(tc: str) -> str:
    return TYPE_LABELS.get(tc, tc)


def _status_of(ep: EndpointCoverage) -> str:
    return ep.status or "empty"


def _get(ep: Any, *names: str) -> Any:
    if isinstance(ep, dict):
        for name in names:
            if name in ep:
                return ep[name]
        return None
    for name in names:
        if hasattr(ep, name):
            return getattr(ep, name)
    return None


def endpoint_to_dict(
    ep: EndpointCoverage,
    *,
    service_map: ServiceMap,
    swagger_tags: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    ref = service_map.resolve(ep.path, swagger_tags=swagger_tags)
    subtype_key = getattr(ep.subtype, "value", str(ep.subtype))
    executed = sorted(_label_type(t) for t in ep.executed_types)
    missing = [_label_type(t) for t in ep.missing_p1]
    return {
        "method": ep.method,
        "path": ep.path,
        "service": ref.key,
        "serviceLabel": ref.label,
        "subtype": ep.subtype_label,
        "subtypeKey": subtype_key,
        "calls": int(ep.calls or 0),
        "coverage": round(float(ep.coverage_pct or 0.0), 2),
        "status": _status_of(ep),
        "executed": executed,
        "missing": missing,
        "description": ep.description or "",
    }


def summarize(endpoints: Sequence[Any]) -> dict[str, Any]:
    n = len(endpoints)
    total_pct = 0.0
    total_calls = 0
    full = partial = empty = exc = 0
    for ep in endpoints:
        pct = float(_get(ep, "coverage", "coverage_pct") or 0.0)
        calls = int(_get(ep, "calls") or 0)
        status = str(_get(ep, "status") or "empty")
        total_pct += pct
        total_calls += calls
        if status == "exception":
            exc += 1
        elif status == "full":
            full += 1
        elif status == "partial":
            partial += 1
        else:
            empty += 1
    return {
        "avg": round(total_pct / n, 2) if n else 0.0,
        "calls": total_calls,
        "full": full,
        "partial": partial,
        "empty": empty,
        "exception": exc,
        "endpoints": n,
    }


def aggregate_services(endpoints: Sequence[Any]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for ep in endpoints:
        key = str(_get(ep, "service") or "unknown")
        label = str(_get(ep, "serviceLabel") or key)
        bucket = buckets.setdefault(key, {"key": key, "label": label, "endpoints": []})
        bucket["endpoints"].append(ep)
    rows = []
    for key, bucket in buckets.items():
        stats = summarize(bucket["endpoints"])
        covered = stats["full"] + stats["partial"] + stats["exception"]
        rows.append(
            {
                "key": key,
                "label": bucket["label"],
                "totalEndpoints": stats["endpoints"],
                "covered": covered,
                "calls": stats["calls"],
                "full": stats["full"],
                "partial": stats["partial"],
                "empty": stats["empty"],
                "exception": stats["exception"],
                "avgCoverage": stats["avg"],
            }
        )
    rows.sort(key=lambda r: (-r["avgCoverage"], r["label"]))
    return rows


def aggregate_subtypes(endpoints: Sequence[Any]) -> list[dict[str, Any]]:
    buckets: dict[str, list] = defaultdict(list)
    labels: dict[str, str] = {}
    for ep in endpoints:
        key = str(_get(ep, "subtypeKey") or _get(ep, "subtype") or "unknown")
        labels[key] = str(_get(ep, "subtype") or key)
        buckets[key].append(ep)
    rows = []
    for key, items in buckets.items():
        stats = summarize(items)
        rows.append(
            {
                "key": key,
                "label": labels[key],
                "avgCoverage": stats["avg"],
                "count": stats["endpoints"],
                "calls": stats["calls"],
                "full": stats["full"],
                "partial": stats["partial"],
                "empty": stats["empty"],
            }
        )
    rows.sort(key=lambda r: (-r["avgCoverage"], r["label"]))
    return rows


def aggregate_methods(endpoints: Sequence[Any]) -> list[dict[str, Any]]:
    buckets: dict[str, list] = defaultdict(list)
    for ep in endpoints:
        buckets[str(_get(ep, "method") or "?").upper()].append(ep)
    rows = []
    for method, items in sorted(buckets.items()):
        stats = summarize(items)
        rows.append(
            {
                "method": method,
                "avgCoverage": stats["avg"],
                "count": stats["endpoints"],
                "calls": stats["calls"],
            }
        )
    return rows


def top_missing_p1(endpoints: Sequence[Any], *, limit: int = 12) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for ep in endpoints:
        missing = _get(ep, "missing") or []
        for tc in missing:
            counter[str(tc)] += 1
    return [{"tc": name, "count": count} for name, count in counter.most_common(limit)]


def heatmap(endpoints: Sequence[Any]) -> dict[str, Any]:
    cells: dict[tuple[str, str], list[float]] = defaultdict(list)
    services: dict[str, str] = {}
    subtypes: dict[str, str] = {}
    for ep in endpoints:
        s_key = str(_get(ep, "service") or "unknown")
        t_key = str(_get(ep, "subtypeKey") or _get(ep, "subtype") or "unknown")
        services[s_key] = str(_get(ep, "serviceLabel") or s_key)
        subtypes[t_key] = str(_get(ep, "subtype") or t_key)
        cells[(s_key, t_key)].append(float(_get(ep, "coverage", "coverage_pct") or 0.0))
    matrix = []
    for (s_key, t_key), values in cells.items():
        matrix.append(
            {
                "service": s_key,
                "subtype": t_key,
                "avg": round(sum(values) / len(values), 2) if values else 0.0,
                "count": len(values),
            }
        )
    return {
        "services": [{"key": k, "label": v} for k, v in sorted(services.items(), key=lambda x: x[1])],
        "subtypes": [{"key": k, "label": v} for k, v in sorted(subtypes.items(), key=lambda x: x[1])],
        "cells": matrix,
    }


def filter_endpoints(
    endpoints: Sequence[dict[str, Any]],
    *,
    services: Optional[Iterable[str]] = None,
    methods: Optional[Iterable[str]] = None,
    subtypes: Optional[Iterable[str]] = None,
    statuses: Optional[Iterable[str]] = None,
    coverage_preset: Optional[str] = None,
    calls_min: Optional[int] = None,
    calls_max: Optional[int] = None,
    missing: Optional[Iterable[str]] = None,
    search: str = "",
) -> list[dict[str, Any]]:
    svc = set(services) if services is not None else None
    meth = {m.upper() for m in methods} if methods is not None else None
    sub = set(subtypes) if subtypes is not None else None
    st = set(statuses) if statuses is not None else None
    miss = set(missing) if missing is not None else None
    lo, hi = COVERAGE_PRESETS.get(coverage_preset or "", (None, None))
    needle = (search or "").strip().lower()

    out = []
    for ep in endpoints:
        if svc is not None and ep.get("service") not in svc:
            continue
        if meth is not None and str(ep.get("method", "")).upper() not in meth:
            continue
        if sub is not None and ep.get("subtype") not in sub and ep.get("subtypeKey") not in sub:
            continue
        if st is not None and ep.get("status") not in st:
            continue
        cov = float(ep.get("coverage") or 0.0)
        if lo is not None and hi is not None and not (lo <= cov <= hi):
            continue
        calls = int(ep.get("calls") or 0)
        if calls_min is not None and calls < calls_min:
            continue
        if calls_max is not None and calls > calls_max:
            continue
        if miss is not None and not miss.intersection(ep.get("missing") or []):
            continue
        if needle:
            blob = " ".join(
                [
                    str(ep.get("path") or ""),
                    str(ep.get("description") or ""),
                    str(ep.get("method") or ""),
                    str(ep.get("service") or ""),
                ]
            ).lower()
            if needle not in blob:
                continue
        out.append(ep)
    return out


def build_payload(
    report: CoverageReport,
    *,
    service_map: Optional[ServiceMap] = None,
    title: str = "partest API coverage",
    engine: str = "partest",
) -> dict[str, Any]:
    smap = service_map or ServiceMap()
    endpoints = [endpoint_to_dict(ep, service_map=smap) for ep in report.endpoints]
    summary = summarize(endpoints)
    return {
        "meta": {
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "engine": engine,
            "title": title,
            "defaultExcluded": list(smap.default_excluded),
        },
        "summary": {
            **summary,
            "avgAll": summary["avg"],
        },
        "services": aggregate_services(endpoints),
        "subtypes": aggregate_subtypes(endpoints),
        "methods": aggregate_methods(endpoints),
        "missingTop": top_missing_p1(endpoints),
        "heatmap": heatmap(endpoints),
        "endpoints": endpoints,
    }
