"""confpartest load / validate helpers (project-agnostic)."""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import unquote, urlsplit


class ConfpartestError(RuntimeError):
    """Invalid or missing confpartest module."""


def load_confpartest(
    module_name: str = "confpartest",
    *,
    project_root: Optional[Union[str, Path]] = None,
) -> Any:
    """Import consumer ``confpartest`` (on ``sys.path``, under *project_root*, or in the pytest root).

    Raises :class:`ConfpartestError` when there is no such module, and when there is one
    that fails while importing, whatever it raised.
    """
    if project_root is not None:
        root = str(Path(project_root).resolve())
        if root not in sys.path:
            sys.path.insert(0, root)
    module = _find_confpartest(module_name)
    if module is None:
        raise ConfpartestError(
            f"Cannot import {module_name!r}. Place confpartest.py at the project root "
            f"(next to pytest.ini) or pass project_root=. Searched: "
            f"{_absence_reason(module_name)}"
        )
    return module


# --- one lookup for every reader of confpartest ------------------------------------------
#
# Coverage, subtype overrides, report settings, ``conf_attr`` and ``load_confpartest`` all
# find the project file through :func:`_find_confpartest`, in this order: a module already in
# ``sys.modules``; one importable from ``sys.path``; ``<pytest root>/confpartest.py``, loaded
# by location — only for callers that allow it, and only when the pytest plugin reported a
# root it considers safe to read from (see ``partest.pytest_plugin._root_usable``).

# Serialises loading the project file by location and reading the overrides between threads.
# The fast path — a module already in ``sys.modules`` — does not take it; loading the
# specification has its own lock (``partest.coverage``), so a slow fetch does not hold up a
# thread that only reads a switch.
_lock = threading.RLock()


@dataclass
class _Root:
    path: Path  # the directory searched: the ini file's, else pytest's rootdir
    usable: bool
    why: str = ""  # when not usable: why the root is not searched


# Roots reported by the pytest plugin (``pytest_configure``), most recent last; taken back in
# ``pytest_unconfigure``. Empty outside pytest and with ``-p no:partest``.
_project_roots: List[_Root] = []
# module name -> (file, module) for modules this package loaded from a root by location.
_loaded_from_root: Dict[str, Tuple[Path, Any]] = {}
# candidate file -> why loading it failed; it is not tried again in the same session.
_root_failures: Dict[str, str] = {}
# Terminal summary sections of the current session: title -> lines.
_notes: Dict[str, List[str]] = {}

NOTES_CONFIG = "partest: confpartest"
NOTES_COVERAGE = "partest: coverage NOT COUNTED"


def _note(section: str, message: str) -> None:
    """A line for the pytest terminal summary; the plugin prints and clears them per session."""
    message = _ADDRESS_RE.sub("", message)
    lines = _notes.setdefault(section, [])
    if message not in lines:
        lines.append(message)


def _snapshot() -> tuple:
    return ({k: list(v) for k, v in _notes.items()}, dict(_root_failures))


def _restore(snapshot: tuple) -> None:
    notes, failures = snapshot
    _notes.clear()
    _notes.update(notes)
    _root_failures.clear()
    _root_failures.update(failures)


def _push_project_root(root: Union[str, Path], *, usable: bool = True, why: str = "") -> None:
    _project_roots.append(_Root(Path(root), usable, why))


def _pop_project_root(root: Union[str, Path]) -> None:
    """Forget *root* and unload what was loaded from it — and only that.

    A ``confpartest`` imported from ``sys.path`` belongs to whoever put it there and stays.
    """
    path = Path(root)
    for i in range(len(_project_roots) - 1, -1, -1):
        if _project_roots[i].path == path:
            del _project_roots[i]
            break
    for name, (file, module) in list(_loaded_from_root.items()):
        if file.parent == path:
            if sys.modules.get(name) is module:
                del sys.modules[name]
            del _loaded_from_root[name]
    for candidate in list(_root_failures):
        if Path(candidate).parent == path:
            del _root_failures[candidate]


def _loaded_by_location(module: Any) -> Optional[Path]:
    """The file *module* was loaded from by the root lookup, or ``None``."""
    for file, loaded in _loaded_from_root.values():
        if loaded is module:
            return file
    return None


