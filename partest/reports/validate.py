"""Check a ``coverage.json`` document against the format this package produces.

The payload is an observable interface, not a private detail of the report: consumers
read it, and some of them **write** it — a map that renders coverage usually ships a
generator for demonstration and test fixtures, and that generator imitates the format by
hand. Until now such a generator had nothing to check itself against, and a drift stayed
silent. One did: it copied ``status`` into ``kind``, so endpoints nobody had called were
filed as ``empty`` and the run's ``unseenRatio`` came out ``0.0`` — not a measured zero
but a zero produced by the wrong label, in the one field that exists to report absence.

So the rules here are deliberately not "is this JSON well-formed". They are the
agreements a hand-written producer gets wrong: which key means what, which value is
allowed to be ``null``, and which numbers must agree with the rows they summarise.

**Absence and wrongness are reported apart.** A key that a current artifact would carry
but an older one would not is a :attr:`Severity.DATED` note, never an error: artifacts
outlive releases, and a validator that fails on last month's file is a validator people
switch off. A key that is present and wrong is an error, and so is a number that
contradicts the endpoints under it.

Nothing here raises. The caller decides what a problem costs — a test asserts the list is
empty, a pipeline prints it, an importer drops the run from its aggregates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "Severity",
    "Problem",
    "validate_coverage_payload",
]


class Severity(str, Enum):
    """How much a problem costs the reader.

    ``DATED`` is not a lesser error, it is a different statement: the document is
    internally consistent and simply predates a field. Collapsing it into ``ERROR`` is
    what makes a format check unusable against stored artifacts.
    """

    ERROR = "error"
    DATED = "dated"


@dataclass(frozen=True)
class Problem:
    """One finding, addressed to the place in the document that carries it."""

    where: str
    what: str
    severity: Severity = Severity.ERROR

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        return f"[{self.severity.value}] {self.where}: {self.what}"


#: Keys every payload has carried since the format existed. Their absence is an error:
#: no release wrote a document without them, so a document without them is not an older
#: artifact — it is something else wearing the name.
_META_ALWAYS: dict[str, type | tuple[type, ...]] = {
    "generated": str,
    "engine": str,
    "title": str,
    "defaultExcluded": list,
    "workers": int,
    "merged": bool,
    "partialRun": bool,
    "callsTotal": int,
}

#: Keys added later, mapped to the release that added them. Absent → ``DATED``;
#: present → checked like any other.
_META_ADDED: dict[str, str] = {
    "unseenRatio": "2.3.0",
    "tlsVerified": "2.0.0",
    "tlsUnverifiedHosts": "2.3.0",
    "tlsUnknownHosts": "2.3.0",
}

_ENDPOINT_KEYS: dict[str, type | tuple[type, ...]] = {
    "method": str,
    "path": str,
    "service": str,
    "serviceLabel": str,
    "subtype": str,
    "subtypeKey": str,
    "calls": int,
    "coverage": (int, float),
    "status": str,
    "kind": str,
    "executed": list,
    "missing": list,
    "description": str,
}

_STATUSES = frozenset({"full", "partial", "empty", "exception", "deprecated"})
_KINDS = frozenset({"full", "partial", "empty", "exception", "unseen"})


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _type_name(expected: type | tuple[type, ...]) -> str:
    if isinstance(expected, tuple):
        return " или ".join(t.__name__ for t in expected)
    return expected.__name__


def _check_type(
    out: list[Problem], where: str, value: Any, expected: type | tuple[type, ...]
) -> bool:
    """``True`` when *value* matches. Booleans are not accepted as integers on purpose:
    ``True == 1`` in Python, and a producer that writes a flag where a count belongs
    would otherwise pass."""
    if expected is bool:
        if not _is_bool(value):
            out.append(Problem(where, f"ожидался bool, получено {type(value).__name__}"))
            return False
        return True
    if expected is int or (isinstance(expected, tuple) and int in expected):
        if _is_bool(value):
            out.append(Problem(where, "получен bool там, где ожидалось число"))
            return False
    if not isinstance(value, expected):
        out.append(
            Problem(where, f"ожидался {_type_name(expected)}, получено {type(value).__name__}")
        )
        return False
    return True


def _check_str_list(out: list[Problem], where: str, value: Any) -> None:
    if not isinstance(value, list):
        out.append(Problem(where, f"ожидался список, получено {type(value).__name__}"))
        return
    for i, item in enumerate(value):
        if not isinstance(item, str):
            out.append(
                Problem(f"{where}[{i}]", f"ожидалась строка, получено {type(item).__name__}")
            )


def _validate_meta(out: list[Problem], meta: Mapping[str, Any], n_endpoints: int) -> None:
    for key, expected in _META_ALWAYS.items():
        if key not in meta:
            out.append(Problem(f"meta.{key}", "ключ отсутствует"))
            continue
        _check_type(out, f"meta.{key}", meta[key], expected)

    for key, since in _META_ADDED.items():
        if key not in meta:
            out.append(
                Problem(
                    f"meta.{key}",
                    f"ключа нет — артефакт старше {since}. Это не «не измерялось»: "
                    "отсутствие ключа и значение в нём отвечают на разные вопросы",
                    Severity.DATED,
                )
            )

    # `unseenRatio` — единственное поле `meta`, которому разрешён `null`, и разрешён он
    # ровно в одном состоянии. Проверять его как «число» — значит воспроизвести тот самый
    # дефект, против которого он заведён: прогон без эндпоинтов не имеет знаменателя, и
    # ноль там утверждал бы «ни один не остался непосещённым».
    if "unseenRatio" in meta:
        ratio = meta["unseenRatio"]
        if ratio is None:
            if n_endpoints:
                out.append(
                    Problem(
                        "meta.unseenRatio",
                        f"null при {n_endpoints} эндпоинтах: «не измерялось» заявлено там, "
                        "где измерять было что",
                    )
                )
        elif _check_type(out, "meta.unseenRatio", ratio, (int, float)):
            if not 0.0 <= float(ratio) <= 1.0:
                out.append(Problem("meta.unseenRatio", f"доля вне диапазона 0..1: {ratio}"))
            elif not n_endpoints:
                out.append(
                    Problem(
                        "meta.unseenRatio",
                        f"{ratio} при нуле эндпоинтов: это не замер, а знаменатель, "
                        "которого не было. Здесь пишется null",
                    )
                )

    if "tlsVerified" in meta:
        _check_type(out, "meta.tlsVerified", meta["tlsVerified"], bool)
    for key in ("tlsUnverifiedHosts", "tlsUnknownHosts"):
        if key in meta:
            _check_str_list(out, f"meta.{key}", meta[key])


def _validate_endpoints(out: list[Problem], endpoints: Sequence[Any]) -> None:
    for i, ep in enumerate(endpoints):
        where = f"endpoints[{i}]"
        if not isinstance(ep, Mapping):
            out.append(Problem(where, f"ожидался объект, получено {type(ep).__name__}"))
            continue

        for key, expected in _ENDPOINT_KEYS.items():
            if key not in ep:
                out.append(Problem(f"{where}.{key}", "ключ отсутствует"))
                continue
            _check_type(out, f"{where}.{key}", ep[key], expected)

        name = f"{ep.get('method', '?')} {ep.get('path', '?')}"
        status, kind, calls = ep.get("status"), ep.get("kind"), ep.get("calls")

        if isinstance(status, str) and status not in _STATUSES:
            out.append(Problem(f"{where}.status", f"{status!r} — не из набора {sorted(_STATUSES)}"))
        if isinstance(kind, str) and kind not in _KINDS:
            out.append(Problem(f"{where}.kind", f"{kind!r} — не из набора {sorted(_KINDS)}"))

        # Здесь и живёт расхождение, ради которого всё это написано. `status` — про
        # методику (все обязательные ячейки, часть, ни одной), `kind` — про то, что
        # наблюдал этот прогон. Производитель, копирующий одно в другое, проходит любую
        # проверку типов и врёт в единственном поле, которое умеет сказать «не видели».
        if isinstance(kind, str) and isinstance(calls, int) and not _is_bool(calls):
            if calls == 0 and kind not in ("unseen", "exception"):
                out.append(
                    Problem(
                        f"{where}.kind",
                        f"{name}: вызовов нет, а kind={kind!r}. Ни одного вызова в этом "
                        "прогоне — это 'unseen'; 'empty' значит «вызывали, но ни одной "
                        "обязательной ячейки»",
                    )
                )
            elif calls > 0 and kind == "unseen":
                out.append(
                    Problem(
                        f"{where}.kind",
                        f"{name}: kind='unseen' при {calls} вызовах",
                    )
                )
        if isinstance(calls, int) and not _is_bool(calls) and calls < 0:
            out.append(Problem(f"{where}.calls", f"{name}: отрицательное число вызовов {calls}"))


def _validate_totals(
    out: list[Problem], meta: Mapping[str, Any], endpoints: Sequence[Any]
) -> None:
    """Числа `meta` должны сходиться со строками под ними.

    Проверка дешёвая и ловит ровно тот класс, который типы пропускают: производитель
    собрал строки правильно, а сводку написал константой.
    """
    rows = [ep for ep in endpoints if isinstance(ep, Mapping)]

    if "callsTotal" in meta and isinstance(meta["callsTotal"], int) and not _is_bool(meta["callsTotal"]):
        actual = sum(
            int(ep["calls"])
            for ep in rows
            if isinstance(ep.get("calls"), int) and not _is_bool(ep.get("calls"))
        )
        if meta["callsTotal"] != actual:
            out.append(
                Problem(
                    "meta.callsTotal",
                    f"{meta['callsTotal']} против {actual} по сумме эндпоинтов",
                )
            )

    ratio = meta.get("unseenRatio")
    if rows and isinstance(ratio, (int, float)) and not _is_bool(ratio):
        unseen = sum(1 for ep in rows if ep.get("kind") == "unseen")
        expected = round(unseen / len(rows), 4)
        if abs(float(ratio) - expected) > 1e-9:
            out.append(
                Problem(
                    "meta.unseenRatio",
                    f"{ratio} против {expected} по разметке kind "
                    f"({unseen} из {len(rows)} непосещённых)",
                )
            )


def validate_coverage_payload(doc: Any) -> list[Problem]:
    """Прочитать документ ``coverage.json`` и вернуть список расхождений с форматом.

    Пустой список — документ согласован. Ошибки и пометки «артефакт старше поля»
    возвращаются вместе; разделить их можно по :attr:`Problem.severity`::

        problems = validate_coverage_payload(json.loads(path.read_text("utf-8")))
        errors = [p for p in problems if p.severity is Severity.ERROR]
        assert not errors, "\\n".join(str(p) for p in errors)

    Ничего не поднимает и ничего не печатает: во что обходится расхождение, решает
    вызывающий.
    """
    out: list[Problem] = []

    if not isinstance(doc, Mapping):
        return [Problem("<корень>", f"ожидался объект, получено {type(doc).__name__}")]

    endpoints = doc.get("endpoints")
    if "endpoints" not in doc:
        out.append(Problem("endpoints", "ключ отсутствует"))
        endpoints = []
    elif not isinstance(endpoints, list):
        out.append(Problem("endpoints", f"ожидался список, получено {type(endpoints).__name__}"))
        endpoints = []

    meta = doc.get("meta")
    if "meta" not in doc:
        out.append(Problem("meta", "ключ отсутствует"))
    elif not isinstance(meta, Mapping):
        out.append(Problem("meta", f"ожидался объект, получено {type(meta).__name__}"))
    else:
        _validate_meta(out, meta, len(endpoints))

    summary = doc.get("summary")
    if "summary" not in doc:
        out.append(Problem("summary", "ключ отсутствует"))
    elif not isinstance(summary, Mapping):
        out.append(Problem("summary", f"ожидался объект, получено {type(summary).__name__}"))
    elif isinstance(summary.get("endpoints"), int) and not _is_bool(summary.get("endpoints")):
        if summary["endpoints"] != len(endpoints):
            out.append(
                Problem(
                    "summary.endpoints",
                    f"{summary['endpoints']} против {len(endpoints)} строк в endpoints",
                )
            )

    # Четыре сводных блока — списки, `heatmap` — объект. Разница не декоративная: я
    # записал её здесь по догадке, и собственный набор тестов поймал ошибку на первом же
    # документе владельца. Правило про чужой формат пишется по коду владельца, а не по
    # тому, как оно выглядит правдоподобно.
    for key in ("services", "subtypes", "methods", "missingTop"):
        if key not in doc:
            out.append(Problem(key, "ключ отсутствует"))
        elif not isinstance(doc[key], list):
            out.append(Problem(key, f"ожидался список, получено {type(doc[key]).__name__}"))

    if "heatmap" not in doc:
        out.append(Problem("heatmap", "ключ отсутствует"))
    elif not isinstance(doc["heatmap"], Mapping):
        out.append(Problem("heatmap", f"ожидался объект, получено {type(doc['heatmap']).__name__}"))

    _validate_endpoints(out, endpoints)

    if isinstance(meta, Mapping):
        _validate_totals(out, meta, endpoints)

    return out
