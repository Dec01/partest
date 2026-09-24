"""What the configuration demands, the installation has to provide.

Two failures guarded here look nothing alike and are the same mistake — a claim made in one
file that another file never backs:

* `pytest.ini` asks for a plugin that no extra installs. Pytest rejects an unknown option
  while parsing arguments, before collection, so a clean `pip install -e .[dev]` runs **zero**
  tests and reports `unrecognized arguments`. This is the third time in the family
  (`partest-gen` in the `dev` extra was the second).
* `setup.py` claims a Python version nobody ran the suite on — or, the other way round,
  stays silent about the one it just passed on.
* `requirements.txt` — the only file `pip-audit` can read here — lists something other than
  what `setup.py` declares. Until 2.1.0 it omitted `python-dotenv` and `Pillow` entirely, so
  the audit had never once looked at them and reported green while doing it.

Declarations are read out of `setup.py` with `ast`, never by importing it: an import would
call `setup()`.
"""

from __future__ import annotations

import ast
import configparser
import re
import sys
import warnings
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Settings core pytest owns — nothing has to be installed for them.
CORE_SETTINGS = {
    "addopts",
    "log_cli",
    "log_cli_level",
    "log_cli_format",
    "log_file",
    "log_file_level",
    "log_file_format",
    "log_file_date_format",
    "markers",
    "testpaths",
}

#: Settings and `addopts` options that only work when a plugin is installed, mapped to the
#: distribution providing it. Everything listed here must be declared in `setup.py`.
PROVIDED_BY = {
    "asyncio_mode": "pytest-asyncio",
    "asyncio_default_fixture_loop_scope": "pytest-asyncio",
    "--reruns": "pytest-rerunfailures",
}

#: Extras a consumer can install — `partest[ui]`, `partest[gen]`. Whatever they can install,
#: the audit has to see.
AUDITED_EXTRAS = ("ui", "gen")

#: Extras that stay out of `requirements.txt` on purpose. `dev` is tooling: it never reaches
#: a consumer, and the audit answers "is what we ship safe", not "what do we use here".
UNAUDITED_EXTRAS = ("dev",)


def _pytest_ini() -> configparser.RawConfigParser:
    """`pytest.ini` as written.

    `RawConfigParser`, because `log_file_date_format` contains `%Y` and the interpolating
    parser fails on it.
    """
    parser = configparser.RawConfigParser()
    parser.read(REPO_ROOT / "pytest.ini", encoding="utf-8")
    return parser


