"""Compare two coverage.json payloads.

A raw percentage diff answers the wrong question. Coverage drops for two very
different reasons: the suite lost a test case, or this run simply did not touch the
endpoint (a filtered selection, an unmerged parallel run, a failed fixture). Only the
first is a regression. The comparison separates them so a pipeline does not raise an
alarm about a partial run, or stay quiet about a real loss hidden behind one.
"""

from __future__ import annotations

from typing import Any

from partest.reports._rules import (
    avg_rule_of,
    count,
    finite,
    is_exception_row,
    is_known_rule,
    STATUS_COUNTERS,
    shown,
    status_counts,
    str_list,
    text,
)

# Everything here reads a document someone else may have written: a value of the wrong type
# is read as absent (`count`, `text`, `str_list`, `finite`, `_mapping`, `_rows`), never raised
# on — a comparison that crashes on one bad row tells the pipeline nothing.


def _rows(payload: dict) -> list:
    """The endpoint rows that are objects; ``[]`` when ``endpoints`` is not a list."""
    endpoints = payload.get("endpoints")
    return [e for e in endpoints if isinstance(e, dict)] if isinstance(endpoints, list) else []


def _ep_key(ep: dict) -> str:
    return f"{text(ep.get('method')).upper()} {text(ep.get('path'))}"


def _kind_of(ep: dict) -> str:
    """``kind``, inferred when the snapshot predates it.

    Snapshots written before ``kind`` existed carry only ``calls`` and the legacy
    ``status``. Reading a missing key as "not unseen" made every uncalled endpoint look
    like one that used to be covered — and comparing against an older snapshot is exactly
    what people do while upgrading, so the wrong answer arrived at the worst moment.

    Zero calls is what ``unseen`` means, and it is the only distinction this module needs;
    for anything that was called we return "" rather than guessing between partial and full.
    """
    kind = text(ep.get("kind"))
    if kind:
        return kind
    return "unseen" if count(ep.get("calls")) == 0 else ""


def _calls_total(payload: dict) -> int:
    """Summed from the endpoints, so it works on payloads written before ``meta``."""
    return sum(count(e.get("calls")) for e in _rows(payload))


def _unseen_fraction(payload: dict) -> float | None:
    """``None`` when the payload has no endpoints at all.

    A share over an empty set is a constant by construction, and ``0.0`` reads as
    "nothing went untouched" — the opposite of the truth, which is that nothing was
    measured. The caller has to decide what an absent measurement means; it cannot be
    folded into a number.
    """
    endpoints = _rows(payload)
    if not endpoints:
        return None
    return sum(1 for e in endpoints if _kind_of(e) == "unseen") / len(endpoints)


def _mapping(value: Any) -> dict:
    """*value* when it is a mapping, else ``{}``: a document is read, not trusted."""
    return value if isinstance(value, dict) else {}


def _summary(payload: dict) -> dict:
    return _mapping(payload.get("summary"))


