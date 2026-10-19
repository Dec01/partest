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


def _unseen_fraction(payload: dict) -> float | None:
    """``None`` when the payload has no endpoints at all.

    A share over an empty set is a constant by construction, and ``0.0`` reads as
    "nothing went untouched" — the opposite of the truth, which is that nothing was
    measured. The caller has to decide what an absent measurement means; it cannot be
    folded into a number.
    """
    endpoints = payload.get("endpoints") or []
    if not endpoints:
        return None
    return sum(1 for e in endpoints if _kind_of(e) == "unseen") / len(endpoints)


def _measured_nothing(payload: dict) -> bool:
    """The payload says it had no endpoints: ``summary.endpoints == 0`` or ``endpoints: []``.

    A numeric ``summary.endpoints`` is the measurement and decides: a payload trimmed to
    ``endpoints: []`` that says ``summary.endpoints: 12`` had twelve. Only without it does an
    empty list count. A payload with neither key (older than both) says nothing, and is not
    taken as empty.
    """
    summary = payload.get("summary") or {}
    count = summary.get("endpoints")
    if isinstance(count, (int, float)) and not isinstance(count, bool):
        return count == 0
    return "endpoints" in payload and not payload.get("endpoints")


def _summary_avg(payload: dict) -> float | None:
    """``summary.avg``; ``None`` — not measured — for a run with no endpoints.

    ``null`` is what a run with no endpoints writes from 2.7.0 on. Releases before it wrote
    ``0.0`` there; with zero endpoints that zero is read as "not measured" too, as
    ``validate_coverage_payload`` reads it — otherwise a 2.6 baseline of an empty run turns
    the next run's whole average into a delta and the pair into a comparable one. A
    ``0.0`` with endpoints is a measured zero; a missing ``summary.avg`` reads as ``0.0``,
    as before.
    """
    summary = payload.get("summary") or {}
    if "avg" not in summary:
        return 0.0
    if summary["avg"] is None:
        return None
    avg = float(summary["avg"] or 0.0)
    if avg == 0.0 and _measured_nothing(payload):
        return None
    return avg


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

    old_avg = _summary_avg(old)
    new_avg = _summary_avg(new)
    # A difference with an unmeasured side is not a number: `new_avg - 0` would present the
    # whole of the other run's average as a change. The delta is `null`, and a warning says
    # which run measured nothing.
    avg_delta = (
        round(new_avg - old_avg, 2) if old_avg is not None and new_avg is not None else None
    )
    warnings = _run_warnings(old, new, not_run)
    notes = _optin_one_sided_note(old, new)
    return {
        "old_avg": old_avg,
        "new_avg": new_avg,
        "avg_delta": avg_delta,
        "coverage_delta": avg_delta,
        "added": added,
        "removed": removed,
        "improved": improved,
        "regressed": regressed,
        "missing_fixed": missing_fixed,
        "missing_new": missing_new,
        "not_run": not_run,
        "comparable": not warnings,
        "warnings": warnings,
        # Soft remarks: they do not decide `comparable`, because the evidence is one-sided.
        "notes": notes,
    }


#: A run that made less than this share of the previous run's calls did not exercise the
#: same suite. Deliberately conservative: two full runs of one suite stay far above it.
_CALL_VOLUME_FLOOR = 0.5


def _run_warnings(old: dict, new: dict, not_run: list) -> list[str]:
    """Reasons the two payloads may not be comparable at all."""
    messages: list[str] = []
    for label, payload in (("previous", old), ("current", new)):
        if _summary_avg(payload) is None:
            messages.append(
                f"{label} run has no endpoints — its average coverage is null (not measured), "
                f"so avg_delta is null"
                + ("" if (payload.get("summary") or {}).get("avg") is None
                   else "; its 0.0 is how releases before 2.7.0 wrote an empty run")
            )
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
    messages.extend(_optin_warning(old, new))
    if not_run:
        messages.append(
            f"{len(not_run)} endpoint(s) were covered before and not called at all now; "
            f"they are reported under 'not_run', not as regressions"
        )
    messages.extend(_call_volume_warning(old, new))
    return messages


def _optin_states(payload: dict) -> "dict | None":
    """Each set's state, or ``None`` when there is no record — also when *payload*, its
    ``meta`` or its ``selection`` is not a mapping (``None``, a list): no record to read."""
    if not isinstance(payload, dict):
        return None
    meta = payload.get("meta")
    selection = meta.get("selection") if isinstance(meta, dict) else None
    optin = selection.get("optin") if isinstance(selection, dict) else None
    if not isinstance(optin, dict):
        return None
    return {
        str(name): (info.get("state") if isinstance(info, dict) else None)
        for name, info in optin.items()
    }


