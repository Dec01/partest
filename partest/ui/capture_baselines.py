"""Capture visual baseline screenshots (optional UI extra).

CLI::

    python -m partest.ui.capture_baselines \\
        --out src/ui/baselines/reference \\
        --frontend-url http://127.0.0.1:3000 \\
        --scenes scenes.json

``scenes.json`` is a list of ``{"name": "home", "path": "/"}`` objects
(optional ``full_page``, ``id`` alias for ``name``).
Without scenes the command exits 0 after printing a hint (safe for CI smoke).

``login`` / ``prepare`` hooks are callables supplied by the **consumer**
(no Keycloak / product walk in the library).

Requires: ``pip install partest[ui]`` and ``playwright install chromium``
(unless ``--dry-run``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from partest.ui.visual import (
    VisualScene,
    inject_freeze_styles,
    inject_freeze_styles_sync,
    wait_ready_for_screenshot,
    wait_ready_for_screenshot_sync,
)

SceneLike = Union[VisualScene, Dict[str, Any]]


def load_scenes(source: Union[str, Path, Sequence[SceneLike], None]) -> List[VisualScene]:
    """Load scenes from a JSON path, list of dicts/VisualScene, or empty."""
    if source is None:
        return []
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"scenes file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("scenes JSON must be a list of {name, path} objects")
        return [_as_scene(item) for item in data]
    return [_as_scene(item) for item in source]


def filter_scenes(
    scenes: Sequence[VisualScene],
    only: Optional[Sequence[str]] = None,
) -> List[VisualScene]:
    """Keep scenes whose ``name``/``id`` is in ``only``. ``None`` = all."""
    parsed = list(scenes)
    if not only:
        return parsed
    wanted = {str(x) for x in only}
    return [s for s in parsed if s.name in wanted or s.id in wanted]


def _as_scene(item: SceneLike) -> VisualScene:
    if isinstance(item, VisualScene):
        return item
    name = item.get("name") or item.get("id")
    path = item.get("path")
    if not name or path is None:
        raise ValueError(f"scene requires name+path, got {item!r}")
    full_page = item.get("full_page", True)
    return VisualScene(
        name=str(name),
        path=str(path),
        prepare=item.get("prepare"),
        full_page=bool(full_page),
    )


def _write_manifest(
    out_dir: Path,
    manifest: List[Dict[str, Any]],
    *,
    frontend_url: str,
    viewport: tuple,
) -> Path:
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "frontend_url": frontend_url,
        "viewport": {"width": int(viewport[0]), "height": int(viewport[1])},
        "scenes": manifest,
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


async def capture_baselines(
    scenes: Sequence[SceneLike],
    out: Union[str, Path],
    *,
    frontend_url: str,
    viewport: tuple = (1440, 900),
    headless: bool = True,
    full_page: bool = True,
    login: Optional[Callable] = None,
    settle_ms: int = 200,
    hide_selectors: Sequence[str] = (),
    only: Optional[Sequence[str]] = None,
    locale: str = "en-US",
    ignore_https_errors: bool = True,
) -> List[Dict[str, Any]]:
    """Async Playwright capture. ``login`` is ``async (page) -> None``."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright required — pip install partest[ui] && playwright install chromium"
        ) from e

    parsed = filter_scenes(load_scenes(list(scenes)), only)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not parsed:
        return []

    base = frontend_url.rstrip("/")
    manifest: List[Dict[str, Any]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": int(viewport[0]), "height": int(viewport[1])},
            locale=locale,
            ignore_https_errors=ignore_https_errors,
            device_scale_factor=1,
        )
        page = await context.new_page()
        if login is not None:
            await login(page)
        for sc in parsed:
            if sc.prepare is not None:
                await sc.prepare(page)
            await page.goto(base + sc.path)
            await inject_freeze_styles(page)
            await wait_ready_for_screenshot(
                page, settle_ms=settle_ms, hide_selectors=hide_selectors
            )
            file_name = f"{sc.name}.png"
            path = out_dir / file_name
            use_full = sc.full_page if sc.full_page is not None else full_page
            await page.screenshot(
                path=str(path),
                full_page=use_full,
                animations="disabled",
                caret="hide",
            )
            manifest.append(
                {
                    "name": sc.name,
                    "path": sc.path,
                    "file": file_name,
                    "full_page": use_full,
                }
            )
        _write_manifest(out_dir, manifest, frontend_url=base, viewport=viewport)
        await context.close()
        await browser.close()
    return manifest


