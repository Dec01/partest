"""Emit the monorepo skeleton (G1 — no entity tests)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from partest.project_gen.ir import SuiteIR
from partest.project_gen.ui_layout import build_ui_files


@dataclass
class WriteResult:
    created: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    root: str = ""


def _write(
    root: Path,
    rel: str,
    content: str,
    *,
    force: bool,
    result: WriteResult,
) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        result.skipped.append(rel.replace("\\", "/"))
        return
    path.write_text(content, encoding="utf-8", newline="\n")
    result.created.append(rel.replace("\\", "/"))


def _py_init() -> str:
    return '"""Package."""\n'


def apply_ui_layout(
    root: Path,
    *,
    name: str = "api-suite",
    force: bool = False,
    result: Optional[WriteResult] = None,
) -> WriteResult:
    """Write G5 UI tree into an existing project root."""
    if result is None:
        result = WriteResult(root=str(root.resolve()))
    for rel, content in build_ui_files(project_name=name).items():
        _write(root, rel, content, force=force, result=result)
    # extend env.example if present
    env_path = root / "env.example"
    if env_path.is_file():
        text = env_path.read_text(encoding="utf-8")
        if "FRONTEND_URL" not in text:
            text += (
                "\n# UI (G5)\n"
                "FRONTEND_URL=http://127.0.0.1:3000\n"
                "FRONTEND_UI_USER=\n"
                "FRONTEND_UI_PASSWORD=\n"
                "UI_HEADED=0\n"
            )
            if force or "FRONTEND_URL" not in env_path.read_text(encoding="utf-8"):
                env_path.write_text(text, encoding="utf-8")
                rel = "env.example"
                if rel not in result.created and rel not in result.skipped:
                    result.created.append(rel + " (UI keys)")
    gitignore = root / ".gitignore"
    if gitignore.is_file():
        gi = gitignore.read_text(encoding="utf-8")
        extra = "\nsrc/ui/baselines/actual/\nsrc/ui/baselines/diff/\n"
        if "baselines/actual" not in gi:
            gitignore.write_text(gi + extra, encoding="utf-8")
    return result


def init_skeleton(
    target: Union[str, Path],
    *,
    name: str = "api-suite",
    with_ui: bool = False,
    force: bool = False,
    openapi_source: Optional[str] = None,
    suite_ir: Optional[SuiteIR] = None,
) -> WriteResult:
    """Create monorepo skeleton under ``target``.

    Does **not** emit entity CRUD tests (G3/G4). Optionally writes IR dump
    when ``suite_ir`` is provided.
    """
    root = Path(target).resolve()
    root.mkdir(parents=True, exist_ok=True)
    result = WriteResult(root=str(root))
    safe_name = (name or "api-suite").strip() or "api-suite"

    openapi_conf = "docs/openapi.yaml"
    if openapi_source:
        openapi_conf = openapi_source

    files: Dict[str, str] = {}

    # --- root ---
    files["README.md"] = f"""# {safe_name}

API autotest suite scaffolded by **partest-gen** (G1 skeleton).

## Layout

```text
src/api/resources/   # paths, payloads, validations, collections
src/api/tests/       # pytest API (entity suites come in G3+)
src/ui/              # optional UI (only if generated with --with-ui)
requirements/        # split deps: base / api / ui / local
```

