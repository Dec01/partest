"""L1 tools: openapi resolve, generate_init, tracking extractors, env profiles."""

from __future__ import annotations

from pathlib import Path

import pytest

from partest.openapi import OpenApiResolveError, resolve_swagger
from partest.tools.generate_init import generate_init_for_directory, main as gen_main
from partest.tracking import (
    chain_extractors,
    default_id_extractor,
    field_id_extractor,
    nested_id_extractor,
)
from partest.env.profiles import KeycloakSettings, frontend_url, keycloak_settings

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"


def test_resolve_swagger_local():
    spec = resolve_swagger(FIXTURE)
    assert "paths" in spec
    assert "/items" in spec["paths"] or any("items" in p for p in spec["paths"])


def test_resolve_swagger_pair():
    spec = resolve_swagger(["local", str(FIXTURE)])
    assert spec["info"]["title"]


def test_resolve_swagger_missing():
    with pytest.raises(OpenApiResolveError):
        resolve_swagger("nope/does-not-exist.yaml")


def test_nested_and_field_extractors():
    nested = nested_id_extractor("data", "id")
    assert nested({"data": {"id": 7}}, "POST", "/items") == ("/items", 7)
    assert nested({"id": 1}, "POST", "/items") is None
    assert nested({"data": {"id": 1}}, "GET", "/items") is None

    field = field_id_extractor("uuid")
    assert field({"uuid": "u1"}, "POST", "/x") == ("/x", "u1")

    chained = chain_extractors(nested, default_id_extractor)
    assert chained({"id": 9}, "POST", "/y") == ("/y", 9)
    assert chained({"data": {"id": 3}}, "POST", "/y") == ("/y", 3)


def test_generate_init(tmp_path: Path):
    pkg = tmp_path / "pkg"
    sub = pkg / "sub"
    sub.mkdir(parents=True)
    (pkg / "a.py").write_text("X = 1\n", encoding="utf-8")
    (sub / "__init__.py").write_text("", encoding="utf-8")
    (sub / "b.py").write_text("Y = 2\n", encoding="utf-8")
    written = generate_init_for_directory(pkg)
    assert any(p.name == "__init__.py" for p in written)
    text = (pkg / "__init__.py").read_text(encoding="utf-8")
    assert "from .a import *" in text
    assert "from .sub import *" in text
    assert (sub / "__init__.py").read_text(encoding="utf-8").find("from .b") >= 0


def test_generate_init_cli(tmp_path: Path):
    pkg = tmp_path / "p"
    pkg.mkdir()
    (pkg / "m.py").write_text("Z=1\n", encoding="utf-8")
    assert gen_main(["--directory", str(pkg)]) == 0
    assert (pkg / "__init__.py").is_file()


def test_keycloak_settings(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_URL", "http://kc/")
    monkeypatch.setenv("KEYCLOAK_REALM", "r")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "c")
    monkeypatch.delenv("KEYCLOAK_CLIENT_SECRET", raising=False)
    # bypass dotenv side effects of other tests
    from partest import env as env_mod

    env_mod._ENV_LOADED = False
    kc = keycloak_settings()
    assert isinstance(kc, KeycloakSettings)
    assert kc.url == "http://kc"
    kw = kc.as_token_manager_kwargs()
    assert kw["realm"] == "r"
    assert "client_secret" not in kw


def test_frontend_url_default(monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    from partest import env as env_mod

    env_mod._ENV_LOADED = False
    assert "127.0.0.1" in frontend_url()
