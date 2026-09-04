"""G3: payloads, validations, Default/NotAllowed test stubs."""

from __future__ import annotations

from pathlib import Path

from partest.project_gen.cli import main as cli_main
from partest.project_gen.emitters.payloads import build_payload_files
from partest.project_gen.emitters.resources import emit_resources
from partest.project_gen.emitters.validations import build_validation_files
from partest.project_gen.openapi_load import load_openapi
from partest.project_gen.skeleton import init_skeleton

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"


def test_payload_files_from_schema():
    ir = load_openapi(FIXTURE)
    files = build_payload_files(ir)
    post = [k for k in files if "post_items_payload" in k]
    assert post
    src = files[post[0]]
    assert "BaseRequestBody" in src
    assert "marked_name" in src
    assert '"name"' in src
    assert "parentId" in src
    assert "TODO: seed FK" in src or "0" in src


def test_validation_files_item_and_list():
    ir = load_openapi(FIXTURE)
    files = build_validation_files(ir)
    get_one = [k for k in files if "get_items_by_id_validation" in k]
    get_list = [k for k in files if k.endswith("get_items_validation.py")]
    assert get_one
    assert get_list
    one_src = files[get_one[0]]
    assert "id" in one_src and "Field" in one_src
    list_src = files[get_list[0]]
    assert "RootModel" in list_src or "List" in list_src


def test_emit_g3_full_tree(tmp_path: Path):
    ir = load_openapi(FIXTURE)
    root = tmp_path / "suite"
    init_skeleton(root, name="shop", force=True)
    result = emit_resources(root, ir, force=True, depth="default")

    assert (root / "src/api/resources/payloads/items/post_items_payload.py").is_file()
    assert (
        root / "src/api/resources/validations/items/get_items_by_id_validation.py"
    ).is_file()
    assert (root / "src/api/tests/items/test_items_default.py").is_file()
    assert (root / "src/api/tests/items/test_items_not_allowed.py").is_file()
    assert (root / "src/api/tests/health/test_health_default.py").is_file()

    coll = (root / "src/api/resources/collections/collection_items.py").read_text(
        encoding="utf-8"
    )
    assert "post_items" in coll
    assert "get_items_by_id" in coll
    assert "ProblemDetailValidation" in coll

    default_t = (root / "src/api/tests/items/test_items_default.py").read_text(
        encoding="utf-8"
    )
    assert "request_default" in default_t
    assert "test_get_items_default" in default_t
    assert "test_post_items_default" in default_t

    na = (root / "src/api/tests/items/test_items_not_allowed.py").read_text(
        encoding="utf-8"
    )
    assert "request_not_allowed" in na
    assert "405" in na

    assert result.created


def test_depth_resources_skips_tests(tmp_path: Path):
    ir = load_openapi(FIXTURE)
    root = tmp_path / "suite"
    init_skeleton(root, name="shop", force=True)
    emit_resources(root, ir, force=True, depth="resources")
    assert not (root / "src/api/tests/items/test_items_default.py").exists()
    assert not (root / "src/api/resources/payloads/items/post_items_payload.py").exists()
    assert (root / "src/api/resources/endpoints/paths.py").is_file()


def test_cli_from_openapi_g3(tmp_path: Path):
    dest = tmp_path / "proj"
    rc = cli_main(
        [
            "from-openapi",
            str(dest),
            "--file",
            str(FIXTURE),
            "--depth",
            "default",
            "--force",
        ]
    )
    assert rc == 0
    assert (dest / "src/api/tests/items/test_items_default.py").is_file()
    assert (dest / "src/api/resources/payloads/items/post_items_payload.py").is_file()


def test_ir_has_response_schema():
    ir = load_openapi(FIXTURE)
    get_item = next(o for o in ir.operations if o.operation_id == "getItem")
    assert get_item.success_response_schema is not None
    props = get_item.success_response_schema.get("properties") or {}
    assert "id" in props
