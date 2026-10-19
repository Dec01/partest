<!-- Part of the partest package: generated documentation, not hand-written.
     Read it with `python -m partest.docs`. Local edits are lost on upgrade. -->

# Recipes — consumer-side adapters

## Keycloak multi-role adapter

```python
# src/api/resources/rbac/roles.py  (consumer)
import os
ALL_ROLES = ("admin", "viewer")

def get_role_credentials(role: str):
    return os.environ[f"KC_USER_{role.upper()}"], os.environ[f"KC_PASS_{role.upper()}"]
```

```python
# conftest
from partest import TokenManager
from partest.env.profiles import keycloak_settings
from src.api.resources.rbac.roles import ALL_ROLES, get_role_credentials

@pytest.fixture(scope="session")
def token_manager():
    kc = keycloak_settings()
    return TokenManager(
        **kc.as_token_manager_kwargs(),
        credentials_provider=get_role_credentials,
        known_roles=ALL_ROLES,
        verbose=False,
    )
```

## Conflict hint provider (domain)

```python
def explain_entity_conflict(body: dict) -> str:
    # product-specific mapping — STAY in consumer
    ...
```

## Tracking nested ids

```python
from partest import TrackingApiClient, CreatedRegistry, nested_id_extractor, default_id_extractor

registry = CreatedRegistry()
api = TrackingApiClient(
    domain,
    registry,
    id_extractors=[
        nested_id_extractor("data", "id"),
        nested_id_extractor("result", "uuid"),
        default_id_extractor,
    ],
)
```

Cleanup 409 retries are built into `CreatedRegistry.cleanup`.

## Marker + DB cleanup contract

Library only marks data:

```python
from partest import marked_name, TEST_MARKER
name = marked_name("Client")  # contains TEST_MARKER
```

SQL delete-by-marker scripts **stay in consumer** (schema-specific).

### Required-only payloads still need the marker

`get_json_required()` sends the minimum the API accepts. If none of the required fields
happens to be the one carrying the marker, the created row is invisible to a
delete-by-marker cleanup and stays on the stand forever. Declare which fields to add:

```python
class RequestBody(BaseRequestBody):
    _json_main = {"buyUnit": "PCS", "name": marked_name("Item")}
    _required = ["buyUnit"]
    _cleanup_fields = ["name"]        # carries TEST_MARKER

RequestBody.get_json_required()          # {"buyUnit": "PCS"}
RequestBody.get_json_required_marked()   # {"buyUnit": "PCS", "name": "<TEST_MARKER> Item 1234"}
```

Opt-in: `_cleanup_fields` defaults to empty and `get_json_required` is unchanged.

## Cleanup that survives a failed validation

A create returns 201 with an id, then `validate_model` rejects the body because the
service added a field and the validator is `extra=forbid`. The test fails, correctly —
but the row exists, and until 1.6 nothing had registered it, so the session cleanup
never deleted it. Every new response field left a trail of orphans.

`TrackingApiClient` now registers the id as soon as the status is 2xx, before schema
validation runs. No configuration needed:

```python
api = TrackingApiClient(domain, registry)
# 201 + unexpected field → the test still fails, the id is still in the registry
```

Pass `track_before_validate=False` for the old ordering. If you carry a local overlay
that popped `validate_model` before calling `super()`, drop it.

### Draining per test instead of per session

```python
@pytest.fixture(autouse=True)
async def cleanup_created(registry, domain, token):
    mark = registry.snapshot()
    yield
    await registry.cleanup_since(mark, domain, token)
```

`snapshot()` records the current size, `cleanup_since(mark, ...)` deletes only what this
test created and forgets it, so the session pass does not retry it. `since(mark)` returns
the tail as a separate registry if you want to inspect it first.

### A resource that outlives the test that created it

Per-test draining has one trap: an object created *during* a test but meant for later
tests. A session-scoped cache filled lazily — by whichever test needs it first — creates
its object inside that test, `cleanup_since` deletes it at teardown, and every later test
receives a cached id that no longer exists.

