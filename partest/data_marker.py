"""Test-data marker helpers for payload naming and cleanup filtering."""

from __future__ import annotations

import os
from typing import Optional

# "AQA" is the common abbreviation for automated QA. Test data carries it so that a
# delete-by-marker cleanup can find rows this suite created and leave everything else
# alone — which is why the marker must never be empty. Override per project with
# TEST_DATA_MARKER when a stand needs a different convention.
TEST_MARKER = (os.getenv("TEST_DATA_MARKER") or "AQA").strip() or "AQA"
# Locale for Faker unique names (LIB-04). Examples: en_US, ru_RU, de_DE.
FAKER_LOCALE = (os.getenv("PARTEST_FAKER_LOCALE") or "en_US").strip() or "en_US"

try:
    from faker import Faker

    _fake: Optional[Faker] = Faker(locale=FAKER_LOCALE)
except ImportError:
    _fake = None


def marked_name(kind: str = "Entity") -> str:
    """Human-readable name including marker, e.g. ``AQA Client 12345678``."""
    if _fake is not None:
        return _fake.unique.bothify(f"{TEST_MARKER} {kind} ########")
    import random

    return f"{TEST_MARKER} {kind} {random.randint(10000000, 99999999)}"


def marked_code(prefix: str) -> str:
    """Code with marker: ``AQA-CL-1234``."""
    prefix = prefix.strip("-_ ").upper()
    if _fake is not None:
        return _fake.unique.bothify(f"{TEST_MARKER}-{prefix}-####")
    import random

    return f"{TEST_MARKER}-{prefix}-{random.randint(1000, 9999)}"


def marked_short(kind: str = "CH") -> str:
    if _fake is not None:
        return _fake.unique.bothify(f"{TEST_MARKER}-{kind}-####")
    import random

    return f"{TEST_MARKER}-{kind}-{random.randint(1000, 9999)}"


def fill_with_marker(length: int, fill: str = "x") -> str:
    """String of exact ``length`` that still contains TEST_MARKER when possible."""
    if length <= 0:
        return ""
    marker = TEST_MARKER
    if length <= len(marker):
        return marker[:length]
    pad = fill[0] if fill else "x"
    return (marker + pad * (length - len(marker)))[:length]


def prefix_marker(text: str) -> str:
    """Ensure marker prefix for ad-hoc names."""
    text = "" if text is None else str(text)
    if TEST_MARKER in text:
        return text
    return f"{TEST_MARKER} {text}"


# Older names for the same five helpers. Kept working for suites that predate the
# ``marked_*`` naming, deprecated because one thing with two public names is a surface
# nobody benefits from — not because of what they are called. Removing them is a
# breaking change and waits for a major version; a deprecation that never warns never
# expires, hence the warning.
def _deprecated_alias(new, old_name: str):
    import functools
    import warnings

    @functools.wraps(new)
    def _wrapper(*args, **kwargs):
        warnings.warn(
            f"{old_name}() is deprecated; use {new.__name__}(). "
            f"The aqa_* aliases will be removed in the next major version.",
            DeprecationWarning,
            stacklevel=2,
        )
        return new(*args, **kwargs)

    _wrapper.__name__ = old_name
    return _wrapper


aqa_name = _deprecated_alias(marked_name, "aqa_name")
aqa_code = _deprecated_alias(marked_code, "aqa_code")
aqa_short = _deprecated_alias(marked_short, "aqa_short")
aqa_fill = _deprecated_alias(fill_with_marker, "aqa_fill")
aqa_prefixed = _deprecated_alias(prefix_marker, "aqa_prefixed")
