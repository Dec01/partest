"""CoverageReport → JSON payload + aggregates (service map is injected)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

from partest.call_storage import run_info, unknown_tls_hosts, unverified_hosts
from partest.reports._rules import AVG_RULE, COUNT_LIMIT, is_exception_row
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



def _percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile. Small samples are the norm here, so no interpolation."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(pct / 100.0 * len(ordered) + 0.5)) - 1))
    return float(ordered[index])


def timing_of(metas: Sequence[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Latency summary for one endpoint, or None when nothing was measured.

    Same caveat as coverage: without merged workers this only describes the calls
    one process made.
    """
    samples = [
        float(m["elapsed_ms"])
        for m in metas or []
        if isinstance(m, dict) and isinstance(m.get("elapsed_ms"), (int, float))
    ]
    if not samples:
        return None

    by_type: dict[str, list[float]] = {}
    for meta in metas:
        value = meta.get("elapsed_ms")
        if not isinstance(value, (int, float)):
            continue
        by_type.setdefault(_label_type(meta.get("type") or "unknown"), []).append(float(value))

    return {
        "n": len(samples),
        "msAvg": round(sum(samples) / len(samples), 2),
        "msP50": round(_percentile(samples, 50), 2),
        "msP95": round(_percentile(samples, 95), 2),
        "msMax": round(max(samples), 2),
        "byType": {
            name: {
                "n": len(values),
                "msAvg": round(sum(values) / len(values), 2),
                "msP95": round(_percentile(values, 95), 2),
            }
            for name, values in sorted(by_type.items())
        },
    }


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
    timing = timing_of(_get(ep, "depth_hints") or [])
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
        "kind": _get(ep, "kind") or "unseen",
        "executed": executed,
        "missing": missing,
        "description": ep.description or "",
        # Axis C, apart from the percentage: of the required cells this run filled, how
        # many some call asked to be checked for the status, for the schema (the arguments
        # it was given, not what passed); `values` is not measured. `null` — nothing
        # measured (no filled cell, an `exception` row, a client without those arguments).
        "depth": _depth_dict(_get(ep, "depth")),
        **({"timing": timing} if timing else {}),
    }


def _depth_dict(depth: Any) -> Optional[dict[str, Any]]:
    """The depth counts when they are what the format writes — integers with
    ``0 < cells``, ``0 <= schema <= status <= cells``, none beyond ``COUNT_LIMIT`` — else
    ``None``. Rows read back from a file (``summarize`` on dicts) may carry anything."""
    if not isinstance(depth, dict):
        return None
    counts = [depth.get(key, 0) for key in ("cells", "status", "schema")]
    if any(isinstance(v, bool) or not isinstance(v, int) for v in counts):
        return None
    cells, status, schema = counts
    if not 0 < cells <= COUNT_LIMIT or not 0 <= schema <= status <= cells:
        return None
    return {"cells": cells, "status": status, "schema": schema, "values": None}


