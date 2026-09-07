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

```python
from partest.validation import ProblemDetailValidation, BaseResponseValidator

# RFC7807 preset
await api.make_request(..., expected_status_code=400, validate_model=ProblemDetailValidation)

# custom consumer validator
class MyErrorValidation(BaseResponseValidator):
    class ResponseErrorBody(BaseModelWithConfig):
        code: str
        message: str
```
