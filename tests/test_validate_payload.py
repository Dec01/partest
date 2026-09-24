"""Проверка формата `coverage.json` ловит то, на чём расходится ручной производитель.

Набор устроен как пара: сначала документ владельца формата обязан пройти без единого
замечания (иначе неверна проверка, а не производитель), и только потом — по одному
случаю на каждое расхождение, которое проверка обязана найти. Второе без первого
бессмысленно: функция, возвращающая пустой список всегда, прошла бы половину набора.
"""

from __future__ import annotations

import copy

import pytest

from partest.reports import Severity, validate_coverage_payload
from partest.methodology.api import MethodSubtype
from partest.reports.analyzer import CoverageReport, EndpointCoverage
from partest.reports.payload import build_payload


def _endpoint(method: str, path: str, *, calls: int, kind: str, status: str) -> EndpointCoverage:
    return EndpointCoverage(
        method=method,
        path=path,
        description="",
        subtype=MethodSubtype.GET_LIST,
        subtype_label="список",
        calls=calls,
        executed_types=set(),
        required_p1=[],
        required_all=[],
        missing_p1=[],
        missing_all=[],
        present_required=[],
        coverage_pct=100.0 if status == "full" else 0.0,
        status=status,
        kind=kind,
    )


def _report(endpoints) -> CoverageReport:
    return CoverageReport(
        endpoints=list(endpoints),
        average_pct=0.0,
        total_calls=sum(e.calls for e in endpoints),
        full_count=0,
        partial_count=0,
        empty_count=0,
        exception_count=0,
        by_subtype={},
        by_swagger={},
    )


@pytest.fixture()
def doc() -> dict:
    """Документ, собранный владельцем формата. Отправная точка всех порч ниже."""
    return build_payload(
        _report(
            [
                _endpoint("GET", "/items", calls=3, kind="full", status="full"),
                _endpoint("POST", "/items", calls=0, kind="unseen", status="empty"),
            ]
        )
    )


def _errors(document) -> list[str]:
    return [str(p) for p in validate_coverage_payload(document) if p.severity is Severity.ERROR]


# --- что обязано проходить -------------------------------------------------


def test_the_owners_own_document_has_no_findings(doc):
    """Без этого всё остальное — проверка чего-то, чего никто не производит."""
    assert validate_coverage_payload(doc) == []


def test_a_run_with_no_endpoints_is_valid_with_a_null_ratio():
    """Пустой прогон — законный документ, и `null` в нём не расхождение, а смысл."""
    empty = build_payload(_report([]))

    assert empty["meta"]["unseenRatio"] is None
    assert validate_coverage_payload(empty) == []


# --- расхождение, ради которого всё написано -------------------------------


def test_kind_copied_from_status_is_found(doc):
    """Настоящий случай: производитель писал в `kind` копию `status`.

    Проверка типов такой документ пропускает — оба значения строки из допустимого
    набора. Врёт он в единственном поле, которое умеет сказать «не видели».
    """
    broken = copy.deepcopy(doc)
    for ep in broken["endpoints"]:
        ep["kind"] = ep["status"]

    found = _errors(broken)

    assert any("вызовов нет" in f and "kind='empty'" in f for f in found), found


def test_a_ratio_that_disagrees_with_the_labels_is_found(doc):
    """Строки собраны верно, сводка написана константой — второй способ солгать тем же числом."""
    broken = copy.deepcopy(doc)
    broken["meta"]["unseenRatio"] = 0.0

    assert any("по разметке kind" in f for f in _errors(broken))


def test_zero_ratio_on_a_run_that_collected_nothing_is_found():
    """Тот самый успокоительный ноль: «ни один не остался непосещённым», не увидев ничего."""
    empty = build_payload(_report([]))
    empty["meta"]["unseenRatio"] = 0.0

    assert any("нуле эндпоинтов" in f for f in _errors(empty))


def test_null_ratio_where_there_was_something_to_measure_is_found(doc):
    """Обратная ошибка: «не измерялось» заявлено там, где измерять было что."""
    broken = copy.deepcopy(doc)
    broken["meta"]["unseenRatio"] = None

    assert any("не измерялось" in f for f in _errors(broken))


def test_unseen_with_calls_is_found(doc):
    broken = copy.deepcopy(doc)
    broken["endpoints"][0]["kind"] = "unseen"

    assert any("kind='unseen' при 3 вызовах" in f for f in _errors(broken))


# --- сводка против строк ---------------------------------------------------


def test_calls_total_that_disagrees_with_the_rows_is_found(doc):
    broken = copy.deepcopy(doc)
    broken["meta"]["callsTotal"] = 99

    assert any("99 против 3" in f for f in _errors(broken))


def test_summary_endpoint_count_that_disagrees_is_found(doc):
    broken = copy.deepcopy(doc)
    broken["summary"]["endpoints"] = 7

    assert any("7 против 2" in f for f in _errors(broken))


# --- «старше поля» отделено от «неверно» -----------------------------------


def test_a_missing_recent_key_is_dated_not_an_error(doc):
    """Артефакты переживают выпуски. Проверка, падающая на прошлогоднем файле, —
    проверка, которую выключают."""
    older = copy.deepcopy(doc)
    del older["meta"]["tlsUnverifiedHosts"]

    problems = validate_coverage_payload(older)

    assert [p.severity for p in problems] == [Severity.DATED]
    assert "старше 2.3.0" in str(problems[0])


def test_a_missing_always_present_key_is_an_error(doc):
    """`callsTotal` есть у формата с самого начала: его отсутствие — не возраст."""
    broken = copy.deepcopy(doc)
    del broken["meta"]["callsTotal"]

    assert any("meta.callsTotal" in f and "отсутствует" in f for f in _errors(broken))


# --- ловушки типов ---------------------------------------------------------


def test_a_bool_where_a_count_belongs_is_found(doc):
    """`True == 1` в Python, поэтому наивная проверка `isinstance(x, int)` это пропустит."""
    broken = copy.deepcopy(doc)
    broken["meta"]["callsTotal"] = True

    assert any("bool там, где ожидалось число" in f for f in _errors(broken))


def test_a_ratio_out_of_range_is_found(doc):
    broken = copy.deepcopy(doc)
    broken["meta"]["unseenRatio"] = 1.5

    assert any("вне диапазона" in f for f in _errors(broken))


def test_a_non_string_in_a_host_list_is_found(doc):
    broken = copy.deepcopy(doc)
    broken["meta"]["tlsUnverifiedHosts"] = ["ok.invalid", 42]

    assert any("tlsUnverifiedHosts[1]" in f for f in _errors(broken))


def test_a_document_that_is_not_an_object_is_reported_once():
    problems = validate_coverage_payload([1, 2, 3])

    assert len(problems) == 1
    assert "<корень>" in str(problems[0])


def test_missing_endpoints_key_is_found(doc):
    broken = copy.deepcopy(doc)
    del broken["endpoints"]

    assert any(f.startswith("[error] endpoints:") for f in _errors(broken))
