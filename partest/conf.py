"""confpartest load / validate helpers (project-agnostic)."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class ConfpartestError(RuntimeError):
    """Invalid or missing confpartest module."""


def load_confpartest(
    module_name: str = "confpartest",
    *,
    project_root: Optional[Union[str, Path]] = None,
) -> Any:
    """Import consumer ``confpartest`` (must be on ``sys.path`` or under project_root)."""
    if project_root is not None:
        root = str(Path(project_root).resolve())
        if root not in sys.path:
            sys.path.insert(0, root)
    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        raise ConfpartestError(
            f"Cannot import {module_name!r}. Place confpartest.py at the project root "
            f"(next to pytest.ini) or pass project_root=. Original: {e}"
        ) from e


def conf_attr(
    name: str,
    default: Any = None,
    *,
    module_name: str = "confpartest",
) -> Any:
    """Read one attribute from the consumer ``confpartest``, if there is one.

    The single reader for every library switch that can be written in the project file.
    Two cases are told apart deliberately:

    * **no ``confpartest`` at all** — legitimate (a suite that only uses ``ApiClient``,
      our own tests) and silent: *default* is returned;
    * **a ``confpartest`` that exists but cannot be imported** — loud. That is a file the
      consumer wrote and meant. Swallowing the failure is how ``tls_verify = False`` ends
      up quietly unread while the run warns that verification is *on*.

    The modules that read switches used to do a bare ``import confpartest`` and swallow
    ``ImportError``, which conflates the two: a project with a non-standard layout got the
    library's defaults back and no hint why.
    """
    module = sys.modules.get(module_name)
    if module is None:
        try:
            spec = importlib.util.find_spec(module_name)
        except Exception:  # a broken parent package, a ValueError from a stub entry
            spec = None
        if spec is None:
            return default
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            raise ConfpartestError(
                f"{module_name} is importable but failed while reading {name!r}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
    return getattr(module, name, default)


def validate_confpartest(conf: Any) -> List[str]:
    """Return a list of validation problems (empty if OK)."""
    errors: List[str] = []
    if conf is None:
        return ["confpartest module is None"]

    swagger = getattr(conf, "swagger_files", None)
    if swagger is None:
        errors.append("missing swagger_files (dict: name -> [source_type, path_or_url])")
    elif not isinstance(swagger, dict):
        errors.append(f"swagger_files must be a dict, got {type(swagger).__name__}")
    else:
        for name, spec in swagger.items():
            if not isinstance(spec, (list, tuple)) or len(spec) < 2:
                errors.append(
                    f"swagger_files[{name!r}] must be [source_type, path_or_url], got {spec!r}"
                )
            else:
                kind = str(spec[0]).lower()
                if kind not in {"local", "url", "file", "path"}:
                    errors.append(
                        f"swagger_files[{name!r}] source_type must be local|url, got {spec[0]!r}"
                    )

    for attr in ("test_types_coverage", "test_types_exception"):
        val = getattr(conf, attr, None)
        if val is not None and not isinstance(val, (list, tuple)):
            errors.append(f"{attr} must be a list/tuple when set")

    return errors


def require_confpartest(
    module_name: str = "confpartest",
    *,
    project_root: Optional[Union[str, Path]] = None,
) -> Any:
    """Load and validate; raise ``ConfpartestError`` with all problems joined."""
    conf = load_confpartest(module_name, project_root=project_root)
    problems = validate_confpartest(conf)
    if problems:
        raise ConfpartestError(
            "Invalid confpartest:\n- " + "\n- ".join(problems)
        )
    return conf


def confpartest_snapshot(conf: Any) -> Dict[str, Any]:
    """Small debug dict for docs/logging (no secrets)."""
    swagger = getattr(conf, "swagger_files", {}) or {}
    return {
        "swagger_services": list(swagger.keys()) if isinstance(swagger, dict) else [],
        "has_matrix_types": hasattr(conf, "test_types_coverage"),
        "pytest_plugin": getattr(conf, "pytest_plugin", None),
        "exceptions": list(getattr(conf, "test_types_exception", []) or []),
    }
