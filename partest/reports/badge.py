"""SVG coverage badge (LIB-COV-BADGE)."""

from __future__ import annotations

from typing import Any, Optional

#: Shown, in grey, for a run that measured nothing (``summary.avg`` is ``null``).
_NOT_MEASURED_TEXT = "n/a"
_NOT_MEASURED_COLOR = "#9f9f9f"


def _color(avg: float) -> str:
    if avg >= 80:
        return "#4c1"
    if avg >= 50:
        return "#dfb317"
    return "#e05d44"


def badge_svg(avg: Optional[float], *, label: str = "coverage") -> str:
    """Shields-style SVG. ``avg`` is 0..100, or ``None`` for "not measured".

    ``None`` is drawn as ``n/a`` in grey, not as ``0.0%`` in red: a run with no endpoints
    has no average, and a red zero would say it covered nothing.
    """
    if avg is None:
        value = _NOT_MEASURED_TEXT
        color = _NOT_MEASURED_COLOR
    else:
        avg = max(0.0, min(100.0, float(avg)))
        value = f"{avg:.1f}%" if avg < 100 else "100%"
        color = _color(avg)
    label_w = 70
    value_w = 54
    total = label_w + value_w
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" '
        f'role="img" aria-label="{label}: {value}">'
        f"<title>{label}: {value}</title>"
        f'<rect width="{label_w}" height="20" fill="#555"/>'
        f'<rect x="{label_w}" width="{value_w}" height="20" fill="{color}"/>'
        f'<g fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
        f'<text x="{label_w / 2}" y="14">{label}</text>'
        f'<text x="{label_w + value_w / 2}" y="14">{value}</text>'
        f"</g></svg>"
    )


def badge_from_payload(payload: dict[str, Any], *, label: str = "coverage") -> str:
    """Badge for ``summary.avg``.

    ``"avg": null`` (a run with no endpoints, 2.7.0 and later) is ``n/a``, and so is the
    ``0.0`` older releases wrote for a run with no endpoints (``summary.endpoints == 0`` or
    ``endpoints: []``) — read the way ``compare`` and ``validate`` read it. A ``0.0`` with
    endpoints is a measured zero; a payload without the key reads as ``0.0`` as it always
    did.
    """
    from partest.reports.compare import _summary_avg

    return badge_svg(_summary_avg(payload), label=label)