def capture_baselines_sync(
    scenes: Sequence[SceneLike],
    out: Union[str, Path],
    *,
    frontend_url: str,
    viewport: tuple = (1440, 900),
    headless: bool = True,
    full_page: bool = True,
    login: Optional[Callable] = None,
    settle_ms: int = 200,
    hide_selectors: Sequence[str] = (),
    only: Optional[Sequence[str]] = None,
    locale: str = "en-US",
    ignore_https_errors: bool = True,
) -> List[Dict[str, Any]]:
    """Sync Playwright capture. ``login`` is ``(page) -> None``."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright required — pip install partest[ui] && playwright install chromium"
        ) from e

    parsed = filter_scenes(load_scenes(list(scenes)), only)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not parsed:
        return []

    base = frontend_url.rstrip("/")
    manifest: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": int(viewport[0]), "height": int(viewport[1])},
            locale=locale,
            ignore_https_errors=ignore_https_errors,
            device_scale_factor=1,
        )
        page = context.new_page()
        if login is not None:
            login(page)
        for sc in parsed:
            if sc.prepare is not None:
                sc.prepare(page)
            page.goto(base + sc.path)
            inject_freeze_styles_sync(page)
            wait_ready_for_screenshot_sync(
                page, settle_ms=settle_ms, hide_selectors=hide_selectors
            )
            file_name = f"{sc.name}.png"
            path = out_dir / file_name
            use_full = sc.full_page if sc.full_page is not None else full_page
            page.screenshot(
                path=str(path),
                full_page=use_full,
                animations="disabled",
                caret="hide",
            )
            manifest.append(
                {
                    "name": sc.name,
                    "path": sc.path,
                    "file": file_name,
                    "full_page": use_full,
                }
            )
        _write_manifest(out_dir, manifest, frontend_url=base, viewport=viewport)
        context.close()
        browser.close()
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m partest.ui.capture_baselines",
        description="Capture UI visual baseline PNGs (partest[ui]).",
    )
    parser.add_argument(
        "--out",
        default="src/ui/baselines/reference",
        help="Output directory for reference PNGs (default: src/ui/baselines/reference)",
    )
    parser.add_argument(
        "--frontend-url",
        default=os.getenv("FRONTEND_URL", "http://127.0.0.1:3000"),
        help="Frontend base URL (env FRONTEND_URL)",
    )
    parser.add_argument(
        "--scenes",
        default=None,
        help="JSON file: list of {name, path} scenes",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Capture only these scene names/ids",
    )
    parser.add_argument(
        "--viewport",
        default="1440x900",
        help="Viewport WIDTHxHEIGHT (default 1440x900)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser headed (default headless)",
    )
    parser.add_argument(
        "--async",
        dest="use_async",
        action="store_true",
        help="Use async Playwright (default: sync)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate args/scenes only; do not launch browser",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        scenes = load_scenes(args.scenes) if args.scenes else []
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    scenes = filter_scenes(scenes, args.only)
    if args.only and args.scenes and not scenes:
        print(f"error: --only did not match any scene: {args.only}", file=sys.stderr)
        return 2

    try:
        w_s, h_s = args.viewport.lower().split("x", 1)
        viewport = (int(w_s), int(h_s))
    except ValueError:
        print("error: --viewport must be WIDTHxHEIGHT, e.g. 1440x900", file=sys.stderr)
        return 2

    if not scenes:
        print(
            "No scenes configured. Pass --scenes path.json "
            'with [{"name": "home", "path": "/"}, ...] '
            "or use the consumer wrapper under src/ui/tools/capture_baselines.py"
        )
        return 0

    if args.dry_run:
        print(f"dry-run: {len(scenes)} scene(s) → {args.out}")
        for sc in scenes:
            print(f"  - {sc.name}: {args.frontend_url.rstrip('/')}{sc.path}")
        return 0

    kwargs = dict(
        frontend_url=args.frontend_url,
        viewport=viewport,
        headless=not args.headed,
    )
    try:
        if args.use_async:
            manifest = asyncio.run(capture_baselines(scenes, args.out, **kwargs))
        else:
            manifest = capture_baselines_sync(scenes, args.out, **kwargs)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    for entry in manifest:
        print("wrote", Path(args.out) / entry["file"])
    print(f"manifest: {len(manifest)} scene(s) → {Path(args.out) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
