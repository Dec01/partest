"""Allure step context managers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Optional

import allure

from partest.reporting.attach import attach_request
from partest.reporting.templates import StepTemplates


@contextmanager
def step(title: str):
    with allure.step(title):
        yield


@contextmanager
def step_http(
    method: str,
    path: str,
    *,
    expected: Any = None,
    headers: Optional[dict] = None,
    body: Any = None,
):
    title = StepTemplates.http(method, path, expected)
    with allure.step(title):
        attach_request(
            method=method,
            path=path,
            headers=headers,
            body=body,
            expected_status=expected,
        )
        yield


@contextmanager
def step_prepare(what: str):
    with allure.step(StepTemplates.prepare(what)):
        yield


@contextmanager
def step_cleanup(what: str):
    with allure.step(StepTemplates.cleanup(what)):
        yield


@contextmanager
def step_as_role(role: str):
    with allure.step(StepTemplates.auth_as(role)):
        yield