## Setup

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
pip install -r requirements/api.txt
cp env.example .env   # fill BASE_URL / tokens
```

## Run

```bash
pytest src/api/tests -q
# coverage report (after suite):
pytest src/api/tests/test_zorro.py -q
```

Generated with partest. Do not commit secrets.
"""

    files["pytest.ini"] = """[pytest]
log_cli = 1
log_cli_level = INFO
log_cli_format = %(message)s
log_file = logs/pytest.log
log_file_level = INFO
log_file_date_format = %Y-%m-%d %H:%M:%S
asyncio_default_fixture_loop_scope = session
asyncio_mode = auto

markers =
    smoke: fast smoke
    api: API suite
    ui: UI suite
    rbac: role checks
    security: security suite
    asyncio: async tests

addopts =
    -ra
"""

    files["requirements.txt"] = "-r requirements/api.txt\n"

    files["requirements/base.txt"] = """httpx>=0.27.2
pydantic>=2.0.0
python-dotenv>=1.0.0
PyYAML>=6.0.2
Faker>=13.12.0
"""

    files["requirements/api.txt"] = """-r base.txt
partest>=1.7.0
pytest>=8.0.0
pytest-asyncio>=0.23.7
allure-pytest>=2.8.18
matplotlib>=3.9.2
requests>=2.31.0
"""

    files["requirements/ui.txt"] = """-r base.txt
partest[ui]>=1.5.0
pytest>=8.0.0
pytest-playwright>=0.5.0
allure-pytest>=2.8.18
"""

    files["requirements/local.txt"] = """-r api.txt
-r ui.txt
"""

    files["env.example"] = """# Copy to .env — never commit real secrets
BASE_URL=http://127.0.0.1:8080
OPENAPI_URL=
TEST_DATA_MARKER=AQA

# Optional OIDC (TokenManager)
KEYCLOAK_URL=
KEYCLOAK_REALM=
KEYCLOAK_CLIENT_ID=
# KEYCLOAK_ADMIN_USER=
# KEYCLOAK_ADMIN_PASSWORD=
"""

    files["confpartest.py"] = f'''"""partest OpenAPI coverage config (project-local)."""

swagger_files = {{
    "{safe_name}": ["local", "{openapi_conf}"],
}}

# Used only when zorro(use_matrix=False)
test_types_coverage = [
    "request_default",
    "request_not_allowed",
]
test_types_exception = [
    "health",
]
'''

    files["conftest.py"] = '''"""Root conftest: env + domain option. API fixtures live under src/api/tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from partest.env import load_project_env, set_project_root


ROOT = Path(__file__).resolve().parent
set_project_root(ROOT)
load_project_env(ROOT)


def pytest_addoption(parser):
    parser.addoption(
        "--domain",
        action="store",
        default=None,
        help="API base URL (overrides BASE_URL from .env)",
    )


@pytest.fixture(scope="session")
def domain(request):
    from partest.env import env, base_url

    cli = request.config.getoption("--domain")
    if cli:
        return cli.rstrip("/")
    try:
        return base_url()
    except RuntimeError:
        return env("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
'''

    files[".gitignore"] = """.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.env
logs/
allure-results/
allure-report/
coverage_report.html
api_call_counts.png
.partest/
dist/
build/
*.egg-info/
"""

    files["docs/README.md"] = f"""# {safe_name} docs

- OpenAPI: place spec at `docs/openapi.yaml` or point `confpartest.py` / `OPENAPI_URL`.
- Coverage methodology is encoded in **partest** (subtypes × test cases).
- Entity tests will be generated in G3+ (`partest-gen from-openapi`).
"""

    # placeholder openapi if none
    files["docs/openapi.yaml"] = """openapi: 3.0.3
info:
  title: Placeholder API
  version: 0.0.0
paths:
  /health:
    get:
      tags: [health]
      summary: Health check
      operationId: getHealth
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
"""

    # --- src/api package tree ---
    for rel in [
        "src/__init__.py",
        "src/api/__init__.py",
        "src/api/resources/__init__.py",
        "src/api/resources/endpoints/__init__.py",
        "src/api/resources/payloads/__init__.py",
        "src/api/resources/validations/__init__.py",
        "src/api/resources/validations/common/__init__.py",
        "src/api/resources/collections/__init__.py",
        "src/api/resources/rbac/__init__.py",
        "src/api/resources/security/__init__.py",
        "src/api/utils/__init__.py",
        "src/api/tests/__init__.py",
    ]:
        files[rel] = _py_init()

    files["src/api/resources/endpoints/paths.py"] = '''"""OpenAPI path constants.

G2+ generator overwrites this file from OpenAPI. Hand-edit carefully.
"""

# Example:
# class PathsHealth:
#     health = "/health"
#
# paths_health = PathsHealth()
'''

    files["src/api/resources/endpoints/configs.py"] = '''"""HTTP headers/params factories — library Config + project extensions."""

from __future__ import annotations

from partest.http import Config as _BaseConfig


class Config(_BaseConfig):
    """Project Config: extend GLOBAL_HEADERS / GLOBAL_PARAMS as needed."""

    pass
'''

    files["src/api/resources/validations/common/problem_detail.py"] = '''"""RFC 7807 error model — re-export library preset."""

from partest.validation import ProblemDetailBody, ProblemDetailValidation

ResponseSuccessBody = ProblemDetailBody
ResponseValidation = ProblemDetailValidation
'''

    files["src/api/resources/validations/common/raw_incorrect_body.py"] = '''"""Transport IncorrectBody cases — re-export library helper (LIB-REC-IB)."""

from partest.validation import RAW_INCORRECT_BODY_CASES, assert_raw_incorrect_body

__all__ = ["RAW_INCORRECT_BODY_CASES", "assert_raw_incorrect_body"]
'''

    files["src/api/resources/payloads/__init__.py"] = '''"""Payloads package. Prefer subclassing partest.payloads.BaseRequestBody."""

from partest.payloads import BaseRequestBody

__all__ = ["BaseRequestBody"]
'''

    files["src/api/resources/collections/collections_manager.py"] = '''"""Register entity collections here (G2+ fills this)."""

from __future__ import annotations

from typing import Optional

from partest.collections import CollectionsManager as _LibManager


class CollectionsManager(_LibManager):
    """G2 ``from-openapi`` overwrites this with named collections."""

    def __init__(self, token: Optional[str] = None):
        super().__init__()
'''

    files["src/api/resources/security/risk_profiles.py"] = '''"""Entity risk profiles — fill from product knowledge.

from partest.security import RiskProfile

# PROFILES = {
#     "health": RiskProfile("health", writes=False, authz=False),
# }
'''

    files["src/api/resources/rbac/roles.py"] = '''"""Role credentials mapping — consumer-only (never commit passwords).

Example::

    import os

    ALL_ROLES = ("admin",)

    def get_role_credentials(role: str):
        if role == "admin":
            return os.environ["KEYCLOAK_ADMIN_USER"], os.environ["KEYCLOAK_ADMIN_PASSWORD"]
        raise ValueError(role)
"""

ALL_ROLES = ()


def get_role_credentials(role: str):
    raise NotImplementedError(
        "Define roles and env-backed credentials for TokenManager.credentials_provider"
    )
'''

    files["src/api/utils/__init__.py"] = '''"""Project utils — prefer partest.* for harness; keep domain helpers here."""
'''

    files["src/api/tests/conftest.py"] = '''"""API session fixtures: client, tracking, collections models."""

from __future__ import annotations

import pytest

from partest import ApiClient, CreatedRegistry, TrackingApiClient, reset_storage


@pytest.fixture(scope="session", autouse=True)
def _clear_coverage():
    reset_storage()
    yield
    reset_storage()


@pytest.fixture(scope="session")
def registry() -> CreatedRegistry:
    return CreatedRegistry()


@pytest.fixture(scope="session")
def api_client(domain, registry):
    """Tracking client (Allure instrumented). Swap to ApiClient if preferred."""
    return TrackingApiClient(domain=domain, registry=registry, instrument=True)


@pytest.fixture(scope="session")
def plain_api_client(domain):
    return ApiClient(domain=domain)


@pytest.fixture(scope="session")
def models():
    """CollectionsManager from G2-generated resources (paths + headers)."""
    from src.api.resources.collections.factory import build_models

    return build_models(token=None)


# Optional: wire TokenManager when roles.py is filled
# @pytest.fixture(scope="session")
# def token_manager(domain):
#     from partest.auth import TokenManager
#     from partest.env import require_env
#     from src.api.resources.rbac.roles import ALL_ROLES, get_role_credentials
#     return TokenManager(
#         keycloak_url=require_env("KEYCLOAK_URL"),
#         realm=require_env("KEYCLOAK_REALM"),
#         client_id=require_env("KEYCLOAK_CLIENT_ID"),
#         credentials_provider=get_role_credentials,
#         known_roles=ALL_ROLES,
#         domain=domain,
#     )
#
# @pytest.fixture(autouse=True)
# async def ensure_fresh_auth(token_manager, models):
#     token = await token_manager.get_token()
#     models.apply_token(token)
'''

    files["src/api/tests/test_zorro.py"] = '''"""Final coverage report (run last in CI after suite)."""

import allure
import pytest

from partest.zorro_report import zorro


@allure.epic("Coverage")
@allure.feature("zorro")
@pytest.mark.asyncio
async def test_coverage_report():
    report = zorro(html_path="coverage_report.html")
    assert report is not None
    assert report.average_pct >= 0
'''

    files["src/api/tests/test_smoke_health.py"] = '''"""Smoke stub against placeholder /health — replace after from-openapi."""

import allure
import pytest

from partest import TypesTestCases
import partest.reporting as ah

types = TypesTestCases


@allure.epic("API")
@allure.feature("health")
@pytest.mark.smoke
@pytest.mark.asyncio
@ah.testcase(title="GET /health smoke", story="Default")
async def test_health_default(api_client):
    """Requires live BASE_URL with /health or will fail — xfail-friendly placeholder."""
    response = await api_client.make_request(
        "GET",
        "/health",
        defining_url="/health",
        expected_status_code=200,
        type=types.request_default,
    )
    # TODO: ah.check_eq(...) on deterministic fields
    assert response is not None or response == ""
'''

    files["logs/.gitkeep"] = ""

    if with_ui:
        # G5 deep UI tree
        files.update(build_ui_files(project_name=safe_name))
        # env UI keys
        files["env.example"] = (
            files.get("env.example", "")
            + "\n# UI (G5)\n"
            "FRONTEND_URL=http://127.0.0.1:3000\n"
            "FRONTEND_UI_USER=\n"
            "FRONTEND_UI_PASSWORD=\n"
            "UI_HEADED=0\n"
        )
        files[".gitignore"] = (
            files.get(".gitignore", "")
            + "\nsrc/ui/baselines/actual/\nsrc/ui/baselines/diff/\n"
        )
        # pytest markers already include ui; extend
        if "ui_smoke" not in files["pytest.ini"]:
            files["pytest.ini"] = files["pytest.ini"].replace(
                "    ui: UI suite\n",
                "    ui: UI suite\n"
                "    ui_smoke: fast UI smoke\n"
                "    ui_auth: UI authentication\n"
                "    ui_rbac: UI role visibility\n"
                "    ui_visual: visual baseline compare\n",
            )

    for rel, content in files.items():
        _write(root, rel, content, force=force, result=result)

    # IR dump for G1 inspectability
    if suite_ir is not None:
        ir_path = root / ".partest" / "suite_ir.json"
        ir_path.parent.mkdir(parents=True, exist_ok=True)
        if force or not ir_path.exists():
            ir_path.write_text(
                json.dumps(suite_ir.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result.created.append(".partest/suite_ir.json")
        else:
            result.skipped.append(".partest/suite_ir.json")

        summary = root / ".partest" / "openapi_summary.md"
        lines = [
            f"# OpenAPI IR summary — {suite_ir.title}",
            "",
            f"- version: `{suite_ir.version}`",
            f"- openapi: `{suite_ir.openapi_version}`",
            f"- source: `{suite_ir.source}`",
            f"- operations: **{len(suite_ir.operations)}**",
            f"- tags: {', '.join(suite_ir.tags()) or '—'}",
            "",
            "| Method | Path | Tag | Subtype | P1 TC |",
            "|--------|------|-----|---------|-------|",
        ]
        for op in suite_ir.operations:
            p1 = ", ".join(op.required_p1) if op.required_p1 else "—"
            lines.append(
                f"| {op.method} | `{op.path}` | {op.tag} | `{op.subtype}` | {p1} |"
            )
        lines.append("")
        lines.append("Entity tests generation: **G3+** (`partest-gen from-openapi --depth p1`).")
        lines.append("")
        text = "\n".join(lines)
        if force or not summary.exists():
            summary.write_text(text, encoding="utf-8")
            result.created.append(".partest/openapi_summary.md")
        else:
            result.skipped.append(".partest/openapi_summary.md")

    return result
