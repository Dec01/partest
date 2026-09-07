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


def _kind_of(ep: dict) -> str:
    """``kind``, inferred when the snapshot predates it.

    Snapshots written before ``kind`` existed carry only ``calls`` and the legacy
    ``status``. Reading a missing key as "not unseen" made every uncalled endpoint look
    like one that used to be covered — and comparing against an older snapshot is exactly
    what people do while upgrading, so the wrong answer arrived at the worst moment.

    Zero calls is what ``unseen`` means, and it is the only distinction this module needs;
    for anything that was called we return "" rather than guessing between partial and full.
    """
    kind = ep.get("kind")
    if kind:
        return str(kind)
    return "unseen" if int(ep.get("calls") or 0) == 0 else ""


def _calls_total(payload: dict) -> int:
    """Summed from the endpoints, so it works on payloads written before ``meta``."""
    return sum(int(e.get("calls") or 0) for e in (payload.get("endpoints") or []))


def _unseen_fraction(payload: dict) -> float:
    endpoints = payload.get("endpoints") or []
    if not endpoints:
        return 0.0
    return sum(1 for e in endpoints if _kind_of(e) == "unseen") / len(endpoints)


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
        became_unseen = _kind_of(b) == "unseen" and _kind_of(a) != "unseen"
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


#: A run that made less than this share of the previous run's calls did not exercise the
#: same suite. Deliberately conservative: two full runs of one suite stay far above it.
_CALL_VOLUME_FLOOR = 0.5


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
            continue
        selection = meta.get("selection") or {}
        expression = selection.get("markexpr") or selection.get("keyword")
        if expression:
            messages.append(
                f"{label} run selected a subset of the suite ({expression!r}"
                + (f", {selection['deselected']} tests deselected"
                   if selection.get("deselected") else "")
                + ") — its coverage describes that subset"
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
    messages.extend(_call_volume_warning(old, new))
    return messages


def _call_volume_warning(old: dict, new: dict) -> list[str]:
    """Catch a filtered run that the endpoint-level view cannot see.

    Coverage is scored per test case, but ``unseen`` is a property of an endpoint. A
    marker filter removes *cases*: the endpoint is still called, it just loses one cell.
    So ``unseenRatio`` stays near zero while a large share of the suite did not run, and
    every lost cell is presented as a regression with the comparison marked comparable.

    A collapse in call volume without a matching rise in never-called endpoints is that
    situation's signature, and it reads from the endpoints themselves — so it also works
    against snapshots written before ``meta`` existed, which is when it is needed most.
    """
    old_calls, new_calls = _calls_total(old), _calls_total(new)
    if old_calls <= 0 or new_calls >= old_calls * _CALL_VOLUME_FLOOR:
        return []
    # A rise in never-called endpoints is already reported through not_run; this warning
    # is about the drop that leaves no trace there.
    if _unseen_fraction(new) - _unseen_fraction(old) >= 0.1:
        return []
    return [
        f"current run made {new_calls} calls against {old_calls} before "
        f"({1 - new_calls / old_calls:.0%} fewer) while the share of never-called "
        f"endpoints barely moved — a filter that drops test cases rather than whole "
        f"endpoints, so lost cells appear under 'regressed' without being lost"
    ]
