from setuptools import find_packages, setup


def readme():
    with open("docs/README.md", "r", encoding="utf-8") as f:
        return f.read()


setup(
    name="partest",
    version="1.5.0",
    author="dec01",
    author_email="parschin.ewg@yandex.ru",
    description=(
        "Methodology-driven API/UI autotest harness with OpenAPI coverage, "
        "security helpers, and partest-gen monorepo scaffold."
    ),
    long_description=readme(),
    long_description_content_type="text/markdown",
    url="https://pypi.org/project/partest/",
    packages=find_packages(exclude=["src", "tests", "build", "dist"]),
    include_package_data=True,
    package_data={
        "partest": ["docs/*.md"],
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
        "dev": [
            "pytest>=8.0.0",
            "pytest-asyncio>=0.23.7",
        ],
    },
    entry_points={
        "console_scripts": [
            "partest-gen=partest.project_gen.cli:main",
        ],
        "pytest11": [
            "partest=partest.pytest_plugin",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Framework :: Pytest",
        "Topic :: Software Development :: Testing",
    ],
    keywords="autotest api ui coverage openapi partest pytest allure playwright",
    project_urls={
        "PyPI": "https://pypi.org/project/partest/",
    },
    python_requires=">=3.9",
)
