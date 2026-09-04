"""G2: paths + collections emitters + sync-openapi CLI."""

from __future__ import annotations

from pathlib import Path

from partest.project_gen.cli import main as cli_main
from partest.project_gen.emitters.paths import build_paths_module_source, get_tag_path_attrs
from partest.project_gen.emitters.resources import emit_resources
from partest.project_gen.openapi_load import load_openapi
from partest.project_gen.skeleton import init_skeleton

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"


def test_paths_module_contains_items():
    ir = load_openapi(FIXTURE)
    src = build_paths_module_source(ir)
    assert "class PathsItems" in src
    assert 'self.items = "/items"' in src or "items" in src
    assert "/items/{id}" in src
    assert "paths = Paths()" in src
    assert "AUTO-GENERATED" in src

    attrs = get_tag_path_attrs(ir)
    assert "items" in attrs
    assert any("/items" == p for p in attrs["items"])


def test_emit_resources_tree(tmp_path: Path):
    ir = load_openapi(FIXTURE)
    root = tmp_path / "suite"
    init_skeleton(root, name="shop", force=True)
    result = emit_resources(root, ir, force=True)

    paths_py = root / "src/api/resources/endpoints/paths.py"
    assert paths_py.is_file()
    text = paths_py.read_text(encoding="utf-8")
    assert "PathsItems" in text
    assert "PathsHealth" in text

    coll = root / "src/api/resources/collections/collection_items.py"
    assert coll.is_file()
    ctext = coll.read_text(encoding="utf-8")
    assert "ItemsCollection" in ctext
    assert "BaseCollection" in ctext
    assert "ModelsPaths" in ctext

    manager = root / "src/api/resources/collections/collections_manager.py"
    mtext = manager.read_text(encoding="utf-8")
    assert "_LibManager" in mtext
    assert "items=" in mtext
    assert "health=" in mtext

    assert (root / ".partest/openapi_summary.md").is_file()
    summary = (root / ".partest/openapi_summary.md").read_text(encoding="utf-8")
    assert "paths.paths_items" in summary
    assert result.created


def test_emit_entities_filter(tmp_path: Path):
    ir = load_openapi(FIXTURE)
    root = tmp_path / "suite"
    init_skeleton(root, name="shop", force=True)
    emit_resources(root, ir, force=True, tags_filter=["items"])

    assert (root / "src/api/resources/collections/collection_items.py").is_file()
    assert not (root / "src/api/resources/collections/collection_health.py").is_file()
    text = (root / "src/api/resources/endpoints/paths.py").read_text(encoding="utf-8")
    assert "PathsItems" in text
    assert "PathsHealth" not in text


def test_generated_banner_allows_resync_without_force(tmp_path: Path):
    ir = load_openapi(FIXTURE)
    root = tmp_path / "suite"
    init_skeleton(root, name="shop", force=True)
    emit_resources(root, ir, force=True)
    # second sync without force should still update generated files
    r2 = emit_resources(root, ir, force=False)
    assert any("paths.py" in c for c in r2.created)


def test_cli_from_openapi_g2(tmp_path: Path):
    dest = tmp_path / "proj"
    rc = cli_main(
        [
            "from-openapi",
            str(dest),
            "--file",
            str(FIXTURE),
            "--name",
            "shop",
            "--force",
        ]
    )
    assert rc == 0
    assert (dest / "src/api/resources/endpoints/paths.py").is_file()
    assert (dest / "src/api/resources/collections/collection_items.py").is_file()


def test_cli_sync_openapi(tmp_path: Path):
    dest = tmp_path / "proj"
    cli_main(["init", str(dest), "--name", "shop", "--force"])
    rc = cli_main(
        ["sync-openapi", str(dest), "--file", str(FIXTURE), "--force", "-v"]
    )
    assert rc == 0
    assert (dest / "src/api/resources/collections/collection_items.py").is_file()
    # filter entities
    rc2 = cli_main(
        [
            "sync-openapi",
            str(dest),
            "--file",
            str(FIXTURE),
            "--entities",
            "health",
            "--force",
        ]
    )
    assert rc2 == 0
    text = (dest / "src/api/resources/endpoints/paths.py").read_text(encoding="utf-8")
    assert "PathsHealth" in text
