"""Browser storage helpers — functions plus a ``Storage`` façade."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class Storage:
    """Sync Playwright local/session storage façade."""

    def __init__(self, page: Any):
        self.page = page

    def get_local(self, key: str) -> Optional[str]:
        return self.page.evaluate(
            "(k) => window.localStorage.getItem(k)",
            key,
        )

    def set_local(self, key: str, value: str) -> None:
        self.page.evaluate(
            "({k, v}) => window.localStorage.setItem(k, v)",
            {"k": key, "v": value},
        )

    def remove_local(self, key: str) -> None:
        self.page.evaluate(
            "(k) => window.localStorage.removeItem(k)",
            key,
        )

    def clear_local(self) -> None:
        self.page.evaluate("() => window.localStorage.clear()")

    def require_local(self, key: str) -> str:
        value = self.get_local(key)
        if value is None or value == "":
            raise AssertionError(f"localStorage missing key={key!r}")
        return value

    def get_session(self, key: str) -> Optional[str]:
        return self.page.evaluate(
            "(k) => window.sessionStorage.getItem(k)",
            key,
        )

    def set_session(self, key: str, value: str) -> None:
        self.page.evaluate(
            "({k, v}) => window.sessionStorage.setItem(k, v)",
            {"k": key, "v": value},
        )

    def dump_local_keys(self) -> List[str]:
        keys: Any = self.page.evaluate("() => Object.keys(window.localStorage)")
        return list(keys or [])


# --- functional helpers (async-friendly / dump all) ---


async def get_local_storage(page) -> Dict[str, Any]:
    return await page.evaluate(
        """() => {
          const out = {};
          for (let i = 0; i < localStorage.length; i++) {
            const k = localStorage.key(i);
            out[k] = localStorage.getItem(k);
          }
          return out;
        }"""
    )


async def set_local_storage(page, data: Dict[str, str]) -> None:
    await page.evaluate(
        """(data) => {
          for (const [k, v] of Object.entries(data)) {
            localStorage.setItem(k, String(v));
          }
        }""",
        data,
    )


async def get_session_storage(page) -> Dict[str, Any]:
    return await page.evaluate(
        """() => {
          const out = {};
          for (let i = 0; i < sessionStorage.length; i++) {
            const k = sessionStorage.key(i);
            out[k] = sessionStorage.getItem(k);
          }
          return out;
        }"""
    )


async def set_session_storage(page, data: Dict[str, str]) -> None:
    await page.evaluate(
        """(data) => {
          for (const [k, v] of Object.entries(data)) {
            sessionStorage.setItem(k, String(v));
          }
        }""",
        data,
    )


async def clear_storage(page) -> None:
    await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")


async def set_auth_token_storage(
    page,
    token: str,
    *,
    key: str = "access_token",
    where: str = "local",
) -> None:
    data = {key: token}
    if where == "session":
        await set_session_storage(page, data)
    else:
        await set_local_storage(page, data)
