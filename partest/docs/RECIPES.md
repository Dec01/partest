# Recipes (consumer adapters)

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

## Resolve OpenAPI

```python
from partest.openapi import resolve_swagger, resolve_from_confpartest

spec = resolve_swagger("docs/openapi.yaml")
spec = resolve_swagger(["url", "https://api/v3/api-docs"], verify=False)
spec = resolve_from_confpartest(service="myservice")
```

## generate package exports

```bash
partest-gen init-package-exports src/api/resources -v
python -m partest.tools.generate_init -d src/api/resources
```

## Collections + HeadersBind (LIB-REC-CM)

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

## IncorrectBody transport set (LIB-REC-IB)

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

## Types (LIB-REC-TYPE)

Write **`type=types.request_default`**, not the string `"type_default"` and not the legacy value `"default"`.

`canonicalize_type("type_default")` → `request_default` (LIB-CANON) so old call_storage still scores. New tests should pass the canonical attribute.

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
