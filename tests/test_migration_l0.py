"""L0 / LIB-* acceptance tests (multi-project safety)."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from partest.client import (
    format_expected_status,
    format_status_mismatch,
    normalize_expected_status,
    status_matches,
)
from partest.collections import BaseCollection, CollectionsManager
from partest.conf import ConfpartestError, require_confpartest, validate_confpartest
from partest.http import Config, HeadersBind
from partest.payloads import BaseRequestBody
from partest.pytest_plugin import plugin_enabled
from partest.security import RiskProfile, by_level, level_of, writable


# --- LIB-01 RiskProfile ---


def test_risk_profile_aqa_fields_critical():
    p = RiskProfile("users", writes=True, authz=True, pii=True)
    assert p.entity == "users"
    assert p.level == "critical"
    assert p.name == "users"  # alias


def test_risk_profile_high_fk():
    p = RiskProfile("clients", writes=True, fk_traversal=True)
    assert p.level == "high"


def test_risk_profile_medium_write():
    p = RiskProfile("notes", writes=True)
    assert p.level == "medium"


def test_risk_profile_low():
    p = RiskProfile("enums")
    assert p.level == "low"


def test_risk_profile_legacy_kwargs():
    p = RiskProfile(name="pay", has_money=True, has_writes=True, has_authz=False)
    assert p.entity == "pay"
    assert p.has_money is True
    assert p.writes is True
    # money+writes → high (extension)
    assert p.level == "high"


def test_risk_profile_from_legacy():
    p = RiskProfile.from_legacy("x", has_writes=True, has_fk=True)
    assert p.fk_traversal and p.level == "high"


def test_risk_registry_helpers():
    PROFILES = {
        "users": RiskProfile("users", writes=True, authz=True),
        "items": RiskProfile("items", writes=True, fk_traversal=True),
        "enums": RiskProfile("enums"),
    }
    assert len(by_level(PROFILES, "critical")) == 1
    assert len(writable(PROFILES)) == 2
    assert level_of(PROFILES, "items") == "high"


# --- LIB-03 multi status ---


def test_normalize_and_match_multi_status():
    assert normalize_expected_status(200) == (200,)
    assert normalize_expected_status((400, 415)) == (400, 415)
    assert status_matches(415, (400, 415))
    assert not status_matches(500, (400, 415))
    assert format_expected_status((400, 415)) == "{400, 415}"


def test_format_status_mismatch_lists_allowed():
    msg = format_status_mismatch(
        method="POST",
        url="/x",
        expected=(400, 415),
        actual=500,
    )
    assert "400" in msg and "415" in msg
    assert "500" in msg


# --- LIB-02 plugin ---


def test_plugin_enabled_env(monkeypatch):
    monkeypatch.setenv("PARTEST_PYTEST_PLUGIN", "0")
    assert plugin_enabled() is False
    monkeypatch.setenv("PARTEST_PYTEST_PLUGIN", "1")
    assert plugin_enabled() is True
    monkeypatch.delenv("PARTEST_PYTEST_PLUGIN", raising=False)


# --- LIB-06 BaseRequestBody property ---


def test_base_request_body_property_style():
    class Body(BaseRequestBody):
        _required = ["name"]

        @property
        def _json_main(self):
            return {"name": "prop-value", "extra": 1}

    b = Body()
    assert b.json["name"] == "prop-value"
    assert "name" in Body.get_json_required()


def test_base_request_body_class_dict():
    class Body(BaseRequestBody):
        _required = ["n"]
        _json_main = {"n": lambda: "x", "o": 2}

    b = Body()
    assert b.json == {"n": "x", "o": 2}


# --- LIB-13/14 collections + headers ---


def test_collections_manager_apply_token():
    class H:
        def __init__(self):
            self.token = None

        def apply_token(self, t):
            self.token = t

    class Coll(BaseCollection):
        def __init__(self):
            self.headers = H()

    mgr = CollectionsManager(a=Coll(), b=Coll())
    mgr.apply_token("tok")
    assert mgr.a.headers.token == "tok"
    assert mgr.b.headers.token == "tok"
    assert "a" in mgr and len(mgr) == 2


def test_config_apply_token_and_headers_bind():
    cfg = Config()
    h = cfg.get_headers(["Accept"], token=None)
    h2 = Config.apply_token(h, "abc")
    assert h2["Authorization"] == "Bearer abc"
    bind = cfg.headers_bind(["Accept", "X-Request-ID"], token="t1")
    assert "Authorization" in bind.headers
    bind.apply_token("t2")
    assert bind.headers["Authorization"].endswith("t2")


# --- confpartest helper ---


def test_validate_confpartest_ok_and_bad():
    ok = SimpleNamespace(
        swagger_files={"api": ["local", "docs/openapi.yaml"]},
        test_types_coverage=["request_default"],
    )
    assert validate_confpartest(ok) == []
    bad = SimpleNamespace(swagger_files="nope")
    errs = validate_confpartest(bad)
    assert errs


def test_require_confpartest_from_tmp(tmp_path: Path, monkeypatch):
    (tmp_path / "confpartest.py").write_text(
        "swagger_files = {'s': ['url', 'https://example.com/o.json']}\n",
        encoding="utf-8",
    )
    # isolate import
    import sys

    monkeypatch.syspath_prepend(str(tmp_path))
    # drop cached module if any
    sys.modules.pop("confpartest", None)
    conf = require_confpartest(project_root=tmp_path)
    assert "s" in conf.swagger_files