def _module_dir(module: Any) -> Optional[Path]:
    file = getattr(module, "__file__", None)
    return Path(file).resolve().parent if file else None


# --- error text that can be shown -----------------------------------------------------

# ``<object at 0x...>`` in an exception text: the same failure from two processes would read
# as two different lines.
_ADDRESS_RE = re.compile(r" at 0x[0-9a-fA-F]+")


def _strip_url_secrets(text: str) -> str:
    """URL credentials removed and every query string replaced by ``?…``.

    The same URL scanner the package's output channels use (:func:`partest.redact._scrub_urls`);
    errors about the project's configuration drop the whole query, the channels only the
    values of secret keys.
    """
    from partest.redact import _scrub_urls

    return _scrub_urls(text, drop_query=True)


def _safe_text(text: Any, *, secrets_of: Optional[str] = None) -> str:
    """*text* without URL credentials, query strings and secret-looking values.

    *secrets_of* is a URL whose password and query values (four characters and longer —
    shorter ones would blank out ordinary words) are removed wherever they appear, for
    messages that quote them out of the URL.

    Not covered: a token in the path, ``;jsessionid=``, a fragment, and a snippet of a spec
    quoted by a YAML parse error.
    """
    from partest.redact import redact_text

    out = str(text)
    if secrets_of:
        try:
            parts = urlsplit(str(secrets_of))
            password = parts.password
        except ValueError:
            parts, password = None, None
        if parts is not None:
            hidden = [password]
            hidden += [v for _, _, v in (q.partition("=") for q in parts.query.split("&"))]
            for value in sorted({h for h in hidden if h and len(h) >= 4}, key=len, reverse=True):
                out = out.replace(value, "…").replace(unquote(value), "…")
    return redact_text(_strip_url_secrets(_ADDRESS_RE.sub("", out)))


def _failure_text(exc: BaseException, *, secrets_of: Optional[str] = None) -> str:
    return f"{type(exc).__name__}: {_safe_text(exc, secrets_of=secrets_of)}"


# --- the lookup -----------------------------------------------------------------------


def _load_from_project_root(module_name: str) -> Any:
    """``<pytest root>/confpartest.py`` when it is there but not on ``sys.path``.

    That is the layout a console ``pytest`` without ``pythonpath = .`` and without a
    ``conftest.py`` beside the ini file produces: nothing puts the root on ``sys.path``, so a
    plain import does not see the file. Loaded by location and registered in
    ``sys.modules``, so a later ``import confpartest`` in the same session gets this module;
    the plugin unloads it when the session ends.

    A file that fails to *load* answers "no confpartest" and the reason goes to the terminal
    summary instead of an exception or a warning: the file was found by a guess about the
    layout, and this code runs from pytest hooks, where a warning under
    ``filterwarnings = error`` is an internal error. What the loaded file *says* is another
    matter: a broken ``subtype_overrides`` in it is as loud as anywhere else; only a spec that
    cannot be fetched is downgraded (see :func:`partest.coverage._ensure_spec`).
    """
    if not _project_roots:
        return None
    root = _project_roots[-1]
    if not root.usable:
        return None
    candidate = root.path / f"{module_name}.py"
    if not candidate.is_file() or str(candidate) in _root_failures:
        return None
    spec = importlib.util.spec_from_file_location(module_name, str(candidate))
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        if isinstance(exc, ImportError):
            reason = (
                f"{candidate} is not on sys.path, and loading it directly failed "
                f"({_failure_text(exc)}). Add `pythonpath = .` to the [pytest] section of the "
                "ini file"
            )
        else:
            reason = f"{candidate} failed while executing: {_failure_text(exc)}"
        _root_failures[str(candidate)] = reason
        _note(NOTES_CONFIG, f"{reason}; its settings are not read")
        return None
    _loaded_from_root[module_name] = (candidate, module)
    _note(
        NOTES_CONFIG,
        f"{candidate} was loaded from the pytest root directory: it is not on sys.path "
        "(`pythonpath = .` would put it there). `pytest_plugin` and `run_metadata` in it are "
        "not read: the plugin reads its own switches only from sys.path",
    )
    return module


