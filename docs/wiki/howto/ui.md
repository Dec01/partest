---
title: UI quickstart (partest[ui])
status: current
verified: 2026-09-07
sources: [partest/ui/__init__.py, partest/ui/base_page.py, partest/ui/page_monitor.py, partest/ui/visual.py, partest/ui/capture_baselines.py, partest/ui/hooks.py]
audience: user
ships_in_wheel: true
---

# UI quickstart (`partest[ui]`)

Time-to-first health assert target: **&lt; 45 minutes**.

## Install

```bash
pip install 'partest[ui]'
playwright install chromium
```

## Sync vs async

| Class | Playwright | Methods |
|-------|------------|---------|
| **`BasePage`** (default) | **sync** (pytest-playwright) | `goto`, `expect_visible` — **no await** |
| **`AsyncBasePage`** | async API | `await goto`, `await expect_visible` |

## Isolation rules

| Do | Don't |
|----|-------|
| Separate `src/ui/conftest.py` | Import `confpartest` swagger loaders in UI |
| `FRONTEND_URL` env | Load OpenAPI / TokenManager session for pure UI |
| `partest.ui` only for harness | Put product page objects in the library |

**Guarantee:** `import partest.ui` does not import coverage storage or confpartest.

```bash
pytest src/ui/tests -q   # must not hit swagger download
```

## Minimal smoke (sync)

```python
from partest.ui import BasePage, PageMonitor, assert_page_healthy

def test_home(page, frontend_url):
    mon = PageMonitor.attach(page, spa_base_url=frontend_url)
    base = BasePage(page, frontend_url)
    base.goto("/")
    base.expect_visible(base.by_test_id("app-shell"))  # product testid
    assert_page_healthy(page, require_app_shell=True)
    mon.finalize(require_app_shell=True)
```

## Scaffold

The generated UI tree comes from the separate `partest-gen` package (`pip install partest-gen`):

```bash
partest-gen init-ui ./my-suite --force
# or
partest-gen from-openapi ./my-suite --file openapi.yaml --depth p1 --with-ui --force
```

## PageMonitor

```python
from partest.ui import PageMonitor, attach_monitor, get_monitor

mon = attach_monitor(
    page,
    spa_base_url=frontend_url,
    api_base_url=os.getenv("BASE_URL", ""),
    record_all_http_errors=True,  # False = asset/API 5xx only
)
mon.add_ignore_urls("cdn.example.com")
# after navigation:
mon.reset()  # clear before intentional 404 probe
```

Aliases: `network_issues` == `network_errors`; legacy attr `_aqa_monitor` set.

## Covering a ticket item

A UI ticket item is not covered by replaying it once. Five columns, and the answer to
each is a separate test or an explicit "not applicable":

| Column | The question |
|---|---|
| **Happy** | the item works as written, for the role it was written for |
| **Negative** | invalid input, a rejected action, a server error — the screen says so and stays usable |
| **Boundary** | empty list, one element, many; the longest allowed value; the earliest and latest date |
| **Side-effect** | what the action changed is visible where it should be, and nowhere it should not |
| **Close** | after the action the screen returns to a sane state: dialog closes, list refreshes, nothing stays spinning |

Skipping **Close** is the most common gap and the most user-visible: an action that
succeeds but leaves a modal open or a stale list reads as broken regardless of what the
API did.

These columns are **not** API test-case types. Do not record them as `request_*` and do
not expect them in `coverage.json` — that file is about HTTP operations. Track them on
the ticket, next to the acceptance criteria.

### Assert a state, not a pixel and not a presence

```python
# not enough: the element exists
page.expect_visible("[data-testid=order-status]")

# what the item actually claims
page.expect_text("[data-testid=order-status]", "Cancelled")
```

"An element is visible" passes on a screen that renders a stale value. Assert the value,
the count, the enabled state — whatever the ticket item promises.

For the **Side-effect** column, prefer asking the API rather than looking at another
screen: a UI action followed by an API read of the same id is the cheapest honest proof
that something really changed. That combination is what makes a test end to end —
see [[howto/layers]].

Selectors, page objects, scenes and reference images stay in the project. The library
supplies the harness; what your screens look like is yours.

## Visual baselines

```bash
python -m partest.ui.capture_baselines \
  --out src/ui/baselines/reference \
  --scenes src/ui/tools/scenes.example.json \
  --only home \
  --dry-run
```

Default capture is **sync** Playwright. Pass `--async` for the 1.4 async API.

Hooks (`login`, `prepare`, `hide_selectors`) stay in the **consumer** — library has no Keycloak walk and no product CSS selectors.

```python
from partest.ui import (
    compare_images,
    inject_freeze_styles_sync,
    wait_ready_for_screenshot_sync,
)

inject_freeze_styles_sync(page)
wait_ready_for_screenshot_sync(page, hide_selectors=["[data-testid=app-loader]"])
r = compare_images(ref, actual, name="home", diff_output="diff/home.png")
assert r.ok, r.summary()
```

## Plugin / PageMonitor hooks

```python
# src/ui/conftest.py
pytest_plugins = ["partest.ui.pytest_plugin"]
```

Markers are registered. Autouse attach/finalize is **off** unless
`PARTEST_UI_MONITOR=1` or `--partest-ui-monitor`.

```python
from partest.ui import attach_page_monitor, finalize_page_monitor, resolve_frontend_url

url = resolve_frontend_url(request.config)  # --frontend-url → FRONTEND_URL
mon = attach_page_monitor(page, spa_base_url=url)
...
finalize_page_monitor(page, test_failed=..., require_app_shell=True)
```

## Auth inject (optional)

```python
from partest.ui import set_auth_token_storage
await set_auth_token_storage(page, access_token, key="access_token")
```

Key names are **product-specific** — not hardcoded in library.

## Plugin

UI markers: enable `pytest_plugins = ["partest.ui.pytest_plugin"]` in UI conftest
(does not load API coverage plugin).

API dual-hook opt-out still: `PARTEST_PYTEST_PLUGIN=0`.
