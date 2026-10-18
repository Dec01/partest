"""Coverage reads ``confpartest`` when it is used, not when partest is imported.

The pytest plugin is an entry point, so ``partest`` is imported before pytest puts the suite
root on ``sys.path``; reading ``confpartest`` at that moment found nothing under a console
``pytest`` and left coverage off for the whole run without a word. The same import fetched
the specification, so an unreachable URL broke every import of the package (see
``test_ui_isolation.py``).

The sessions here run in a subprocess started by a small runner that imports partest
*before* pytest starts and then takes the repository off ``sys.path`` — no later than the
entry point imports it, and without depending on partest being installed.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import textwrap
import threading
import time
import types

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

RUNNER = """\
import json, os, sys
repo = sys.argv[1]
sys.path.insert(0, repo)
import partest  # what the entry point does, before the suite root is on sys.path
sys.path.remove(repo)
import pytest
codes = []
# Several sessions in one process: [[cwd, [args...]], ...].
for cwd, args in json.loads(sys.argv[2]):
    os.chdir(cwd)
    codes.append(int(pytest.main(args)))
print("CODES", codes)
sys.exit(max(codes))
"""

SPEC = """\
openapi: 3.0.0
info: {title: probe, version: "1"}
paths:
  /items:
    get:
      description: list items
      responses: {"200": {description: ok}}
"""

TRACKED_TEST = '''\
import asyncio

from partest import call_count
from partest.coverage import track_api_calls


class Client:
    @track_api_calls
    async def make_request(self, method, endpoint, **kwargs):
        return None


def test_one_call():
    asyncio.run(Client().make_request("GET", "/items", type="request_default"))
    counted = {key[:2]: value for key, value in call_count.items()}
    print("COUNTED", counted)
'''

REPORT_TEST = '''\
from partest.reports.analyzer import analyze_coverage


def test_report():
    analyze_coverage()
'''


def _project(tmp_path, *, name="suite", ini_extra="", conf=None, conf_dir="."):
    project = tmp_path / name
    (project / "tests").mkdir(parents=True)
    (project / "pytest.ini").write_text(
        "[pytest]\ntestpaths = tests\n" + ini_extra, encoding="utf-8"
    )
    (project / "openapi.yaml").write_text(SPEC, encoding="utf-8")
    if conf is None:
        conf = 'swagger_files = {"api": ["local", "openapi.yaml"]}\n'
    if conf is not False:
        target = project / conf_dir
        target.mkdir(parents=True, exist_ok=True)
        (target / "confpartest.py").write_text(conf, encoding="utf-8")
    return project


def _environ(**extra):
    environ = dict(os.environ)
    for name in list(environ):
        if name.startswith("PARTEST_") or name in {"PYTEST_ADDOPTS", "PYTHONPATH"}:
            environ.pop(name)
    # The entry point may or may not be installed; load this tree's plugin explicitly.
    environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environ.update(extra)
    return environ


def _run(tmp_path, cwd, *args, sessions=None, **env):
    """One pytest session in *cwd*; or several, *sessions* = [(cwd, args), ...]."""
    runner = tmp_path / "runner" / "run.py"
    runner.parent.mkdir(exist_ok=True)
    runner.write_text(RUNNER, encoding="utf-8")
    common = ["-p", "partest.pytest_plugin", "-p", "no:cacheprovider", "-s", "-rA"]
    sessions = sessions or [(cwd, list(args))]
    plan = json.dumps([[str(where), [*common, *extra]] for where, extra in sessions])
    cmd = [sys.executable, str(runner), str(REPO), plan]
    result = subprocess.run(
        cmd, cwd=tmp_path, env=_environ(**env), capture_output=True, text=True, timeout=300
    )
    return result.returncode, result.stdout + result.stderr


COUNTED_ONE = "COUNTED {('GET', '/items'): 1}"


# --- finding the project file --------------------------------------------------------


def test_console_pytest_without_pythonpath_still_counts(tmp_path):
    """The quickstart layout, a console ``pytest``, no ``pythonpath``, no root conftest."""
    project = _project(tmp_path)
    (project / "tests" / "test_probe.py").write_text(TRACKED_TEST, encoding="utf-8")

    code, out = _run(tmp_path, project)

    assert code == 0, out
    assert COUNTED_ONE in out
    # The run names the file it read and where from.
    assert "partest: confpartest" in out
    assert "was loaded from the pytest root directory" in out


def test_pythonpath_dot_counts_without_the_root_lookup(tmp_path):
    project = _project(tmp_path, ini_extra="pythonpath = .\n")
    (project / "tests" / "test_probe.py").write_text(TRACKED_TEST, encoding="utf-8")

    code, out = _run(tmp_path, project)

    assert code == 0, out
    assert COUNTED_ONE in out
    assert "loaded from the pytest root directory" not in out


def test_a_run_from_a_subdirectory_finds_the_spec_next_to_confpartest(tmp_path):
    """``cd tests && pytest``: a relative ``local`` spec is taken from confpartest's directory."""
    project = _project(tmp_path)
    (project / "tests" / "test_probe.py").write_text(TRACKED_TEST, encoding="utf-8")

    code, out = _run(tmp_path, project / "tests")

    assert code == 0, out
    assert COUNTED_ONE in out


