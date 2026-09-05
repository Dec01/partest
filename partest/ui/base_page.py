"""Base Page Object helpers — **sync** API for pytest-playwright suites.

Also provides :class:`AsyncBasePage` for async Playwright.
"""

from __future__ import annotations

import re
from typing import Any, Optional, Pattern, Union

# Optional playwright imports
try:
    from playwright.sync_api import Page as SyncPage
    from playwright.sync_api import expect as sync_expect
except ImportError:  # pragma: no cover
    SyncPage = object  # type: ignore
    sync_expect = None  # type: ignore

try:
    from playwright.async_api import Page as AsyncPage
    from playwright.async_api import expect as async_expect
except ImportError:  # pragma: no cover
    AsyncPage = object  # type: ignore
    async_expect = None  # type: ignore

_IMPORT_HINT = "partest[ui] requires playwright — pip install partest[ui]"


def _step(title: str):
    try:
        import allure

        return allure.step(title)
    except Exception:
        from contextlib import nullcontext

        return nullcontext()


class BasePage:
    """Sync Page Object base.

    Prefer ``data-testid`` locators. Do not close browser/context from here.
    """

    def __init__(self, page: Any, base_url: str = ""):
        if sync_expect is None and not hasattr(page, "goto"):
            raise RuntimeError(_IMPORT_HINT)
        self.page = page
        self.base_url = (base_url or "").rstrip("/")

    # --- navigation ---

    def goto(self, path: str = "/", *, wait_until: str = "domcontentloaded") -> "BasePage":
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        with _step(f"Open {url}"):
            self.page.goto(url, wait_until=wait_until)
            try:
                from partest.ui.allure_ui import attach_url

                attach_url(self.page, name="opened_url")
            except Exception:
                pass
        return self

    def url(self) -> str:
        return self.page.url

    def title(self) -> str:
        return self.page.title()

    def reload(self, *, wait_until: str = "domcontentloaded") -> "BasePage":
        with _step("Reload page"):
            self.page.reload(wait_until=wait_until)
        return self

    # --- health ---

    def expect_page_healthy(
        self,
        *,
        require_app_shell: bool = False,
        context: str = "",
        **kwargs: Any,
    ) -> None:
        from partest.ui.health import assert_page_healthy

        assert_page_healthy(
            self.page,
            require_app_shell=require_app_shell,
            context=context or self.__class__.__name__,
            **kwargs,
        )

    def attach_step_screenshot(self, name: str) -> None:
        with _step(f"Screenshot: {name}"):
            from partest.ui.allure_ui import attach_screenshot

            attach_screenshot(self.page, name=name)

    # --- locators ---

    def by_test_id(self, test_id: str):
        return self.page.get_by_test_id(test_id)

    def by_role(self, role: str, *, name: Optional[str] = None, **kwargs):
        return self.page.get_by_role(role, name=name, **kwargs)

    def by_text(self, text: str, **kwargs):
        return self.page.get_by_text(text, **kwargs)

    # --- expects ---

    def expect_visible(self, locator, *, timeout: Optional[float] = None) -> None:
        if sync_expect is None:
            raise RuntimeError(_IMPORT_HINT)
        sync_expect(locator).to_be_visible(timeout=timeout)

    def expect_hidden(self, locator, *, timeout: Optional[float] = None) -> None:
        if sync_expect is None:
            raise RuntimeError(_IMPORT_HINT)
        sync_expect(locator).to_be_hidden(timeout=timeout)

    def expect_url_contains(
        self, fragment: Union[str, Pattern[str]], *, timeout: Optional[float] = None
    ) -> None:
        if sync_expect is None:
            raise RuntimeError(_IMPORT_HINT)
        pattern = (
            fragment
            if hasattr(fragment, "search")
            else re.compile(".*" + re.escape(str(fragment)) + ".*")
        )
        sync_expect(self.page).to_have_url(pattern, timeout=timeout)

    def screenshot(
        self,
        path: Optional[str] = None,
        *,
        full_page: bool = True,
        name: Optional[str] = None,
    ) -> bytes:
        if path is None and name:
            path = f"{name}.png"
        return self.page.screenshot(path=path, full_page=full_page)


class AsyncBasePage:
    """Async Playwright Page Object base (opt-in)."""

    def __init__(self, page: Any, base_url: str = ""):
        if async_expect is None and not hasattr(page, "goto"):
            raise RuntimeError(_IMPORT_HINT)
        self.page = page
        self.base_url = (base_url or "").rstrip("/")

    async def goto(
        self, path: str = "/", *, wait_until: str = "domcontentloaded"
    ) -> "AsyncBasePage":
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        await self.page.goto(url, wait_until=wait_until)
        return self

    async def reload(self, *, wait_until: str = "domcontentloaded") -> "AsyncBasePage":
        await self.page.reload(wait_until=wait_until)
        return self

    def by_test_id(self, test_id: str):
        return self.page.get_by_test_id(test_id)

    def by_role(self, role: str, **kwargs):
        return self.page.get_by_role(role, **kwargs)

    def by_text(self, text: str, **kwargs):
        return self.page.get_by_text(text, **kwargs)

    async def expect_visible(self, locator, timeout: Optional[float] = None) -> None:
        if async_expect is None:
            raise RuntimeError(_IMPORT_HINT)
        await async_expect(locator).to_be_visible(timeout=timeout)

    async def expect_hidden(self, locator, timeout: Optional[float] = None) -> None:
        if async_expect is None:
            raise RuntimeError(_IMPORT_HINT)
        await async_expect(locator).to_be_hidden(timeout=timeout)

    async def expect_url_contains(
        self, fragment: Union[str, Pattern[str]], timeout: Optional[float] = None
    ) -> None:
        if async_expect is None:
            raise RuntimeError(_IMPORT_HINT)
        pattern = (
            fragment
            if hasattr(fragment, "search")
            else re.compile(f".*{re.escape(str(fragment))}.*")
        )
        await async_expect(self.page).to_have_url(pattern, timeout=timeout)

    async def expect_page_healthy(self, **kwargs) -> None:
        from partest.ui.health import assert_page_healthy

        assert_page_healthy(self.page, **kwargs)

    async def screenshot(
        self,
        path: Optional[str] = None,
        *,
        full_page: bool = True,
        name: Optional[str] = None,
    ) -> bytes:
        if path is None and name:
            path = f"{name}.png"
        return await self.page.screenshot(path=path, full_page=full_page)
