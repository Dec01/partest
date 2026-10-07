"""Generic .env loader helpers (project-root injectable)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

_ENV_LOADED = False
_PROJECT_ROOT: Optional[Path] = None


def set_project_root(root: Union[str, Path]) -> Path:
    """Set project root used by :func:`load_project_env`."""
    global _PROJECT_ROOT, _ENV_LOADED
    _PROJECT_ROOT = Path(root).resolve()
    _ENV_LOADED = False
    return _PROJECT_ROOT


def project_root() -> Path:
    if _PROJECT_ROOT is not None:
        return _PROJECT_ROOT
    # Fallback: env or cwd
    env_root = os.getenv("PARTEST_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path.cwd()


def load_project_env(root: Optional[Union[str, Path]] = None) -> Path:
    """Load ``.env`` from project root (idempotent). Requires python-dotenv."""
    global _ENV_LOADED, _PROJECT_ROOT
    if root is not None:
        _PROJECT_ROOT = Path(root).resolve()
    base = project_root()
    env_path = base / ".env"
    if not _ENV_LOADED:
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path)
            load_dotenv()
        except ImportError:
            pass
        _ENV_LOADED = True
    return env_path


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    load_project_env()
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value


def require_env(name: str) -> str:
    value = env(name)
    if not value:
        raise RuntimeError(
            f"Environment variable `{name}` is not set. "
            f"Copy env.example → .env and fill values (root: {project_root()})."
        )
    return value


def base_url(env_name: str = "BASE_URL") -> str:
    return require_env(env_name).rstrip("/")


def openapi_url(
    *,
    openapi_env: str = "OPENAPI_URL",
    base_env: str = "BASE_URL",
    default_path: str = "/v3/api-docs",
) -> str:
    explicit = env(openapi_env)
    if explicit:
        return explicit.rstrip("/")
    return f"{base_url(base_env)}{default_path}"
