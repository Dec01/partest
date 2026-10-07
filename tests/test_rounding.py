"""partest.rounding: agreement within the rounding of inputs and output, nothing more.

The cases are built so that the boundary is known exactly: a value one unit in the last
place inside the derived interval must pass, one unit outside must fail. A check that only
ever saw comfortable margins would pass with any tolerance at all.
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from partest.rounding import (
    Interval,
    Rounded,
    RoundingNoteWarning,
    agrees_with_formula,
    agrees_with_sum,
    half_unit,
)


def D(text: str) -> Decimal:
    return Decimal(text)


# --- half units and intervals -------------------------------------------------


@pytest.mark.parametrize(
    "scale, expected",
    [(0, "0.5"), (2, "0.005"), (4, "0.00005"), (-1, "5"), (-2, "50"), (None, "0")],
)
def test_half_unit(scale, expected):
    assert half_unit(scale) == D(expected)


def test_a_rounded_value_stands_for_its_rounding_interval():
    assert Rounded(12.34, 2).interval == Interval("12.335", "12.345")
    assert Rounded("7", None).interval == Interval.point(7)


def test_floats_are_read_as_the_decimal_they_print_as():
    assert Rounded(0.1, 1).decimal == D("0.1")


def test_interval_arithmetic_is_sound_for_signs_and_division():
    a = Interval(-2, 3)
    b = Interval(4, 5)
    assert a + b == Interval(2, 8)
    assert a - b == Interval(-7, -1)
    assert a * b == Interval(-10, 15)
    assert a / b == Interval(D("-0.5"), D("0.75"))
    assert 1 - b == Interval(-4, -3)
    assert 10 / b == Interval(2, D("2.5"))
    assert -a == Interval(-3, 2)
    assert abs(a) == Interval(0, 3)
    assert a ** 2 == Interval(0, 9)  # not [-6, 9]: an even power is never negative
    assert Interval(-3, -2) ** 2 == Interval(4, 9)
    assert Interval(-3, 2) ** 3 == Interval(-27, 8)
    assert a ** 0 == Interval.point(1)


def test_division_rounds_outward():
    from fractions import Fraction

    third = Interval.point(1) / 3
    assert Fraction(third.lo) < Fraction(1, 3) < Fraction(third.hi)
    tenth = Interval.point(1) / 10  # exact in decimal: no widening needed
    assert tenth == Interval.point("0.1")


def test_division_by_an_interval_around_zero_is_refused():
    with pytest.raises(ZeroDivisionError, match="contains zero"):
        Interval(1, 2) / Interval(-1, 1)


@pytest.mark.parametrize(
    "use",
    [
        lambda x: x > 0,
        lambda x: bool(x),
        lambda x: max(x, x),
        lambda x: round(x, 2),
        lambda x: float(x),
        lambda x: math.sqrt(x),
        lambda x: x ** 0.5,
        lambda x: x if x != 0 else 0,
        lambda x: x == 0,
        lambda x: 0 in [x],
    ],
    ids=["compare", "bool", "max", "round", "float", "math", "fractional-power", "ne-number",
         "eq-number", "membership"],
)
def test_what_would_silently_pick_an_end_raises(use):
    with pytest.raises(TypeError):
        use(Interval(1, 2))


# --- the check ----------------------------------------------------------------


def product(rate, count):
    return rate * count


def test_the_tolerance_is_derived_not_chosen():
    """3.14 (±0.005) × 8.395 (±0.0005) ∈ [26.3167575, 26.4038475]; output ±0.005."""
    check = agrees_with_formula(
        Rounded(26.36, 2, "total"), product, Rounded(3.14, 2, "rate"), Rounded(8.395, 3, "count")
    )
    assert check
    assert check.ok is True
    assert check.computed == D("26.36030")
    assert check.predicted == Interval("26.3167575", "26.4038475")
    assert check.accepted == Interval("26.3117575", "26.4088475")
    assert check.deviation == D("-0.00030")


def test_one_unit_inside_passes_and_one_unit_outside_fails():
    rate, count = Rounded(3.14, 2, "rate"), Rounded(8.395, 3, "count")
    assert agrees_with_formula(Rounded("26.40", 2), product, rate, count)
    assert not agrees_with_formula(Rounded("26.41", 2), product, rate, count)
    assert agrees_with_formula(Rounded("26.32", 2), product, rate, count)
    assert not agrees_with_formula(Rounded("26.31", 2), product, rate, count)


def test_isclose_is_wrong_in_both_directions():
    """The motivating pair: a fixed rel_tol passes a defect and fails a correct value."""
    # Precise inputs: a 0.05 % defect is outside the derived interval…
    precise = agrees_with_formula(
        Rounded("100.050", 3), product, Rounded("10.000", 3), Rounded("10.000", 3)
    )
    assert not precise
    assert math.isclose(100.05, 100.0, rel_tol=1e-3)  # …and inside a "reasonable" tolerance.

    # A formula that amplifies rounding: dividing by a small rounded number.
    amplified = agrees_with_formula(
        Rounded("4.55", 2), lambda a, b: a / b, Rounded("1.0", 1), Rounded("0.2", 1)
    )
    assert amplified  # 1.0/0.2 = 5, but 0.95..1.05 / 0.15..0.25 spans 3.8..7
    assert not math.isclose(4.55, 5.0, rel_tol=1e-3)


def test_resolution_says_how_sharp_the_check_was():
    sharp = agrees_with_formula(
        Rounded("100.000", 3), product, Rounded("10.0000", 4), Rounded("10.0000", 4)
    )
    coarse = agrees_with_formula(Rounded("100", 0), product, Rounded("10", 0), Rounded("10", 0))
    assert sharp.resolution < 1e-4
    assert coarse.resolution > 0.1
    # Half the width of what is accepted, relative to the computed value.
    assert sharp.resolution == pytest.approx(float(sharp.accepted.width / 2 / sharp.computed))


def test_resolution_is_none_when_the_computed_value_is_zero():
    check = agrees_with_formula(Rounded(0, 2), lambda a, b: a - b, Rounded(1.5, 1), Rounded(1.5, 1))
    assert check
    assert check.resolution is None


def test_sum_tolerance_is_the_sum_of_half_units():
    parts = [Rounded(3.33, 2)] * 3  # 9.99, each ±0.005 → ±0.015, total ±0.005 → ±0.02
    assert agrees_with_sum(Rounded("10.01", 2, "sum"), parts)
    assert not agrees_with_sum(Rounded("10.02", 2, "sum"), parts)
    assert agrees_with_sum(Rounded("9.97", 2), parts)
    assert not agrees_with_sum(Rounded("9.96", 2), parts)
    check = agrees_with_sum(Rounded("10.00", 2), parts)
    assert check.accepted == Interval("9.97", "10.01")


def test_an_unrounded_input_contributes_no_width():
    check = agrees_with_formula(Rounded("6.0", 1), lambda a, b: a * b, Rounded(2, None), Rounded(3, None))
    assert check.predicted == Interval.point(6)
    assert check.accepted == Interval("5.95", "6.05")


def test_constants_in_the_formula_are_exact_decimals():
    check = agrees_with_formula(Rounded("0.3", 1), lambda a: a * 0.1, Rounded(3, None))
    assert check.computed == D("0.3")


def test_a_value_with_more_decimals_than_its_scale_is_noted():
    with pytest.warns(RoundingNoteWarning, match="beyond its declared scale 2"):
        check = agrees_with_formula(
            Rounded(0.30000000000000004, 2, "sum"), lambda a, b: a + b, Rounded(0.1, 1), Rounded(0.2, 1)
        )
    assert check  # still sound: the declared interval is wider than the record
    assert any("sum" in note and "beyond its declared scale 2" in note for note in check.notes)


def test_the_protocol_is_readable_and_serialisable():
    check = agrees_with_formula(
        Rounded(26.36, 2, "total"), product, Rounded(3.14, 2, "rate"), Rounded(8.395, 3, "count")
    )
    text = str(check)
    for fragment in ("total agrees with", "rate = 3.14", "scale 3", "resolution", "accepted"):
        assert fragment in text
    assert "agrees" in repr(check) and "resolution ±" in repr(check)
    data = check.as_dict()
    assert data["ok"] is True
    assert data["inputs"]["rate"] == {"value": 3.14, "scale": 2}
    assert data["accepted"] == [26.3117575, 26.4088475]
    import json

    json.dumps(data)

    failed = agrees_with_formula(Rounded("26.50", 2, "total"), product, Rounded(3.14, 2), Rounded(8.395, 3))
    assert "does NOT agree" in str(failed) and "DISAGREES" in repr(failed)


@pytest.mark.parametrize("bad", [None, True, "abc", float("nan"), float("inf"), [1]])
def test_bad_values_are_refused_loudly(bad):
    with pytest.raises((TypeError, ValueError)):
        agrees_with_formula(Rounded(bad, 2), lambda a: a, Rounded(1, 2))


def test_inputs_must_carry_their_scale():
    with pytest.raises(TypeError, match="Rounded"):
        agrees_with_formula(Rounded(1, 2), lambda a: a, 1.0)


def test_the_predicted_interval_contains_every_point_of_the_input_box():
    """Soundness, sampled: any true inputs that round to the recorded ones land inside."""
    import random
    from decimal import localcontext

    rng = random.Random(20261007)

    def formula(a, b, c, d):
        return (a * b - c) / d + a ** 2

    for _ in range(200):
        inputs = [Rounded(round(rng.uniform(-50, 50), s), s) for s in (2, 1, 3, 0)]
        if inputs[3].interval.lo <= 0 <= inputs[3].interval.hi:
            continue
        predicted = formula(*(i.interval for i in inputs))
        for _ in range(20):
            point = [
                i.interval.lo + (i.interval.hi - i.interval.lo) * Decimal(rng.random())
                for i in inputs
            ]
            with localcontext() as ctx:
                ctx.prec = 80
                value = formula(*point)
            assert predicted.lo <= value <= predicted.hi


def test_equality_with_a_number_says_why():
    with pytest.raises(TypeError, match="intervals are not ordered"):
        Interval(1, 2) != 0  # noqa: B015
    assert Interval(1, 2) == Interval(1, 2)
    assert Interval(1, 2) != Interval(1, 3)


def test_a_clean_check_emits_no_warning():
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert agrees_with_formula(Rounded("6.0", 1), lambda a: a * 2, Rounded("3.0", 1))


# --- outward rounding of every operation ----------------------------------------
#
# Operands of 40 significant digits make every exact result longer than the 60 digits the
# arithmetic keeps, so the bounds must straddle it. With an ordinary rounding context both
# bounds collapse onto one rounded value that lies on one side of the truth.

from fractions import Fraction  # noqa: E402

A = Decimal("1.234567890123456789012345678901234567891")
B = Decimal("9.876543210987654321098765432109876543211")
TINY = Decimal("1E-70")


def _straddles(interval, exact):
    return Fraction(interval.lo) < exact < Fraction(interval.hi)


def test_multiplication_rounds_outward():
    assert _straddles(Interval.point(A) * Interval.point(B), Fraction(A) * Fraction(B))


def test_addition_rounds_outward():
    assert _straddles(Interval.point(A) + Interval.point(TINY), Fraction(A) + Fraction(TINY))


def test_subtraction_rounds_outward():
    assert _straddles(Interval.point(A) - Interval.point(TINY), Fraction(A) - Fraction(TINY))


def test_negation_is_exact_not_rounded_to_28_digits():
    """``-Decimal`` rounds to the default context; a bound must never be rounded inward."""
    product = Interval.point(A) * Interval.point(B)
    assert (-product).lo == product.hi.copy_negate()
    assert _straddles(-product, -(Fraction(A) * Fraction(B)))
    assert _straddles(abs(-product), Fraction(A) * Fraction(B))


def test_powers_round_outward():
    assert _straddles(Interval.point(A) ** 3, Fraction(A) ** 3)
    assert _straddles(Interval.point(A.copy_negate()) ** 3, -(Fraction(A) ** 3))


# --- inputs that would only burn time or overflow --------------------------------


def test_a_huge_power_is_refused():
    with pytest.raises(ValueError, match="exceeds the supported maximum"):
        Interval(1, 2) ** 10**9


@pytest.mark.parametrize("scale", [10**6, -(10**6)])
def test_an_absurd_scale_is_a_clear_error(scale):
    with pytest.raises(ValueError, match="outside"):
        agrees_with_formula(Rounded(1, scale), lambda a: a, Rounded(1, 2))


def test_decimal_overflow_becomes_a_clear_error():
    with pytest.raises(ValueError, match="range decimal arithmetic"):
        agrees_with_formula(
            Rounded(1, 0), lambda a: a ** 64 * a ** 64 * a ** 64 * a ** 64, Rounded("1E+9000", 0)
        )