def test_noconftest_turns_the_root_lookup_off_and_the_summary_says_so(tmp_path):
    project = _project(tmp_path)
    (project / "tests" / "test_probe.py").write_text(TRACKED_TEST, encoding="utf-8")
    (project / "tests" / "test_report.py").write_text(REPORT_TEST, encoding="utf-8")

    code, out = _run(tmp_path, project, "--noconftest")

    assert code == 0, out
    assert "COUNTED {}" in out
    assert "partest: coverage NOT COUNTED" in out
    assert "was not tried: --noconftest is set" in out


def test_a_ui_session_does_not_execute_the_root_confpartest(tmp_path):
    """The plugin's own switches are read in every session; they do not use the root lookup."""
    project = _project(tmp_path)
    (project / "tests" / "test_ui.py").write_text(
        "import sys\n\n\ndef test_screen():\n    assert 'confpartest' not in sys.modules\n",
        encoding="utf-8",
    )

    code, out = _run(tmp_path, project)

    assert code == 0, out
    assert "partest: confpartest" not in out


def test_a_second_session_in_the_process_does_not_inherit_the_first(tmp_path):
    """``pytest_unconfigure`` unloads the root module and forgets the specification."""
    first = _project(tmp_path, name="first")
    (first / "tests" / "test_probe.py").write_text(TRACKED_TEST, encoding="utf-8")
    second = _project(tmp_path, name="second", conf=False)
    (second / "tests" / "test_clean.py").write_text(
        textwrap.dedent(
            """\
            import sys

            from partest import coverage
            from partest.methodology.api.overrides import active_overrides


            def test_nothing_left_over():
                assert "confpartest" not in sys.modules
                assert coverage.get_paths_info() == []
                assert active_overrides() == {}
            """
        ),
        encoding="utf-8",
    )
    (first / "confpartest.py").write_text(
        'swagger_files = {"api": ["local", "openapi.yaml"]}\n'
        'subtype_overrides = {"GET /items": "get_static_object"}\n',
        encoding="utf-8",
    )

    code, out = _run(tmp_path, None, sessions=[(first, []), (second, [])])

    assert code == 0, out
    assert COUNTED_ONE in out
    assert "CODES [0, 0]" in out


# --- when it cannot be read: say what happened, do not turn a green run red ----------


def test_an_empty_report_is_said_out_loud_and_still_written_under_w_error(tmp_path):
    """confpartest where nothing looks; ``filterwarnings = error``; report from the plugin."""
    project = _project(tmp_path, conf_dir="config", ini_extra="filterwarnings = error\n")
    (project / "tests" / "test_probe.py").write_text(TRACKED_TEST, encoding="utf-8")
    json_path = tmp_path / "coverage.json"

    code, out = _run(tmp_path, project, PARTEST_COVERAGE_JSON=str(json_path))

    assert code == 0, out
    assert json_path.is_file(), out
    assert json.loads(json_path.read_text(encoding="utf-8"))["endpoints"] == []
    assert "partest: coverage NOT COUNTED" in out
    assert "no confpartest module on sys.path and no" in out
    assert f"Put confpartest.py in {project}" in out


def test_a_root_confpartest_that_fails_to_execute_is_named_as_such(tmp_path):
    project = _project(tmp_path, conf="swagger_files = {\n")
    (project / "tests" / "test_report.py").write_text(REPORT_TEST, encoding="utf-8")

    code, out = _run(tmp_path, project)

    assert code == 0, out
    assert "failed while executing: SyntaxError" in out
    assert "no confpartest module" not in out
    assert "pythonpath = ." not in out


def test_a_root_confpartest_that_needs_the_path_suggests_pythonpath(tmp_path):
    project = _project(
        tmp_path,
        conf="from project_settings import SPEC  # a sibling module: needs the root on sys.path\n"
        'swagger_files = {"api": ["local", SPEC]}\n',
    )
    (project / "project_settings.py").write_text('SPEC = "openapi.yaml"\n', encoding="utf-8")
    (project / "tests" / "test_report.py").write_text(REPORT_TEST, encoding="utf-8")

    code, out = _run(tmp_path, project)

    assert code == 0, out
    assert "loading it directly failed (ModuleNotFoundError" in out
    assert "pythonpath = ." in out
    assert "partest: coverage NOT COUNTED" in out


