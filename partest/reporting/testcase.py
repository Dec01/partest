"""Allure testcase decorator and dynamic metadata helpers."""

from __future__ import annotations

import asyncio
from functools import wraps
from typing import Callable, Optional, Sequence

import allure


def testcase(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    story: Optional[str] = None,
    severity: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
):
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            _apply_meta(title, description, story, severity, tags, func)
            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            _apply_meta(title, description, story, severity, tags, func)
            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _apply_meta(title, description, story, severity, tags, func):
    if title:
        allure.dynamic.title(title)
    desc = description
    if desc is None and func.__doc__:
        desc = func.__doc__.strip()
    if desc:
        allure.dynamic.description(desc)
    if story:
        allure.dynamic.story(story)
    if severity:
        allure.dynamic.severity(severity)
    if tags:
        for t in tags:
            allure.dynamic.tag(t)


def set_description(text: str) -> None:
    allure.dynamic.description(text)


def set_title(text: str) -> None:
    allure.dynamic.title(text)
