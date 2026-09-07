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
    install_requires=[
        "httpx>=0.27.2",
        "pyyaml>=6.0.2",
        "matplotlib>=3.9.2",
        "allure-pytest>=2.8.18",
        "pytest-asyncio>=0.23.7",
        "pytest>=8.0.0",
        "pydantic>=2.0.0",
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
        "Faker>=13.12.0",
    ],
    extras_require={
        "ui": [
            "playwright>=1.40.0",
            "Pillow>=10.0.0",
        ],
        # The scaffold generator is a separate distribution: it runs once when a project is
        # created, not on every test run, and for a code generator the names of the files it
        # writes are the public API. This extra exists so `pip install 'partest[gen]'` still
        # gets you both, and so `partest.project_gen` keeps resolving.
        "gen": [
            "partest-gen>=1.0.0",
        ],
        "dev": [
            "pytest>=8.0.0",
            "pytest-asyncio>=0.23.7",
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
