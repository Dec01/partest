# partest

Methodology-driven **API (and optional UI) autotest harness** for Python, with OpenAPI coverage
that measures whether the *right* test cases exist — not just whether an endpoint was called.

```bash
pip install partest
pip install 'partest[ui]'     # + Playwright and Pillow for UI suites
```

## What you get

- **`ApiClient`** — async HTTP for suites: JSON, form, files, raw `content=`, multi-status
  expectations, GraphQL, and rich status-mismatch errors.
- **Coverage by methodology** — every operation is classified into a method subtype, and each
  subtype has a required set of test cases. The report tells you which cases are *missing*.
- **A UI methodology too** — surface types (list, form, card, shell, dialog, report), the check
  families each one owes, and the depth each check has to reach. The surface type is declared by
  your page object: nothing guesses it from markup.
- **A scaffold, if you want one** — [partest-gen](https://pypi.org/project/partest-gen/) is a
  separate package that writes a runnable suite straight from an OpenAPI file.
- **Reporting** — `check_*` helpers, Allure steps and attaches (Allure is a soft dependency),
  interactive HTML coverage, `coverage.json`, compare / badge / stub CLI.
- **Auth, tracking, security** — OIDC `TokenManager` with injected credentials, created-resource
  tracking with LIFO cleanup, `SecHttp` raw transport, JWT tampering sets, `RiskProfile`.
- **UI extra** — `BasePage`, `PageMonitor`, storage helpers, visual comparison, baseline capture.

## A first test

```python
from partest import ApiClient, TypesTestCases
from partest.zorro_report import zorro

types = TypesTestCases

async def test_get_item(api_client):
    """Item is returned by id."""
    await api_client.make_request(
        "GET",
        "/items/{id}",
        add_url1="/1",
        defining_url="/items/{id}",       # OpenAPI template — this is what coverage matches
        expected_status_code=200,
        validate_model=ItemValidation,
        type=types.request_default,       # explicit type beats inference
    )

def test_zorro():
    report = zorro()                      # Allure summary + coverage HTML
    # report.endpoints[*].missing_p1 → your backlog for the next test cases
```

## Scaffold a whole suite

The generator ships separately, as
[partest-gen](https://pypi.org/project/partest-gen/) — it runs once when a project is created
rather than on every test run, so it is not part of this install:

```bash
pip install partest-gen        # brings partest with it
partest-gen from-openapi ./my-suite --file openapi.yaml --depth p1 --with-ui
partest-gen sync-openapi ./my-suite --depth p1     # after the spec changes
```

`--depth resources` emits paths and collections, `default` adds payloads, validators and the
first tests, `p1` adds the full priority-one stub matrix plus a checklist per tag.

Upgrading from a version where the generator lived inside this package? `partest.project_gen`
still resolves once `partest-gen` is installed, and `pip install 'partest[gen]'` installs
both. The `partest-gen` command itself now comes from that package, not this one.

## Documentation

Source, issues and the full documentation wiki: **https://github.com/Dec01/partest**

The user-facing pages also ship **inside the package**, so they are readable next to your
installed copy without a trip to the browser:

```bash
python -m partest.docs list                  # what is available
python -m partest.docs show howto-quickstart # read a page
python -m partest.docs path                  # where the files live
```

Included: quickstart, migration notes, the coverage methodology, permissions, upload testing,
reporting, security, UI, recipes, layers, and enterprise notes (shared client, retries,
redaction, xdist). The decisions behind them — why coverage is scored this way, what stays in
your project — live in the repository, not the wheel.

Or from Python:

```python
from partest.docs import list_docs, read_doc
print(read_doc("concepts-methodology.md"))
```

## Requirements

Python 3.10+, with the suite run on 3.10 and 3.14. Core dependencies: `httpx`, `pydantic`, `pyyaml`, `pytest`, `pytest-asyncio`,
`allure-pytest`, `requests`, `python-dotenv`, `Faker`, `matplotlib`. The `ui` extra adds
`playwright` and `Pillow`.

**pytest 9 is required from 2.1.0 on** (`pytest>=9.0.3,<10`). The advisory that raised the
floor, `PYSEC-2026-1845`, has no fix in any 8.x release, so pytest 8 is not supported rather
than deprecated — stay on `partest 2.0.1` if you cannot move yet. The ceiling is there
because `partest` is a pytest plugin and loads in every session: it says pytest 9 was run
and pytest 10 was not, and it is lifted by a patch release once the suite passes on 10.

The bundled pytest plugin loads automatically and enriches Allure titles. Turn it off with
`PARTEST_PYTEST_PLUGIN=0`, `pytest_plugin = False` in `confpartest.py`, or `pytest -p no:partest`
if your project already owns Allure hooks.

## License

MIT.
