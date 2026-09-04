"""Allure text templates and HTTP status hints (domain-agnostic)."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional, Sequence

from allure_commons.types import Severity as AllureSeverity

_HTTP_STATUS_HINTS_EN: Dict[int, str] = {
    400: "Bad request / validation error (body or params).",
    401: "Missing or expired credentials (not authenticated).",
    403: "Authenticated but not allowed (RBAC / ownership / scope).",
    404: "Resource not found (or hidden by policy).",
    405: "HTTP method not supported on this path.",
    409: "Conflict: uniqueness, FK/integrity, or business state.",
    415: "Unsupported Content-Type / media type.",
    422: "Semantic validation failed (Unprocessable Entity).",
    429: "Too many requests — rate limited.",
    500: "Internal server error.",
    502: "Bad Gateway — upstream failure.",
    503: "Service temporarily unavailable.",
}

_HTTP_STATUS_HINTS_RU: Dict[int, str] = {
    400: "Некорректный запрос / ошибка валидации (тело или параметры).",
    401: "Нет или просрочены учётные данные (не аутентифицирован).",
    403: "Аутентифицирован, но нет прав (RBAC / ownership / scope).",
    404: "Ресурс не найден (или скрыт политикой).",
    405: "HTTP-метод не поддерживается на этом пути.",
    409: "Конфликт: уникальность, FK/целостность или бизнес-состояние.",
    415: "Неподдерживаемый Content-Type / media type.",
    422: "Семантическая валидация не пройдена (Unprocessable Entity).",
    429: "Слишком много запросов — rate limit.",
    500: "Внутренняя ошибка сервера.",
    502: "Bad Gateway — сбой upstream.",
    503: "Сервис временно недоступен.",
}

_HTTP_STATUS_HINTS = _HTTP_STATUS_HINTS_EN
_hints_locale = "en"

# Optional consumer hook for 409 entity-specific hints
_conflict_hint_provider: Optional[Callable[[str, Any], str]] = None


def set_conflict_hint_provider(provider: Optional[Callable[[str, Any], str]]) -> None:
    """Register pluggable 409 explanation (path, request_body) -> str."""
    global _conflict_hint_provider
    _conflict_hint_provider = provider


def set_status_hints_locale(locale: str = "en") -> None:
    """Switch built-in status hints: ``en`` (default) or ``ru`` (L5.4)."""
    global _HTTP_STATUS_HINTS, _hints_locale
    loc = (locale or "en").lower()
    if loc.startswith("ru"):
        _HTTP_STATUS_HINTS = _HTTP_STATUS_HINTS_RU
        _hints_locale = "ru"
    else:
        _HTTP_STATUS_HINTS = _HTTP_STATUS_HINTS_EN
        _hints_locale = "en"


def status_hints_locale() -> str:
    return _hints_locale


class Severity:
    BLOCKER = AllureSeverity.BLOCKER
    CRITICAL = AllureSeverity.CRITICAL
    NORMAL = AllureSeverity.NORMAL
    MINOR = AllureSeverity.MINOR
    TRIVIAL = AllureSeverity.TRIVIAL


def _brief(data: Any, limit: int = 600) -> str:
    try:
        if isinstance(data, (dict, list)):
            text = json.dumps(data, ensure_ascii=False, default=str)
        else:
            text = str(data)
    except Exception:
        text = repr(data)
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _problem_detail_summary(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    parts = []
    for key in ("status", "title", "detail", "type", "instance", "message", "error"):
        if key in body and body[key] is not None:
            parts.append(f"{key}={body[key]!r}")
    if "errors" in body:
        parts.append(f"errors={_brief(body['errors'], 300)}")
    return "; ".join(parts)


def http_status_hint(code: Any) -> str:
    try:
        return _HTTP_STATUS_HINTS.get(int(code), "")
    except (TypeError, ValueError):
        return ""


def explain_conflict(path: str, request_body: Any = None) -> str:
    if _conflict_hint_provider:
        try:
            return _conflict_hint_provider(path, request_body) or ""
        except Exception:
            pass
    return "Uniqueness or data-integrity conflict (see Problem Detail)."


class ErrorTemplates:
    @staticmethod
    def mismatch(*, field: str, expected: Any, actual: Any, context: str = "") -> str:
        ctx = f"\nContext: {context}" if context else ""
        return (
            f"Value mismatch for «{field}».\n"
            f"  Expected: {expected!r}\n"
            f"  Actual: {actual!r}"
            f"{ctx}"
        )

    @staticmethod
    def status(
        *,
        expected: Any,
        actual: Any,
        method: str = "",
        path: str = "",
        response_body: Any = None,
        request_body: Any = None,
        hint: str = "",
    ) -> str:
        where = f" {method} {path}".strip()
        where = f" ({where})" if where else ""
        lines = [
            f"Unexpected HTTP status code{where}.",
            f"  Expected: {expected}",
            f"  Actual: {actual}",
        ]
        if hint:
            lines.append(f"  Hint: {hint}")
        if request_body is not None:
            lines.append(f"  Request body: {_brief(request_body)}")
        if response_body is not None:
            lines.append(f"  Response body: {_brief(response_body)}")
        return "\n".join(lines)

    @staticmethod
    def conflict_409(
        *,
        method: str,
        path: str,
        expected: Any,
        request_body: Any = None,
        response_body: Any = None,
        entity_hint: str = "",
    ) -> str:
        lines = [
            "HTTP 409 Conflict — data conflict (not authz / not found).",
            f"  Request: {method.upper()} {path}",
            f"  Expected status: {expected}",
            f"  Actual status: 409",
        ]
        if entity_hint:
            lines.append(f"  Entity context: {entity_hint}")
        if request_body is not None:
            lines.append(f"  Request body: {_brief(request_body)}")
        problem = _problem_detail_summary(response_body)
        if problem:
            lines.append(f"  Problem Detail: {problem}")
        elif response_body is not None:
            lines.append(f"  Response body: {_brief(response_body)}")
        lines.append(
            "  Typical causes: unique key taken; FK still referenced; business state conflict."
        )
        return "\n".join(lines)

    @staticmethod
    def not_in_list(*, item: Any, field: str = "id", list_name: str = "response") -> str:
        return (
            f"Item not found in list «{list_name}».\n"
            f"  Looked for {field}={item!r}"
        )

    @staticmethod
    def type_mismatch(*, field: str, expected_type: str, actual: Any) -> str:
        return (
            f"Type mismatch for «{field}».\n"
            f"  Expected type: {expected_type}\n"
            f"  Actual: {type(actual).__name__} = {actual!r}"
        )

    @staticmethod
    def forbidden_access(*, role: str, method: str, path: str, actual: Any) -> str:
        return (
            f"Expected access denial (403) for role «{role}».\n"
            f"  Request: {method} {path}\n"
            f"  Actual status: {actual}"
        )

    @staticmethod
    def unexpected_allow(*, role: str, method: str, path: str, actual: Any) -> str:
        return (
            f"Role «{role}» was allowed but should not be.\n"
            f"  Request: {method} {path}\n"
            f"  Status: {actual}"
        )

    @staticmethod
    def precondition(*, what: str, detail: str = "") -> str:
        d = f"\n  {detail}" if detail else ""
        return f"Test precondition failed: {what}.{d}"

    @staticmethod
    def contains_secret(*, fields: Sequence[str]) -> str:
        return "Sensitive fields found in response:\n  " + ", ".join(fields)


class StepTemplates:
    @staticmethod
    def http(method: str, path: str, expected: Any = None) -> str:
        base = f"HTTP {method.upper()} {path}"
        if expected is not None:
            return f"{base} → expect status={expected}"
        return base

    @staticmethod
    def prepare(what: str) -> str:
        return f"Prepare: {what}"

    @staticmethod
    def assert_field(field: str, expected: Any = None) -> str:
        if expected is not None:
            return f"Check field «{field}» == {expected!r}"
        return f"Check field «{field}»"

    @staticmethod
    def assert_status(expected: Any) -> str:
        return f"Check HTTP status == {expected}"

    @staticmethod
    def assert_list_contains(field: str, value: Any) -> str:
        return f"Check list contains {field}={value!r}"

    @staticmethod
    def assert_schema(model_name: str = "") -> str:
        return f"Validate response schema{(' (' + model_name + ')') if model_name else ''}"

    @staticmethod
    def cleanup(what: str) -> str:
        return f"Cleanup: {what}"

    @staticmethod
    def auth_as(role: str) -> str:
        return f"Act as role «{role}»"

    @staticmethod
    def business(rule: str) -> str:
        return f"Business rule: {rule}"


class DescriptionTemplates:
    @staticmethod
    def crud(action: str, entity: str, extra: str = "") -> str:
        base = (
            f"**Goal:** {action} entity «{entity}».\n\n"
            f"**Typical steps:**\n"
            f"1. HTTP request with valid credentials\n"
            f"2. Check status code\n"
            f"3. Validate schema (pydantic) and key fields\n"
        )
        if extra:
            base += f"\n**Details:** {extra}\n"
        return base

    @staticmethod
    def negative(action: str, entity: str, expected_status: Any, reason: str = "") -> str:
        r = f"\n**Denial reason:** {reason}" if reason else ""
        return (
            f"**Goal:** negative scenario — {action} «{entity}».\n\n"
            f"**Expected:** HTTP {expected_status}.{r}\n"
        )

    @staticmethod
    def rbac(role: str, method: str, resource: str, expected_status: Any) -> str:
        return (
            f"**RBAC check**\n\n"
            f"- Role: `{role}`\n"
            f"- Action: `{method}` on `{resource}`\n"
            f"- Expected status: **{expected_status}**\n"
        )

    @staticmethod
    def security(owasp: str, attack: str, expected: str) -> str:
        return (
            f"**Security / {owasp}**\n\n"
            f"- Vector: {attack}\n"
            f"- Expected safe behaviour: {expected}\n"
        )


def format_http_status_failure(
    *,
    method: str,
    path: str,
    expected: Any,
    actual: Any,
    request_body: Any = None,
    response_body: Any = None,
    original_message: str = "",
) -> str:
    try:
        actual_int = int(actual) if actual is not None else None
    except (TypeError, ValueError):
        actual_int = None

    if actual_int == 409:
        msg = ErrorTemplates.conflict_409(
            method=method,
            path=path,
            expected=expected,
            request_body=request_body,
            response_body=response_body,
            entity_hint=explain_conflict(path, request_body),
        )
    else:
        msg = ErrorTemplates.status(
            expected=expected,
            actual=actual,
            method=method,
            path=path,
            response_body=response_body,
            request_body=request_body,
            hint=http_status_hint(actual),
        )
    if original_message and original_message not in msg:
        msg += f"\n  Original error: {original_message}"
    return msg
