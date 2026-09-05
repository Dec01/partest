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
- **`partest-gen`** — scaffold a runnable pytest monorepo suite straight from an OpenAPI file.
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

```bash
partest-gen from-openapi ./my-suite --file openapi.yaml --depth p1 --with-ui
partest-gen sync-openapi ./my-suite --depth p1     # after the spec changes
```

`--depth resources` emits paths and collections, `default` adds payloads, validators and the
first tests, `p1` adds the full priority-one stub matrix plus a checklist per tag.

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

Python 3.9+. Core dependencies: `httpx`, `pydantic`, `pyyaml`, `pytest`, `pytest-asyncio`,
`allure-pytest`, `requests`, `python-dotenv`, `Faker`, `matplotlib`. The `ui` extra adds
`playwright` and `Pillow`.

The bundled pytest plugin loads automatically and enriches Allure titles. Turn it off with
`PARTEST_PYTEST_PLUGIN=0`, `pytest_plugin = False` in `confpartest.py`, or `pytest -p no:partest`
if your project already owns Allure hooks.

## License

MIT.
