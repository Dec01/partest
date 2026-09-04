"""Compare two coverage.json payloads (LIB-COV-CMP)."""

from __future__ import annotations

from typing import Any


def _ep_key(ep: dict) -> str:
    return f"{ep.get('method', '').upper()} {ep.get('path', '')}"


def compare_payloads(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Diff two ``build_payload`` JSON documents."""
    old_eps = {_ep_key(e): e for e in (old.get("endpoints") or [])}
    new_eps = {_ep_key(e): e for e in (new.get("endpoints") or [])}
    old_keys = set(old_eps)
    new_keys = set(new_eps)

    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)

    improved: list[dict[str, Any]] = []
    regressed: list[dict[str, Any]] = []
    missing_fixed: list[str] = []
    missing_new: list[str] = []

    for key in sorted(old_keys & new_keys):
        a, b = old_eps[key], new_eps[key]
        da = float(a.get("coverage") or 0.0)
        db = float(b.get("coverage") or 0.0)
        delta = round(db - da, 2)
        if delta > 0.009:
            improved.append({"endpoint": key, "from": da, "to": db, "delta": delta})
        elif delta < -0.009:
            regressed.append({"endpoint": key, "from": da, "to": db, "delta": delta})
        old_miss = set(a.get("missing") or [])
        new_miss = set(b.get("missing") or [])
        for tc in sorted(old_miss - new_miss):
            missing_fixed.append(f"{key} :: {tc}")
        for tc in sorted(new_miss - old_miss):
            missing_new.append(f"{key} :: {tc}")

    old_avg = float((old.get("summary") or {}).get("avg") or 0.0)
    new_avg = float((new.get("summary") or {}).get("avg") or 0.0)
    return {
        "old_avg": old_avg,
        "new_avg": new_avg,
        "avg_delta": round(new_avg - old_avg, 2),
        "coverage_delta": round(new_avg - old_avg, 2),
        "added": added,
        "removed": removed,
        "improved": improved,
        "regressed": regressed,
        "missing_fixed": missing_fixed,
        "missing_new": missing_new,
    }
