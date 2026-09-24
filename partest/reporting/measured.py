"""Assertions with a third outcome: «not measured».

A check has two outcomes only while there is something to measure. When the data the
assertion reads was never collected — the file is absent, the queue is unreachable, the
sample is empty — the comparison still runs and still succeeds, and the report shows a
pass nobody earned. Aggregates are the worst case: a difference, a share or a mean over an
empty sample is ``0`` or ``1`` *by construction*, so the assertion guarding it cannot fail
even in principle.

:func:`check_measured` takes the premise of measurability as a **required argument** and
runs the assertion only when that premise holds. Otherwise it records the third outcome —
what was not measured and why. That outcome does not fail the run (an unmeasurable premise
is not a defect of the code under test) and it is not a pass either: the step is titled
``NOT MEASURED``, the attachment carries ``passed: null``, the test is tagged, a
:class:`NotMeasuredWarning` is raised and the run keeps a ledger
(:func:`not_measured_records`).

Typical use::

    import partest.reporting as ah

    ah.check_measured(
        ah.measurable(samples, what="latency samples"),
        lambda: ah.check_lt(mean(samples), 200, field="mean latency"),
        what="mean latency under the budget",
    )

The premise may also be a plain boolean, and then the reason is mandatory::

    ah.check_measured(
        bool(baseline),
        lambda: ah.check_eq(after - before, 0, field="growth"),
        what="growth against the baseline",
        reason="the baseline snapshot was never taken",
    )
"""

from __future__ import annotations

import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, List, Tuple

from partest.reporting.attach import attach_not_measured
from partest.reporting.templates import ErrorTemplates, StepTemplates

try:
    import allure
except ImportError:  # pragma: no cover - allure stays a soft dependency
    allure = None  # type: ignore


class NotMeasuredWarning(UserWarning):
    """Raised when an assertion was skipped for want of data.

    A warning rather than an error on purpose: the run is not broken, but the reader of a
    green run must not conclude that the assertion held. Projects that want the stricter
    reading turn it into a failure themselves::

        [pytest]
        filterwarnings = error::partest.reporting.NotMeasuredWarning
    """


@dataclass(frozen=True)
class Premise:
    """Whether an assertion can be measured at all, and why not when it cannot."""

    ok: bool
    reason: str = ""
    what: str = ""

    def __post_init__(self) -> None:
        # A premise that does not hold is exactly the case that ends up in the report, and
        # «not measured» without a reason is indistinguishable from a silent pass.
        if not self.ok and not (self.reason or "").strip():
            raise ValueError("a Premise that does not hold must carry a reason")

    def __bool__(self) -> bool:
        return bool(self.ok)

    def __and__(self, other: Any) -> "Premise":
        """Combine premises: an aggregate over two samples needs both of them."""
        if isinstance(other, Premise):
            if self.ok and other.ok:
                return Premise(True, what=", ".join(w for w in (self.what, other.what) if w))
            return self if not self.ok else other
        if self.ok and not other:
            return Premise(False, reason="a combined premise did not hold", what=self.what)
        return self

    __rand__ = __and__


@dataclass(frozen=True)
class NotMeasured:
    """One assertion that was never made, and the reason it could not be."""

    what: str
    reason: str


_records: List[NotMeasured] = []


def not_measured_records() -> Tuple[NotMeasured, ...]:
    """Everything this process failed to measure, in the order it happened."""
    return tuple(_records)


def reset_not_measured() -> None:
    """Forget the ledger (the pytest plugin calls this at session start)."""
    _records.clear()


def measurable(sample: Any, *, what: str, min_size: int = 1) -> Premise:
    """Premise «this sample is large enough for the assertion to mean anything».

    ``None`` means the sample was never collected; too few items mean an aggregate over it
    is fixed by construction. Objects without a length (iterators, scalars) are taken as
    measurable when they are not ``None`` — nothing here can count them without consuming
    them.
    """
    _require_text(what, "what")
    if sample is None:
        return Premise(False, reason=f"«{what}» was never collected (None)", what=what)
    try:
        size = len(sample)
    except TypeError:
        return Premise(True, what=what)
    if size < min_size:
        return Premise(
            False,
            reason=(
                f"«{what}» holds {size} item(s), fewer than the {min_size} this assertion "
                f"needs — an aggregate over it is fixed by construction, not measured"
            ),
            what=what,
        )
    return Premise(True, what=what)


def mark_not_measured(*, what: str, reason: str) -> None:
    """Record the third outcome directly, when there is no assertion to run at all.

    :func:`check_measured` is the usual entry point; this one is for the places that
    discover the missing data before an assertion can even be written.
    """
    _require_text(what, "what")
    _require_text(reason, "reason")
    _report_not_measured(what, reason, stacklevel=3)


def _report_not_measured(what: str, reason: str, *, stacklevel: int) -> None:
    """One place for the third outcome: ledger, step, attachment, tag, warning."""
    _records.append(NotMeasured(what=what, reason=reason))
    with _step(StepTemplates.not_measured(what, reason)):
        attach_not_measured(what=what, reason=reason)
    _tag_test()
    warnings.warn(
        ErrorTemplates.not_measured(what=what, reason=reason),
        NotMeasuredWarning,
        stacklevel=stacklevel,
    )


def check_measured(
    premise: Any,
    assertion: Callable[[], Any],
    *,
    what: str,
    reason: str = "",
) -> bool:
    """Run *assertion* only if *premise* holds; otherwise report «not measured».

    *premise* is positional and required so that it cannot be forgotten: the point of this
    helper is that measurability is stated, not assumed. It is a :class:`Premise` (from
    :func:`measurable`, say) or any truthy value — and then *reason* is required, because
    the third outcome without a reason is indistinguishable from a silent pass.

    *assertion* is a zero-argument callable: a ``lambda``, a ``functools.partial`` or a
    local function wrapping several ``check_*`` calls. Returns ``True`` when the assertion
    was actually made.
    """
    _require_text(what, "what")
    if not callable(assertion):
        raise TypeError(
            "check_measured(premise, assertion, ...): assertion must be a zero-argument "
            f"callable, got {type(assertion).__name__}"
        )
    if isinstance(premise, Premise):
        # A Premise cannot exist without a reason for not holding (see __post_init__).
        why = reason or premise.reason
    else:
        why = reason
        if not why:
            raise ValueError(
                "check_measured(...) needs reason=... when the premise is a plain value: "
                "an unmeasured assertion without a reason reads like a pass. Pass "
                "reason='…' or build the premise with measurable(...)."
            )
    if premise:
        with _step(StepTemplates.measured(what)):
            assertion()
        return True
    _report_not_measured(what, why, stacklevel=3)
    return False


def _require_text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}=… must be a non-empty string")


@contextmanager
def _step(title: str):
    if allure is None:
        yield
        return
    with allure.step(title):
        yield


def _tag_test() -> None:
    """Flag the test itself, so the outcome is visible without opening the steps."""
    if allure is None:
        return
    try:
        allure.dynamic.tag("not-measured")
    except Exception:  # pragma: no cover - no live Allure lifecycle outside a test
        pass