def optin_comparable(old: dict, new: dict) -> "tuple[bool | None, list[str]]":
    """Did two runs select the same opt-in marker sets? ``(verdict, changes)``.

    ``old`` and ``new`` are ``coverage.json`` payloads (``build_payload`` documents). Each
    set's state — ``env``, ``markexpr`` or ``off`` — is read from ``meta.selection.optin``:

    * ``(True, [])`` — both payloads carry the record and every set has the same state;
    * ``(False, changes)`` — both carry it and they differ; ``changes`` has one line per set,
      ``"slow: off → env"`` (``absent`` for a set only one run declared, ``recorded
      without a state`` for a malformed record), sorted by name;
    * ``(None, [])`` — at least one payload has no record: an artifact older than the key, a
      project without opt-in sets, or not a payload at all (``None``, a list). Nothing proves
      the runs differ or match; for two real payloads :func:`compare_payloads` does not flag
      such a pair (it may add a soft ``notes`` line) — it takes payloads only, not ``None``.

    An opt-in set is deselected, not skipped, so nothing else in the payload shows it: the
    run with the expensive set switched on simply has more cases. :func:`compare_payloads`
    marks a ``False`` pair not ``comparable``; this is the same verdict for a reader that
    needs it alone.
    """
    before, after = _optin_states(old), _optin_states(new)
    if before is None or after is None:
        return None, []
    if before == after:
        return True, []
    def shown(states: dict, name: str) -> str:
        if name not in states:
            return "absent"
        return str(states[name]) if states[name] else "recorded without a state"

    changed = [
        f"{name}: {shown(before, name)} → {shown(after, name)}"
        for name in sorted(set(before) | set(after))
        if before.get(name) != after.get(name) or (name in before) != (name in after)
    ]
    return False, changed


def _optin_warning(old: dict, new: dict) -> list[str]:
    """Two runs that ran different opt-in marker sets did not run the same suite.

    Compared only when both payloads carry ``meta.selection.optin`` — an older artifact, or
    a project without opt-in sets, says nothing either way, and guessing would flag every
    such pair. See :func:`optin_comparable`.
    """
    verdict, changed = optin_comparable(old, new)
    if verdict is not False:
        return []
    return [
        "the runs selected different opt-in marker sets (" + "; ".join(changed)
        + ") — they did not run the same suite"
    ]


def _optin_one_sided_note(old: dict, new: dict) -> list[str]:
    """Only one payload carries ``meta.selection.optin``, and in it a set did something.

    The other payload is older than the key, or came from a project without opt-in sets:
    nothing proves the two runs differ, so this does not touch ``comparable`` — but a run
    that deselected a set, or ran one through its variable, may well not match a run that
    cannot say what it did.
    """
    sides = {"previous": _optin_records(old), "current": _optin_records(new)}
    present = [label for label, rec in sides.items() if rec is not None]
    if len(present) != 1:
        return []
    recorded = present[0]
    missing = "current" if recorded == "previous" else "previous"
    acted = {
        name: info for name, info in sides[recorded].items()
        if int((info or {}).get("deselected") or 0) > 0 or (info or {}).get("state") == "env"
    }
    if not acted:
        return []
    described = ", ".join(
        f"{name}: "
        + (f"deselected {int(info.get('deselected') or 0)}"
           if int(info.get("deselected") or 0) > 0 else "enabled by env")
        for name, info in sorted(acted.items())
    )
    return [
        f"{missing} run carries no opt-in record; {recorded} {described} — "
        "comparability cannot be confirmed"
    ]


def _optin_records(payload: dict) -> "dict | None":
    selection = (payload.get("meta") or {}).get("selection") or {}
    optin = selection.get("optin")
    return optin if isinstance(optin, dict) else None


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
    # is about the drop that leaves no trace there. A payload with no endpoints measured
    # no such rise — it explains nothing, so the warning stands rather than being
    # suppressed by an "unseen share of zero" that was never observed.
    old_unseen, new_unseen = _unseen_fraction(old), _unseen_fraction(new)
    if old_unseen is not None and new_unseen is not None and new_unseen - old_unseen >= 0.1:
        return []
    return [
        f"current run made {new_calls} calls against {old_calls} before "
        f"({1 - new_calls / old_calls:.0%} fewer) while the share of never-called "
        f"endpoints barely moved — a filter that drops test cases rather than whole "
        f"endpoints, so lost cells appear under 'regressed' without being lost"
    ]
