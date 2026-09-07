"""Coverage analysis and report generation."""

from partest.reports.analyzer import CoverageAnalyzer, EndpointCoverage, analyze_coverage
from partest.reports.badge import badge_from_payload, badge_svg
from partest.reports.compare import compare_payloads
from partest.reports.history import (
    append_snapshot,
    latest_snapshot,
    list_snapshots,
    previous_snapshot,
    prune_snapshots,
)
from partest.reports.html_coverage import write_html_report
from partest.reports.payload import build_payload
from partest.reports.services import ServiceMap, ServiceRef, resolve_service
from partest.reports.stubs import generate_stubs
from partest.reports.writer import write_enhanced_report, zorro_enhanced

__all__ = [
    "CoverageAnalyzer",
    "EndpointCoverage",
    "analyze_coverage",
    "write_html_report",
    "write_enhanced_report",
    "zorro_enhanced",
    "build_payload",
    "compare_payloads",
    "append_snapshot",
    "list_snapshots",
    "prune_snapshots",
    "previous_snapshot",
    "latest_snapshot",
    "badge_svg",
    "badge_from_payload",
    "generate_stubs",
    "ServiceMap",
    "ServiceRef",
    "resolve_service",
]