Every registry entry has an **owner**. Nobody claims it — it belongs to the test, and
everything works as above. Claim it for a wider area and per-test cleanup leaves it alone:

```python
async def shared_item(api, registry):
    if _cache.get("item") is None:                 # the first test to need it pays for it
        with registry.owned_by("session"):         # or api.owned_by("session")
            _cache["item"] = await api.make_request(
                "POST", "/items", json_data=body, expected_status_code=201,
                type=types.request_new_object,
            )
    return _cache["item"]
```

- `owned_by(owner)` — a context manager; whatever this registry tracks inside the block,
  including ids `TrackingApiClient` registers from responses, belongs to `owner`. The claim
  lives in a context variable: a concurrent task outside the block is not affected, and
  another registry is not affected.
- `adopt(resource_id, owner, endpoint=None)` — claim after the fact, when the id is known
  only once the create returned. Returns how many entries moved. With nothing tracked under
  that id it tracks it (given `endpoint=`) or raises `LookupError` — a claim that silently
  did nothing would let the per-test cleanup delete what you believe is protected.
  `owner=None` hands it back to the test.
- `track(endpoint, id, owner=...)`, `owner_of(endpoint, id)` and `owned(owner)` (a registry
  of one owner's entries) for the rest.

**Claim the parents with the resource.** Wrap the whole chain of creates in `owned_by`, not
only the last call — it is the form that cannot miss a parent; with `adopt`, adopt each one.
The two orders behave differently:

| Parent | Child | After per-test cleanup |
|---|---|---|
| test | claimed | **broken.** The parent is deleted; the service either cascades the delete to the child — the cache now holds an id that is gone — or refuses it with 409 because a child exists, and the parent's delete is retried, given up and left on the stand |
| claimed | test | fine: the children go after each test, the parent stays for its area |
| claimed | claimed | fine: both stay, and their area's cleanup removes them child-first (LIFO) |

**Do not hold `owned_by` across the `yield` of an async fixture.** pytest-asyncio may run the
teardown half of a fixture in a different context from its setup, and a context-variable claim
cannot be undone there — partest reports it as a `RuntimeError` instead of the bare
`ValueError` from `contextvars`. Claim around the creating calls only, or record the owner
directly:

```python
@pytest.fixture(scope="module")
async def shared_folder(registry, api, domain, token):
    with registry.owned_by("module-folders"):          # setup only — the block ends here
        folder = await api.make_request("POST", "/folders", json_data=body,
                                        expected_status_code=201, type=types.request_new_object)
    yield folder
    await registry.cleanup_owned("module-folders", domain, token)
```

Who cleans up what:

| Call | Removes |
|---|---|
| `cleanup_since(mark, ...)` | what the test owns after `mark`; claimed entries stay, in order |
| `cleanup_owned(owner, ...)` | everything `owner` owns, wherever it sits — the teardown of a module or class area |
| `cleanup(...)` | everything — the session pass, unchanged. The id goes into the DELETE path as one encoded segment; a blank id is never sent. A `delete_builder=` gets the id as the service sent it and encodes it itself — `urllib.parse.quote(str(rid), safe="")`; an absolute URL on another host from it takes the auth header there |

The owner is any hashable: `"session"`, `("module", request.module.__name__)`. A module-level
area claims with its key and drains in its own teardown:

```python
@pytest.fixture(scope="module", autouse=True)
async def module_area(request, registry, domain, token):
    key = ("module", request.module.__name__)
    yield key                                      # tests create with registry.owned_by(key)
    await registry.cleanup_owned(key, domain, token)
```

`snapshot()` marks are positions, so call `cleanup_owned` at the end of its area, not inside
a test that is still holding a mark.

`TEST_OWNER` (`None`, importable from `partest`) is the owner of everything nobody claimed.

## Resolve OpenAPI

```python
from partest.openapi import resolve_swagger, resolve_from_confpartest

spec = resolve_swagger("docs/openapi.yaml")
spec = resolve_swagger(["url", "https://api/v3/api-docs"], verify=False)
spec = resolve_from_confpartest(service="myservice")
```

## generate package exports

```bash
python -m partest.tools.generate_init -d src/api/resources
partest-gen init-package-exports src/api/resources -v   # same thing, needs partest-gen
```

## Collections + HeadersBind

```python
from partest import CollectionsManager, Config
from partest.collections import BaseCollection
from partest.http import HeadersBind

class ItemsCollection(BaseCollection):
    def __init__(self):
        self.headers = Config().headers_bind(["Accept", "X-Request-ID"])

mgr = CollectionsManager(items=ItemsCollection())
mgr.apply_token(token)  # refreshes every named collection
```

## IncorrectBody transport set

```python
import pytest
from partest.validation import RAW_INCORRECT_BODY_CASES, assert_raw_incorrect_body

@pytest.mark.parametrize("content, content_type, expected", RAW_INCORRECT_BODY_CASES)
async def test_create_raw_rejected(api_client, models, content, content_type, expected):
    await assert_raw_incorrect_body(
        api_client,
        "POST",
        models.items.paths.items,
        models.items.headers.write,
        content=content,
        content_type=content_type,
        expected_status_code=expected,
        defining_url="/items",
    )
```

Keep these on **ApiClient** (`content=`), never raw httpx — otherwise coverage misses the call.

## Which type= for which call

A rich suite can produce a full-looking matrix or a hollow one depending entirely on
what each call declares. Test names and Allure stories do not reach the matrix — only
`type=` does. The classic hole: a fixture's setup POST records as `request_default` for
the create endpoint, so the endpoint looks covered while nothing tested creation.

| The call | `type=` |
|---|---|
| your POST inside `test_create_..._success` | `request_default` |
| a fixture or helper seeding data | `request_new_object` |
| a POST CREATE endpoint at P1 | **both** cells: Default *and* NewObject |
| the first happy PUT | `request_default` |
| a second PUT changing a field | `request_update_object` |
| a happy DELETE | `request_default` on the DELETE itself |
| GET or DELETE with an unknown id | `request_not_found` |
| repeated DELETE, or a soft-cancel cleanup | `request_lifecycle_delete` |
| the setup POST inside a delete test | `request_new_object` |
| all four access cells | `request_permissions` |

The rule behind the table: record what the call **proves**, not which test it happens to
sit in. A seed proves that creation works, wherever it runs.

## Types

Write **`type=types.request_default`**, not the string `"type_default"` and not the legacy value `"default"`.

`canonicalize_type("type_default")` → `request_default` so old call_storage still scores. New tests should pass the canonical attribute.

## Monorepo API + UI

```text
requirements/{base,api,ui}.txt
src/api/…   # partest coverage + TokenManager
src/ui/…    # partest[ui] only; isolated conftest
```

```bash
pytest src/api/tests -q
pytest src/ui/tests -q   # no swagger
```

## Problem Detail / custom error body

`validate_model=` takes a validator **instance**: `ApiClient` calls `validate_error(body)` on it
for a non-2xx status and `validate_success(body)` for a 2xx one.

```python
from partest.validation import ProblemDetailValidation

# RFC 9457 core: detail, instance, status, title, optional type — any other member fails
await api.make_request(..., expected_status_code=400, validate_model=ProblemDetailValidation())
```

`ProblemDetailBody` forbids members it does not declare (`extra="forbid"`), and RFC 9457 lets an
API add its own. Declare the ones your API sends — the rest still fail. A member that appears
is caught; one that disappears is caught only if you declare it required:

```python
from typing import Optional
from partest.validation import ProblemDetailBody, ProblemDetailValidation

class OrderProblem(ProblemDetailBody):
    code: str                       # required extension
    retry_after: Optional[int] = None

validate_model=ProblemDetailValidation(OrderProblem)
```

The common shape — a top-level `code` and per-field `errors[]` — is ready-made:

```python
from partest.validation import ProblemDetailValidation, ProblemDetailWithErrors

validate_model=ProblemDetailValidation(ProblemDetailWithErrors)
# {"detail": …, "instance": …, "status": 400, "title": …,
#  "code": "VALIDATION_FAILED",
#  "errors": [{"field": "name", "code": "required", "message": "must not be blank"}]}
```

| Member | Rule in `ProblemDetailWithErrors` |
|---|---|
| `code` | optional; string or integer |
| `errors` | optional; a list of `ProblemDetailErrorItem` — a body **without** `errors` passes |
| element `detail`, `pointer` | optional strings — the element shape RFC 9457 §3 shows: `{"detail": "must be a positive integer", "pointer": "#/age"}` |
| element `field`, `code`, `message` | optional; typed (`code` string or integer) |
| other keys in an element | **rejected** (`extra_forbidden`) — with every element field optional, this is what notices `field` renamed to `fieldName` |
| any other top-level member | **rejected** (`extra_forbidden`) |

The RFC 9457 §3 example itself fails on its top level, not on its elements: it has no
`detail`, `instance` or `status`, which `ProblemDetailBody` requires and the RFC does not.

Both extensions are optional, so their disappearance is not caught. If the endpoint must return
`errors`, or `code`, declare it required in a subclass. Element keys beyond those five differ
between APIs (`rejectedValue` …): declare yours in a subclass of the element:

```python
from typing import List, Optional, Union
from partest.validation import ProblemDetailErrorItem, ProblemDetailWithErrors

class RejectedItem(ProblemDetailErrorItem):
    rejectedValue: Optional[Union[str, int]] = None   # {"field": "age", "rejectedValue": -1}

class ApiProblem(ProblemDetailWithErrors):
    code: str                            # required: its absence fails
    errors: List[RejectedItem]           # required: a missing list fails
```

An element that should take anything can be opened with
`model_config = ConfigDict(extra="allow")` in the subclass; the extra keys land in
`item.model_extra`. The top level stays closed either way.

A body that fails reads: the model, the number of errors, one `path [type]: message` line per
error without the value; for the first five errors below the top level, the object holding the
failing member (`in …`, at most 200 characters), because it often lies beyond the cut of the
body; then the body. Bodies and parents are masked by key (`token`, `password`, `secret` …) and
shortened. Against `ProblemDetailWithErrors`:

```text
Response data validation failed for ProblemDetailWithErrors (2 errors):
  errors.0.rejectedValue [extra_forbidden]: Extra inputs are not permitted
    in errors.0 = {"field": "age", "message": "must be positive", "rejectedValue": -1}
  token [extra_forbidden]: Extra inputs are not permitted
Response body: {"detail": "Validation failed", "instance": "/orders", "status": 400, "title": "Bad Request", "token": "***", "errors": [{"field": "age", "message": "must be positive", "rejectedValue": -1}]}
```

The same masking holds in every other channel: the pytest traceback (the
`AssertionError` carries no chained pydantic error, so no `input_value=`; the error list is on
it as `validation_errors` — `loc`, `type`, `msg` per error), the stdout of
`PydanticResponseError.print_error` (the rejected value is described by its type only), the
INFO request/response log, the status-mismatch message and the Allure attachments — see
[Enterprise notes — shared client, retries, redaction, xdist](howto-enterprise.md). A value under a key the masking does not know is shown as is.

On a 409, `ErrorTemplates.conflict_409` prints the Problem Detail summary — `status`, `title`,
`detail`, `type`, `instance`, `code`, `message`, `error`, `errors` — whatever the model.

An error body that is not a Problem Detail at all gets its own validator:

```python
from partest.validation import BaseModelWithConfig, BaseResponseValidator

class MyErrorBody(BaseModelWithConfig):
    code: str
    message: str

class MyErrorValidation(BaseResponseValidator):
    @property
    def ResponseSuccessBody(self):
        return MyErrorBody

validate_model=MyErrorValidation()
```