def _setup_keyword(name: str):
    """One `setup()` keyword, read without running the file."""
    source = (REPO_ROOT / "setup.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "setup":
            for keyword in node.keywords:
                if keyword.arg == name:
                    return ast.literal_eval(keyword.value)
    raise AssertionError(f"setup({name}=...) not found in setup.py")


def _declared_distributions() -> set[str]:
    """Every distribution an install can bring in, runtime and extras alike."""
    requirements = list(_setup_keyword("install_requires"))
    for extra in _setup_keyword("extras_require").values():
        requirements.extend(extra)
    return {
        # ``maxsplit=1`` by name: passing it positionally is deprecated since 3.13.
        re.split(r"[<>=!~\[;]", item, maxsplit=1)[0].strip().lower()
        for item in requirements
    }


def _split(requirement: str) -> tuple[str, str]:
    """`"pytest>=9.0.3,<10"` → `("pytest", ">=9.0.3,<10")`.

    The name is lower-cased because `Pillow` and `pillow` are one distribution; the
    specifier is kept exactly as written, because that is the thing being compared.
    """
    name = re.split(r"[<>=!~\[;]", requirement, maxsplit=1)[0]
    return name.strip().lower(), requirement[len(name):].strip()


def _declared_for_audit() -> dict[str, str]:
    """Every bound a consumer can get: `install_requires` plus the consumer-facing extras."""
    extras = _setup_keyword("extras_require")
    declared = list(_setup_keyword("install_requires"))
    for extra in AUDITED_EXTRAS:
        declared.extend(extras[extra])
    return dict(_split(item) for item in declared)


def _audited() -> dict[str, str]:
    """`requirements.txt` as `pip-audit` reads it — comments and blank lines dropped."""
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    return dict(
        _split(line)
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _configured_entries() -> set[str]:
    """Setting names plus the options `addopts` passes, e.g. `asyncio_mode`, `--reruns`."""
    config = _pytest_ini()
    entries = set(config["pytest"])
    for line in config["pytest"].get("addopts", "").split():
        entries.add(line.split("=", 1)[0])
    return entries


def test_every_plugin_the_config_asks_for_is_installable():
    """A setting whose plugin no extra installs makes the whole run fail at argument parsing.

    Not a subset of the tests fails — all of them, with a message about arguments that
    mentions no plugin at all.
    """
    declared = _declared_distributions()

    missing = {
        entry: PROVIDED_BY[entry]
        for entry in _configured_entries()
        if entry in PROVIDED_BY and PROVIDED_BY[entry] not in declared
    }

    assert not missing, (
        "pytest.ini requires plugins that setup.py never declares, so a clean "
        f"`pip install -e .[dev]` cannot run the suite: {missing}"
    )


def test_no_configured_entry_goes_unreviewed():
    """New settings get classified, instead of quietly joining the ones already checked.

    Without this the guard above only ever protects the entries somebody remembered to
    list, which is the same blind spot in a new place.
    """
    unknown = _configured_entries() - CORE_SETTINGS - set(PROVIDED_BY)

    assert not unknown, (
        f"pytest.ini entries nobody classified: {sorted(unknown)}. Add each to CORE_SETTINGS "
        "if core pytest owns it, or to PROVIDED_BY with the distribution that provides it."
    )


def _shipped_packages() -> set[str]:
    """Every package inside `partest`, asked of the import system rather than of a glob.

    `pkgutil.iter_modules` goes through the path finders and imports nothing, and it starts
    from the *imported* package rather than from a path spelled out here. That is what makes
    it usable as an expectation for a walk that starts from a path spelled out here: a walk
    that resolved somewhere else is measured against a tree that did not move with it.

    `setuptools.find_packages` would answer the same question, but setuptools is not a
    dependency of this package and is absent from a 3.12+ virtual environment — the exact
    kind of undeclared claim the rest of this file exists to catch.
    """
    import pkgutil

    import partest

    def walk(directory: Path, name: str) -> set[str]:
        found = {name}
        for info in pkgutil.iter_modules([str(directory)]):
            if info.ispkg:
                found |= walk(directory / info.name, f"{name}.{info.name}")
        return found

    return walk(Path(partest.__file__).resolve().parent, "partest")


def _assert_the_walk_covers_the_package(paths) -> None:
    """Premise for a check that walks the package and reports the files that offend.

    Nothing offends in an empty corpus, so such a check passes loudest when its walk broke:
    a root that moved, a mask that narrowed, a tree that was never there. The expectation is
    named rather than counted — every package that ships has to be represented among the
    files read, which also catches a walk that stopped half way through the tree.
    """
    expected = _shipped_packages()
    assert len(expected) > 1, (
        f"the expectation itself is empty: {sorted(expected)} is the whole package tree, so "
        "agreeing with it would prove nothing"
    )

    found = {".".join(p.relative_to(REPO_ROOT).parent.parts) for p in paths}
    assert not expected - found, (
        f"the walk read no module of {sorted(expected - found)}: a check over this corpus "
        "reports «no offenders» for files it never opened"
    )


def test_the_package_has_no_invalid_escape_sequences():
    """`"\\>"` in a plain string is a warning today and a syntax error in a coming Python.

    It fires on import, in the consumer's own output, for a package they only installed.
    The whole package is compiled rather than a known file list: the next one would appear
    somewhere else.
    """
    sources = sorted((REPO_ROOT / "partest").rglob("*.py"))
    _assert_the_walk_covers_the_package(sources)

    offenders = []
    for path in sources:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        offenders += [
            f"{path.relative_to(REPO_ROOT)}:{item.lineno}: {item.message}"
            for item in caught
            if "escape sequence" in str(item.message)
        ]

    assert not offenders, offenders


def test_the_interpreter_the_suite_runs_on_is_declared():
    """Support is claimed because the suite passed, and claimed wherever it passed.

    The classifier list is how an installer learns the package was meant for their
    interpreter; a version that quietly stays out of it is support nobody can find.
    """
    claimed = {
        line.rsplit("::", 1)[1].strip()
        for line in _setup_keyword("classifiers")
        if line.startswith("Programming Language :: Python :: ")
    }
    running = f"{sys.version_info.major}.{sys.version_info.minor}"

    assert running in claimed, (
        f"the suite just passed on Python {running}, which setup.py does not claim: "
        f"{sorted(claimed)}"
    )


def test_the_claimed_versions_start_at_the_floor_and_have_no_gaps():
    """`python_requires` and the classifiers say the same thing or one of them is wrong."""
    floor = _setup_keyword("python_requires")
    assert floor.startswith(">="), f"unexpected python_requires: {floor!r}"

    minor_of = lambda version: tuple(int(part) for part in version.split("."))  # noqa: E731
    claimed = sorted(
        minor_of(line.rsplit("::", 1)[1].strip())
        for line in _setup_keyword("classifiers")
        if line.startswith("Programming Language :: Python :: 3.")
    )

    assert claimed[0] == minor_of(floor[2:].strip()), (
        f"python_requires is {floor!r} but the classifiers start at {claimed[0]}"
    )
    assert claimed == [(3, minor) for minor in range(claimed[0][1], claimed[-1][1] + 1)], (
        f"a version is missing between {claimed[0]} and {claimed[-1]}: {claimed}"
    )


def test_the_audited_requirements_match_what_the_package_declares():
    """`requirements.txt` exists for `pip-audit` and has to describe what is installed.

    `pip-audit` reads dependencies from `pyproject.toml` or `requirements.txt` only; the ones
    `setup.py` declares imperatively are invisible to it. So the file is kept — and once it
    is kept, a list that has drifted is worse than no list at all: the audit runs, reports
    green, and audits something else. `python-dotenv` sat in `install_requires` and nowhere
    in `requirements.txt` for as long as both existed, and that is how a known advisory in it
    survived every green gate.

    Names *and* bounds are compared. A name-only check would pass a file that lists
    `requests>=2.31.0` while the package declares `>=2.33.0` — and the audit would then be
    run against a floor nobody ships.
    """
    declared, audited = _declared_for_audit(), _audited()

    assert set(declared) == set(audited), (
        "requirements.txt disagrees with setup.py — the audit is not looking at what is "
        "installed.\n"
        f"  declared in setup.py, missing from requirements.txt: "
        f"{sorted(set(declared) - set(audited))}\n"
        f"  listed in requirements.txt, declared nowhere: "
        f"{sorted(set(audited) - set(declared))}"
    )

    drifted = {
        name: (spec, audited[name]) for name, spec in declared.items() if audited[name] != spec
    }
    assert not drifted, (
        "the bounds drifted apart, so the audit runs against versions the package does not "
        f"declare — name: (setup.py, requirements.txt): {drifted}"
    )


def test_every_extra_is_either_audited_or_deliberately_left_out():
    """A new extra gets classified instead of quietly escaping the audit.

    Without this, the guard above only protects the extras somebody remembered to list —
    the same blind spot one level up.
    """
    extras = set(_setup_keyword("extras_require"))
    classified = set(AUDITED_EXTRAS) | set(UNAUDITED_EXTRAS)

    assert extras == classified, (
        f"extras nobody classified: {sorted(extras - classified)}; classified but gone from "
        f"setup.py: {sorted(classified - extras)}. A consumer-facing extra belongs in "
        "AUDITED_EXTRAS and in requirements.txt; tooling belongs in UNAUDITED_EXTRAS."
    )


def test_the_pytest_the_suite_runs_on_is_inside_the_declared_range():
    """The window `setup.py` declares is the window the suite is actually run in.

    `partest` is a `pytest11` plugin: it loads in every session of the consumer, so a major
    it has not been run under is a promise, not a fact. The upper bound is how that promise
    is withheld — and this is what keeps it honest in both directions. Raising the cap
    without running the suite under the new major fails here; so does running the suite under
    a pytest the package tells consumers it does not support.
    """
    from packaging.specifiers import SpecifierSet

    declared = _declared_for_audit()["pytest"]
    running = pytest.__version__

    assert SpecifierSet(declared).contains(running, prereleases=True), (
        f"the suite is running on pytest {running}, which setup.py excludes ({declared}): "
        "either the run is wrong or the declaration is"
    )
