"""Coverage report entry points: Allure attachments + standalone HTML."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import allure

from partest.allure_graph import create_chart
from partest.call_storage import call_count
from partest.methodology.matrix import CoveragePriority
from partest.reports.analyzer import CoverageReport, analyze_coverage
from partest.reports.html_coverage import write_html_report
from partest.test_types import TYPE_LABELS


def _label(tc: str) -> str:
    return TYPE_LABELS.get(tc, tc)


def _text_summary(report: CoverageReport) -> str:
    border = "*" * 56
    lines = [
        border,
        f"Average coverage (methodology P1 set): {report.average_pct:.2f}%",
        f"Total tracked calls: {report.total_calls}",
        f"Endpoints: full={report.full_count} partial={report.partial_count} "
        f"empty={report.empty_count} exception={report.exception_count}",
        border,
        "",
    ]

    for src, bucket in report.by_swagger.items():
        lines.append(f"Source group '{src}': {bucket['avg_pct']:.2f}% ({bucket['count']} endpoints)")
    lines.append("")

    lines.append("=== By subtype ===")
    for key, bucket in sorted(report.by_subtype.items(), key=lambda x: -x[1]["avg_pct"]):
        lines.append(
            f"  {bucket.get('label', key)}: {bucket['avg_pct']:.1f}% ({bucket['count']} ep)"
        )
    lines.append("")
    return "\n".join(lines)


def _endpoint_block(report: CoverageReport) -> str:
    blocks = []
    for ep in sorted(report.endpoints, key=lambda e: (e.coverage_pct, e.method, e.path)):
        executed = ", ".join(_label(t) for t in sorted(ep.executed_types)) or "—"
        missing = ", ".join(_label(t) for t in ep.missing_p1) or "—"
        present = ", ".join(_label(t) for t in ep.present_required) or "—"
        blocks.append(
            "\n".join(
                [
                    f"{ep.description or '(no description)'}",
                    f"  {ep.method} {ep.path}",
                    f"  Subtype: {ep.subtype_label}",
                    f"  Calls: {ep.calls} | Coverage: {ep.coverage_pct:.1f}% | Status: {ep.status}",
                    f"  Executed: {executed}",
                    f"  Present required: {present}",
                    f"  Missing P1: {missing}",
                    "",
                ]
            )
        )
    return "\n".join(blocks)


def _missing_matrix(report: CoverageReport) -> str:
    lines = ["Missing first-priority test cases by endpoint:", ""]
    any_missing = False
    for ep in report.endpoints:
        if not ep.missing_p1 or ep.is_exception:
            continue
        any_missing = True
        lines.append(f"- {ep.method} {ep.path}")
        for tc in ep.missing_p1:
            lines.append(f"    • {_label(tc)}")
    if not any_missing:
        lines.append("None — all P1 cases present or marked exception.")
    return "\n".join(lines)


def generate_coverage_report(
    *,
    html_path: Union[str, Path] = "coverage_report.html",
    attach_allure: bool = True,
    write_html: bool = True,
    use_matrix: bool = True,
    max_priority: CoveragePriority = CoveragePriority.P1,
    chart_path: str = "api_call_counts.png",
    title: str = "partest API coverage",
) -> CoverageReport:
    """Analyze coverage, write HTML, optionally attach artifacts to Allure.

    Parameters
    ----------
    html_path:
        Output path for the standalone HTML report.
    attach_allure:
        If True, attach text summary, missing matrix, chart to the current Allure test.
    write_html:
        If True, write the HTML file.
    use_matrix:
        If True, required TC come from methodology matrix per subtype.
        If False, fall back to confpartest.test_types_coverage list.
    max_priority:
        Include TC up to this priority when scoring (default P1 only).
    """
    report = analyze_coverage(use_matrix=use_matrix, max_priority=max_priority)

    if write_html:
        out = write_html_report(report, html_path, title=title)
        if attach_allure:
            try:
                with open(out, "rb") as f:
                    allure.attach(
                        f.read(),
                        name="Coverage HTML",
                        attachment_type=allure.attachment_type.HTML,
                    )
            except Exception:
                pass

    if attach_allure:
        allure.attach(
            _text_summary(report),
            name="Coverage summary",
            attachment_type=allure.attachment_type.TEXT,
        )
        allure.attach(
            _endpoint_block(report),
            name="Coverage by endpoint",
            attachment_type=allure.attachment_type.TEXT,
        )
        allure.attach(
            _missing_matrix(report),
            name="Missing P1 test cases",
            attachment_type=allure.attachment_type.TEXT,
        )

        try:
            create_chart(call_count)
            with open(chart_path, "rb") as f:
                allure.attach(
                    f.read(),
                    name="Call counts chart",
                    attachment_type=allure.attachment_type.PNG,
                )
        except Exception:
            pass

        # Per-subtype text attachments
        for key, bucket in report.by_subtype.items():
            lines = [
                f"{bucket.get('label', key)} — avg {bucket['avg_pct']:.1f}%",
                f"endpoints: {bucket['count']}",
                "",
            ]
            for ep in report.endpoints:
                if ep.subtype.value != key:
                    continue
                lines.append(
                    f"{ep.method} {ep.path}: {ep.coverage_pct:.0f}% "
                    f"(missing P1: {', '.join(_label(t) for t in ep.missing_p1) or '—'})"
                )
            allure.attach(
                "\n".join(lines),
                name=f"Subtype: {bucket.get('label', key)}",
                attachment_type=allure.attachment_type.TEXT,
            )

    return report


def zorro(
    html_path: Union[str, Path] = "coverage_report.html",
    *,
    use_matrix: bool = True,
    max_priority: CoveragePriority = CoveragePriority.P1,
) -> CoverageReport:
    """Backward-compatible entry used by test_zorro.

    Generates Allure attachments and ``coverage_report.html``.
    """
    return generate_coverage_report(
        html_path=html_path,
        attach_allure=True,
        write_html=True,
        use_matrix=use_matrix,
        max_priority=max_priority,
    )
