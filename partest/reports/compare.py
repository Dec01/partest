"""Compare two coverage.json payloads.

A raw percentage diff answers the wrong question. Coverage drops for two very
different reasons: the suite lost a test case, or this run simply did not touch the
endpoint (a filtered selection, an unmerged parallel run, a failed fixture). Only the
first is a regression. The comparison separates them so a pipeline does not raise an
alarm about a partial run, or stay quiet about a real loss hidden behind one.
"""

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
    not_run: list[dict[str, Any]] = []
    missing_fixed: list[str] = []
    missing_new: list[str] = []

    for key in sorted(old_keys & new_keys):
        a, b = old_eps[key], new_eps[key]
        da = float(a.get("coverage") or 0.0)
        db = float(b.get("coverage") or 0.0)
        delta = round(db - da, 2)
        # An endpoint nobody called this run tells us nothing about the suite. Report
        # it separately instead of counting it as a regression.
        became_unseen = b.get("kind") == "unseen" and a.get("kind") != "unseen"
        if became_unseen:
            not_run.append({"endpoint": key, "from": da, "to": db, "delta": delta})
        elif delta > 0.009:
            improved.append({"endpoint": key, "from": da, "to": db, "delta": delta})
        elif delta < -0.009:
            regressed.append({"endpoint": key, "from": da, "to": db, "delta": delta})

        if became_unseen:
            # Its "missing" list is an artefact of not running, not a lost test case.
            continue
        old_miss = set(a.get("missing") or [])
        new_miss = set(b.get("missing") or [])
        for tc in sorted(old_miss - new_miss):
            missing_fixed.append(f"{key} :: {tc}")
        for tc in sorted(new_miss - old_miss):
            missing_new.append(f"{key} :: {tc}")

    old_avg = float((old.get("summary") or {}).get("avg") or 0.0)
    new_avg = float((new.get("summary") or {}).get("avg") or 0.0)
    warnings = _run_warnings(old, new, not_run)
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
        "not_run": not_run,
        "comparable": not warnings,
        "warnings": warnings,
    }


def _run_warnings(old: dict, new: dict, not_run: list) -> list[str]:
    """Reasons the two payloads may not be comparable at all."""
    messages: list[str] = []
    for label, payload in (("previous", old), ("current", new)):
        meta = payload.get("meta") or {}
        workers = int(meta.get("workers") or 1)
        if workers > 1 and not meta.get("merged", True):
            messages.append(
                f"{label} run used {workers} workers without merging — "
                f"its numbers are one worker's slice, not the suite"
            )
        elif meta.get("partialRun"):
            ratio = meta.get("unseenRatio")
            messages.append(
                f"{label} run looks partial"
                + (f" ({ratio:.0%} of endpoints never called)" if isinstance(ratio, float) else "")
            )
    if not_run:
        messages.append(
            f"{len(not_run)} endpoint(s) were covered before and not called at all now; "
            f"they are reported under 'not_run', not as regressions"
        )
    return messages
