"""G4: full P1 matrix test stubs."""

from __future__ import annotations

from pathlib import Path

from partest.project_gen.cli import main as cli_main
from partest.project_gen.emitters.resources import emit_resources
from partest.project_gen.emitters.tests_p1 import build_p1_test_files
from partest.project_gen.openapi_load import load_openapi
from partest.project_gen.skeleton import init_skeleton
from partest.project_gen.emitters.paths import get_tag_path_attrs

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"


def test_p1_files_for_post_create():
    ir = load_openapi(FIXTURE)
    attrs = get_tag_path_attrs(ir)
    files = build_p1_test_files(ir, attrs)
    # POST create P1 includes new_object, incorrect_body, elements, extra, permissions
    assert any("test_items_new_object.py" in k for k in files)
    assert any("test_items_incorrect_body.py" in k for k in files)
    assert any("test_items_elements.py" in k for k in files)
    assert any("test_items_extra_data.py" in k for k in files)
    assert any("test_items_permissions.py" in k for k in files)
    # GET dynamic P1: permissions, not_found
    assert any("test_items_not_found.py" in k for k in files)
    assert any("P1_CHECKLIST.md" in k for k in files)

    body = next(v for k, v in files.items() if k.endswith("incorrect_body.py"))
    assert "assert_raw_incorrect_body" in body
    assert "RAW_INCORRECT_BODY_CASES" in body
    assert "request_incorrect_body" in body or "assert_raw_incorrect_body" in body

    elems = next(v for k, v in files.items() if k.endswith("elements.py"))
    assert "get_json_miss_required" in elems
    assert "request_elements" in elems


def test_emit_depth_p1(tmp_path: Path):
    ir = load_openapi(FIXTURE)
    root = tmp_path / "suite"
    init_skeleton(root, name="shop", force=True)
    emit_resources(root, ir, force=True, depth="p1")

    assert (root / "src/api/tests/items/test_items_default.py").is_file()
    assert (root / "src/api/tests/items/test_items_not_allowed.py").is_file()
    assert (root / "src/api/tests/items/test_items_permissions.py").is_file()
    assert (root / "src/api/tests/items/test_items_new_object.py").is_file()
    assert (root / "src/api/tests/items/test_items_incorrect_body.py").is_file()
    assert (root / "src/api/tests/items/test_items_elements.py").is_file()
    assert (root / "src/api/tests/items/test_items_extra_data.py").is_file()
    assert (root / "src/api/tests/items/test_items_not_found.py").is_file()
    assert (root / "src/api/tests/items/P1_CHECKLIST.md").is_file()
    # payloads still present
    assert (root / "src/api/resources/payloads/items/post_items_payload.py").is_file()


def test_depth_default_no_p1_extras(tmp_path: Path):
    ir = load_openapi(FIXTURE)
    root = tmp_path / "suite"
    init_skeleton(root, name="shop", force=True)
    emit_resources(root, ir, force=True, depth="default")
    assert (root / "src/api/tests/items/test_items_default.py").is_file()
    assert not (root / "src/api/tests/items/test_items_permissions.py").exists()
    assert not (root / "src/api/tests/items/P1_CHECKLIST.md").exists()


def test_cli_depth_p1(tmp_path: Path):
    dest = tmp_path / "proj"
    rc = cli_main(
        [
            "from-openapi",
            str(dest),
            "--file",
            str(FIXTURE),
            "--depth",
            "p1",
            "--force",
        ]
    )
    assert rc == 0
    assert (dest / "src/api/tests/items/test_items_new_object.py").is_file()
    summary = (dest / ".partest/openapi_summary.md").read_text(encoding="utf-8")
    assert "G4" in summary or "p1" in summary.lower()
