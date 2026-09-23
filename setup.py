import pathlib
import re

from setuptools import find_packages, setup

HERE = pathlib.Path(__file__).parent


def version():
    """Single source of truth: partest/__init__.py. Never duplicate the number here."""
    text = (HERE / "partest" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise RuntimeError("cannot find __version__ in partest/__init__.py")
    return match.group(1)


def readme():
    """PyPI long_description. Kept short on purpose — the repository holds the detail."""
    return (HERE / "docs" / "PYPI.md").read_text(encoding="utf-8")


setup(
    name="partest",
    version=version(),
    author="dec01",
    author_email="parshin.ewgeniy@yandex.ru",
    license="MIT",
    description=(
        "Methodology-driven API/UI autotest harness with OpenAPI coverage "
        "and security helpers."
    ),
    long_description=readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/Dec01/partest",
    packages=find_packages(exclude=["src", "tests", "build", "dist"]),
    include_package_data=True,
    package_data={
        # py.typed: the package ships its annotations (PEP 561). Coverage is partial —
        # TrackingApiClient delegates unknown attributes and types as Any there.
        "partest": ["py.typed", "docs/*.md"],
        "partest.docs": ["*.md"],
    },
    # The floors are audited, not decorative. What `pip-audit` reads in `requirements.txt` is
    # a resolved environment; what a consumer actually gets from `pip install partest` is the
    # *oldest* version each line still allows. Audited as such on 2026-09-23 (a file of
    # `name==floor` fed to `pip-audit -r`): 24 findings in 5 packages, of which one package —
    # Pillow, in the `ui` extra — nobody had ever looked at.
    #
    # A floor is the release that *fixed* the advisory, never "something recent": a package
    # must not demand more than it needs. Raising a floor past the fix costs the consumer a
    # co-ordinated upgrade they did not ask for.
    install_requires=[
        "httpx>=0.27.2",
        "pyyaml>=6.0.2",
        "matplotlib>=3.9.2",
        "allure-pytest>=2.8.18",
        # Not a security floor: every pytest-asyncio below 1.3.0 declares `pytest<9`, so with
        # the old floor here the resolver would satisfy the pair by taking pytest *back* to 8
        # and saying nothing. That is exactly how the consumer's environment was pinned to
        # pytest 8 by pytest-asyncio and pytest-playwright until both lifted the cap.
        "pytest-asyncio>=1.3.0",
        # PYSEC-2026-1845. Fixed in 9.0.3, and in no 8.x release — there is nothing to
        # back-port to, so support for pytest 8 ends here rather than being deprecated.
        #
        # The ceiling is the deliberate part. `partest` registers as a `pytest11` plugin on six
        # hooks, so it loads in *every* session of the consumer, including runs that never
        # touch partest; a hook whose signature a new major drops fails at plugin registration,
        # before collection, and takes the whole session with it. `<10` says "this major was
        # run, the next one was not" instead of promising a compatibility nobody checked.
        # The obligation that comes with it: the cap is lifted by a patch release as soon as
        # the suite passes on the next major, and it is never left to expire quietly — a stale
        # cap silently downgrades the consumer, which is the failure we just paid for.
        "pytest>=9.0.3,<10",
        "pydantic>=2.4.0",  # PYSEC-2026-1812, fixed in 2.4.0
        "requests>=2.33.0",  # PYSEC-2026-1873 / -1872 / -2275, last of them fixed in 2.33.0
        "python-dotenv>=1.2.2",  # PYSEC-2026-2270, fixed in 1.2.2
        "Faker>=13.12.0",
    ],
    extras_require={
        "ui": [
            "playwright>=1.40.0",
            # Eighteen advisories at the old floor of 10.0.0, the last of them fixed in
            # 12.3.0. An extra is installed by consumers like everything else, and this one
            # had never been audited: `requirements.txt` did not list it.
            "Pillow>=12.3.0",
        ],
        # The scaffold generator is a separate distribution: it runs once when a project is
        # created, not on every test run, and for a code generator the names of the files it
        # writes are the public API. This extra exists so `pip install 'partest[gen]'` still
        # gets you both, and so `partest.project_gen` keeps resolving.
        "gen": [
            "partest-gen>=1.0.0",
        ],
        # What the test suite needs beyond the runtime dependencies. None of the last
        # three is imported by the package itself:
        #
        # * pytest-rerunfailures — ``pytest.ini`` puts ``--reruns=2`` into ``addopts``,
        #   and pytest rejects an unknown option before it collects anything: without the
        #   plugin a clean ``pip install -e .[dev]`` cannot run a single test. What the
        #   configuration demands, the installation has to provide —
        #   ``tests/test_packaging.py`` keeps the two in step;
        # * pytest-xdist — the plugin detects a parallel run through
        #   ``hasattr(config, "workerinput")`` and never imports it, but one case runs a
        #   real ``-n 2`` session;
        # * partest-gen — ``tests/test_project_gen_bridge.py`` checks that the old
        #   ``partest.project_gen`` imports still resolve, and to the *same* module
        #   objects. Without the distribution those cases skip, and the release's central
        #   promise then goes unchecked in a gate that still reports green. Same floor as
        #   the ``gen`` extra. Working on both repositories at once, install the sibling
        #   checkout instead: ``pip install -e ../partest_gen --no-deps``.
        "dev": [
            "pytest>=9.0.3,<10",
            "pytest-asyncio>=1.3.0",
            "pytest-rerunfailures>=12.0",
            # 3.0.0 was never released — the first 3.x on PyPI is 3.0.2. `>=3.0.0` resolved
            # anyway, which is why it went unnoticed, but a floor naming a version that does
            # not exist cannot be audited: `pip-audit` on `pytest-xdist==3.0.0` fails to
            # resolve instead of reporting.
            "pytest-xdist>=3.0.2",
            "partest-gen>=1.0.0",
        ],
    },
    entry_points={
        # No partest-gen console script here: it is declared by the distribution that
        # implements it. Two distributions owning one command make the winner depend on
        # installation order.
        "pytest11": [
            "partest=partest.pytest_plugin",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        # 3.14 is claimed because the suite was run there, not because it looked likely:
        # same result as on 3.10, and every dependency resolves with a cp314 wheel or
        # without an ABI tag at all.
        "Programming Language :: Python :: 3.14",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Framework :: Pytest",
        "Topic :: Software Development :: Testing",
    ],
    keywords="autotest api ui coverage openapi partest pytest allure playwright",
    project_urls={
        "Source": "https://github.com/Dec01/partest",
        "Issues": "https://github.com/Dec01/partest/issues",
        "Changelog": "https://github.com/Dec01/partest/blob/master/CHANGELOG.md",
        "Documentation": "https://github.com/Dec01/partest/blob/master/docs/wiki/index.md",
        "PyPI": "https://pypi.org/project/partest/",
    },
    # 3.9 was declared but never verified, and partest-gen was broken there:
    # Path.write_text(newline=...) needs 3.10. Dropping the claim beats shipping one
    # that does not hold. Suites on 3.9 keep resolving to 1.7.1.
    python_requires=">=3.10",
)