def test_a_broken_spec_behind_a_root_confpartest_is_reported_not_raised(tmp_path):
    """Such a run counted nothing before the root lookup existed; it must not turn red now."""
    project = _project(tmp_path, conf='swagger_files = {"api": ["local", "missing.yaml"]}\n')
    (project / "tests" / "test_probe.py").write_text(TRACKED_TEST, encoding="utf-8")
    (project / "tests" / "test_report.py").write_text(REPORT_TEST, encoding="utf-8")

    code, out = _run(tmp_path, project)

    assert code == 0, out
    assert "COUNTED {}" in out
    assert "could not load the OpenAPI specification swagger_files['api']" in out


def test_a_broken_spec_on_sys_path_fails_the_tracked_call_not_the_import(tmp_path):
    project = _project(
        tmp_path,
        ini_extra="pythonpath = .\n",
        conf='swagger_files = {"api": ["local", "missing.yaml"]}\n',
    )
    (project / "tests" / "test_probe.py").write_text(
        textwrap.dedent(
            '''\
            def test_import_is_fine():
                from partest import httpx_client  # noqa: F401
                import partest.ui  # noqa: F401
            '''
        )
        + TRACKED_TEST,
        encoding="utf-8",
    )

    code, out = _run(tmp_path, project)

    assert code == 1, out
    assert "PASSED tests/test_probe.py::test_import_is_fine" in out
    assert "FAILED tests/test_probe.py::test_one_call" in out
    assert "could not load the OpenAPI specification swagger_files['api']" in out


# --- in-process: the pieces the sessions above are made of ---------------------------


@pytest.fixture
def coverage_state(monkeypatch):
    """A coverage module that has decided nothing, restored afterwards."""
    from partest import conf, coverage

    for name, value in (
        ("swagger_files", None),
        ("SWAGGER_AVAILABLE", None),
        ("paths_info", []),
        ("_spec_loaded", False),
        ("_spec_error", None),
        ("_spec_note", ""),
    ):
        monkeypatch.setattr(coverage, name, value)
    monkeypatch.setattr(conf, "_project_roots", [conf._Root(REPO, True)])
    monkeypatch.setattr(conf, "_notes", {})
    return coverage


def _fake_conf(monkeypatch, directory=None, **attrs):
    module = types.ModuleType("confpartest")
    if directory is not None:
        module.__file__ = str(pathlib.Path(directory) / "confpartest.py")
    for name, value in attrs.items():
        setattr(module, name, value)
    monkeypatch.setitem(sys.modules, "confpartest", module)
    return module


def test_secrets_in_a_spec_url_do_not_reach_the_error(monkeypatch, coverage_state):
    from partest.conf import ConfpartestError

    _fake_conf(
        monkeypatch,
        swagger_files={"api": ["url", "http://alice:s3cr3tpw@127.0.0.1:9/openapi.json?token=t0k3n"]},
    )

    with pytest.raises(ConfpartestError) as caught:
        coverage_state._ensure_spec()

    text = str(caught.value)
    assert "swagger_files['api']" in text
    assert "s3cr3tpw" not in text and "t0k3n" not in text and "alice" not in text
    # And the reason the report prints is the same sanitised text.
    assert "t0k3n" not in coverage_state._coverage_unavailable_reason()


def test_safe_text_strips_userinfo_and_queries():
    from partest.conf import _safe_text

    text = _safe_text(
        "404 for url: https://u:pw@h.example/spec.json?token=abc and url: /x.json?key=v",
        secrets_of="https://u:pw@h.example/spec.json?token=abc",
    )
    assert "pw" not in text and "abc" not in text and "key=v" not in text
    assert "https://h.example/spec.json?…" in text


def test_paths_info_is_filled_in_place(monkeypatch, tmp_path, coverage_state):
    (tmp_path / "openapi.yaml").write_text(SPEC, encoding="utf-8")
    _fake_conf(monkeypatch, tmp_path, swagger_files={"api": ["local", "openapi.yaml"]})
    imported = coverage_state.paths_info  # what `from partest.coverage import paths_info` holds

    coverage_state._ensure_spec()

    assert coverage_state.SWAGGER_AVAILABLE is True
    assert imported is coverage_state.paths_info and len(imported) == 1


