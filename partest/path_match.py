"""Resolve a concrete request URL to its OpenAPI path template.

Coverage is keyed by the OpenAPI template, so the concrete URL a suite sends
(``/orders/customer/5``) has to be mapped back to the template that produced it
(``/orders/customer/{customerId}``). Getting this wrong does not fail a test — it
silently records the call against the wrong key, or against none at all, and the
endpoint then reads as uncovered while its tests are green.

The previous approach appended the first unused path parameter found anywhere in the
whole specification, which produced ``/orders/customer/{id}`` for the example above.
This module matches per operation instead: segment count, literal segments, and a
preference for the template with the longest literal prefix.

Pure functions — no I/O, no global state, so the behaviour is testable without a stand.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional, Sequence, Tuple

_PLACEHOLDER = re.compile(r"^\{[^}]*\}$")


def is_placeholder(segment: str) -> bool:
    return bool(_PLACEHOLDER.match(segment or ""))


def split_segments(path: str) -> List[str]:
    """Path to segments, ignoring query string, fragment and trailing slash."""
    text = (path or "").split("?", 1)[0].split("#", 1)[0]
    return [s for s in text.split("/") if s]


def build_concrete_url(
    endpoint: str,
    add_urls: Sequence[Optional[str]] = (),
    after_url: str = "",
) -> str:
    """Join the parts the client joins, so matching sees the URL that was sent."""
    parts = [(endpoint or "").rstrip("/")]
    for add in add_urls:
        if not add:
            continue
        parts.append("/" + str(add).strip("/"))
    if after_url:
        parts.append("/" + str(after_url).strip("/"))
    url = "".join(parts)
    if not url.startswith("/"):
        url = "/" + url
    return url


def _template_matches(concrete: Sequence[str], template: Sequence[str]) -> bool:
    if len(concrete) != len(template):
        return False
    for actual, expected in zip(concrete, template):
        if is_placeholder(expected):
            if not actual:
                return False
            continue
        if actual != expected:
            return False
    return True


def _score(template_segments: Sequence[str]) -> Tuple[int, int, int]:
    """Rank candidates: longest literal prefix, then most literals, then shortest.

    ``/orders/user`` beats ``/orders/{id}`` for the URL ``/orders/user`` because its
    first placeholder is further right (there is none at all).
    """
    first_placeholder = next(
        (i for i, s in enumerate(template_segments) if is_placeholder(s)),
        len(template_segments),
    )
    literals = sum(1 for s in template_segments if not is_placeholder(s))
    return (first_placeholder, literals, -sum(len(s) for s in template_segments))


def match_template(concrete_url: str, templates: Iterable[str]) -> Optional[str]:
    """Best OpenAPI template for a concrete URL, or None when nothing matches."""
    concrete = split_segments(concrete_url)
    if not concrete:
        return None

    best: Optional[str] = None
    best_score: Optional[Tuple[int, int, int]] = None
    for template in templates:
        segments = split_segments(template)
        if not _template_matches(concrete, segments):
            continue
        score = _score(segments)
        if best_score is None or score > best_score:
            best, best_score = template, score
    return best


def resolve_endpoint_template(
    method: str,
    concrete_url: str,
    paths_info: Iterable[Any],
) -> Optional[str]:
    """Template for ``method`` + ``concrete_url`` among loaded OpenAPI paths."""
    wanted = (method or "").upper()
    templates = [
        getattr(path, "path", "")
        for path in paths_info
        if str(getattr(path, "method", "")).upper() == wanted
    ]
    return match_template(concrete_url, [t for t in templates if t])