def _measured_nothing(payload: dict) -> bool:
    """The payload says it had no endpoints: ``summary.endpoints == 0`` or ``endpoints: []``.

    A numeric ``summary.endpoints`` is the measurement and decides: a payload trimmed to
    ``endpoints: []`` that says ``summary.endpoints: 12`` had twelve. Only without it does an
    empty list count. A payload with neither key (older than both) says nothing, and is not
    taken as empty.
    """
    count = _summary(payload).get("endpoints")
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
    as before. A value that is not a finite number is not a measurement either.
    """
    summary = _summary(payload)
    if "avg" not in summary:
        return 0.0
    if summary["avg"] is None:
        return None
    avg = finite(summary["avg"] or 0.0)
    if avg is None or (avg == 0.0 and _measured_nothing(payload)):
        return None
    return avg


def _summary_depth(payload: dict) -> dict | None:
    """``summary.depth`` shares when both are finite numbers; ``None`` otherwise."""
    depth = _summary(payload).get("depth")
    if not isinstance(depth, dict):
        return None
    shares = {key: finite(depth.get(key)) for key in ("statusPct", "schemaPct")}
    if any(v is None for v in shares.values()):
        return None
    return shares


def _exception_rows(payload: dict) -> int | None:
    """How many ``exception`` endpoints the payload has; ``None`` when it cannot say."""
    recorded = _summary(payload).get("exception")
    if isinstance(recorded, int) and not isinstance(recorded, bool):
        return count(recorded)
    if isinstance(payload.get("endpoints"), list):
        return sum(1 for e in _rows(payload) if is_exception_row(e))
    return None


def _all_exception(payload: dict) -> bool:
    """The payload has endpoints and every one of them is ``exception``."""
    exceptions = _exception_rows(payload)
    total = _summary(payload).get("endpoints")
    if not (isinstance(total, int) and not isinstance(total, bool)):
        endpoints = payload.get("endpoints")
        total = len(endpoints) if isinstance(endpoints, list) else None
    return bool(total) and exceptions == total


def _rule_of(payload: dict) -> Any:
    return avg_rule_of(_mapping(payload.get("meta")))


def _recompute_under_rule_2(payload: dict) -> Any:
    """The payload's average recomputed from its rows without ``exception`` — the rule this
    package writes. ``False`` when that cannot be done honestly: the rows are not all in the
    file (fewer than ``summary.endpoints``, or status counts in ``summary`` the rows do not
    add up to), or a row carries a value that is not what the format writes."""
    from partest.reports.payload import _depth_dict, summarize

    endpoints = payload.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        return False
    rows = _rows(payload)
    if len(rows) != len(endpoints):
        return False
    summary = _summary(payload)
    total = summary.get("endpoints")
    if isinstance(total, int) and not isinstance(total, bool) and total != len(rows):
        return False  # trimmed: the rows are not the run
    seen = status_counts(rows)
    for key in STATUS_COUNTERS:
        recorded = summary.get(key)
        if isinstance(recorded, int) and not isinstance(recorded, bool) and recorded != seen[key]:
            return False
    for e in rows:
        if finite(e.get("coverage") or 0.0) is None:
            return False
        calls = e.get("calls")
        if calls is not None and (isinstance(calls, bool) or not isinstance(calls, int)):
            return False
        depth = e.get("depth")
        if depth is not None and _depth_dict(depth) is None and not (
            isinstance(depth, dict) and depth.get("cells") == 0
        ):
            return False
    try:
        return summarize(rows)["avg"]
    except (TypeError, ValueError, OverflowError):
        return False


def _effective_averages(old: dict, new: dict) -> tuple:
    """Both averages under one rule: ``(avgs, warnings, notes, recomputed)``.

    Rule 1 (no ``meta.avgRule``, as every release before 2.7.0 wrote, or ``1``) put an
    ``exception`` row into the average as 100 %; rule 2 leaves it out. A rule-1 side without
    such rows has the same number under both. With them, its average is recomputed from its
    own rows by the same ``summarize`` that writes the other side — a note says so and
    ``avg_recomputed`` carries both numbers; only when the rows cannot be used is the pair
    left without a trend (a warning). A rule this package does not know is never recomputed:
    a warning, and the averages as recorded.
    """
    avgs = {"previous": _summary_avg(old), "current": _summary_avg(new)}
    payloads = {"previous": old, "current": new}
    rules = {label: _rule_of(payload) for label, payload in payloads.items()}
    unknown = [label for label, rule in rules.items() if not is_known_rule(rule)]
    if unknown:
        return avgs, [
            f"{label} run declares meta.avgRule {shown(rules[label])}, a rule this package "
            f"does not know — its average is not recomputed, so avg_delta is not a trend"
            for label in unknown
        ], [], None
    if rules["previous"] == rules["current"]:
        return avgs, [], [], None
    label = "previous" if rules["previous"] == 1 else "current"
    exceptions = _exception_rows(payloads[label])
    if exceptions == 0:
        return avgs, [], [], None
    what = (
        f"{exceptions} exception endpoint(s)" if exceptions is not None
        else "its exception endpoints"
    )
    value = _recompute_under_rule_2(payloads[label])
    if value is False:
        return avgs, [
            f"{label} run averaged under rule 1 (no meta.avgRule, or 1: {what} inside the "
            f"average as 100 %) and its rows cannot be used to recompute it — not all in the "
            f"file, or not in the format — so avg_delta is not a trend"
        ], [], None
    recomputed = {"side": label, "recorded": avgs[label], "recomputed": value}
    avgs[label] = value
    if value is None:
        # Every row is `exception`: nothing to average. The "no scored endpoints" warning
        # says it; a note with `None` in it would say nothing more.
        return avgs, [], [], recomputed
    recorded = recomputed["recorded"]
    return avgs, [], [
        f"{label} run averaged under rule 1 (no meta.avgRule, or 1): its average counted "
        f"{what} as 100 % ({recorded if recorded is not None else 'not a number'}); "
        f"recomputed from its rows without them: {value}"
    ], recomputed


def compare_payloads(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Diff two ``build_payload`` JSON documents."""
    old_eps = {_ep_key(e): e for e in _rows(old)}
    new_eps = {_ep_key(e): e for e in _rows(new)}
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
        da = finite(a.get("coverage")) or 0.0
        db = finite(b.get("coverage")) or 0.0
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
        old_miss = set(str_list(a.get("missing")))
        new_miss = set(str_list(b.get("missing")))
        for tc in sorted(old_miss - new_miss):
            missing_fixed.append(f"{key} :: {tc}")
        for tc in sorted(new_miss - old_miss):
            missing_new.append(f"{key} :: {tc}")

    avgs, rule_warnings, rule_notes, recomputed = _effective_averages(old, new)
    old_avg, new_avg = avgs["previous"], avgs["current"]
    # A difference with an unmeasured side is not a number: `new_avg - 0` would present the
    # whole of the other run's average as a change. The delta is `null`, and a warning says
    # which run measured nothing.
    avg_delta = (
        round(new_avg - old_avg, 2) if old_avg is not None and new_avg is not None else None
    )
    warnings = _run_warnings(old, new, not_run, avgs) + rule_warnings
    notes = _optin_one_sided_note(old, new) + rule_notes
    old_depth, new_depth = _summary_depth(old), _summary_depth(new)
    return {
        "old_avg": old_avg,
        "new_avg": new_avg,
        "avg_delta": avg_delta,
        "coverage_delta": avg_delta,
        # When one side was written under the old rule for `exception` endpoints (no
        # `meta.avgRule`) and has such rows: which side, its recorded average and the one
        # recomputed without them, which `old_avg` / `new_avg` carry. `null` otherwise.
        "avg_recomputed": recomputed,
        # Axis C, in percentage points of measured cells; `null` when either side has no
        # `summary.depth` — not measured, or written by a release without depth.
        "depth_delta": (
            {
                key: round(new_depth[key] - old_depth[key], 2)
                for key in ("statusPct", "schemaPct")
            }
            if old_depth is not None and new_depth is not None
            else None
        ),
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


def _run_warnings(old: dict, new: dict, not_run: list, avgs: dict | None = None) -> list[str]:
    """Reasons the two payloads may not be comparable at all."""
    messages: list[str] = []
    if avgs is None:
        avgs = {"previous": _summary_avg(old), "current": _summary_avg(new)}
    for label, payload in (("previous", old), ("current", new)):
        if avgs[label] is None and _all_exception(payload):
            # Endpoints, and an average of `null`: every one of them is `exception`
            # (`meta.avgRule` 2), so nothing was scored.
            messages.append(
                f"{label} run has no scored endpoints (all of them are exception) — its "
                f"average coverage is null (not measured), so avg_delta is null"
            )
        elif avgs[label] is None and not _measured_nothing(payload) and (
            _summary(payload).get("avg") is not None
        ):
            messages.append(
                f"{label} run has an average that is not a finite number — not a "
                f"measurement, so avg_delta is null"
            )
        elif avgs[label] is None:
            messages.append(
                f"{label} run has no endpoints — its average coverage is null (not measured), "
                f"so avg_delta is null"
                + ("" if _summary(payload).get("avg") is None
                   else "; its 0.0 is how releases before 2.7.0 wrote an empty run")
            )
        meta = _mapping(payload.get("meta"))
        workers = count(meta.get("workers")) or 1
        if workers > 1 and not meta.get("merged", True):
            messages.append(
                f"{label} run used {workers} workers without merging — "
                f"its numbers are one worker's slice, not the suite"
            )
            continue
        selection = _mapping(meta.get("selection"))
        expression = text(selection.get("markexpr")) or text(selection.get("keyword"))
        if expression:
            messages.append(
                f"{label} run selected a subset of the suite ({expression!r}"
                + (f", {count(selection.get('deselected'))} tests deselected"
                   if count(selection.get("deselected")) else "")
                + ") — its coverage describes that subset"
            )
        elif meta.get("partialRun"):
            ratio = finite(meta.get("unseenRatio"))
            messages.append(
                f"{label} run looks partial"
                + (f" ({ratio:.0%} of endpoints never called)" if ratio is not None else "")
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
    def state_of(states: dict, name: str) -> str:
        if name not in states:
            return "absent"
        return text(states[name]) or "recorded without a state"

    changed = [
        f"{name}: {state_of(before, name)} → {state_of(after, name)}"
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
        name: _mapping(info) for name, info in sides[recorded].items()
        if count(_mapping(info).get("deselected")) > 0 or _mapping(info).get("state") == "env"
    }
    if not acted:
        return []
    described = ", ".join(
        f"{name}: "
        + (f"deselected {count(info.get('deselected'))}"
           if count(info.get("deselected")) > 0 else "enabled by env")
        for name, info in sorted(acted.items())
    )
    return [
        f"{missing} run carries no opt-in record; {recorded} {described} — "
        "comparability cannot be confirmed"
    ]


def _optin_records(payload: dict) -> "dict | None":
    selection = _mapping(_mapping(payload.get("meta")).get("selection"))
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
