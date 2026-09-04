"""Visual compare + freeze helpers (Pillow required for compare).

Freeze / wait helpers have **sync** and **async** variants. Default names that
existed in 1.4 stay async so ``await inject_freeze_styles(page)`` still works.
Sync Playwright (aqa / pytest-playwright) should call ``*_sync``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Union


FREEZE_STYLE_ID = "partest-visual-freeze"

# Generic only — no product / framework screen selectors.
FREEZE_CSS = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
}
html { scroll-behavior: auto !important; }
* { scrollbar-width: none !important; }
::-webkit-scrollbar { width: 0 !important; height: 0 !important; display: none !important; }
"""

_INJECT_FREEZE_JS = """
(payload) => {
  const { css, id } = payload;
  let s = document.getElementById(id);
  if (!s) {
    s = document.createElement('style');
    s.id = id;
    document.head.appendChild(s);
  }
  s.textContent = css;
}
"""

_FONTS_AND_RAF_JS = """
async () => {
  try {
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready;
    }
  } catch (e) {}
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  return document.readyState;
}
"""

_STABILIZE_JS = """
(selectors) => {
  for (const sel of selectors || []) {
    try {
      document.querySelectorAll(sel).forEach((el) => {
        el.style.visibility = 'hidden';
      });
    } catch (e) {}
  }
  document.querySelectorAll('input, textarea').forEach((el) => {
    try { el.blur(); } catch (e) {}
  });
}
"""


@dataclass
class VisualCompareResult:
    equal: bool
    diff_ratio: float
    diff_path: Optional[Path] = None
    message: str = ""
    name: str = ""
    max_diff_ratio: float = 0.0
    different_pixels: int = 0
    total_pixels: int = 0
    baseline_path: Optional[Path] = None
    actual_path: Optional[Path] = None

    @property
    def ok(self) -> bool:
        """Alias for ``equal`` (LIB-UI-04 / aqa shim drop)."""
        return self.equal

    def summary(self) -> str:
        flag = "OK" if self.equal else "DIFF"
        label = self.name or "compare"
        if self.message:
            return f"{flag} {label}: {self.message}"
        return (
            f"{flag} {label}: diff_ratio={self.diff_ratio:.4f} "
            f"(max {self.max_diff_ratio:.4f})"
        )


@dataclass
class VisualScene:
    name: str
    path: str
    prepare: Optional[Callable] = None
    full_page: bool = True

    @property
    def id(self) -> str:
        """aqa-style alias for ``name``."""
        return self.name


def inject_freeze_styles_sync(page, *, css: str = FREEZE_CSS) -> None:
    """Disable animations/scrollbars on a **sync** Playwright page (idempotent)."""
    try:
        page.add_style_tag(content=css)
    except Exception:
        page.evaluate(_INJECT_FREEZE_JS, {"css": css, "id": FREEZE_STYLE_ID})


async def inject_freeze_styles(page, *, css: str = FREEZE_CSS) -> None:
    """Async Playwright page (1.4 name kept)."""
    try:
        await page.add_style_tag(content=css)
    except Exception:
        await page.evaluate(_INJECT_FREEZE_JS, {"css": css, "id": FREEZE_STYLE_ID})


def stabilize_page_sync(page, hide_selectors: Sequence[str] = ()) -> None:
    """Hide optional consumer selectors + blur inputs (sync). No domain defaults."""
    page.evaluate(_STABILIZE_JS, list(hide_selectors or ()))


async def stabilize_page(page, hide_selectors: Sequence[str] = ()) -> None:
    await page.evaluate(_STABILIZE_JS, list(hide_selectors or ()))


def wait_ready_for_screenshot_sync(
    page,
    *,
    settle_ms: int = 200,
    timeout_ms: int = 30_000,
    networkidle: bool = True,
    hide_selectors: Sequence[str] = (),
) -> None:
    """Wait for a quiet document on a **sync** page before screenshot."""
    try:
        page.wait_for_function(
            "() => document.readyState === 'complete'",
            timeout=timeout_ms,
        )
    except Exception:
        pass
    try:
        page.evaluate(_FONTS_AND_RAF_JS)
    except Exception:
        page.wait_for_timeout(min(200, settle_ms))
    if networkidle:
        try:
            page.wait_for_load_state("networkidle", timeout=min(20_000, timeout_ms))
        except Exception:
            page.wait_for_timeout(min(400, settle_ms * 2))
    if hide_selectors:
        stabilize_page_sync(page, hide_selectors)
    if settle_ms:
        page.wait_for_timeout(settle_ms)


async def wait_ready_for_screenshot(
    page,
    *,
    settle_ms: int = 200,
    timeout_ms: int = 30_000,
    networkidle: bool = True,
    hide_selectors: Sequence[str] = (),
) -> None:
    """Async wait (1.4 name kept). Extra kwargs are backward-compatible."""
    try:
        await page.wait_for_function(
            "() => document.readyState === 'complete'",
            timeout=timeout_ms,
        )
    except Exception:
        pass
    try:
        await page.evaluate(_FONTS_AND_RAF_JS)
    except Exception:
        await page.wait_for_timeout(min(200, settle_ms))
    if networkidle:
        try:
            await page.wait_for_load_state("networkidle", timeout=min(20_000, timeout_ms))
        except Exception:
            await page.wait_for_timeout(min(400, settle_ms * 2))
    if hide_selectors:
        await stabilize_page(page, hide_selectors)
    if settle_ms:
        await page.wait_for_timeout(settle_ms)


def compare_images(
    reference: Union[str, Path],
    actual: Union[str, Path],
    *,
    diff_path: Optional[Union[str, Path]] = None,
    diff_output: Optional[Union[str, Path]] = None,
    name: str = "",
    max_diff_ratio: float = 0.01,
    color_tolerance: int = 10,
) -> VisualCompareResult:
    """Pixel diff. ``diff_output`` is an alias of ``diff_path`` (aqa)."""
    try:
        from PIL import Image, ImageChops
    except ImportError as e:
        raise RuntimeError("Pillow required — pip install partest[ui]") from e

    ref_p = Path(reference)
    act_p = Path(actual)
    out = Path(diff_path or diff_output) if (diff_path or diff_output) else None

    ref = Image.open(ref_p).convert("RGB")
    act = Image.open(act_p).convert("RGB")
    if ref.size != act.size:
        return VisualCompareResult(
            False,
            1.0,
            message=f"size mismatch {ref.size} vs {act.size}",
            name=name,
            max_diff_ratio=max_diff_ratio,
            baseline_path=ref_p,
            actual_path=act_p,
        )
    diff = ImageChops.difference(ref, act)
    w, h = ref.size
    total = w * h
    bad = 0
    px = diff.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if max(r, g, b) > color_tolerance:
                bad += 1
    ratio = bad / total if total else 0.0
    if out and bad:
        out.parent.mkdir(parents=True, exist_ok=True)
        diff.save(out)
    return VisualCompareResult(
        equal=ratio <= max_diff_ratio,
        diff_ratio=ratio,
        diff_path=out if bad else None,
        message=f"diff_ratio={ratio:.4f} (max {max_diff_ratio})",
        name=name,
        max_diff_ratio=max_diff_ratio,
        different_pixels=bad,
        total_pixels=total,
        baseline_path=ref_p,
        actual_path=act_p,
    )
