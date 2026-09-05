"""Page health monitor: network, assets, console and page errors.

Sync Playwright-oriented (LIB-UI-02). Works with duck-typed page objects.
Importing this module must not load OpenAPI or project config (LIB-11).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

MONITOR_ATTR = "_partest_monitor"
MONITOR_ATTR_LEGACY = "_aqa_monitor"

# Noise we never treat as test-breaking (favicon, maps, trackers, extensions).
_IGNORE_URL_SUBSTR = (
    "favicon",
    ".map",
    "chrome-extension://",
    "devtools://",
    "google-analytics",
    "googletagmanager",
    "mc.yandex",
    "metrika",
    "hotjar",
    "browser-intake",
    "doubleclick.net",
    "sentry.io/api",
)

_CRITICAL_RESOURCE_TYPES = frozenset(
    {
        "document",
        "stylesheet",
        "script",
        "font",
        "xhr",
        "fetch",
    }
)

_LIBRARY_CONSOLE_RE = re.compile(
    r"(Failed to fetch dynamically imported module|"
    r"Loading chunk \d+ failed|"
    r"Cannot find module|"
    r"is not defined|"
    r"ChunkLoadError|"
    r"Loading CSS chunk|"
    r"net::ERR_|"
    r"Importing a module script failed|"
    r"loading chunk|"
    r"failed to fetch dynamically imported)",
    re.I,
)

# Generic SPA convention (scaffold); override via PageMonitor.app_shell_selector
_DEFAULT_APP_SHELL = '[data-testid="app-shell"]'
_DEFAULT_APP_PAGE = '[data-testid="app-page"]'


@dataclass
class NetworkIssue:
    kind: str  # requestfailed | http_error
    url: str
    method: str = ""
    status: Optional[int] = None
    resource_type: str = ""
    failure_text: str = ""

    def summary(self) -> str:
        if self.kind == "requestfailed":
            return (
                f"[requestfailed] {self.method} {self.resource_type} "
                f"{self.url} — {self.failure_text}"
            )
        return f"[http {self.status}] {self.method} {self.resource_type} {self.url}"


@dataclass
class ConsoleIssue:
    level: str
    text: str
    location: str = ""

    @property
    def type(self) -> str:
        """Alias for older code using ``type``."""
        return self.level

    def summary(self) -> str:
        loc = f" @ {self.location}" if self.location else ""
        return f"[{self.level}] {self.text}{loc}"


@dataclass
class PageMonitor:
    """Collects network / console / page errors for one Page lifetime."""

    page: Any = None
    spa_origin: str = ""
    api_hosts: Sequence[str] = field(default_factory=tuple)
    network_issues: List[NetworkIssue] = field(default_factory=list)
    console_errors: List[ConsoleIssue] = field(default_factory=list)
    page_errors: List[str] = field(default_factory=list)
    app_shell_selector: str = _DEFAULT_APP_SHELL
    app_page_selector: str = _DEFAULT_APP_PAGE
    ignore_url_substrings: List[str] = field(
        default_factory=lambda: list(_IGNORE_URL_SUBSTR)
    )
    _attached: bool = False
    _handlers: Dict[str, Any] = field(default_factory=dict, repr=False)

    # --- aliases ---
    @property
    def network_errors(self) -> List[NetworkIssue]:
        return self.network_issues

    def add_ignore_urls(self, *substrings: str) -> "PageMonitor":
        self.ignore_url_substrings.extend(substrings)
        return self

    # --- lifecycle ---------------------------------------------------------

    @classmethod
    def attach(
        cls,
        page: Any,
        *,
        spa_base_url: str = "",
        api_base_url: str = "",
        app_shell_selector: str = _DEFAULT_APP_SHELL,
    ) -> "PageMonitor":
        spa_origin = _origin(spa_base_url) or _origin(getattr(page, "url", "") or "")
        api_hosts: List[str] = []
        if api_base_url:
            host = urlparse(api_base_url).netloc
            if host:
                api_hosts.append(host.lower())
        mon = cls(
            page=page,
            spa_origin=spa_origin,
            api_hosts=tuple(api_hosts),
            app_shell_selector=app_shell_selector,
        )
        mon.start()
        setattr(page, MONITOR_ATTR, mon)
        setattr(page, MONITOR_ATTR_LEGACY, mon)
        return mon

    def start(self, page: Any = None) -> "PageMonitor":
        if page is not None:
            self.page = page
        if self.page is None:
            raise RuntimeError("PageMonitor.start requires a page")
        if self._attached:
            return self

        def on_requestfailed(req) -> None:
            try:
                url = req.url
                if self._ignore_url(url):
                    return
                rtype = getattr(req, "resource_type", "") or ""
                if rtype not in _CRITICAL_RESOURCE_TYPES and not self._is_app_url(url):
                    return
                failure = getattr(req, "failure", None) or {}
                if isinstance(failure, dict):
                    text = failure.get("errorText") or ""
                else:
                    text = str(failure or "")
                self.network_issues.append(
                    NetworkIssue(
                        kind="requestfailed",
                        url=url,
                        method=getattr(req, "method", "") or "",
                        status=0,
                        resource_type=rtype,
                        failure_text=text or "unknown",
                    )
                )
            except Exception:
                pass

        def on_response(resp) -> None:
            try:
                status = int(resp.status)
                url = str(resp.url)
                req = resp.request
            except Exception:
                return
            if status < 400:
                return
            if self._ignore_url(url):
                return
            rtype = getattr(req, "resource_type", "") or ""
            is_asset = rtype in ("stylesheet", "script", "font", "document")
            is_api = self._is_api_url(url) or rtype in ("xhr", "fetch")
            if is_asset and status >= 400:
                self.network_issues.append(
                    NetworkIssue(
                        kind="http_error",
                        url=url,
                        method=getattr(req, "method", "") or "",
                        status=status,
                        resource_type=rtype,
                    )
                )
                return
            if is_api and status >= 500:
                self.network_issues.append(
                    NetworkIssue(
                        kind="http_error",
                        url=url,
                        method=getattr(req, "method", "") or "",
                        status=status,
                        resource_type=rtype,
                    )
                )
                return
            if self._is_spa_url(url) and status >= 500:
                self.network_issues.append(
                    NetworkIssue(
                        kind="http_error",
                        url=url,
                        method=getattr(req, "method", "") or "",
                        status=status,
                        resource_type=rtype,
                    )
                )

        def on_console(msg) -> None:
            try:
                level = getattr(msg, "type", "") or ""
                text = getattr(msg, "text", "") or ""
            except Exception:
                return
            if level not in ("error", "assert"):
                if level == "warning" and _LIBRARY_CONSOLE_RE.search(text or ""):
                    pass
                else:
                    return
            if self._ignore_console(text):
                return
            loc = ""
            try:
                loc_obj = getattr(msg, "location", None) or {}
                if isinstance(loc_obj, dict):
                    loc = f"{loc_obj.get('url', '')}:{loc_obj.get('lineNumber', '')}"
            except Exception:
                pass
            self.console_errors.append(
                ConsoleIssue(level=level, text=text or "", location=loc)
            )

        def on_pageerror(exc: Any) -> None:
            text = str(exc) if exc is not None else "pageerror"
            if self._ignore_console(text):
                return
            self.page_errors.append(text)

        self.page.on("requestfailed", on_requestfailed)
        self.page.on("response", on_response)
        self.page.on("console", on_console)
        try:
            self.page.on("pageerror", on_pageerror)
        except Exception:
            pass
        self._handlers = {
            "requestfailed": on_requestfailed,
            "response": on_response,
            "console": on_console,
            "pageerror": on_pageerror,
        }
        self._attached = True
        return self

    def stop(self) -> None:
        if not self._attached or self.page is None:
            return
        for event, handler in self._handlers.items():
            try:
                self.page.remove_listener(event, handler)
            except Exception:
                pass
        self._attached = False

    def reset(self) -> None:
        self.network_issues.clear()
        self.console_errors.clear()
        self.page_errors.clear()

    # --- classification ----------------------------------------------------

    def _ignore_url(self, url: str) -> bool:
        return should_ignore_url(url, extra=self.ignore_url_substrings)

    def _ignore_console(self, text: str) -> bool:
        t = (text or "").lower()
        if "resizeobserver loop" in t:
            return True
        if "favicon" in t:
            return True
        if "[hmr]" in t or "webpack" in t:
            return True
        return False

    def _is_spa_url(self, url: str) -> bool:
        if not self.spa_origin:
            return False
        return _origin(url) == self.spa_origin

    def _is_api_url(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        if host in {h.lower() for h in self.api_hosts}:
            return True
        path = urlparse(url).path or ""
        return "/api/" in path or path.startswith("/api")

    def _is_app_url(self, url: str) -> bool:
        return self._is_spa_url(url) or self._is_api_url(url)

    # --- libraries / assets ------------------------------------------------

    def collect_loaded_assets(self) -> Dict[str, Any]:
        """Snapshot of scripts/styles via Performance API + DOM readiness (sync)."""
        if self.page is None:
            return {"error": "no page", "readyState": "unknown", "scriptCount": 0}
        shell_sel = self.app_shell_selector.replace("\\", "\\\\").replace("'", "\\'")
        page_sel = self.app_page_selector.replace("\\", "\\\\").replace("'", "\\'")
        try:
            return self.page.evaluate(
                f"""() => {{
                  const resources = performance.getEntriesByType('resource') || [];
                  const scripts = resources
                    .filter(r => r.initiatorType === 'script'
                      || /\\.m?js(\\?|$)/i.test(r.name))
                    .map(r => ({{
                      name: r.name,
                      duration: Math.round(r.duration || 0),
                      transferSize: r.transferSize || 0,
                      initiatorType: r.initiatorType,
                    }}));
                  const styles = resources
                    .filter(r => r.initiatorType === 'link'
                      || r.initiatorType === 'css'
                      || /\\.css(\\?|$)/i.test(r.name))
                    .map(r => ({{
                      name: r.name,
                      duration: Math.round(r.duration || 0),
                      transferSize: r.transferSize || 0,
                    }}));
                  const fonts = resources
                    .filter(r => /\\.(woff2?|ttf|otf)(\\?|$)/i.test(r.name))
                    .map(r => r.name);
                  return {{
                    readyState: document.readyState,
                    title: document.title || '',
                    scriptCount: scripts.length,
                    styleCount: styles.length,
                    fontCount: fonts.length,
                    scripts: scripts.slice(0, 40),
                    styles: styles.slice(0, 20),
                    hasAppShell: !!document.querySelector('{shell_sel}'),
                    hasAppPage: !!document.querySelector('{page_sel}'),
                    bodyChildCount: document.body
                      ? document.body.children.length : 0,
                  }};
                }}"""
            )
        except Exception as ex:
            return {"error": str(ex), "readyState": "unknown", "scriptCount": 0}

    def library_issues(self, *, require_app_shell: bool = False) -> List[str]:
        issues: List[str] = []
        assets = self.collect_loaded_assets()
        if assets.get("error"):
            issues.append(f"Performance snapshot failed: {assets['error']}")
            return issues

        ready = assets.get("readyState")
        if ready not in ("interactive", "complete"):
            issues.append(
                f"document.readyState={ready!r} (expected interactive|complete)"
            )

        url = _safe_url(self.page)
        on_auth_host = "keycloak" in url.lower() or "auth." in url.lower()

        if not on_auth_host:
            if int(assets.get("scriptCount") or 0) < 1:
                issues.append(
                    "No script resources in Performance timeline — "
                    "SPA libraries may not have loaded"
                )
            if require_app_shell and not assets.get("hasAppShell"):
                issues.append(
                    f"{self.app_shell_selector} missing — SPA shell/bootstrap failed"
                )
            if int(assets.get("bodyChildCount") or 0) < 1:
                issues.append("document.body has no children — blank page")

        for c in self.console_errors:
            if is_library_console_message(c.text or ""):
                issues.append(f"Library/console: {c.summary()}")

        for pe in self.page_errors:
            if is_library_console_message(pe or "") or "ChunkLoadError" in (pe or ""):
                issues.append(f"Library/pageerror: {pe}")

        for n in self.network_issues:
            if n.resource_type in ("script", "stylesheet", "font"):
                issues.append(f"Asset load: {n.summary()}")

        return issues

    def critical_issues(
        self,
        *,
        require_app_shell: bool = False,
        check_libraries: bool = True,
    ) -> List[str]:
        issues: List[str] = []
        for n in self.network_issues:
            issues.append(f"Network: {n.summary()}")
        for c in self.console_errors:
            issues.append(f"Console: {c.summary()}")
        for pe in self.page_errors:
            issues.append(f"PageError: {pe}")
        if check_libraries:
            for lib in self.library_issues(require_app_shell=require_app_shell):
                if lib not in issues and not any(lib in i for i in issues):
                    if lib.startswith("Asset load:"):
                        continue
                    if lib.startswith("Library/console:"):
                        continue
                    issues.append(lib)
        return issues

    def has_critical_issues(self, **kwargs) -> bool:
        return bool(self.critical_issues(**kwargs))

    def format_issues(self, **kwargs) -> str:
        issues = self.critical_issues(**kwargs)
        if not issues:
            return "Page health: OK (no critical network/library/console issues)"
        lines = ["Page health FAILED — critical issues:", ""]
        for i, issue in enumerate(issues, 1):
            lines.append(f"  {i}. {issue}")
        lines.append("")
        lines.append(
            "See Allure attachments: ui_network_issues, ui_console_errors, "
            "ui_assets, ui_final_screenshot"
        )
        return "\n".join(lines)

    def issues_summary(self) -> str:
        return self.format_issues()

    # --- Allure ------------------------------------------------------------

    def attach_report(self, *, require_app_shell: bool = False) -> None:
        from partest.ui import allure_ui

        assets = self.collect_loaded_assets()
        issues = self.critical_issues(require_app_shell=require_app_shell)

        allure_ui.attach_json(
            "ui_health_summary",
            {
                "url": _safe_url(self.page),
                "ok": not issues,
                "issue_count": len(issues),
                "issues": issues,
                "network_issue_count": len(self.network_issues),
                "console_error_count": len(self.console_errors),
                "page_error_count": len(self.page_errors),
                "scriptCount": assets.get("scriptCount"),
                "styleCount": assets.get("styleCount"),
                "readyState": assets.get("readyState"),
                "hasAppShell": assets.get("hasAppShell"),
            },
        )
        if self.network_issues:
            allure_ui.attach_json(
                "ui_network_issues",
                [n.__dict__ for n in self.network_issues],
            )
        else:
            allure_ui.attach_text(
                "ui_network_issues",
                "none — no critical network failures recorded",
            )
        if self.console_errors or self.page_errors:
            allure_ui.attach_json(
                "ui_console_errors",
                {
                    "console": [c.__dict__ for c in self.console_errors],
                    "page_errors": list(self.page_errors),
                },
            )
        else:
            allure_ui.attach_text(
                "ui_console_errors",
                "none — no console/page errors recorded",
            )
        allure_ui.attach_json("ui_assets", assets)
        allure_ui.attach_text(
            "ui_health_verdict",
            self.format_issues(require_app_shell=require_app_shell),
        )

    def attach_final_screenshot(self, name: str = "ui_final_screenshot") -> None:
        from partest.ui import allure_ui

        allure_ui.attach_screenshot(self.page, name=name)
        allure_ui.attach_url(self.page, name="ui_final_url")

    def finalize(
        self,
        *,
        test_failed: bool = False,
        require_app_shell: bool = False,
        assert_healthy: bool = True,
    ) -> None:
        """End-of-test: screenshot + Allure; fail if health broken and test was green."""
        try:
            self.attach_final_screenshot()
        except Exception:
            pass
        try:
            self.attach_report(require_app_shell=require_app_shell)
        except Exception:
            pass
        if test_failed or not assert_healthy:
            return
        if self.has_critical_issues(require_app_shell=require_app_shell):
            import pytest

            pytest.fail(self.format_issues(require_app_shell=require_app_shell))


def _origin(url: str) -> str:
    if not url:
        return ""
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return ""
    return f"{p.scheme}://{p.netloc}".lower()


def _safe_url(page: Any) -> str:
    try:
        return page.url or ""
    except Exception:
        return ""


def should_ignore_url(
    url: str, *, extra: Optional[Sequence[str]] = None
) -> bool:
    """Pure helper for unit tests (LIB-UI-03)."""
    u = (url or "").lower()
    subs = list(_IGNORE_URL_SUBSTR)
    if extra:
        subs.extend(extra)
    return any(s.lower() in u for s in subs)


def is_library_console_message(text: str) -> bool:
    """True if console text looks like missing chunk/module (LIB-UI-03)."""
    return bool(_LIBRARY_CONSOLE_RE.search(text or ""))


def attach_monitor(
    page: Any,
    monitor: Optional[PageMonitor] = None,
    *,
    spa_base_url: str = "",
    api_base_url: str = "",
    **kwargs: Any,
) -> PageMonitor:
    """Attach monitor (alias of ``PageMonitor.attach`` for free-function API)."""
    if monitor is not None:
        monitor.start(page)
        setattr(page, MONITOR_ATTR, monitor)
        setattr(page, MONITOR_ATTR_LEGACY, monitor)
        if spa_base_url:
            monitor.spa_origin = _origin(spa_base_url) or monitor.spa_origin
        if api_base_url:
            host = urlparse(api_base_url).netloc
            if host and host.lower() not in {h.lower() for h in monitor.api_hosts}:
                monitor.api_hosts = tuple(monitor.api_hosts) + (host.lower(),)
        return monitor
    return PageMonitor.attach(
        page, spa_base_url=spa_base_url, api_base_url=api_base_url, **kwargs
    )


def get_monitor(page: Any) -> Optional[PageMonitor]:
    return getattr(page, MONITOR_ATTR, None) or getattr(page, MONITOR_ATTR_LEGACY, None)


def detach_monitor(page: Any) -> None:
    mon = get_monitor(page)
    if mon is not None:
        mon.stop()
    for attr in (MONITOR_ATTR, MONITOR_ATTR_LEGACY):
        if hasattr(page, attr):
            try:
                delattr(page, attr)
            except Exception:
                setattr(page, attr, None)
