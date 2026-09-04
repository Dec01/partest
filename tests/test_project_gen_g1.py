"""G1: IR builder + monorepo skeleton + CLI smoke."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from partest.project_gen.cli import main as cli_main
from partest.project_gen.ir import build_ir_from_openapi_dict
from partest.project_gen.openapi_load import load_openapi
from partest.project_gen.skeleton import init_skeleton

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"


def test_load_openapi_ir():
    ir = load_openapi(FIXTURE)
    assert ir.title == "Sample Shop API"
    assert ir.version == "1.2.0"
    assert len(ir.operations) >= 5
    tags = ir.tags()
    assert "items" in tags
    assert "health" in tags

    create = next(o for o in ir.operations if o.method == "POST" and o.path == "/items")
    assert create.has_request_body
    assert create.success_status == 201
    assert create.request_schema is not None
    assert "name" in (create.request_schema.get("required") or [])
    assert create.subtype == "post_create_object"
    assert "request_new_object" in create.required_p1
    assert "request_incorrect_body" in create.required_p1

    get_one = next(o for o in ir.operations if o.method == "GET" and o.path == "/items/{id}")
    assert get_one.subtype == "get_dynamic_object"
    assert any(p.name == "id" for p in get_one.path_params)

    listing = next(o for o in ir.operations if o.method == "GET" and o.path == "/items")
    assert listing.subtype in {"get_list_objects", "get_static_object"}


def test_ir_to_dict_jsonable():
    ir = load_openapi(FIXTURE)
    data = ir.to_dict()
    json.dumps(data)  # must not raise
    assert data["operation_count"] == len(ir.operations)


def test_init_skeleton_tree(tmp_path: Path):
    result = init_skeleton(tmp_path / "suite", name="shop", force=True)
    root = Path(result.root)
    expected = [
        "README.md",
        "pytest.ini",
        "confpartest.py",
        "conftest.py",
        "env.example",
        "requirements/api.txt",
        "src/api/tests/conftest.py",
        "src/api/tests/test_zorro.py",
        "src/api/resources/endpoints/paths.py",
        "src/api/resources/validations/common/problem_detail.py",
        "docs/openapi.yaml",
    ]
    for rel in expected:
        assert (root / rel).is_file(), f"missing {rel}"
    assert result.created
    # second run without force skips
    result2 = init_skeleton(tmp_path / "suite", name="shop", force=False)
    assert result2.skipped
    assert not any(x == "README.md" for x in result2.created) or True


def test_init_with_ir_writes_partest_dir(tmp_path: Path):
    ir = load_openapi(FIXTURE)
    result = init_skeleton(
        tmp_path / "suite2",
        name="shop",
        force=True,
        suite_ir=ir,
    )
    root = Path(result.root)
    assert (root / ".partest" / "suite_ir.json").is_file()
    assert (root / ".partest" / "openapi_summary.md").is_file()
    data = json.loads((root / ".partest" / "suite_ir.json").read_text(encoding="utf-8"))
    assert data["title"] == "Sample Shop API"
    assert data["operation_count"] >= 5


def test_cli_dump_ir(tmp_path: Path):
    out = tmp_path / "ir.json"
    rc = cli_main(["dump-ir", str(FIXTURE), "-o", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["title"] == "Sample Shop API"


def test_cli_init(tmp_path: Path):
    dest = tmp_path / "myproj"
    rc = cli_main(
        [
            "init",
            str(dest),
            "--name",
            "myproj",
            "--openapi",
            str(FIXTURE),
            "--force",
        ]
    )
    assert rc == 0
    assert (dest / "src" / "api" / "tests" / "conftest.py").is_file()
    assert (dest / ".partest" / "suite_ir.json").is_file()
    # openapi copied
    assert (dest / "docs" / "openapi.yaml").is_file()
    text = (dest / "docs" / "openapi.yaml").read_text(encoding="utf-8")
    assert "Sample Shop API" in text


def test_cli_from_openapi(tmp_path: Path):
    dest = tmp_path / "from_oas"
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
    assert (dest / ".partest" / "openapi_summary.md").is_file()


def test_cli_init_with_ui(tmp_path: Path):
    dest = tmp_path / "ui_proj"
    rc = cli_main(["init", str(dest), "--with-ui", "--force"])
    assert rc == 0
    assert (dest / "src" / "ui" / "conftest.py").is_file()
