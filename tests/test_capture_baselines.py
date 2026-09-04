"""Unit tests for partest.ui.capture_baselines CLI (no browser)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from partest.ui.capture_baselines import filter_scenes, load_scenes, main
from partest.ui.visual import VisualScene


def test_load_scenes_from_json(tmp_path: Path):
    p = tmp_path / "scenes.json"
    p.write_text(
        json.dumps([{"name": "home", "path": "/"}, {"name": "login", "path": "/login"}]),
        encoding="utf-8",
    )
    scenes = load_scenes(p)
    assert len(scenes) == 2
    assert scenes[0].name == "home"
    assert scenes[1].path == "/login"


def test_load_scenes_from_list():
    scenes = load_scenes([{"name": "a", "path": "/a"}, VisualScene("b", "/b")])
    assert [s.name for s in scenes] == ["a", "b"]


def test_load_scenes_id_alias_and_full_page():
    scenes = load_scenes([{"id": "home", "path": "/", "full_page": False}])
    assert scenes[0].name == "home"
    assert scenes[0].id == "home"
    assert scenes[0].full_page is False


def test_filter_scenes_only():
    scenes = load_scenes(
        [{"name": "a", "path": "/a"}, {"name": "b", "path": "/b"}]
    )
    assert [s.name for s in filter_scenes(scenes, ["b"])] == ["b"]
    assert len(filter_scenes(scenes, None)) == 2


def test_load_scenes_empty():
    assert load_scenes(None) == []
    assert load_scenes([]) == []


def test_load_scenes_invalid(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text('{"not": "list"}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_scenes(p)
    with pytest.raises(ValueError):
        load_scenes([{"name": "x"}])  # missing path


def test_cli_no_scenes_exits_zero():
    assert main([]) == 0


def test_cli_dry_run(tmp_path: Path, capsys):
    p = tmp_path / "scenes.json"
    p.write_text(json.dumps([{"name": "home", "path": "/"}]), encoding="utf-8")
    rc = main(
        [
            "--dry-run",
            "--scenes",
            str(p),
            "--out",
            str(tmp_path / "ref"),
            "--frontend-url",
            "http://example.test",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "home" in out
    assert "example.test" in out


def test_cli_only_dry_run(tmp_path: Path, capsys):
    p = tmp_path / "scenes.json"
    p.write_text(
        json.dumps([{"name": "home", "path": "/"}, {"name": "other", "path": "/x"}]),
        encoding="utf-8",
    )
    rc = main(["--dry-run", "--scenes", str(p), "--only", "home"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "home" in out
    assert "other" not in out


def test_cli_only_misses(tmp_path: Path):
    p = tmp_path / "scenes.json"
    p.write_text(json.dumps([{"name": "home", "path": "/"}]), encoding="utf-8")
    assert main(["--dry-run", "--scenes", str(p), "--only", "nope"]) == 2


def test_cli_bad_viewport(tmp_path: Path):
    p = tmp_path / "scenes.json"
    p.write_text(json.dumps([{"name": "home", "path": "/"}]), encoding="utf-8")
    assert main(["--scenes", str(p), "--viewport", "wide", "--dry-run"]) == 2


def test_cli_missing_scenes_file():
    assert main(["--scenes", "nope-does-not-exist.json", "--dry-run"]) == 2


def test_module_export():
    import importlib

    cb = importlib.import_module("partest.ui.capture_baselines")
    assert callable(cb.main)
    assert callable(cb.capture_baselines)
    # package must not shadow the submodule with the function name
    import partest.ui as ui

    assert hasattr(ui, "load_scenes")
    assert callable(ui.load_scenes)