def summarize_depth(endpoints: Sequence[Any]) -> Optional[dict[str, Any]]:
    """Axis C over a set of endpoints, pooled by cell; ``None`` when no cell was measured.

    ``statusPct`` / ``schemaPct`` — the share of measured cells where some call asked for at
    least a status check / a schema check. Pooled, not averaged over endpoints: one test case is one
    cell, and an endpoint with seven cells says seven things about depth. ``exception`` rows
    are outside, as they are outside the average.
    """
    cells = status = schema = 0
    for ep in endpoints:
        if is_exception_row(ep):
            continue
        depth = _depth_dict(_get(ep, "depth"))
        if depth is None:
            continue
        cells += depth["cells"]
        status += depth["status"]
        schema += depth["schema"]
    if not cells:
        return None
    return {
        "cells": cells,
        "status": status,
        "schema": schema,
        "values": None,
        "statusPct": round(status / cells * 100.0, 2),
        "schemaPct": round(schema / cells * 100.0, 2),
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
        total_calls += calls
        if is_exception_row(ep):
            # Counted, not scored (`AVG_RULE` 2): an `exception` row's 100 % means "the
            # matrix does not apply here", and averaged in it lifted the number as much as
            # a fully tested endpoint.
            exc += 1
            continue
        total_pct += pct
        if status == "full":
            full += 1
        elif status == "partial":
            partial += 1
        else:
            empty += 1
    scored = n - exc
    return {
        # An average over no endpoints is not a measurement. `0.0` here read as "nothing is
        # covered" — the same number a run that called everything and covered nothing would
        # give — so a run that collected no endpoints is `null`, as `meta.unseenRatio` is.
        # The same for a set of `exception` rows only: nothing in it is scored.
        "avg": round(total_pct / scored, 2) if scored else None,
        "calls": total_calls,
        "full": full,
        "partial": partial,
        "empty": empty,
        "exception": exc,
        "endpoints": n,
        "scored": scored,
        "depth": summarize_depth(endpoints),
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
        # `exception` rows are not covered work (`AVG_RULE` 2); `exception` counts them.
        covered = stats["full"] + stats["partial"]
        rows.append(
            {
                "key": key,
                "label": bucket["label"],
                "totalEndpoints": stats["endpoints"],
                # The rows the average and `covered` are taken from: all but `exception`.
                "scored": stats["scored"],
                "covered": covered,
                "calls": stats["calls"],
                "full": stats["full"],
                "partial": stats["partial"],
                "empty": stats["empty"],
                "exception": stats["exception"],
                "avgCoverage": stats["avg"],
            }
        )
    rows.sort(key=_by_avg_coverage)
    return rows


def _by_avg_coverage(row: dict[str, Any]) -> tuple:
    """Highest average first, then by label; a row without an average goes last.

    A row has no average when every endpoint in it is `exception` (`AVG_RULE` 2): nothing
    in it is scored.
    """
    avg = row.get("avgCoverage")
    return (avg is None, -(avg or 0.0), row.get("label") or "")


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
                "scored": stats["scored"],
                "calls": stats["calls"],
                "full": stats["full"],
                "partial": stats["partial"],
                "empty": stats["empty"],
                "exception": stats["exception"],
            }
        )
    rows.sort(key=_by_avg_coverage)
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
                "scored": stats["scored"],
                "exception": stats["exception"],
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
    counts: Counter[tuple[str, str]] = Counter()
    services: dict[str, str] = {}
    subtypes: dict[str, str] = {}
    for ep in endpoints:
        s_key = str(_get(ep, "service") or "unknown")
        t_key = str(_get(ep, "subtypeKey") or _get(ep, "subtype") or "unknown")
        services[s_key] = str(_get(ep, "serviceLabel") or s_key)
        subtypes[t_key] = str(_get(ep, "subtype") or t_key)
        counts[(s_key, t_key)] += 1
        if not is_exception_row(ep):
            cells[(s_key, t_key)].append(float(_get(ep, "coverage", "coverage_pct") or 0.0))
    matrix = []
    # A cell exists once an endpoint is in it, and an empty run has no cells. Its average
    # is over the rows that are not `exception` (`AVG_RULE` 2), `null` when there are none.
    for (s_key, t_key), count in counts.items():
        values = cells.get((s_key, t_key)) or []
        matrix.append(
            {
                "service": s_key,
                "subtype": t_key,
                "avg": round(sum(values) / len(values), 2) if values else None,
                "count": count,
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

    workers = int(run_info.get("workers", 1) or 1)
    merged = bool(run_info.get("merged", False))
    calls_total = sum(int(e.get("calls") or 0) for e in endpoints)
    unseen = sum(1 for e in endpoints if e.get("kind") == "unseen")
    # A run that collected no endpoints at all — a failed fixture, an unmerged worker
    # shard, an empty specification — measured nothing. `0.0` would ship "none of the
    # endpoints went untouched" into the artifact, which is the most reassuring reading
    # of the least informative run. `null` is the value that cannot be mistaken for a
    # measurement.
    unseen_ratio = round(unseen / len(endpoints), 4) if endpoints else None
    selection = dict(run_info.get("selection") or {})
    # Three ways this run fails to describe the suite: a lot of endpoints went untouched,
    # parallel workers were never merged, or the run selected a subset in the first place.
    # The third needs asking, not measuring: a marker filter drops test *cases*, so the
    # endpoint is still called and `unseen_ratio` stays near zero while half the suite
    # never ran. Without this, such a run compared against a full one reports every
    # dropped cell as a regression, and calls the comparison sound.
    #
    # An unmeasured ratio is not a fourth reason. `partialRun` is a bool and every reader
    # of it phrases the same claim — "some endpoints were never called" — which is false,
    # not true, for a run that has no endpoints to call. That claim now belongs to
    # `unseenRatio: null`, which says "not measured" without pretending to be a count.
    partial_run = (
        (unseen_ratio is not None and unseen_ratio >= 0.2)
        or (workers > 1 and not merged)
        or bool(selection.get("markexpr") or selection.get("keyword"))
    )

    all_metas: list[dict[str, Any]] = []
    for ep in report.endpoints:
        all_metas.extend(getattr(ep, "depth_hints", None) or [])
    run_timing = timing_of(all_metas)

    return {
        "meta": {
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "engine": engine,
            "title": title,
            "defaultExcluded": list(smap.default_excluded),
            "workers": workers,
            "merged": merged,
            "partialRun": partial_run,
            "callsTotal": calls_total,
            "unseenRatio": unseen_ratio,
            # The rule `summary.avg`, `avgCoverage`, the heatmap and `covered` follow — see
            # `AVG_RULE`. A reader that trends the average compares it within one rule.
            "avgRule": AVG_RULE,
            # A run without certificate verification is a fact about the artifact, not
            # about one call: the warning it emitted does not outlive the session, and
            # whoever reads the report a week later has no other way to know. It does not
            # touch `comparable` — an unverified run is still a valid measurement of
            # coverage.
            "tlsVerified": bool(run_info.get("tlsVerified", True)),
            # Which hosts, not only whether. `tlsVerified` is one bit for the run and a
            # single auxiliary service switches it off — a self-signed certificate reached
            # while a plugin configures itself made every run of one project report
            # `false`, including the runs that never called the API. These two lists are
            # added next to the flag and never instead of it: reading them is optional,
            # and a consumer that knows only `tlsVerified` reads exactly what it did
            # before. Empty lists are emitted rather than omitted, so "nothing was
            # accepted unverified" and "an older artifact" stay distinguishable.
            "tlsUnverifiedHosts": sorted(unverified_hosts),
            "tlsUnknownHosts": sorted(unknown_tls_hosts),
            **({"selection": selection} if selection else {}),
        },
        **({"timing": run_timing} if run_timing else {}),
        "summary": {
            **summary,
            # `null` together with `avg` when the run has no endpoints.
            "avgAll": summary["avg"],
        },
        "services": aggregate_services(endpoints),
        "subtypes": aggregate_subtypes(endpoints),
        "methods": aggregate_methods(endpoints),
        "missingTop": top_missing_p1(endpoints),
        "heatmap": heatmap(endpoints),
        "endpoints": endpoints,
    }
