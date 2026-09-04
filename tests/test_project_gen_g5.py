"""G5: deep UI monorepo layout."""

from __future__ import annotations

from pathlib import Path

from partest.project_gen.cli import main as cli_main
from partest.project_gen.skeleton import apply_ui_layout, init_skeleton
from partest.project_gen.ui_layout import build_ui_files


def test_build_ui_files_has_core_tree():
    files = build_ui_files(project_name="demo")
    expected = [
        "src/ui/conftest.py",
        "src/ui/pages/base_page.py",
        "src/ui/pages/login_page.py",
        "src/ui/utils/page_monitor.py",
        "src/ui/utils/health.py",
        "src/ui/utils/visual_compare.py",
        "src/ui/fixtures/auth.py",
        "src/ui/fixtures/api_seed.py",
        "src/ui/tests/smoke/test_ui_smoke.py",
        "src/ui/tests/visual/test_visual_smoke.py",
        "src/ui/tools/capture_baselines.py",
        "src/ui/tools/scenes.example.json",
        "scripts/run_ui.ps1",
        "scripts/run_ui.sh",
        "docs/UI_GUIDE.md",
        "src/ui/README.md",
    ]
    for rel in expected:
        assert rel in files, f"missing {rel}"
    assert "isolated" in files["src/ui/conftest.py"].lower() or "OpenAPI" in files["src/ui/conftest.py"]
    assert "pytest_plugins" in files["src/ui/conftest.py"]
    assert "partest.ui.pytest_plugin" in files["src/ui/conftest.py"]
    assert "async_playwright" not in files["src/ui/conftest.py"]
    assert "from partest.ui import BasePage" in files["src/ui/pages/base_page.py"]
    assert "AsyncBasePage" not in files["src/ui/pages/base_page.py"]
    assert "capture_baselines_sync" in files["src/ui/tools/capture_baselines.py"]
    smoke = files["src/ui/tests/smoke/test_ui_smoke.py"]
    assert "@pytest.mark.asyncio" not in smoke
    assert "await " not in smoke


def test_init_with_ui(tmp_path: Path):
    root = tmp_path / "suite"
    result = init_skeleton(root, name="shop", with_ui=True, force=True)
    assert (root / "src/ui/conftest.py").is_file()
    assert (root / "src/ui/utils/page_monitor.py").is_file()
    assert (root / "docs/UI_GUIDE.md").is_file()
    assert (root / "scripts/run_ui.ps1").is_file()
    env = (root / "env.example").read_text(encoding="utf-8")
    assert "FRONTEND_URL" in env
    assert result.created


def test_init_ui_on_existing(tmp_path: Path):
    root = tmp_path / "suite"
    init_skeleton(root, name="shop", with_ui=False, force=True)
    assert not (root / "src/ui/conftest.py").exists()
    apply_ui_layout(root, name="shop", force=True)
    assert (root / "src/ui/tests/smoke/test_ui_smoke.py").is_file()
    assert (root / "src/ui/baselines/reference/.gitkeep").is_file()


def test_cli_init_ui(tmp_path: Path):
    dest = tmp_path / "proj"
    cli_main(["init", str(dest), "--name", "demo", "--force"])
    rc = cli_main(["init-ui", str(dest), "--force", "-v"])
    assert rc == 0
    assert (dest / "src/ui/README.md").is_file()
    assert (dest / "docs/UI_GUIDE.md").is_file()


def test_page_monitor_reexports_library(tmp_path: Path):
    """G5 utils re-export partest.ui (1.3)."""
    files = build_ui_files()
    assert "from partest.ui.page_monitor import" in files["src/ui/utils/page_monitor.py"]
    assert "BasePage" in files["src/ui/pages/base_page.py"]
    assert "partest.ui" in files["src/ui/pages/base_page.py"]