def _absence_reason(module_name: str = "confpartest") -> str:
    """Where the lookup looked, when it found nothing — for messages, not for logic."""
    if module_name in sys.modules and sys.modules[module_name] is None:
        return f"import of {module_name} is blocked (sys.modules[{module_name!r}] is None)"
    if not _project_roots:
        return (
            f"no {module_name} module on sys.path; the pytest root directory was not searched "
            "because it was not reported (the partest plugin is disabled, `-p no:partest`, or "
            "this is not a pytest run). Put the directory with confpartest.py on sys.path, e.g. "
            "`pythonpath = .` in pytest.ini"
        )
    root = _project_roots[-1]
    candidate = root.path / f"{module_name}.py"
    if str(candidate) in _root_failures:
        return _root_failures[str(candidate)]
    if not root.usable:
        return (
            f"no {module_name} module on sys.path; {candidate} was not tried: {root.why}. "
            "Put its directory on sys.path, e.g. `pythonpath = .` in pytest.ini"
        )
    return (
        f"no {module_name} module on sys.path and no {candidate}. Put confpartest.py in "
        f"{root.path}"
    )


def _find_confpartest(
    module_name: str = "confpartest", *, reading: str = "", fallback: bool = True
) -> Any:
    """The consumer ``confpartest`` module, or ``None`` when the project has none.

    * already imported, or importable from ``sys.path`` — that module;
    * not importable, *fallback* allowed, and ``confpartest.py`` in a usable pytest root —
      loaded from there (:func:`_load_from_project_root`);
    * neither — ``None``, silently: a suite that only uses ``ApiClient`` has no file;
    * found, but raises while importing — :class:`ConfpartestError`, whatever it raised.

    The pytest plugin's own switches pass ``fallback=False``: they are read in every
    session, a UI-only one included, and must not execute a file nothing else asked for —
    nor read one that something else loaded by location, or they would change in the
    middle of a session.

    The error message is sanitised (:func:`_safe_text`) and carries no exception chain: a
    traceback would print the original text, credentials included.
    """

    def known() -> Any:
        module = sys.modules[module_name]
        # ``None`` there means "this import is blocked" (Python's convention).
        if module is not None and not fallback and _loaded_by_location(module) is not None:
            return None
        return module

    if module_name in sys.modules:
        return known()
    failure = None
    with _lock:
        if module_name in sys.modules:
            return known()
        try:
            spec = importlib.util.find_spec(module_name)
        except Exception:  # a broken parent package, a ValueError from a stub entry
            spec = None
        if spec is None:
            return _load_from_project_root(module_name) if fallback else None
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            failure = _failure_text(exc)
    what = f"while reading {reading!r}" if reading else "while importing"
    raise ConfpartestError(f"{module_name} is importable but failed {what}: {failure}") from None


def conf_attr(
    name: str,
    default: Any = None,
    *,
    module_name: str = "confpartest",
    fallback: bool = True,
) -> Any:
    """Read one attribute from the consumer ``confpartest``, if there is one.

    The reader for every library switch that can be written in the project file. Two cases
    are told apart:

    * **no ``confpartest`` at all** — legitimate (a suite that only uses ``ApiClient``,
      our own tests) and silent: *default* is returned;
    * **a ``confpartest`` that exists but cannot be imported** — :class:`ConfpartestError`.
      That is a file the consumer wrote and meant; swallowing the failure would leave, say,
      ``tls_verify = False`` unread while the run warns that verification is *on*.

    *fallback* is passed on to :func:`_find_confpartest`.
    """
    module = _find_confpartest(module_name, reading=name, fallback=fallback)
    if module is None:
        return default
    return getattr(module, name, default)


def _resolve_relative(value: Any, module: Any) -> Any:
    """A relative path that does not exist from the cwd, taken from *module*'s directory.

    ``swagger_files`` ``local`` entries and ``subtype_overrides`` paths are written relative
    to the project root, and a run started from a subdirectory (``cd tests && pytest``, an
    IDE) would otherwise not find them. A path that exists from the cwd keeps its meaning.
    """
    if not isinstance(value, (str, Path)):
        return value
    path = Path(value)
    if path.is_absolute() or path.exists():
        return value
    base = _module_dir(module)
    if base is not None and (base / path).exists():
        return str(base / path)
    return value


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
