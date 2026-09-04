"""Write interactive HTML + coverage.json; wrap zorro()."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from partest.methodology.matrix import CoveragePriority
from partest.reports.analyzer import CoverageReport
from partest.reports.interactive_html import render_html
from partest.reports.payload import build_payload
from partest.reports.services import ServiceMap


@dataclass(frozen=True)
class EnhancedReportPaths:
    html: Path
    json: Path


def write_enhanced_report(
    report: CoverageReport,
    *,
    html_path: Union[str, Path] = "coverage_report.html",
    json_path: Union[str, Path] = "coverage.json",
    title: str = "partest API coverage",
    service_map: Optional[ServiceMap] = None,
) -> EnhancedReportPaths:
    payload = build_payload(report, service_map=service_map or ServiceMap(), title=title)
    html_out = Path(html_path)
    json_out = Path(json_path)
    html_out.write_text(render_html(payload, title=title), encoding="utf-8")
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return EnhancedReportPaths(html=html_out.resolve(), json=json_out.resolve())


def zorro_enhanced(
    html_path: Union[str, Path] = "coverage_report.html",
    json_path: Union[str, Path] = "coverage.json",
    *,
    use_matrix: bool = True,
    max_priority: CoveragePriority = CoveragePriority.P1,
    title: str = "partest API coverage",
    attach_allure: bool = True,
    service_map: Optional[ServiceMap] = None,
) -> CoverageReport:
    """Analyze via partest, then write interactive HTML + coverage.json."""
    from partest.zorro_report import generate_coverage_report

    report = generate_coverage_report(
        html_path=html_path,
        attach_allure=attach_allure,
        write_html=False,
        use_matrix=use_matrix,
        max_priority=max_priority,
        title=title,
    )
    paths = write_enhanced_report(
        report,
        html_path=html_path,
        json_path=json_path,
        title=title,
        service_map=service_map,
    )
    if attach_allure:
        try:
            import allure

            with open(paths.html, "rb") as fh:
                allure.attach(
                    fh.read(),
                    name="Coverage HTML",
                    attachment_type=allure.attachment_type.HTML,
                )
            with open(paths.json, "rb") as fh:
                allure.attach(
                    fh.read(),
                    name="coverage.json",
                    attachment_type=allure.attachment_type.JSON,
                )
        except Exception:
            pass
    return report
