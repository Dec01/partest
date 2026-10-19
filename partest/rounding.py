"""Check "this value is that formula of those values" when every number was rounded on the way.

An API returns ``total = 26.36`` and next to it ``rate = 3.14`` and ``count = 8.395``. The
service computed ``total`` from unrounded inputs and then rounded everything it wrote — the
inputs to their scale, the output to its own. Recomputing ``rate * count`` from what the
response says gives ``26.3603`` and will not match ``26.36`` exactly; the question is
whether the gap is what rounding *can* produce or more than that.

``math.isclose(actual, expected, rel_tol=1e-3)`` answers a different question. Its
tolerance is picked by eye and is the same for every formula, so it is wrong in both
directions at once: too loose where the inputs were recorded precisely (a real defect of
0.05 % passes), too tight where the formula amplifies rounding — dividing by a small rounded
number, subtracting two close ones — and a correct value fails. Nothing in it knows which
side was rounded, or to what.

Here the tolerance is not chosen; it is derived. Each input recorded at scale ``s`` stands
for an interval ``value ± ½·10^−s``. The formula is evaluated over those intervals with
interval arithmetic, the result is widened by the output's own half unit, and the check is
whether the recorded output lies inside. The width of that interval is reported as the
**resolution** of the check: ``±0.002 %`` says the comparison was sharp, ``±4 %`` says the
inputs were recorded too coarsely to tell much — worth knowing before trusting a green.

::

    from partest.rounding import Rounded, agrees_with_formula, agrees_with_sum

    check = agrees_with_formula(
        Rounded(body["total"], 2, "total"),
        lambda rate, count: rate * count,
        Rounded(body["rate"], 2, "rate"),
        Rounded(body["count"], 3, "count"),
    )
    assert check, str(check)          # str() is the full protocol: inputs, interval, resolution

    assert agrees_with_sum(Rounded(body["sum"], 2), [Rounded(p, 2) for p in parts])

The formula receives :class:`Interval` objects and may use ``+ - * /``, unary minus,
``abs`` and integer powers, with plain numbers mixed in. Anything that needs to *compare*
an interval — ``if``, ``max``, ``round``, ``math.*`` — raises ``TypeError`` instead of
quietly picking one end. Arithmetic is :mod:`decimal` with outward rounding, so the
interval is never narrower than the truth; a float is read as the shortest decimal that
prints it (``0.1`` is ``0.1``), which is what a JSON number on the wire was.

By default a value is taken as rounded to nearest (any tie rule: half-up, half-even,
half-down — the interval is closed). A value rounded in one direction says so with
``rounding=``: ``"floor"`` (toward −∞), ``"ceiling"`` (toward +∞), ``"toward_zero"``
(the extra digits dropped). Its interval is then a whole unit wide and on one side of the
record: ``Rounded(12.34, 2, rounding="floor")`` stands for ``[12.34, 12.35]``. "Amounts are
rounded down" in a specification usually means the digits are dropped — ``"toward_zero"``:
for a negative amount (a refund, a correction) ``-12.349`` becomes ``-12.34``, which
``"floor"`` would write ``-12.35``. The two agree only for values that cannot be negative.
Away from zero (``decimal.ROUND_UP``) and ``decimal.ROUND_05UP`` are not modelled and raise
``ValueError``.

A float the service computed and did not round is good to some number of *significant*
digits, not decimals: ``Rounded(ratio, significant=12)`` stands for every value within half a
unit of its twelfth significant digit, and its extra digits are not a note — nobody claimed
it was rounded. Several checks at once — :func:`assert_all_agree`: one protocol, one
``AssertionError`` listing every disagreement.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    Context,
    Decimal,
    DecimalException,
    InvalidOperation,
)
from typing import Any, Callable, Dict, Iterable, Optional, Sequence, Tuple, Union

Number = Union[int, float, str, Decimal]

_PRECISION = 60
#: Largest integer power an interval may be raised to; a formula needing more is not one
#: this check was built for, and a huge exponent would only burn time.
MAX_POWER = 64
#: Largest ``abs(scale)``. Beyond it the half unit leaves the range ``decimal`` represents.
MAX_SCALE = 10_000


class RoundingNoteWarning(UserWarning):
    """A remark on a check that passed or failed for its own reasons — read it anyway.

    Emitted for every entry of :attr:`Agreement.notes`, so that a note is not lost on a
    green run where nobody prints the protocol.
    """
_FLOOR = Context(prec=_PRECISION, rounding=ROUND_FLOOR)
_CEIL = Context(prec=_PRECISION, rounding=ROUND_CEILING)


def _dec(value: Any, *, what: str = "value") -> Decimal:
    """A number as the decimal it was written as."""
    if isinstance(value, bool) or value is None:
        raise TypeError(f"{what} must be a number, got {value!r}")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        result = Decimal(repr(value))
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except InvalidOperation:
            raise ValueError(f"{what} is not a number: {value!r}") from None
    else:
        raise TypeError(f"{what} must be int, float, str or Decimal, got {type(value).__name__}")
    if not result.is_finite():
        raise ValueError(f"{what} must be finite, got {value!r}")
    return result


def half_unit(scale: Optional[int]) -> Decimal:
    """Half a unit in the last place of a value rounded to ``scale`` decimals.

    ``half_unit(2) == Decimal("0.005")``; a negative scale rounds to tens, hundreds…;
    ``None`` means "not rounded" and gives zero.
    """
    if scale is None:
        return Decimal(0)
    if isinstance(scale, bool) or not isinstance(scale, int):
        raise TypeError(f"scale must be an int or None, got {scale!r}")
    if abs(scale) > MAX_SCALE:
        raise ValueError(f"scale {scale} is outside ±{MAX_SCALE}: no recorded number has that")
    return Decimal(5).scaleb(-scale - 1)


_NO_COMPARISON = (
    "intervals are not ordered: comparing one would pick an end silently; "
    "use arithmetic only in the formula"
)


class Interval:
    """A closed interval ``[lo, hi]`` of decimals with outward-rounded arithmetic."""

    __slots__ = ("lo", "hi")

    def __init__(self, lo: Number, hi: Optional[Number] = None) -> None:
        low = _dec(lo, what="interval bound")
        high = low if hi is None else _dec(hi, what="interval bound")
        if low > high:
            raise ValueError(f"empty interval: lo {low} > hi {high}")
        self.lo = low
        self.hi = high

    @classmethod
    def point(cls, value: Number) -> "Interval":
        return cls(value, value)

    @property
    def width(self) -> Decimal:
        return _CEIL.subtract(self.hi, self.lo)

    @property
    def mid(self) -> Decimal:
        return (self.lo + self.hi) / 2

    def contains(self, value: Union[Number, "Interval"]) -> bool:
        if isinstance(value, Interval):
            return self.lo <= value.lo and value.hi <= self.hi
        v = _dec(value)
        return self.lo <= v <= self.hi

    def widen(self, by: Number) -> "Interval":
        """``[lo − by, hi + by]``; ``by`` must not be negative."""
        d = _dec(by, what="widening")
        if d < 0:
            raise ValueError("cannot widen by a negative amount")
        return Interval(_FLOOR.subtract(self.lo, d), _CEIL.add(self.hi, d))

    # --- arithmetic -----------------------------------------------------------

    @staticmethod
    def _coerce(other: Any) -> "Interval":
        if isinstance(other, Interval):
            return other
        return Interval.point(other)

    def __add__(self, other: Any) -> "Interval":
        o = self._coerce(other)
        return Interval(_FLOOR.add(self.lo, o.lo), _CEIL.add(self.hi, o.hi))

    __radd__ = __add__

    def __sub__(self, other: Any) -> "Interval":
        o = self._coerce(other)
        return Interval(_FLOOR.subtract(self.lo, o.hi), _CEIL.subtract(self.hi, o.lo))

    def __rsub__(self, other: Any) -> "Interval":
        return self._coerce(other) - self

    def __neg__(self) -> "Interval":
        # copy_negate, never unary minus: ``-d`` rounds to the *default* context (28 digits).
        return Interval(self.hi.copy_negate(), self.lo.copy_negate())

    def __pos__(self) -> "Interval":
        return self

    def __abs__(self) -> "Interval":
        if self.lo >= 0:
            return self
        if self.hi <= 0:
            return -self
        return Interval(0, max(self.lo.copy_negate(), self.hi))

    def __mul__(self, other: Any) -> "Interval":
        o = self._coerce(other)
        pairs = [(a, b) for a in (self.lo, self.hi) for b in (o.lo, o.hi)]
        return Interval(
            min(_FLOOR.multiply(a, b) for a, b in pairs),
            max(_CEIL.multiply(a, b) for a, b in pairs),
        )

    __rmul__ = __mul__

    def __truediv__(self, other: Any) -> "Interval":
        o = self._coerce(other)
        if o.lo <= 0 <= o.hi:
            raise ZeroDivisionError(
                f"divisor interval {o!r} contains zero: the rounding of the inputs does not "
                "bound the result, so this formula cannot be checked at these scales"
            )
        pairs = [(a, b) for a in (self.lo, self.hi) for b in (o.lo, o.hi)]
        return Interval(
            min(_FLOOR.divide(a, b) for a, b in pairs),
            max(_CEIL.divide(a, b) for a, b in pairs),
        )

    def __rtruediv__(self, other: Any) -> "Interval":
        return self._coerce(other) / self

    def __pow__(self, exponent: Any) -> "Interval":
        if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent < 0:
            raise TypeError("an interval can only be raised to a non-negative integer power")
        if exponent > MAX_POWER:
            raise ValueError(f"power {exponent} exceeds the supported maximum of {MAX_POWER}")
        if exponent == 0:
            return Interval.point(1)
        if exponent % 2 == 1 or self.lo >= 0:
            return Interval(_power(self.lo, exponent, up=False), _power(self.hi, exponent, up=True))
        if self.hi <= 0:  # even power of a non-positive interval: mirror it first
            return Interval(
                _power(self.hi.copy_negate(), exponent, up=False),
                _power(self.lo.copy_negate(), exponent, up=True),
            )
        return Interval(0, _power(max(self.lo.copy_negate(), self.hi), exponent, up=True))

    # --- what an interval refuses to be ----------------------------------------

    def __bool__(self) -> bool:
        raise TypeError(
            "an interval has no truth value: a formula checked here may use arithmetic only"
        )

    def _no_order(self, other: Any) -> bool:
        raise TypeError(_NO_COMPARISON)

    __lt__ = __le__ = __gt__ = __ge__ = _no_order

    def __eq__(self, other: Any) -> bool:
        """Two intervals are equal when their bounds are; against a number it is refused.

        ``x != 0`` inside a formula would otherwise be quietly true for an interval that
        contains zero, and pick a branch the way a comparison picks an end.
        """
        if not isinstance(other, Interval):
            raise TypeError(_NO_COMPARISON)
        return self.lo == other.lo and self.hi == other.hi

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash((self.lo, self.hi))

    def __round__(self, ndigits: Optional[int] = None) -> Any:
        raise TypeError("round() on an interval would hide the rounding this check accounts for")

    def __float__(self) -> float:
        raise TypeError("an interval is not a number; use .lo, .hi or .mid")

    def __repr__(self) -> str:
        return f"[{_fmt(self.lo)}, {_fmt(self.hi)}]"


def _power(base: Decimal, exponent: int, *, up: bool) -> Decimal:
    """``base ** exponent`` rounded outward, by repeated directed multiplication.

    Correct for a non-negative base, and for a negative one with an odd exponent: the sign
    is carried and the magnitude rounded the other way.
    """
    ctx = _CEIL if up else _FLOOR
    if base < 0:
        magnitude = _power(base.copy_negate(), exponent, up=not up)
        return magnitude.copy_negate()
    result = Decimal(1)
    for _ in range(exponent):
        result = ctx.multiply(result, base)
    return result


def _fmt(value: Decimal, digits: int = 12) -> str:
    """Short, readable decimal for messages — the exact one lives on the object."""
    if value == 0:
        return "0"
    rounded = value.normalize(Context(prec=digits))
    text = f"{rounded:f}" if -20 < rounded.adjusted() < 20 else str(rounded)
    return text


#: How a recorded value was rounded: to nearest (the default), down, up, toward zero.
ROUNDING_MODES = ("half", "floor", "ceiling", "toward_zero")
_DECIMAL_ROUNDING = {
    ROUND_HALF_UP: "half",
    ROUND_HALF_EVEN: "half",
    ROUND_HALF_DOWN: "half",
    ROUND_FLOOR: "floor",
    ROUND_CEILING: "ceiling",
    ROUND_DOWN: "toward_zero",  # decimal's ROUND_DOWN truncates; it is not "floor"
}
_SCALE_REQUIRED: Any = object()


@dataclass(frozen=True)
class Rounded:
    """A number as it was recorded: its value and the scale it was rounded to.

    ``scale`` is the number of decimals kept (``2`` for ``12.34``). ``None`` means the value
    is an **exact decimal** — a count, a constant from the specification, a number the
    test wrote itself. A float the service *computed* is not exact even when it is not
    rounded to a scale: its last digits are binary noise, and declaring it ``None`` makes
    the check demand more than the arithmetic can give. Give such a value the scale it is
    meaningful to, or ``significant=``. ``label`` names it in messages.

    ``significant=N`` (instead of ``scale``) — the value is good to ``N`` significant digits:
    the unit is that of its ``N``-th significant digit, whatever its magnitude
    (``Rounded(0.30000000000000004, significant=12)`` is ``0.3 ± 5·10⁻¹³``). It does not claim
    the value was rounded, so digits beyond it are not a note. Zero has no significant
    digits and is taken as exact.

    ``rounding=`` — how the service rounded: ``"half"`` (to nearest, any tie rule — the
    default, the interval is ``value ± ½ unit``), ``"floor"`` (toward −∞:
    ``[value, value + unit]``), ``"ceiling"`` (toward +∞: ``[value − unit, value]``),
    ``"toward_zero"`` (digits dropped: floor for a positive value, ceiling for a negative one,
    ``[−unit, unit]`` for zero — the right one for "rounded down" amounts that can be
    negative). The :mod:`decimal` constants are accepted too — ``ROUND_DOWN`` is
    ``"toward_zero"``, as in :mod:`decimal`, and every ``ROUND_HALF_*`` is ``"half"``;
    ``ROUND_UP`` (away from zero) and ``ROUND_05UP`` are not modelled: ``ValueError``.

    ``Rounded(x, None, significant=N)`` is accepted — ``None`` is what ``scale`` becomes
    under ``significant=``; any other ``scale`` together with it is a ``TypeError``.
    """

    value: Number
    scale: Optional[int] = _SCALE_REQUIRED
    label: str = ""
    significant: Optional[int] = field(default=None, kw_only=True)
    rounding: str = field(default="half", kw_only=True)

    def __post_init__(self) -> None:
        if self.significant is not None:
            if self.scale is not _SCALE_REQUIRED and self.scale is not None:
                raise TypeError("give scale or significant=, not both")
            if (
                isinstance(self.significant, bool)
                or not isinstance(self.significant, int)
                or self.significant < 1
            ):
                raise ValueError(
                    f"significant must be a positive int, got {self.significant!r}"
                )
            object.__setattr__(self, "scale", None)
        elif self.scale is _SCALE_REQUIRED:
            raise TypeError(
                "Rounded() needs the scale the value was rounded to (None for an exact "
                "value), or significant="
            )
        mode = _DECIMAL_ROUNDING.get(self.rounding, self.rounding)
        if mode not in ROUNDING_MODES:
            raise ValueError(
                f"rounding must be one of {', '.join(ROUNDING_MODES)}, got {self.rounding!r}"
            )
        object.__setattr__(self, "rounding", mode)

    @property
    def decimal(self) -> Decimal:
        return _dec(self.value, what=self.label or "value")

    @property
    def effective_scale(self) -> Optional[int]:
        """The decimals the value is good to: ``scale``, or derived from ``significant``."""
        if self.significant is None:
            return self.scale
        d = self.decimal
        if d == 0:
            return None
        scale = self.significant - 1 - d.adjusted()
        if abs(scale) > MAX_SCALE:
            raise ValueError(
                f"{self.label or 'value'} = {self.value!r} at {self.significant} significant "
                f"digits is a unit of 1E{-scale}: beyond the ±{MAX_SCALE} decimals this check "
                "represents — no recorded number is that small or that large"
            )
        return scale

    @property
    def half_unit(self) -> Decimal:
        return half_unit(self.effective_scale)

    @property
    def unit(self) -> Decimal:
        """One unit in the last place kept (zero for an exact value)."""
        return self.half_unit * 2

    def _offsets(self, sign: int) -> Tuple[Decimal, Decimal]:
        """``(below, above)``: a record ``r`` of this sign stands for ``[r + below, r + above]``."""
        h = self.half_unit
        u = h * 2
        mode = self.rounding
        if mode == "toward_zero":
            mode = "floor" if sign > 0 else "ceiling" if sign < 0 else "both"
        if mode == "floor":
            return Decimal(0), u
        if mode == "ceiling":
            return -u, Decimal(0)
        if mode == "both":
            return -u, u
        return -h, h

    @property
    def interval(self) -> Interval:
        """Every value that rounds to this one at this scale, in this direction."""
        d = self.decimal
        below, above = self._offsets(1 if d > 0 else -1 if d < 0 else 0)
        return Interval(_FLOOR.add(d, below), _CEIL.add(d, above))

    def excess_digits(self) -> int:
        """How many decimals the value carries beyond its declared scale (0 if none).

        Always 0 for ``significant=``: such a value is not claimed to be rounded.
        """
        if self.scale is None:
            return 0
        sign, digits, exponent = self.decimal.as_tuple()
        if not isinstance(exponent, int):
            return 0
        # Trailing zeros carry no information; strip them exactly (no context rounding).
        while len(digits) > 1 and digits[-1] == 0:
            digits = digits[:-1]
            exponent += 1
        return max(0, -exponent - self.scale)


def _accepted(predicted: Interval, output: Rounded) -> Interval:
    """Every record a correct service could write for a true value inside ``predicted``.

    A record ``r`` stands for ``[r + below, r + above]``; it is possible when that meets
    ``predicted``, i.e. ``r ∈ [lo − above, hi − below]``. Truncation depends on the sign of
    ``r``, so its accepted set is the hull of the positive, negative and zero records.
    """
    lo, hi = predicted.lo, predicted.hi
    if output.rounding != "toward_zero" or output.half_unit == 0:
        below, above = output._offsets(1)
        return Interval(_FLOOR.subtract(lo, above), _CEIL.subtract(hi, below))
    u = output.unit
    ends = []
    if hi > 0:  # positive records, floored: [r, r + u]
        ends.append((max(_FLOOR.subtract(lo, u), Decimal(0)), hi))
    if lo < 0:  # negative records, ceiled: [r − u, r]
        ends.append((lo, min(_CEIL.add(hi, u), Decimal(0))))
    if lo <= u and hi >= -u:  # zero: [−u, u]
        ends.append((Decimal(0), Decimal(0)))
    return Interval(min(e[0] for e in ends), max(e[1] for e in ends))


def _how(r: Rounded) -> str:
    """How a value was recorded, for the protocol. The default reads as it always did."""
    if r.significant is not None:
        text = f"{r.significant} significant digits → scale {r.effective_scale}"
    else:
        text = f"scale {r.scale}"
    if r.rounding != "half":
        text += f", rounded {r.rounding.replace('_', ' ')}"
    return text


def _how_dict(r: Rounded) -> Dict[str, Any]:
    """The non-default parts of how a value was recorded; empty for ``scale`` + half."""
    extra: Dict[str, Any] = {}
    if r.significant is not None:
        extra["significant"] = r.significant
    if r.rounding != "half":
        extra["rounding"] = r.rounding
    return extra


def _spread(r: Rounded) -> str:
    """Where the true value lies around the record: ``±0.005`` or ``−0 … +0.01``."""
    if r.rounding == "half" or r.half_unit == 0:
        return f"±{_fmt(r.half_unit)}"
    d = r.decimal
    below, above = r._offsets(1 if d > 0 else -1 if d < 0 else 0)
    return f"−{_fmt(-below)} … +{_fmt(above)}"


@dataclass(frozen=True)
class Agreement:
    """The protocol of one check. Truthy when the recorded value agrees.

    * ``computed`` — the formula on the recorded inputs taken at face value;
    * ``predicted`` — the formula over the inputs' rounding intervals;
    * ``accepted`` — ``predicted`` widened by the output's half unit: every recorded output
      a correct service could have written;
    * ``resolution`` — half the width of ``accepted`` relative to ``|computed|``: how sharp the
      check was (``None`` when ``computed`` is zero);
    * ``notes`` — things worth reading even on a pass, e.g. a value carrying more decimals
      than its declared scale.
    """

    ok: bool
    label: str
    actual: Decimal
    computed: Decimal
    predicted: Interval
    accepted: Interval
    resolution: Optional[float]
    inputs: Tuple[Rounded, ...]
    output: Rounded
    notes: Tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.ok

    @property
    def deviation(self) -> Decimal:
        """``actual − computed``: the raw gap, before rounding is accounted for."""
        return self.actual - self.computed

    def as_dict(self) -> Dict[str, Any]:
        """JSON-friendly protocol, for an attachment or a log line."""
        return {
            "label": self.label,
            "ok": self.ok,
            "actual": float(self.actual),
            "computed": float(self.computed),
            "accepted": [float(self.accepted.lo), float(self.accepted.hi)],
            "resolution_pct": None if self.resolution is None else self.resolution * 100,
            "inputs": {
                (i.label or f"#{n}"): {
                    "value": float(i.decimal),
                    "scale": i.effective_scale,
                    **_how_dict(i),
                }
                for n, i in enumerate(self.inputs, 1)
            },
            "output_scale": self.output.effective_scale,
            **{f"output_{k}": v for k, v in _how_dict(self.output).items()},
            "notes": list(self.notes),
        }

    def __repr__(self) -> str:
        verdict = "agrees" if self.ok else "DISAGREES"
        res = "n/a" if self.resolution is None else f"±{self.resolution * 100:.4g}%"
        return (
            f"<{self.label or 'value'} {verdict}: actual {_fmt(self.actual)}, "
            f"computed {_fmt(self.computed)}, accepted {self.accepted!r}, resolution {res}>"
        )

    def __str__(self) -> str:
        verdict = "agrees with" if self.ok else "does NOT agree with"
        lines = [
            f"{self.label or 'value'} {verdict} the formula within the rounding of its inputs",
            f"  actual      {_fmt(self.actual)}  ({_how(self.output)})",
            f"  computed    {_fmt(self.computed)}  (inputs at face value)",
            f"  deviation   {_fmt(self.deviation)}",
            f"  predicted   {self.predicted!r}  (formula over the inputs' intervals)",
            f"  accepted    {self.accepted!r}  (widened by the output's "
            + ("half unit)" if self.output.rounding == "half" else "rounding)"),
            "  resolution  "
            + ("n/a (computed value is zero)" if self.resolution is None
               else f"±{self.resolution * 100:.4g}% of the computed value"),
            "  inputs:",
        ]
        for n, i in enumerate(self.inputs, 1):
            lines.append(
                f"    {i.label or f'#{n}'} = {_fmt(i.decimal)}  ({_how(i)}, {_spread(i)})"
            )
        lines.extend(f"  note: {note}" for note in self.notes)
        return "\n".join(lines)


def agrees_with_formula(
    actual: Rounded,
    formula: Callable[..., Any],
    *inputs: Rounded,
    label: str = "",
) -> Agreement:
    """Does ``actual`` agree with ``formula(*inputs)``, given how each was rounded?

    ``formula`` is called twice: once with every input as a point (``computed``), once with
    every input as its rounding interval (``predicted``). It may return an
    :class:`Interval` or a plain number (a constant formula).
    """
    for n, item in enumerate((actual, *inputs)):
        if not isinstance(item, Rounded):
            raise TypeError(
                f"{'actual' if n == 0 else f'input #{n}'} must be a Rounded(value, scale), "
                f"got {type(item).__name__}"
            )
    name = label or actual.label
    try:
        computed_iv = Interval._coerce(formula(*(Interval.point(i.decimal) for i in inputs)))
        predicted = Interval._coerce(formula(*(i.interval for i in inputs)))
        accepted = _accepted(predicted, actual)
    except DecimalException as exc:
        raise ValueError(
            f"the formula left the range decimal arithmetic can represent "
            f"({type(exc).__name__}); check the scales and the magnitudes of the inputs"
        ) from exc
    value = actual.decimal
    computed = computed_iv.mid
    resolution: Optional[float] = None
    if computed != 0:
        resolution = float(accepted.width / 2 / abs(computed))
    notes = []
    for n, item in enumerate((actual, *inputs)):
        extra = item.excess_digits()
        if extra:
            who = item.label or ("actual" if n == 0 else f"input #{n}")
            notes.append(
                f"{who} = {item.value!r} has {extra} decimal(s) beyond its declared scale "
                f"{item.scale}: either the scale is wrong or the value was not rounded to it"
            )
    for note in notes:
        warnings.warn(f"{name or 'value'}: {note}", RoundingNoteWarning, stacklevel=2)
    return Agreement(
        ok=accepted.contains(value),
        label=name,
        actual=value,
        computed=computed,
        predicted=predicted,
        accepted=accepted,
        resolution=resolution,
        inputs=tuple(inputs),
        output=actual,
        notes=tuple(notes),
    )


def agrees_with_sum(total: Rounded, parts: Sequence[Rounded], *, label: str = "") -> Agreement:
    """``total`` against the sum of ``parts``: the tolerance is the sum of every half unit.

    Splitting a total into parts and rounding each one is the common case: ten parts at two
    decimals may disagree with their rounded total by up to ``10 × 0.005 + 0.005``, and by
    no more.
    """
    return agrees_with_formula(total, lambda *xs: sum(xs, Interval.point(0)), *parts, label=label)


def assert_all_agree(
    checks: Iterable[Agreement], *, name: str = "rounding checks"
) -> Tuple[Agreement, ...]:
    """Attach the protocol of every check, then fail once, naming every disagreement.

    ``assert check, str(check)`` per value stops at the first one and hides the rest; a
    response with five computed fields deserves one verdict on all five::

        assert_all_agree([
            agrees_with_formula(Rounded(body["total"], 2, "total"), mul, rate, count),
            agrees_with_sum(Rounded(body["sum"], 2, "sum"), parts),
        ], name="invoice totals")

    With Allure available the protocol is attached as ``<name>`` (JSON, every
    :meth:`Agreement.as_dict`) and ``<name>.txt`` (every ``str()``), on a pass as well as on
    a failure; without it nothing is attached and the rest works the same. The
    ``AssertionError`` lists each failed check's full protocol. Returns the checks, so the
    caller can read them. An empty set raises ``ValueError``: no check is not a pass.
    """
    items = tuple(checks)
    for n, item in enumerate(items, 1):
        if not isinstance(item, Agreement):
            raise TypeError(
                f"check #{n} must be an Agreement (agrees_with_formula / agrees_with_sum), "
                f"got {type(item).__name__}"
            )
    if not items:
        raise ValueError(f"{name}: no checks were given — nothing was compared")
    failed = [a for a in items if not a]
    header = f"{name}: {len(items) - len(failed)} of {len(items)} agree"
    _attach_protocol(name, items, header)
    if failed:
        raise AssertionError(
            f"{name}: {len(failed)} of {len(items)} do NOT agree — "
            + ", ".join(a.label or "value" for a in failed)
            + "\n\n"
            + "\n\n".join(str(a) for a in failed)
        )
    return items


def _attach_protocol(name: str, items: Sequence[Agreement], header: str) -> None:
    """Allure attachments when ``partest.reporting`` and Allure are there; nothing otherwise."""
    try:
        from partest.reporting.attach import attach_json, attach_text
    except Exception:  # reporting is optional for this module
        return
    attach_json(name, [a.as_dict() for a in items])
    attach_text(f"{name}.txt", header + "\n\n" + "\n\n".join(str(a) for a in items))


__all__ = [
    "Agreement",
    "Interval",
    "ROUNDING_MODES",
    "Rounded",
    "RoundingNoteWarning",
    "agrees_with_formula",
    "agrees_with_sum",
    "assert_all_agree",
    "half_unit",
]