def test_switching_counting_off_by_hand_still_works(monkeypatch, tmp_path, coverage_state):
    import asyncio

    from partest import call_storage

    (tmp_path / "openapi.yaml").write_text(SPEC, encoding="utf-8")
    _fake_conf(monkeypatch, tmp_path, swagger_files={"api": ["local", "openapi.yaml"]})
    monkeypatch.setattr(coverage_state, "SWAGGER_AVAILABLE", False)
    before = dict(call_storage.call_count)

    @coverage_state.track_api_calls
    async def make_request(self, method, endpoint, **kwargs):
        return None

    asyncio.run(make_request(None, "GET", "/items", type="request_default"))

    assert dict(call_storage.call_count) == before
    assert coverage_state._spec_loaded is False
    assert "switched off" in coverage_state._coverage_unavailable_reason()


def test_nothing_is_decided_before_the_root_is_reported(monkeypatch, tmp_path, coverage_state):
    """A conftest's ``pytest_configure`` runs before the plugin's: "no file" is not final yet."""
    from partest import conf

    monkeypatch.setattr(conf, "_project_roots", [])
    monkeypatch.setitem(sys.modules, "confpartest", None)

    coverage_state._ensure_spec()
    assert coverage_state._spec_loaded is False

    (tmp_path / "openapi.yaml").write_text(SPEC, encoding="utf-8")
    _fake_conf(monkeypatch, tmp_path, swagger_files={"api": ["local", "openapi.yaml"]})
    coverage_state._ensure_spec()
    assert coverage_state.SWAGGER_AVAILABLE is True


