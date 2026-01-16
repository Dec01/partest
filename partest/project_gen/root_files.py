class RootFile:
    """Class representing a single root file with name and content."""
    def __init__(self, name: str, content: str):
        """
        Initialize a RootFile object.

        Args:
            name (str): The name of the file (e.g., 'requirements.txt').
            content (str): The content of the file.
        """
        self.name = name
        self.content = content

    def __repr__(self):
        """Return a string representation of the RootFile object."""
        return f"RootFile(name='{self.name}', content_length={len(self.content)})"


class RootFilesContainer:
    """Class to manage all root files for the project."""
    def __init__(self):
        """Initialize the container with a list of root files."""
        self.files = [
            RootFile(
                name="requirements.txt",
                content="""attrs==24.2.0
certifi==2024.8.30
charset-normalizer==3.4.0
Faker>=13.12.0
idna==3.10
iniconfig==2.0.0
jsonschema==4.22.0
packaging==25.0
pluggy==1.5.0
py==1.11.0
pyparsing==3.0.9
pyrsistent==0.18.1
pytest==8.3.3
python-dateutil==2.9.0.post0
requests==2.32.3
six==1.17.0
tomli==2.2.1
urllib3==2.4.0
pytest-repeat==0.9.4
pytest-asyncio>=0.23.7
pydantic==2.9.2
pytest-rerunfailures~=15.1
ruff==0.11.13
allure-pytest>=2.8.18
allure-python-commons~=2.13.5
httpx~=0.28.1
swagger-parser>=1.0.2
matplotlib>=3.9.2
pyyaml>=6.0.2
partest>=0.2.5
fake-useragent>=2.2.0
"""
            ),
            RootFile(
                name="pytest.ini",
                content="""[pytest]
log_cli = 1
log_cli_level = INFO
log_cli_format = %(message)s
log_file = logs/pytest.log
log_file_level = INFO
log_file_format = %(asctime)s [%(levelname)8s] %(message)s (%(filename)s:%(lineno)s)
log_file_date_format=%Y-%m-%d %H:%M:%S
asyncio_default_fixture_loop_scope=session
asyncio_mode=auto

markers =
    dev: test
    stage: test
    dependency: dependency_test
    asyncio: asyncio_request

addopts =
    --reruns=2
"""
            ),
            RootFile(
                name="README.md",
                content="""# Autotests Project

Generated project for API testing based on Swagger specifications.
"""
            ),
            RootFile(
                name="Dockerfile",
                content="""FROM python:3.10-alpine

ARG run_env
ARG run_domain
ENV env $run_env
ENV domain $run_domain

LABEL "channel"="Test"
LABEL "Creator"="Test"

WORKDIR ./usr/corp-test-stable
COPY . .

RUN apk update && apk upgrade && apk add bash
RUN pip3 install -r requirements.txt

CMD pytest --domain "$domain" -m "$env" --verbose -o junit_family=xunit2 --junitxml=reports\\pytest\\result.xml -s src/tests/*
"""
            ),
            RootFile(
                name="conftest.py",
                content="""import time
import pytest
from partest import ApiClient, call_storage
from src.models.collections.collections_manager import ModelsManager



def pytest_addoption(parser):
    parser.addoption("--domain", action="store", default="http://url.ru")

@pytest.fixture(scope="session")
def domain(request):
    return request.config.getoption("--domain")

@pytest.fixture(scope="session")
def api_client(domain):
    return ApiClient(domain=domain, verify=False)

def pytest_make_parametrize_id(config, val):
    return repr(val)

@pytest.fixture(autouse=True)
def slow_down_tests():
    yield
    time.sleep(0)


@pytest.fixture(scope='session', autouse=True)
def clear_call_data():
    global call_count, call_type
    call_storage.call_count.clear()
    call_storage.call_type.clear()
    yield
    
@pytest.fixture(scope="session")
def models(auth_token: str):
    return ModelsManager(token=auth_token)
"""
            ),
            RootFile(
                name=".gitignore",
                content="""### Python template .gitignore
__pycache__/
*.py[cod]
*$py.class

*.so


.Python
.pytest_cache
env/
reports/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
*.egg-info/
.installed.cfg
*.egg
allure-reports
allure-results

*.manifest
*.spec

pip-log.txt
pip-delete-this-directory.txt

htmlcov/
.tox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*,cover
.hypothesis/

*.mo
*.pot

*.log
local_settings.py

instance/
.webassets-cache

.scrapy

docs/_build/

target/

.ipynb_checkpoints
.python-version
celerybeat-schedule
.env
venv/
ENV/
.spyderproject
.ropeproject
[Bb]in
[Ii]nclude
[Ll]ib
[Ll]ib64
[Ll]ocal
[Ss]cripts
pyvenv.cfg
.venv
pip-selfcheck.json
Pipfile
Pipfile.lock

# Навсяк (малоли что добавлять буду), чтоб незабыть.
.idea/
.idea/**/workspace.xml
.idea/**/tasks.xml
.idea/**/usage.statistics.xml
.idea/**/dictionaries
.idea/**/shelf
.idea/**/aws.xml
.idea/**/contentModel.xml
.idea/**/dataSources/
.idea/**/dataSources.ids
.idea/**/dataSources.local.xml
.idea/**/sqlDataSources.xml
.idea/**/dynamic.xml
.idea/**/uiDesigner.xml
.idea/**/dbnavigator.xml
.idea/**/gradle.xml
.idea/**/libraries
cmake-build-*/
.idea/**/mongoSettings.xml
*.iws
out/
.idea_modules/
atlassian-ide-plugin.xml
.idea/replstate.xml
.idea/sonarlint/
com_crashlytics_export_strings.xml
crashlytics.properties
crashlytics-build.properties
fabric.properties
.idea/httpRequests
.idea/caches/build_file_checksums.ser
__pycache__
api_reference.json
"""
            )
        ]

    def get_files(self):
        """Return the list of root files."""
        return self.files

    def add_file(self, name: str, content: str):
        """Add a new root file to the container."""
        self.files.append(RootFile(name, content))

    def get_file_by_name(self, name: str):
        """Retrieve a root file by its name."""
        for file in self.files:
            if file.name == name:
                return file
        return None

    def update_file_content(self, name: str, new_content: str):
        """Update the content of an existing root file."""
        for file in self.files:
            if file.name == name:
                file.content = new_content
                return True
        return False