<!-- Part of the partest package: generated documentation, not hand-written.
     Read it with `python -m partest.docs`. Local edits are lost on upgrade. -->

# Coverage methodology

partest does not measure coverage as "an endpoint was called once". It measures whether the
**required set of test cases for that kind of endpoint** exists. Three axes define that set.

## Axis A — method subtype

What kind of operation this is, derived from HTTP method + path shape. Not "POST", but
"POST that creates a child under a parent" vs "POST that runs an action" vs "POST that filters
a list" — because each has a different risk profile and therefore a different required TC set.

Canonical list: `MethodSubtype` in `partest/methodology/subtypes.py` — 11 classic subtypes
(GET static/dynamic/list, POST create/upload/create-to-object/filter, PATCH object/elem, PUT,
DELETE) plus operational specializations (`get_by_parent`, `get_by_self`, `delete_physical`,
`delete_soft`, `delete_blocked`, `action`, `get_external_id`).

Assignment is done by `classify_endpoint` (`partest/methodology/classifier.py`). The classifier is
a heuristic over method + path segments; it is the part most likely to be wrong on an unusual API.

A wrong subtype does not fail anything — the endpoint just gets the required test-case set of some
other kind of operation, and the coverage number is confidently wrong. When you spot one, say so
explicitly in `confpartest.py`:

```python
subtype_overrides = {
    "POST /orders/{id}/lines": "action",       # not a create under a parent
    "GET /reports/summary": "get_static_object",
}
# or a YAML file:
subtype_overrides = "src/api/resources/coverage/subtypes.yaml"
```

Routes match by shape, so `{id}` and `{orderId}` are the same route. An unknown subtype or a
malformed key raises at load time rather than being ignored — an override that silently does
nothing is indistinguishable from the misclassification it was written to fix.

## Axis B — test-case type

What is being checked. Canonical names live in `TypesTestCases`
(`partest/test_types.py`): `request_default`, `request_permissions`, `request_new_object`,
`request_update_object`, `request_incorrect_body`, `request_elements`, `request_extra_data`,
`request_not_found`, `request_not_allowed`, `request_params`, `request_env_list`,
`request_compare_benchmark`, …

Legacy aliases (`default`, `405`, `elem`, `type_default`, …) still resolve via
`canonicalize_type`. Write canonical names in new code.

## Axis A × B — the matrix

`partest/methodology/matrix.py` maps every subtype to a priority per TC type:
`P1` (implement first) · `P2` · `P3` · `NA` (not applicable).

**The matrix is the source of truth, not this page.** Do not copy it into documentation — it
changes, and a copy silently goes wrong. Read it, or call the API:

```python
from partest.methodology import required_p1, priority_of
```

Shape of it, as orientation only:

| Subtype | typical P1 set |
|---|---|
| GET STATIC | Default + Benchmark |
| GET DYNAMIC | Default + Permissions + NotFound |
| GET LIST | Default + Permissions |
| POST CREATE | Default, Permissions, NewObject, IncorrectBody, Elements, ExtraData |
| PUT / PATCH | Default, Permissions, UpdateObject, IncorrectBody, Elements, ExtraData, NotFound |
| DELETE | Default, Permissions, NotFound |

## Axis C — assertion depth

Per test case, in order: **status → schema (`validate_model`) → values**.

Status-only is not coverage for Default, Elements or Benchmark cases. A test that asserts `200`
and nothing else passes while the payload is empty. Steps are described in
`partest/methodology/steps.py`.

## Type inference and why `type=` still matters

`partest/methodology/inference.py` can guess the TC type from the request/response, but it is
**high-confidence only** for three situations: `405` not-allowed, `404` not-found, and a
deliberately broken raw body. Everything else — permissions, new/update object, elements,
extra data, env lists, benchmarks — is ambiguous from the wire alone.

Rule: pass `type=` explicitly. Explicit always wins over inference. Do not remove `type=` from
existing tests to "let inference handle it".

## What "100% covered" means here

The required P1 set for the endpoint's subtype is present, with correct `type=`, and each case
asserts to the depth axis C requires. A file existing, or a call being made, is not coverage.

`request_permissions` deserves special mention: it is one type covering four security layers
(allowed, foreign object, disabled account, no session). One 401 is not the type covered —
see [Permissions — four cells, not one 401](howto-permissions.md).

Related: [Coverage honesty — when the number lies](concepts-coverage-honesty.md) · [Permissions — four cells, not one 401](howto-permissions.md) · [Reporting cookbook — checks, steps, attaches](howto-reporting.md) · [Interactive coverage report and CLI](howto-coverage-html.md)
