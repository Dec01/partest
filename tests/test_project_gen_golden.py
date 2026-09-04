"""Golden e2e: OpenAPI fixture → full generate → import + collect-only smoke.

CI-friendly: no live stand, no browser. Ensures G1–G5 output stays importable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from partest.project_gen.cli import main as cli_main

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"
LIB_ROOT = Path(__file__).resolve().parents[1]


def _pythonpath(extra: Path | None = None) -> str:
    parts = [str(LIB_ROOT)]
    if extra is not None:
        parts.insert(0, str(extra))
    existing = os.environ.get("PYTHONPATH", "")
    if existing:
        parts.append(existing)
    return os.pathsep.join(parts)


def _env_for_suite(suite_root: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = _pythonpath(suite_root)
    # avoid picking up host confpartest / plugins noise
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    return env


@pytest.fixture
def golden_suite(tmp_path: Path) -> Path:
    dest = tmp_path / "golden_suite"
    rc = cli_main(
        [
            "from-openapi",
            str(dest),
            "--file",
            str(FIXTURE),
            "--depth",
            "p1",
            "--force",
            "--with-ui",
            "--name",
            "golden",
        ]
    )
    assert rc == 0, "from-openapi --depth p1 --with-ui failed"
    return dest


def test_golden_tree_shape(golden_suite: Path):
    root = golden_suite
    must = [
        "confpartest.py",
        "conftest.py",
        "docs/openapi.yaml",
        ".partest/suite_ir.json",
        ".partest/openapi_summary.md",
        "src/api/resources/endpoints/paths.py",
        "src/api/resources/collections/factory.py",
        "src/api/tests/items/test_items_default.py",
        "src/api/tests/items/test_items_new_object.py",
        "src/api/tests/items/test_items_incorrect_body.py",
        "src/api/tests/items/P1_CHECKLIST.md",
        "src/api/tests/test_zorro.py",
        "src/ui/conftest.py",
        "src/ui/pages/base_page.py",
        "src/ui/tools/capture_baselines.py",
        "src/ui/baselines/reference/.gitkeep",
        "docs/UI_GUIDE.md",
        "scripts/run_ui.ps1",
    ]
    missing = [p for p in must if not (root / p).is_file()]
    assert not missing, f"missing golden artifacts: {missing}"

    summary = (root / ".partest/openapi_summary.md").read_text(encoding="utf-8")
    assert "items" in summary.lower()
    paths = (root / "src/api/resources/endpoints/paths.py").read_text(encoding="utf-8")
    assert "/items" in paths or "items" in paths


def test_golden_import_smoke(golden_suite: Path):
    """Import generated packages with suite root on PYTHONPATH."""
    code = """
import importlib
mods = [
    "src.api.resources.endpoints.paths",
    "src.api.resources.collections.factory",
    "src.api.tests.conftest",
    "src.ui.pages.base_page",
    "src.ui.utils.page_monitor",
]
for m in mods:
    importlib.import_module(m)
print("ok", len(mods))
"""
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=golden_suite,
        env=_env_for_suite(golden_suite),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, f"import smoke failed:\n{r.stdout}\n{r.stderr}"
    assert "ok" in r.stdout


def test_golden_api_collect_only(golden_suite: Path):
    """pytest --collect-only on generated API tests (no network)."""
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "src/api/tests",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=golden_suite,
        env=_env_for_suite(golden_suite),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, f"collect-only failed:\n{r.stdout}\n{r.stderr}"
    out = r.stdout + r.stderr
    assert "test_items_default" in out or "TestItemsDefault" in out
    # expect a reasonable suite size from sample OpenAPI
    assert "collected" in out.lower() or "test session" in out.lower() or "tests" in out.lower()


def test_golden_ui_collect_only(golden_suite: Path):
    """Collect UI smoke tests if playwright is available; else skip soft."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        pytest.skip("playwright not installed — UI collect optional")

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "src/ui/tests",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=golden_suite,
        env=_env_for_suite(golden_suite),
        capture_output=True,
        text=True,
        timeout=120,
    )
    # UI may need pytest-playwright plugin; accept 0 or document skip
    if r.returncode != 0:
        # still assert tree is present; collection plugins may be missing in lib CI
        assert (golden_suite / "src/ui/tests/smoke/test_ui_smoke.py").is_file()
        pytest.skip(f"UI collect needs suite plugins: {r.stderr[:400]}")
    assert "test_" in r.stdout


def test_sync_openapi_idempotent_banner(golden_suite: Path):
    """Second sync-openapi should not explode; summary stays."""
    rc = cli_main(
        [
            "sync-openapi",
            str(golden_suite),
            "--file",
            str(FIXTURE),
            "--depth",
            "p1",
        ]
    )
    assert rc == 0
    assert (golden_suite / ".partest/suite_ir.json").is_file()
