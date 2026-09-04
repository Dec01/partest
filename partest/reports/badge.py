"""SVG coverage badge (LIB-COV-BADGE)."""

from __future__ import annotations

from typing import Any


def _color(avg: float) -> str:
    if avg >= 80:
        return "#4c1"
    if avg >= 50:
        return "#dfb317"
    return "#e05d44"


def badge_svg(avg: float, *, label: str = "coverage") -> str:
    """Shields-style SVG. ``avg`` is 0..100."""
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
    avg = float((payload.get("summary") or {}).get("avg") or 0.0)
    return badge_svg(avg, label=label)
