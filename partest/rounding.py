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

Only round-to-nearest is modelled (any tie rule: half-up, half-even, half-down — the
interval is closed). A value *truncated* to its scale is off by up to a whole unit in one
direction and is not covered.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Context, Decimal, InvalidOperation
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Union

Number = Union[int, float, str, Decimal]

_PRECISION = 60
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
    return Decimal(5).scaleb(-scale - 1)


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
        return Interval(-self.hi, -self.lo)

    def __pos__(self) -> "Interval":
        return self

    def __abs__(self) -> "Interval":
        if self.lo >= 0:
            return self
        if self.hi <= 0:
            return -self
        return Interval(0, max(-self.lo, self.hi))

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
        if exponent == 0:
            return Interval.point(1)
        if exponent % 2 == 1 or self.lo >= 0:
            return Interval(_power(self.lo, exponent, up=False), _power(self.hi, exponent, up=True))
        if self.hi <= 0:  # even power of a non-positive interval: mirror it first
            return Interval(_power(-self.hi, exponent, up=False), _power(-self.lo, exponent, up=True))
        return Interval(0, _power(max(-self.lo, self.hi), exponent, up=True))

    # --- what an interval refuses to be ----------------------------------------

    def __bool__(self) -> bool:
        raise TypeError(
            "an interval has no truth value: a formula checked here may use arithmetic only"
        )

    def _no_order(self, other: Any) -> bool:
        raise TypeError(
            "intervals are not ordered: comparing one would pick an end silently; "
            "use arithmetic only in the formula"
        )

    __lt__ = __le__ = __gt__ = __ge__ = _no_order

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Interval) and self.lo == other.lo and self.hi == other.hi

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
        magnitude = _power(-base, exponent, up=not up)
        return -magnitude
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


@dataclass(frozen=True)
class Rounded:
    """A number as it was recorded: its value and the scale it was rounded to.

    ``scale`` is the number of decimals kept (``2`` for ``12.34``); ``None`` means the value
    is exact. ``label`` names it in messages.
    """

    value: Number
    scale: Optional[int]
    label: str = ""

    @property
    def decimal(self) -> Decimal:
        return _dec(self.value, what=self.label or "value")

    @property
    def half_unit(self) -> Decimal:
        return half_unit(self.scale)

    @property
    def interval(self) -> Interval:
        """Every value that rounds to this one at this scale."""
        return Interval.point(self.decimal).widen(self.half_unit)

    def excess_digits(self) -> int:
        """How many decimals the value carries beyond its declared scale (0 if none)."""
        if self.scale is None:
            return 0
        exponent = self.decimal.normalize().as_tuple().exponent
        if not isinstance(exponent, int):
            return 0
        return max(0, -exponent - self.scale)


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
                (i.label or f"#{n}"): {"value": float(i.decimal), "scale": i.scale}
                for n, i in enumerate(self.inputs, 1)
            },
            "output_scale": self.output.scale,
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
            f"  actual      {_fmt(self.actual)}  (scale {self.output.scale})",
            f"  computed    {_fmt(self.computed)}  (inputs at face value)",
            f"  deviation   {_fmt(self.deviation)}",
            f"  predicted   {self.predicted!r}  (formula over the inputs' intervals)",
            f"  accepted    {self.accepted!r}  (widened by the output's half unit)",
            "  resolution  "
            + ("n/a (computed value is zero)" if self.resolution is None
               else f"±{self.resolution * 100:.4g}% of the computed value"),
            "  inputs:",
        ]
        for n, i in enumerate(self.inputs, 1):
            lines.append(
                f"    {i.label or f'#{n}'} = {_fmt(i.decimal)}  (scale {i.scale}, ±{_fmt(i.half_unit)})"
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
    computed_iv = Interval._coerce(formula(*(Interval.point(i.decimal) for i in inputs)))
    predicted = Interval._coerce(formula(*(i.interval for i in inputs)))
    accepted = predicted.widen(actual.half_unit)
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


__all__ = [
    "Agreement",
    "Interval",
    "Rounded",
    "agrees_with_formula",
    "agrees_with_sum",
    "half_unit",
]
