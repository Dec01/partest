"""The averaging rule of the coverage report, in one place.

Which rows an average leaves out, which rule a ``coverage.json`` says it follows, and how a
missing average is printed: the analyzer, the payload, ``compare``, the validator and both
HTML reports read these, so the rule cannot drift between them.
"""

from __future__ import annotations

import math
from typing import Any, Optional

#: The rule this package writes to ``meta.avgRule``. ``1`` (also what a file without the
#: key follows): an ``exception`` row counts as 100 % inside every average and in a
#: service's ``covered``. ``2``: ``exception`` rows are outside them, and still counted.
AVG_RULE = 2

#: Rules this package can read. An integer above them is a newer rule; anything else is not
#: a rule.
KNOWN_AVG_RULES = frozenset({1, 2})

EXCEPTION = "exception"


def is_exception_row(row: Any) -> bool:
    """Whether a row stays out of every average: an ``EndpointCoverage`` or a payload row."""
    if isinstance(row, dict):
        return row.get("status") == EXCEPTION
    return bool(getattr(row, "is_exception", False)) or getattr(row, "status", None) == EXCEPTION


#: The status counters of ``summary``, and how a row's ``status`` lands in them: ``empty`` takes
#: every status that is not one of the other three (``deprecated``, a missing status).
STATUS_COUNTERS = ("full", "partial", "empty", "exception")


def status_counts(rows: Any) -> dict:
    """``summary.full`` / ``partial`` / ``empty`` / ``exception`` as the rows give them — the
    rule ``summarize`` writes by, and the one ``compare`` and the validator check against."""
    counts = dict.fromkeys(STATUS_COUNTERS, 0)
    for row in rows:
        status = row.get("status") if isinstance(row, dict) else None
        counts[status if status in ("full", "partial", "exception") else "empty"] += 1
    return counts


def avg_rule_of(meta: Any) -> Any:
    """``meta.avgRule`` as written; ``1`` when the key is absent (or ``meta`` is not a
    mapping) — the rule every earlier release followed without writing it."""
    if not isinstance(meta, dict) or "avgRule" not in meta:
        return 1
    return meta["avgRule"]


def is_known_rule(rule: Any) -> bool:
    return isinstance(rule, int) and not isinstance(rule, bool) and rule in KNOWN_AVG_RULES


def finite(value: Any) -> Optional[float]:
    """*value* as a finite ``float``; ``None`` for a non-number, a bool, ``inf`` / ``nan``, or
    an integer too large for a float — a document is read, never trusted to fit."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


#: Larger than any real count of calls or endpoints, small enough for float arithmetic and
#: for ``str()`` (Python 3.11+ refuses to print integers of more than 4300 digits).
COUNT_LIMIT = 10**12


def count(value: Any) -> int:
    """*value* as a non-negative count: an ``int`` or a finite ``float`` (not a bool), capped at
    :data:`COUNT_LIMIT`; anything else is ``0``. For reading a document, never for writing."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, min(value, COUNT_LIMIT))
    number = finite(value)
    if number is None:
        return 0
    return max(0, min(int(number), COUNT_LIMIT))


def text(value: Any) -> str:
    """*value* when it is a string, else ``""``."""
    return value if isinstance(value, str) else ""


def str_list(value: Any) -> list:
    """The strings of *value* when it is a list, else ``[]``."""
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def shown(value: Any, limit: int = 60) -> str:
    """*value* for a message: shortened, and never an exception — ``str()`` of an integer of
    thousands of digits raises from Python 3.11 on."""
    try:
        rendered = repr(value) if isinstance(value, str) else str(value)
    except ValueError:
        return "<a number too long to show>"
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"


def json_safe(value: Any) -> Any:
    """*value* with what a JSON reader cannot take replaced by ``None``.

    ``json.loads`` accepts ``NaN`` and ``Infinity`` and ``json.dumps`` writes them back as bare
    tokens that ``JSON.parse`` and most other readers refuse; an integer of thousands of
    digits cannot be written at all from Python 3.11 on. Both become "no value". Nesting
    deeper than the interpreter allows raises ``RecursionError`` — the caller decides.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, int) and not isinstance(value, bool):
        return value if value.bit_length() <= 1024 else None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def pct_text(value: Optional[float], digits: int) -> str:
    """A percentage, or ``n/a`` for an average over nothing scored."""
    return "n/a" if value is None else f"{value:.{digits}f}%"


def bucket_average(bucket: dict) -> Optional[float]:
    """``avg_pct`` of an analyzer bucket, or ``None`` when nothing in it was scored."""
    if bucket.get("scored", bucket.get("count", 0)) == 0:
        return None
    return bucket.get("avg_pct")


def report_average(report: Any) -> Optional[float]:
    """``CoverageReport.average_pct``, or ``None`` when no row is scored."""
    scored = getattr(report, "scored_count", None)
    if scored is None:
        scored = sum(1 for ep in report.endpoints if not is_exception_row(ep))
    return report.average_pct if scored else None


def bucket_order(item: tuple) -> tuple:
    """Sort key for ``(key, bucket)``: highest average first, nothing scored last."""
    avg = bucket_average(item[1])
    return (avg is None, -(avg or 0.0))
