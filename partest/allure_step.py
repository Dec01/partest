"""Allure step context manager that degrades when Allure is unavailable.

Dependency-free on purpose: imported by both the API client and the UI package, and
``import partest.ui`` must not pull the OpenAPI/coverage session with it.

Why this exists as a module rather than a three-line helper in each file: the obvious
implementation is wrong in a way that hides real failures.

    @contextmanager
    def _step(title):
        try:
            import allure
            with allure.step(title):
                yield
        except Exception:
            yield          # <- runs when the *body* raised, not just the import

When the guarded block raises, the exception is thrown back in at the ``yield``, the
``except`` catches it and yields a second time, and ``contextlib`` turns that into
``RuntimeError: generator didn't stop after throw()``. The caller sees that instead of
the AssertionError with the formatted status/schema diagnostics.

Here the guard covers only acquiring the step, never the body.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Optional


def _acquire(title: str) -> Optional[Any]:
    """Allure step context manager, or None when Allure is missing or unusable."""
    try:
        import allure

        return allure.step(title)
    except Exception:
        return None


@contextmanager
def allure_step(title: str) -> Iterator[None]:
    """Run the block inside an Allure step; pass exceptions through untouched."""
    step = _acquire(title)
    if step is None:
        yield
        return

    try:
        step.__enter__()
    except Exception:
        # Allure present but not reporting (no results dir, broken plugin state).
        yield
        return

    try:
        yield
    except BaseException as exc:
        if not step.__exit__(type(exc), exc, exc.__traceback__):
            raise
    else:
        step.__exit__(None, None, None)
