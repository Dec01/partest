"""Optional pytest plugin: Allure title/description enrichment.

**Auto-loaded** via setuptools ``pytest11`` entry point ``partest``.

Disable when the consumer already has Allure hooks (avoids double attach)::

    # env
    PARTEST_PYTEST_PLUGIN=0

    # or confpartest.py
    pytest_plugin = False

    # or CLI
    pytest -p no:partest

Enable explicitly after disable::

    PARTEST_PYTEST_PLUGIN=1
    # or confpartest: pytest_plugin = True
    # or pytest_plugins = ["partest.pytest_plugin"]

``PARTEST_PYTEST_PLUGIN`` governs the **Allure** side only. Recording what the run
selected (``-m``/``-k``, deselected count) is a separate switch, on by default, because
it writes nothing to Allure and cannot collide with anybody's hooks::

    PARTEST_RUN_METADATA=0        # or confpartest: run_metadata = False

Turning that one off costs the report its only exact signal that the run covered a
subset of the suite — see :func:`_record_selection`.

A third, independent piece: opt-in marker sets (``partest_optin_markers`` in the ini file,
:mod:`partest.optin`). Inert unless that option names something.

A fourth: the ``known_defect`` marker (:mod:`partest.known_defect`) — a strict xfail that
only an ``AssertionError`` from the test body satisfies. Registered in every session.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any, Iterable, List, Optional

import pytest

from partest.flags import coerce_bool, env_bool


def _env_flag(name: str) -> Optional[bool]:
    return env_bool(name)


def _conf_flag(name: str) -> Optional[bool]:
    """Read a boolean-ish attribute from the consumer ``confpartest``.

    One reading for both halves of the switch, and the same one the TLS switch uses
    (:mod:`partest.flags`). The two used to differ: ``PARTEST_PYTEST_PLUGIN=disabled``
    turned the plugin off while ``pytest_plugin = "disabled"`` was not recognised and read
    as *on*. ``confpartest`` is reached through :func:`partest.conf.conf_attr`, so a
    project whose file is there but broken hears about it instead of quietly getting the
    library's defaults.
    """
    from partest.conf import conf_attr

    # No root lookup: these switches are read in every session, a UI-only one included,
    # and must not execute a confpartest nothing else in the run asked for.
    return coerce_bool(conf_attr(name, fallback=False))


def _switch(env_name: str, conf_name: str, *, default: bool) -> bool:
    """Env wins over confpartest; neither set means *default*."""
    env = _env_flag(env_name)
    if env is not None:
        return env
    conf = _conf_flag(conf_name)
    if conf is not None:
        return conf
    return default


def plugin_enabled() -> bool:
    """Whether the Allure-side hooks run (env wins over confpartest).

    This is the switch for what the plugin *adds to Allure*: display names and the
    failure summary. It is off in projects that own their own Allure hooks. Run
    metadata is deliberately not behind it — see :func:`run_metadata_enabled`.
    """
    # Default ON so greenfield gets titles; consumers with dual hooks opt out.
    return _switch("PARTEST_PYTEST_PLUGIN", "pytest_plugin", default=True)


def run_metadata_enabled() -> bool:
    """Whether the run records how it was selected (env wins over confpartest).

    Separate from :func:`plugin_enabled` because the two answer different questions.
    The Allure hooks are turned off to avoid double attachments; recording the
    selection attaches nothing, writes no file and prints nothing — it only fills
    ``partest.call_storage.run_info``, so there is nothing for it to collide with.
    Sharing one flag meant that every project which followed the advice to disable the
    plugin also lost the one signal that its run was partial, and only found out when a
    filtered run was later compared against a full one.
    """
    return _switch("PARTEST_RUN_METADATA", "run_metadata", default=True)


def _humanize_test_name(name: str) -> str:
    if name.startswith("test_"):
        name = name[5:]
    return name.replace("_", " ").strip().capitalize()


def _format_param_value(value: Any) -> str:
    if callable(value):
        return "<callable>"
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = str(value)
    else:
        text = repr(value)
    if len(text) > 48:
        return text[:45] + "..."
    return text


def _base_title_from_item(item) -> str:
    func = getattr(item, "function", None)
    if func and func.__doc__:
        first = func.__doc__.strip().splitlines()[0].strip()
        if first:
            return first
    raw = getattr(item, "originalname", None) or item.name.split("[")[0]
    return _humanize_test_name(raw)


def _title_with_params(item) -> str:
    base = _base_title_from_item(item)
    callspec = getattr(item, "callspec", None)
    if not callspec or not callspec.params:
        return base
    priority = (
        "role",
        "code",
        "name",
        "kind",
        "field",
        "resource",
        "method",
        "matrix",
        "collection",
    )
    keys: List[str] = [
        k for k in priority if k in callspec.params and not callable(callspec.params[k])
    ]
    keys += [
        k for k, v in callspec.params.items() if k not in keys and not callable(v)
    ]
    if not keys:
        return base
    extras = ", ".join(
        f"{k}={_format_param_value(callspec.params[k])}" for k in keys[:4]
    )
    return f"{base} · {extras}"


def pytest_itemcollected(item) -> None:
    """Set Allure display name from docstring + key params."""
    if not plugin_enabled():
        return
    try:
        import allure  # noqa: F401
    except ImportError:
        return
    title = _title_with_params(item)
    for obj in (getattr(item, "obj", None), getattr(item, "function", None)):
        if obj is None:
            continue
        try:
            setattr(obj, "__allure_display_name__", title)
        except Exception:
            pass


def pytest_runtest_makereport(item, call):
    """Attach short failure summary on test call failure."""
    if not plugin_enabled():
        return
    if call.when != "call" or call.excinfo is None:
        return
    # Optional: skip failure_summary when consumer attaches its own
    fail_env = _env_flag("PARTEST_ALLURE_FAILURE_SUMMARY")
    if fail_env is False:
        return
    try:
        import allure
        from allure_commons.types import AttachmentType
    except ImportError:
        return
    try:
        exc = call.excinfo.value
        from partest.redact import _already_masked, _scrub_text

        shown = str(exc) if _already_masked(exc) else _scrub_text(exc)
        text = f"{type(exc).__name__}: {shown}"
        allure.attach(
            text[:8000],
            name="failure_summary",
            attachment_type=AttachmentType.TEXT,
        )
    except Exception:
        pass


# --- Opt-in marker sets -----------------------------------------------------


def pytest_addoption(parser) -> None:
    """``partest_optin_markers`` in the ini file; see :mod:`partest.optin`."""
    from partest.optin import add_ini

    add_ini(parser)


def pytest_configure(config) -> None:
    """Register the opt-in deselection — only when ``partest_optin_markers`` names something.

    Not behind either switch above: it decides what runs, it does not decorate a report,
    and a project that turned the Allure half off still wants its long tests kept out.
    """
    from partest import known_defect
    from partest.optin import configure

    configure(config)
    # Not behind a switch either: it decides an outcome, and an unregistered marker would
    # fail every project running with --strict-markers.
    known_defect.configure(config)
    _begin_session_state(config)
    _push_project_root(config)


def _rootpath(config) -> Optional[str]:
    """The directory searched for ``confpartest.py``: the ini file's, else pytest's rootdir.

    The ini file's directory, because that is where the documentation puts the project file
    and where ``pythonpath = .`` points; ``--rootdir`` (IDEs set it) can name another one.
    """
    inipath = getattr(config, "inipath", None)
    if inipath is not None:
        return str(Path(inipath).parent)
    root = getattr(config, "rootpath", None) or getattr(config, "rootdir", None)
    return str(root) if root is not None else None


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _root_usable(config, root: Path) -> "tuple[bool, str]":
    """Whether ``<root>/confpartest.py`` may be loaded by location in this session.

    The root lookup exists for one layout — a suite run from inside its own root without
    ``pythonpath`` — and is kept to it. Not when the run asked for no project code
    (``--noconftest``), and not when the root pytest chose contains neither the current
    directory nor the test paths (``--rootdir``, ``-c`` pointing elsewhere): a file there
    belongs to some other project.
    """
    option = getattr(config, "option", None)
    if getattr(option, "noconftest", False):
        return False, "--noconftest is set"
    try:
        if config.pluginmanager.is_blocked("conftest"):
            return False, "-p no:conftest is set"
    except Exception:
        pass
    params = getattr(config, "invocation_params", None)
    cwd = Path(getattr(params, "dir", None) or Path.cwd())
    if _inside(cwd, root):
        return True, ""
    args = [str(a).split("::", 1)[0] for a in (getattr(config, "args", None) or [])]
    paths = [Path(a) if Path(a).is_absolute() else cwd / a for a in args if a]
    if paths and all(_inside(path, root) for path in paths):
        return True, ""
    return False, (
        f"{root} contains neither the current directory ({cwd}) nor the test paths"
    )


def _push_project_root(config) -> None:
    """Tell :mod:`partest.conf` the pytest root (see :func:`partest.conf._find_confpartest`).

    A console ``pytest`` puts neither the current directory nor the root on ``sys.path``;
    ``pythonpath = .`` or a ``conftest.py`` in the root does. Without either, a
    ``confpartest.py`` next to the ini file is invisible to a plain import.
    """
    root = _rootpath(config)
    if root is None:
        return
    from partest.conf import _push_project_root as push

    usable, why = _root_usable(config, Path(root))
    push(root, usable=usable, why=why)


_STATE_KEY = pytest.StashKey[tuple]()


def _begin_session_state(config) -> None:
    """Keep what was decided before this session, and start it from a clean slate.

    Paired with :func:`pytest_unconfigure`, which puts it back: sequential sessions in one
    process each read their own project, and an in-process session nested in another
    (``pytester``) hands the outer one its state back. A ``confpartest`` imported from
    ``sys.path`` is not part of that state — it stays in ``sys.modules`` and the nested
    session sees it.
    """
    try:
        from partest import conf, coverage
        from partest.methodology.api import overrides

        config.stash[_STATE_KEY] = (conf._snapshot(), coverage._snapshot(), overrides._snapshot())
        coverage._reset_session_state()
        overrides._reset_session_state()
        conf._notes.clear()
    except Exception:
        pass


def pytest_unconfigure(config) -> None:
    """End of session: the root goes, what was loaded from it is unloaded, state is restored."""
    try:
        from partest import conf, coverage
        from partest.methodology.api import overrides

        root = _rootpath(config)
        if root is not None:
            conf._pop_project_root(root)
        saved = config.stash.get(_STATE_KEY, None)
        if saved is not None:
            conf._restore(saved[0])
            coverage._restore(saved[1])
            overrides._restore(saved[2])
    except Exception:
        pass


# --- What this run actually selected --------------------------------------


def _reset_selection_state() -> None:
    """Forget how this process was selected (see :func:`pytest_sessionstart`)."""
    try:
        from partest.call_storage import reset_selection

        reset_selection()
    except Exception:
        pass


def _reset_not_measured_state() -> None:
    """Forget what the previous session could not measure (see :mod:`partest.reporting`)."""
    try:
        from partest.reporting.measured import reset_not_measured

        reset_not_measured()
    except Exception:
        pass


def _write_partest_notes(terminalreporter) -> None:
    """What the run could not count, and which project file it read from where.

    Said here rather than as warnings: these come from pytest hooks and from
    ``pytest_sessionfinish``, where ``filterwarnings = error`` turns a warning into an
    internal error or a lost report. And a report alone only shows zeros, which read like a
    suite that tested nothing rather than one that measured nothing.
    """
    try:
        from partest import conf

        sections = [(title, list(lines)) for title, lines in conf._notes.items() if lines]
    except Exception:
        return
    try:
        for title, lines in sections:
            terminalreporter.write_sep("-", title)
            for line in lines:
                terminalreporter.write_line(f"  {line}")
    except Exception:
        pass


def pytest_terminal_summary(terminalreporter, exitstatus=0, config=None) -> None:
    """Say out loud which assertions were never made, and which reports measured nothing.

    A run where half the checks had no data to read still ends with ``passed``, and the
    Allure evidence is one click away from a reader who has no reason to look. This
    section is the cheap part of the same signal: it costs nothing when the ledger is
    empty, which is every run that never used :func:`~partest.reporting.check_measured`.
    """
    _write_partest_notes(terminalreporter)
    try:
        from partest.reporting.measured import not_measured_records

        records = not_measured_records()
    except Exception:
        return
    if not records:
        return
    counted: "dict[tuple, int]" = {}
    for rec in records:
        key = (rec.what, rec.reason)
        counted[key] = counted.get(key, 0) + 1
    try:
        terminalreporter.write_sep("-", "partest: NOT MEASURED assertions")
        for (what, reason), times in list(counted.items())[:20]:
            suffix = f" (x{times})" if times > 1 else ""
            terminalreporter.write_line(f"  {what}{suffix}: {reason}")
        if len(counted) > 20:
            terminalreporter.write_line(f"  ... and {len(counted) - 20} more")
        terminalreporter.write_line(
            "  these assertions never ran: green here means unknown, not verified"
        )
    except Exception:
        pass


def _node_ids(items: Iterable[Any]) -> List[str]:
    return [str(getattr(item, "nodeid", None) or item) for item in items]


def _record_selection(config, deselected: Optional[Iterable[str]] = None) -> None:
    """Note that the run covered a subset, so the report can say so.

    Coverage is scored per test case, but "never called" is a property of an endpoint.
    A marker filter removes cases: the endpoint is still hit, it just loses one cell —
    so the unseen ratio stays near zero and nothing in the numbers reveals that half the
    suite did not run. Comparing such a run against a full one then presents every
    dropped cell as a regression. The selection expression is the one exact signal, and
    it is only available here.

    *deselected* is the node ids removed, not their number: they are kept as a set in
    :data:`partest.call_storage.deselected_nodes` so that a parallel run, where every
    worker deselects the same tests, reports the filter once instead of once per worker.
    """
    try:
        from partest.call_storage import record_deselected, run_info
    except Exception:
        return
    option = getattr(config, "option", None)
    if option is None:
        return
    selection = run_info.setdefault("selection", {})
    for name, key in (("markexpr", "markexpr"), ("keyword", "keyword")):
        value = (getattr(option, name, None) or "").strip()
        if value:
            selection[key] = value
    if deselected:
        record_deselected(deselected)


def pytest_collection_modifyitems(config, items) -> None:
    if not run_metadata_enabled():
        return
    _record_selection(config)


def pytest_deselected(items) -> None:
    """``-m`` and ``-k`` come through here; ``--deselect`` and plugins do too."""
    if not run_metadata_enabled() or not items:
        return
    config = getattr(items[0], "config", None)
    if config is not None:
        _record_selection(config, deselected=_node_ids(items))


# --- Coverage under pytest-xdist ------------------------------------------


def _xdist_merge_enabled() -> bool:
    """Merging is on by default; opt out with ``PARTEST_XDIST_MERGE=0``."""
    env = _env_flag("PARTEST_XDIST_MERGE")
    return True if env is None else env


def _is_xdist_worker(config) -> bool:
    return hasattr(config, "workerinput")


def pytest_sessionstart(session) -> None:
    """Start from a clean slate: this run's selection, then last run's shards.

    Both halves are about a second run inheriting the first one's facts. The selection is
    per process, so it matters to anyone calling ``pytest.main()`` twice in one
    interpreter — the second, unfiltered run would otherwise report the first run's
    deselected tests and a marker expression it never got.
    """
    _reset_selection_state()
    _reset_not_measured_state()
    if not _xdist_merge_enabled() or _is_xdist_worker(session.config):
        return
    try:
        from partest.call_storage import clear_shards

        clear_shards()
    except Exception:
        pass


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error) -> None:
    """pytest-xdist: a worker's terminal-summary notes reach the controller's summary."""
    notes = (getattr(node, "workeroutput", None) or {}).get("partest_notes") or {}
    try:
        from partest import conf

        for title, lines in notes.items():
            for line in lines:
                conf._note(title, line)
    except Exception:
        pass


def _hand_notes_to_controller(session) -> None:
    workeroutput = getattr(session.config, "workeroutput", None)
    if workeroutput is None:
        return
    try:
        from partest import conf

        workeroutput["partest_notes"] = {t: list(lines) for t, lines in conf._notes.items()}
    except Exception:
        pass


def pytest_sessionfinish(session, exitstatus) -> None:
    """Workers write their counters; the controller merges them.

    Without this, ``pytest -n`` reports whichever worker happened to run the report
    test, and every endpoint exercised elsewhere reads as never called.
    """
    _hand_notes_to_controller(session)
    if not _xdist_merge_enabled():
        return
    try:
        from partest.call_storage import merge_shards, run_info, write_shard
    except Exception:
        return

    if _is_xdist_worker(session.config):
        try:
            write_shard()
        except OSError:
            pass
        return

    # Controller (or a plain serial run: then there are no shards and nothing changes).
    try:
        merge_shards()
    except Exception:
        return

    if run_metadata_enabled():
        # The controller never collects under xdist, so its `-m` / `-k` reached no hook.
        # `config.option` still has them, and this is the last chance to read it. The
        # deselected ids came in with the shards above.
        _record_selection(session.config)

    if run_info.get("workers", 1) > 1 and not run_info.get("merged"):
        if _env_flag("PARTEST_COVERAGE_REQUIRE_MERGE"):
            raise session.Failed(
                "partest: coverage was collected under xdist without a merge; "
                "the numbers are one worker's slice, not the suite"
            )

    _write_controller_report()


def _write_controller_report() -> None:
    """Optionally render the coverage report here, where the merged data lives.

    A report produced by a test cannot see the merge: that test runs on one worker,
    and merging happens on the controller after every worker has finished. Set
    ``PARTEST_COVERAGE_JSON`` (and optionally ``PARTEST_COVERAGE_HTML``) to have the
    artifact written from the controller instead.
    """
    json_path = (os.getenv("PARTEST_COVERAGE_JSON") or "").strip()
    html_path = (os.getenv("PARTEST_COVERAGE_HTML") or "").strip()
    if not json_path and not html_path:
        return
    try:
        from partest.reports import zorro_enhanced

        # Warnings are shown, not raised: under `filterwarnings = error` a warning raised
        # here would cost the run its coverage.json.
        with warnings.catch_warnings():
            warnings.simplefilter("default")
            zorro_enhanced(
                html_path=html_path or "coverage_report.html",
                json_path=json_path or "coverage.json",
                attach_allure=False,
            )
    except Exception as exc:  # a broken report must not fail a green suite
        print(f"partest: could not write the coverage report: {exc}")