def test_two_threads_load_the_spec_once(monkeypatch, tmp_path, coverage_state):
    import partest.parparser as parparser

    loads = []

    class SlowSettings:
        def __init__(self, files):
            self.files = files

        def collect_paths_info(self):
            loads.append(1)
            time.sleep(0.2)
            return []

    monkeypatch.setattr(parparser, "SwaggerSettings", SlowSettings)
    _fake_conf(monkeypatch, tmp_path, swagger_files={"api": ["local", "openapi.yaml"]})

    threads = [threading.Thread(target=coverage_state._ensure_spec) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert loads == [1]


def test_a_report_built_without_the_spec_says_so_even_with_rows(monkeypatch, coverage_state):
    """xdist: the controller merges workers' calls but its own spec load failed."""
    from partest import call_storage, conf
    from partest.conf import ConfpartestError
    from partest.reports.analyzer import analyze_coverage

    monkeypatch.setattr(coverage_state, "_spec_loaded", True)
    monkeypatch.setattr(coverage_state, "_spec_error", ConfpartestError("spec went away"))
    monkeypatch.setitem(call_storage.call_count, ("GET", "/merged", "from a worker"), 3)
    monkeypatch.setitem(call_storage.call_type, ("GET", "/merged", "from a worker"), ["request_default"])

    report = analyze_coverage()

    assert report.endpoints  # the merged calls alone
    lines = conf._notes.get(conf.NOTES_COVERAGE, [])
    assert any("built without the specification" in line and "spec went away" in line for line in lines)


def test_without_the_plugin_an_empty_report_warns(monkeypatch, coverage_state):
    from partest import conf
    from partest.reports.analyzer import analyze_coverage

    monkeypatch.setattr(conf, "_project_roots", [])
    monkeypatch.setitem(sys.modules, "confpartest", None)

    with pytest.warns(UserWarning, match="import of confpartest is blocked"):
        analyze_coverage()

    monkeypatch.delitem(sys.modules, "confpartest")
    assert "was not reported" in conf._absence_reason()


@pytest.fixture
def overrides_state(monkeypatch):
    from partest import conf
    from partest.methodology.api import overrides

    saved = dict(overrides._overrides)
    monkeypatch.setattr(overrides, "_conf_consulted", False)
    monkeypatch.setattr(overrides, "_explicit", False)
    monkeypatch.setattr(overrides, "_from_conf", False)
    monkeypatch.setattr(conf, "_project_roots", [conf._Root(REPO, True)])
    monkeypatch.setattr(conf, "_notes", {})
    yield overrides
    overrides._overrides.clear()
    overrides._overrides.update(saved)


def test_overrides_are_read_from_confpartest_on_first_use(monkeypatch, overrides_state):
    overrides_state._overrides.clear()
    _fake_conf(monkeypatch, subtype_overrides={"GET /media-types": "get_static_object"})

    assert overrides_state.active_overrides() == {"GET /media-types": "get_static_object"}

    # ... and dropped with the session that read them.
    overrides_state._reset_session_state()
    monkeypatch.setitem(sys.modules, "confpartest", None)
    assert overrides_state.active_overrides() == {}


def test_an_overrides_file_is_found_next_to_confpartest(monkeypatch, tmp_path, overrides_state):
    (tmp_path / "subtypes.yaml").write_text('"GET /reports": action\n', encoding="utf-8")
    _fake_conf(monkeypatch, tmp_path, subtype_overrides="subtypes.yaml")

    assert overrides_state.active_overrides() == {"GET /reports": "action"}


def test_an_explicit_override_is_not_replaced_by_confpartest_later(monkeypatch, overrides_state):
    overrides_state.set_subtype_overrides({"GET /widgets": "get_list_objects"})
    _fake_conf(monkeypatch, subtype_overrides={"GET /media-types": "get_static_object"})

    assert overrides_state.active_overrides() == {"GET /widgets": "get_list_objects"}
    overrides_state._reset_session_state()
    assert overrides_state.active_overrides() == {"GET /widgets": "get_list_objects"}


def test_a_bad_override_in_confpartest_stays_loud(monkeypatch, overrides_state):
    _fake_conf(monkeypatch, subtype_overrides={"GET /a": "not_a_subtype"})

    with pytest.raises(ValueError, match="unknown subtype"):
        overrides_state.lookup("GET", "/a")
    # Not consulted-and-forgotten: the next lookup raises again.
    with pytest.raises(ValueError, match="unknown subtype"):
        overrides_state.lookup("GET", "/a")


def test_load_confpartest_wraps_any_failure(tmp_path, monkeypatch):
    from partest.conf import ConfpartestError, load_confpartest

    (tmp_path / "partest_probe_conf.py").write_text("1 / 0\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "partest_probe_conf", raising=False)

    with pytest.raises(ConfpartestError, match="ZeroDivisionError"):
        load_confpartest("partest_probe_conf")


def test_the_root_lookup_is_used_only_where_allowed(tmp_path, monkeypatch):
    from partest import conf

    (tmp_path / "partest_probe_root.py").write_text("flag = 'on'\n", encoding="utf-8")
    monkeypatch.delitem(sys.modules, "partest_probe_root", raising=False)
    monkeypatch.setattr(conf, "_project_roots", [])
    monkeypatch.setattr(conf, "_notes", {})

    assert conf.conf_attr("flag", "default", module_name="partest_probe_root") == "default"

    conf._push_project_root(tmp_path, usable=False, why="not ours")
    assert conf.conf_attr("flag", "default", module_name="partest_probe_root") == "default"
    assert "not ours" in conf._absence_reason("partest_probe_root")

    conf._push_project_root(tmp_path)
    try:
        assert conf.conf_attr("flag", "default", module_name="partest_probe_root", fallback=False) == "default"
        assert conf.conf_attr("flag", module_name="partest_probe_root") == "on"
    finally:
        conf._pop_project_root(tmp_path)
        conf._pop_project_root(tmp_path)
    assert "partest_probe_root" not in sys.modules  # unloaded with its root


# --- secrets do not leave through the exception chain ---------------------------------

SECRET_PW = "s3cr3tpw"
SEEN_AUTH: list = []
SECRET_TOKEN = "t0k3nvalue"


@pytest.fixture
def spec_server():
    """A local HTTP server: ``/openapi.yaml`` serves SPEC, anything else is 404."""
    import http.server

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - the stdlib's name
            SEEN_AUTH.append(self.headers.get("Authorization"))
            if self.path.split("?", 1)[0] == "/openapi.yaml":
                body = SPEC.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/yaml")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _secret_url(host, path="/missing.json"):
    return f"http://alice:{SECRET_PW}@{host}{path}?token={SECRET_TOKEN}"


def _assert_clean(text):
    assert SECRET_PW not in text and SECRET_TOKEN not in text and "alice" not in text, text


def test_the_traceback_of_a_spec_failure_carries_no_secret(monkeypatch, spec_server, coverage_state):
    import traceback

    from partest.conf import ConfpartestError

    _fake_conf(monkeypatch, swagger_files={"api": ["url", _secret_url(spec_server)]})

    for _ in range(2):  # the first raise, and the cached one
        with pytest.raises(ConfpartestError) as caught:
            coverage_state._ensure_spec()
        err = caught.value
        assert err.__cause__ is None and err.__suppress_context__
        _assert_clean("".join(traceback.format_exception(type(err), err, err.__traceback__)))
        assert "swagger_files['api']" in str(err)


def test_a_broken_confpartest_traceback_carries_no_secret(tmp_path, monkeypatch):
    import traceback

    from partest.conf import ConfpartestError, _find_confpartest

    (tmp_path / "partest_probe_secret.py").write_text(
        f"raise RuntimeError('cannot reach {_secret_url('db.example')}')\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "partest_probe_secret", raising=False)

    with pytest.raises(ConfpartestError) as caught:
        _find_confpartest("partest_probe_secret")
    err = caught.value
    assert err.__cause__ is None and err.__suppress_context__
    _assert_clean("".join(traceback.format_exception(type(err), err, err.__traceback__)))


def test_resolve_swagger_failure_carries_no_secret(spec_server):
    import traceback

    from partest.openapi import OpenApiResolveError, resolve_swagger

    with pytest.raises(OpenApiResolveError) as caught:
        resolve_swagger(["url", _secret_url(spec_server)], timeout=5)
    err = caught.value
    assert err.__cause__ is None and err.__suppress_context__
    _assert_clean("".join(traceback.format_exception(type(err), err, err.__traceback__)))


def test_a_pytest_run_with_a_secret_spec_url_prints_no_secret(tmp_path, spec_server):
    """The terminal, junit XML and Allure results — what a CI run keeps."""
    project = _project(
        tmp_path,
        ini_extra="pythonpath = .\n",
        conf=f'swagger_files = {{"api": ["url", "{_secret_url(spec_server)}"]}}\n',
    )
    (project / "tests" / "test_probe.py").write_text(TRACKED_TEST, encoding="utf-8")
    junit = tmp_path / "junit.xml"
    alluredir = tmp_path / "allure"

    code, out = _run(
        tmp_path, project, f"--junitxml={junit}", "-p", "allure_pytest.plugin",
        f"--alluredir={alluredir}", "-vv", "-l",  # -l: locals of every traceback frame
    )

    assert code == 1, out
    assert "could not load the OpenAPI specification swagger_files['api']" in out
    _assert_clean(out)
    _assert_clean(junit.read_text(encoding="utf-8"))
    results = list(alluredir.glob("*-result.json"))
    assert results, out
    for result in results:
        _assert_clean(result.read_text(encoding="utf-8"))


def test_safe_text_edge_cases():
    from partest.conf import _safe_text

    assert "ss@" not in _safe_text("for url: https://u:p@ss@h.example/x")
    assert _safe_text("for url: https://u:p@ss@h.example/x") == "for url: https://h.example/x"
    assert "s3cr3t" not in _safe_text("connect alice:s3cr3t@db.example:5432/x failed")
    # Short query values are not hunted through the message: it must stay readable.
    text = _safe_text("a b and s3cr3tpw", secrets_of="http://u:s3cr3tpw@h/x?a=b&t=longvalue")
    assert text == "a b and …"


# --- the plugin's own switches, roots, notes ------------------------------------------


def test_the_plugin_switches_do_not_read_a_file_loaded_from_the_root(tmp_path):
    """Before and after a tracked call loads the root confpartest, the switches stay put."""
    project = _project(
        tmp_path,
        conf='swagger_files = {"api": ["local", "openapi.yaml"]}\n'
        "pytest_plugin = False\nrun_metadata = False\n",
    )
    (project / "tests" / "test_probe.py").write_text(
        TRACKED_TEST
        + textwrap.dedent(
            """\

            def test_switches_after_the_call():
                from partest.pytest_plugin import plugin_enabled, run_metadata_enabled

                assert (plugin_enabled(), run_metadata_enabled()) == (True, True)
            """
        ),
        encoding="utf-8",
    )

    code, out = _run(tmp_path, project)

    assert code == 0, out
    assert COUNTED_ONE in out
    assert "`pytest_plugin` and `run_metadata` in it are not read" in out


def test_fallback_false_does_not_see_a_module_loaded_by_location(tmp_path, monkeypatch):
    from partest import conf

    (tmp_path / "partest_probe_sw.py").write_text("flag = 'from-file'\n", encoding="utf-8")
    monkeypatch.delitem(sys.modules, "partest_probe_sw", raising=False)
    monkeypatch.setattr(conf, "_project_roots", [])
    monkeypatch.setattr(conf, "_notes", {})
    conf._push_project_root(tmp_path)
    try:
        assert conf.conf_attr("flag", module_name="partest_probe_sw") == "from-file"
        assert conf.conf_attr("flag", "default", module_name="partest_probe_sw", fallback=False) == "default"
    finally:
        conf._pop_project_root(tmp_path)


def test_the_root_is_the_ini_directory_not_rootdir(tmp_path):
    """``--rootdir`` (IDEs set it) does not move where confpartest.py is looked for."""
    project = _project(tmp_path)
    (project / "tests" / "test_probe.py").write_text(TRACKED_TEST, encoding="utf-8")

    code, out = _run(tmp_path, project, f"--rootdir={project / 'tests'}")

    assert code == 0, out
    assert COUNTED_ONE in out


def test_a_foreign_ini_directory_is_not_searched(tmp_path):
    """``-c`` names an ini elsewhere: its confpartest.py belongs to another project."""
    other = _project(tmp_path, name="other")
    suite = _project(tmp_path, name="suite", conf=False)
    (suite / "tests" / "test_report.py").write_text(REPORT_TEST, encoding="utf-8")

    code, out = _run(tmp_path, tmp_path, "-c", str(other / "pytest.ini"), str(suite / "tests"))

    assert code == 0, out
    assert "was not tried" in out and "contains neither the current directory" in out
    assert "was loaded from the pytest root directory" not in out


def test_p_no_conftest_turns_the_root_lookup_off(tmp_path):
    project = _project(tmp_path)
    (project / "tests" / "test_report.py").write_text(REPORT_TEST, encoding="utf-8")

    code, out = _run(tmp_path, project, "-p", "no:conftest")

    assert code == 0, out
    assert "was not tried: -p no:conftest is set" in out


def test_worker_notes_reach_the_controller_under_xdist(tmp_path):
    pytest.importorskip("xdist")
    project = _project(tmp_path, conf=False)
    (project / "tests" / "test_note.py").write_text(
        textwrap.dedent(
            """\
            import pytest


            @pytest.mark.parametrize("n", [1, 2])
            def test_note(n):
                from partest import conf

                conf._note(conf.NOTES_COVERAGE, "probe line from a worker")
            """
        ),
        encoding="utf-8",
    )
    environ = _environ(PYTHONPATH=str(REPO))
    cmd = [
        sys.executable, "-m", "pytest", "-p", "partest.pytest_plugin", "-p", "xdist.plugin",
        "-p", "no:cacheprovider", "-n", "2", "-q",
    ]
    result = subprocess.run(cmd, cwd=project, env=environ, capture_output=True, text=True, timeout=300)
    out = result.stdout + result.stderr

    assert result.returncode == 0, out
    assert "partest: coverage NOT COUNTED" in out
    assert out.count("probe line from a worker") == 1, out


def test_the_report_from_sessionfinish_survives_w_error(tmp_path, spec_server):
    """The first spec load happens in the controller's sessionfinish and warns (TLS off)."""
    project = _project(
        tmp_path,
        ini_extra="pythonpath = .\nfilterwarnings = error\n",
        conf=f'swagger_files = {{"api": ["url", "http://{spec_server}/openapi.yaml"]}}\n',
    )
    (project / "tests" / "test_plain.py").write_text("def test_plain():\n    pass\n", encoding="utf-8")
    json_path = tmp_path / "coverage.json"

    code, out = _run(
        tmp_path, project, PARTEST_COVERAGE_JSON=str(json_path), PARTEST_TLS_VERIFY="0"
    )

    assert code == 0, out
    assert json_path.is_file(), out
    assert [e["path"] for e in json.loads(json_path.read_text(encoding="utf-8"))["endpoints"]] == ["/items"]


# --- in-process: smaller pieces ---------------------------------------------------------


def test_session_state_is_put_back_for_an_outer_session(tmp_path, monkeypatch, coverage_state):
    """A nested in-process session starts clean and hands the outer one its state back."""
    from partest import conf
    from partest import pytest_plugin as plugin

    monkeypatch.setattr(coverage_state, "_spec_loaded", True)
    monkeypatch.setattr(coverage_state, "SWAGGER_AVAILABLE", True)
    monkeypatch.setattr(coverage_state, "_spec_note", "outer")
    conf._note(conf.NOTES_COVERAGE, "outer note")

    inner = types.SimpleNamespace(stash=pytest.Stash(), inipath=None, rootpath=tmp_path)
    plugin._begin_session_state(inner)
    assert coverage_state.SWAGGER_AVAILABLE is None and conf._notes == {}
    conf._note(conf.NOTES_COVERAGE, "inner note")
    plugin.pytest_unconfigure(inner)

    assert coverage_state.SWAGGER_AVAILABLE is True and coverage_state._spec_note == "outer"
    assert conf._notes == {conf.NOTES_COVERAGE: ["outer note"]}


def test_swagger_available_true_by_hand_does_not_switch_counting_off(monkeypatch, tmp_path, coverage_state):
    (tmp_path / "openapi.yaml").write_text(SPEC, encoding="utf-8")
    _fake_conf(monkeypatch, tmp_path, swagger_files={"api": ["local", "openapi.yaml"]})
    monkeypatch.setattr(coverage_state, "SWAGGER_AVAILABLE", True)

    coverage_state._ensure_spec()

    assert coverage_state.swagger_files and len(coverage_state.paths_info) == 1


def test_source_kinds_are_read_as_validate_confpartest_accepts_them(monkeypatch, tmp_path, coverage_state):
    (tmp_path / "openapi.yaml").write_text(SPEC, encoding="utf-8")
    _fake_conf(monkeypatch, tmp_path, swagger_files={"api": ["FILE", "openapi.yaml"]})

    coverage_state._ensure_spec()

    assert len(coverage_state.paths_info) == 1


def test_a_relative_ca_bundle_is_found_next_to_confpartest(monkeypatch, tmp_path):
    from partest import tls

    (tmp_path / "ca.pem").write_text("not a real bundle\n", encoding="utf-8")
    _fake_conf(monkeypatch, tmp_path, tls_verify="ca.pem")
    monkeypatch.delenv("PARTEST_TLS_VERIFY", raising=False)

    assert tls._from_confpartest() == str(tmp_path / "ca.pem")


def test_resolve_from_confpartest_finds_the_spec_next_to_confpartest(tmp_path):
    from partest.openapi import resolve_from_confpartest

    (tmp_path / "openapi.yaml").write_text(SPEC, encoding="utf-8")
    conf_module = types.ModuleType("confpartest")
    conf_module.__file__ = str(tmp_path / "confpartest.py")
    conf_module.swagger_files = {"api": ["local", "openapi.yaml"]}

    assert "/items" in resolve_from_confpartest(conf_module)["paths"]


def test_a_blocked_import_is_not_loaded_from_the_root(monkeypatch, tmp_path):
    from partest import conf

    (tmp_path / "confpartest.py").write_text("flag = 1\n", encoding="utf-8")
    monkeypatch.setattr(conf, "_project_roots", [conf._Root(tmp_path, True)])
    monkeypatch.setattr(conf, "_notes", {})
    monkeypatch.setitem(sys.modules, "confpartest", None)

    assert conf._find_confpartest() is None
    assert sys.modules["confpartest"] is None
    assert "blocked" in conf._absence_reason()


def test_overrides_decide_nothing_before_the_root_is_reported(monkeypatch, overrides_state):
    from partest import conf

    monkeypatch.setattr(conf, "_project_roots", [])
    monkeypatch.setitem(sys.modules, "confpartest", None)

    overrides_state.active_overrides()

    assert overrides_state._conf_consulted is False


def test_report_settings_fall_back_when_confpartest_is_broken(monkeypatch):
    from partest import conf
    from partest.reports import analyzer
    from partest.test_types import EXCEPTION_TYPES

    real = conf.conf_attr

    def broken(name, default=None, **kwargs):
        if name.startswith("test_types_"):
            raise conf.ConfpartestError("broken")
        return real(name, default, **kwargs)

    monkeypatch.setattr(conf, "conf_attr", broken)
    assert analyzer._load_exceptions_from_conf() == set(EXCEPTION_TYPES)
    assert analyzer._load_required_from_conf() is None


def test_report_settings_accept_any_iterable(monkeypatch):
    from partest.reports import analyzer

    _fake_conf(monkeypatch, test_types_exception={"health": 1}.keys())
    assert "health" in analyzer._load_exceptions_from_conf()


def test_a_successful_fetch_logs_no_secret_at_info(spec_server, caplog, monkeypatch, coverage_state):
    """Both roads to a spec: ``openapi.resolve_swagger`` (httpx) and coverage (requests)."""
    import base64
    import logging

    from partest.openapi import resolve_swagger

    url = _secret_url(spec_server, "/openapi.yaml")
    SEEN_AUTH.clear()
    with caplog.at_level(logging.INFO):
        assert "/items" in resolve_swagger(["url", url], timeout=5)["paths"]
        _fake_conf(monkeypatch, swagger_files={"api": ["url", url]})
        coverage_state._ensure_spec()
        assert len(coverage_state.paths_info) == 1

    assert any("HTTP Request" in r.getMessage() for r in caplog.records)  # httpx did log it
    _assert_clean(caplog.text)
    expected = "Basic " + base64.b64encode(f"alice:{SECRET_PW}".encode()).decode()
    assert SEEN_AUTH[:2] == [expected, expected]  # the credentials still reach the server


def test_cleaning_text_is_linear_on_hostile_input():
    from partest.conf import _safe_text

    for chunk in ("a:@!", "a.", "ab-", "a:", "x@", "/a?"):
        text = chunk * (65536 // len(chunk))
        started = time.perf_counter()
        _safe_text(text)
        assert time.perf_counter() - started < 1.0, chunk


def test_the_same_failure_from_two_processes_is_one_summary_line(monkeypatch):
    """A refused connection quotes ``<... object at 0x...>``: different in every process."""
    import socket

    import requests

    from partest import conf

    monkeypatch.setattr(conf, "_notes", {})
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()  # nothing listens there now
    texts = []
    for _ in range(2):
        try:
            requests.get(f"http://127.0.0.1:{port}/openapi.json", timeout=5)
        except requests.RequestException as exc:
            texts.append(conf._failure_text(exc))
    assert len(texts) == 2
    for text in texts:
        conf._note(conf.NOTES_COVERAGE, text)
    assert len(conf._notes[conf.NOTES_COVERAGE]) == 1
    assert " at 0x" not in conf._notes[conf.NOTES_COVERAGE][0]
