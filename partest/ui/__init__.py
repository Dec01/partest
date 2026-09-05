"""UI harness (optional extra: pip install partest[ui]).

Default Page Object API is **sync** (:class:`BasePage`) for pytest-playwright suites.
Use :class:`AsyncBasePage` for async Playwright.
"""

from partest.ui.allure_ui import attach_failure_context, attach_screenshot, attach_url
from partest.ui.base_page import AsyncBasePage, BasePage
from partest.ui.health import (
    assert_libraries_loaded,
    assert_page_console_clean,
    assert_page_healthy,
    assert_page_network_clean,
    ensure_monitor,
)
from partest.ui.page_monitor import (
    MONITOR_ATTR,
    ConsoleIssue,
    NetworkIssue,
    PageMonitor,
    attach_monitor,
    detach_monitor,
    get_monitor,
    is_library_console_message,
    should_ignore_url,
)
from partest.ui.storage import (
    Storage,
    clear_storage,
    get_local_storage,
    get_session_storage,
    set_auth_token_storage,
    set_local_storage,
    set_session_storage,
)
from partest.ui.visual import (
    FREEZE_CSS,
    VisualCompareResult,
    VisualScene,
    compare_images,
    inject_freeze_styles,
    inject_freeze_styles_sync,
    stabilize_page,
    stabilize_page_sync,
    wait_ready_for_screenshot,
    wait_ready_for_screenshot_sync,
)
from partest.ui.capture_baselines import filter_scenes, load_scenes
from partest.ui.hooks import (
    attach_page_monitor,
    finalize_page_monitor,
    resolve_api_base_url,
    resolve_frontend_url,
)

__all__ = [
    "BasePage",
    "AsyncBasePage",
    "PageMonitor",
    "NetworkIssue",
    "ConsoleIssue",
    "MONITOR_ATTR",
    "attach_monitor",
    "get_monitor",
    "detach_monitor",
    "should_ignore_url",
    "is_library_console_message",
    "assert_page_network_clean",
    "assert_page_console_clean",
    "assert_page_healthy",
    "assert_libraries_loaded",
    "ensure_monitor",
    "attach_screenshot",
    "attach_url",
    "attach_failure_context",
    "compare_images",
    "VisualCompareResult",
    "VisualScene",
    "FREEZE_CSS",
    "inject_freeze_styles",
    "inject_freeze_styles_sync",
    "stabilize_page",
    "stabilize_page_sync",
    "wait_ready_for_screenshot",
    "wait_ready_for_screenshot_sync",
    "filter_scenes",
    "resolve_frontend_url",
    "resolve_api_base_url",
    "attach_page_monitor",
    "finalize_page_monitor",
    "Storage",
    "get_local_storage",
    "set_local_storage",
    "get_session_storage",
    "set_session_storage",
    "set_auth_token_storage",
    "clear_storage",
    "load_scenes",
]
