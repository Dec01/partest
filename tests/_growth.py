"""How a cost grows with its input — for tests that guard against quadratic blow-ups.

A wall-clock limit (``assert elapsed < 2.0``) measures the machine as much as the code: a CI
host busy with parallel runs failed such limits with a correct implementation. What these
tests are written for is the *shape* of the cost — a regex that backtracks, a scan that
restarts at every position — and that shape survives a slow machine: linear work on four
times the input costs about four times as much, quadratic work sixteen times.

So the cost is compared with itself, in the same process, on the same machine: the best of
several runs on *n* against the best of several runs on *factor × n*. The best run discards
the moments the machine was busy elsewhere; the garbage collector is off while measuring.
"""

from __future__ import annotations

import gc
import time
from typing import Any, Callable


def _best(run: Callable[[Any], Any], arg: Any, repeats: int) -> float:
    best = float("inf")
    for _ in range(repeats):
        started = time.perf_counter()
        run(arg)
        best = min(best, time.perf_counter() - started)
    return best


def growth_ratio(
    make: Callable[[int], Any],
    run: Callable[[Any], Any],
    n: int,
    *,
    factor: int = 4,
    repeats: int = 5,
) -> float:
    """``cost(make(factor * n)) / cost(make(n))``, each the best of *repeats* runs."""
    small, large = make(n), make(factor * n)
    run(small)  # warm up: compiled patterns, imports, caches of the interpreter
    enabled = gc.isenabled()
    gc.collect()
    gc.disable()
    try:
        t_small = _best(run, small, repeats)
        t_large = _best(run, large, repeats)
    finally:
        if enabled:
            gc.enable()
    return t_large / max(t_small, 1e-6)


def assert_linear(
    make: Callable[[int], Any],
    run: Callable[[Any], Any],
    n: int,
    *,
    factor: int = 4,
    repeats: int = 5,
    attempts: int = 3,
    label: Any = "",
) -> None:
    """Fail when the cost grows faster than linearly — quadratic growth or worse.

    For ``factor=4`` linear work gives about 4 (``n log n`` about 4.5) and quadratic about 16;
    the limit is the geometric middle, 8 — a wide margin either way. Pick *n* so that the
    small input still takes a measurable time (a millisecond or more). The best of
    *attempts* measurements is compared, so a burst of load during one of them is not a
    failure.
    """
    limit = factor * factor ** 0.5
    # A busy machine only ever inflates a measurement, and on either side; quadratic work
    # is over the limit every time. So the best of a few attempts is the one that counts.
    ratio = float("inf")
    for _ in range(attempts):
        ratio = min(ratio, growth_ratio(make, run, n, factor=factor, repeats=repeats))
        if ratio < limit:
            return
    assert ratio < limit, (
        f"{label}: {factor}x the input cost {ratio:.1f}x the time (linear ~{factor}, "
        f"limit {limit:.0f}) — the work grows faster than the input"
    )
