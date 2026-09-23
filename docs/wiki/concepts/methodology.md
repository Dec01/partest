---
title: Coverage methodology — two areas, three axes each
status: current
verified: 2026-09-23
sources: [partest/methodology/__init__.py, partest/methodology/api/subtypes.py, partest/methodology/api/matrix.py, partest/methodology/api/steps.py, partest/methodology/api/inference.py, partest/methodology/api/classifier.py, partest/test_types.py, partest/methodology/ui/surfaces.py, partest/methodology/ui/checks.py, partest/methodology/ui/matrix.py, partest/methodology/ui/steps.py]
audience: agent
ships_in_wheel: true
---

# Coverage methodology

partest does not measure coverage as "an endpoint was called once". It measures whether the
**required set of test cases for that kind of thing** exists.

There are **two areas**, and they are separate packages with the same shape:

| Area | Import | Axis A — what this is | Axis B — what is checked | Axis C — how deep |
|---|---|---|---|---|
| API | `partest.methodology.api` | method subtype | test-case type | status → schema → value |
| UI | `partest.methodology.ui` | surface type | check family | visible → value → survives reload → baseline |

`partest.methodology` re-exports both, so `from partest.methodology import …` keeps working for
every name it ever exported. The submodules moved, though — `partest.methodology.subtypes` is now
`partest.methodology.api.subtypes`, and the rest with it. Old and new paths side by side:
[[howto/migration]].

**One difference between the areas is structural, not a gap.** The API half derives axis A from
the OpenAPI specification, so it has a classifier and type inference. No project ships a
machine-readable description of its screens, so **the UI half has neither**: the surface type is
declared by the consumer, next to its own page object. Deriving it from markup is not attempted —
a wrong guess silently swaps in the required set of a different kind of screen.

---

# API methodology

## Axis A — method subtype

What kind of operation this is, derived from HTTP method + path shape. Not "POST", but
"POST that creates a child under a parent" vs "POST that runs an action" vs "POST that filters
a list" — because each has a different risk profile and therefore a different required TC set.

Canonical list: `MethodSubtype` in `partest/methodology/api/subtypes.py` — 11 classic subtypes
(GET static/dynamic/list, POST create/upload/create-to-object/filter, PATCH object/elem, PUT,
DELETE) plus operational specializations (`get_by_parent`, `get_by_self`, `delete_physical`,
`delete_soft`, `delete_blocked`, `action`, `get_external_id`).

Assignment is done by `classify_endpoint` (`partest/methodology/api/classifier.py`). The classifier
is a heuristic over method + path segments; it is the part most likely to be wrong on an unusual API.

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

`partest/methodology/api/matrix.py` maps every subtype to a priority per TC type:
`P1` (implement first) · `P2` · `P3` · `NA` (not applicable).

**The matrix is the source of truth, not this page.** Do not copy it into documentation — it
changes, and a copy silently goes wrong. Read it, or call the API:

```python
from partest.methodology import p1_test_cases, required_test_cases
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
`partest/methodology/api/steps.py`.

## Type inference and why `type=` still matters

`partest/methodology/api/inference.py` can guess the TC type from the request/response, but it is
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
see [[howto/permissions]].

---

# UI methodology

Same three axes, and nothing in it is derived automatically. It is a vocabulary plus a matrix:
the library says which checks a kind of screen owes, the suite says which screen it is looking at.

## Axis A — surface type

`SurfaceType` in `partest/methodology/ui/surfaces.py`. Six types and an `UNKNOWN` fallback, and a
type is in the list only because it **changes the required set of checks**:

| Surface | What makes it its own type |
|---|---|
| `LIST_TABLE` | the only surface with a column set, sorting, paging and user-configured view state |
| `EDIT_FORM` | submits input; permissions branch into read-only vs editable |
| `ENTITY_CARD` | read-only single object: no submit, nothing to configure |
| `NAV_SHELL` | the chrome; the menu is where a role's surface area is visible |
| `MODAL` | cannot survive a reload, and its permission to open belongs to the parent surface |
| `REPORT_VIEW` | aggregates and charts: an empty period is normal input, and pixels are the only readable assertion |

**Declare it, next to the page object:**

```python
from partest.methodology import SurfaceType, required_checks

class ClientsPage(BasePage):
    surface = SurfaceType.LIST_TABLE

required_checks(ClientsPage.surface)     # what this kind of screen owes
```

A screen that is two of these at once (a list inside a dialog) is two surfaces; declare the one
whose checks you are writing. A surface left `UNKNOWN` is required to do exactly one thing —
render — which is not a usable plan and is not meant to be one.

There is no `classify_surface`, and a test asserts there is no name like it in the package. The
API classifier is only possible because a specification exists; a screen-shape guesser would have
the same failure mode with none of the evidence.

## Axis B — check families

`UiTestCases` in `partest/methodology/ui/checks.py`:

`screen_render` · `screen_submit` · `screen_filter` · `screen_sort` · `screen_columns` ·
`screen_paging` · `screen_state_persistence` · `screen_permissions` · `screen_empty_state` ·
`screen_error_state` · `screen_visual`

The list is short on purpose: a family is here because suites write it, not because it sounds
plausible. Several checks a suite writes separately are one family here — a filter by date and a
filter by status are both `screen_filter`.

**`screen_state_persistence` is why this axis exists.** Every other family describes one load of a
screen, so "the filter the user set is still set after a reload" had nowhere to live. The defect it
catches — view state stored nowhere, or stored and never read back — is invisible to a suite that
starts each test from a clean browser profile, which is every suite.

`screen_submit` is the one family not taken straight from practice: the others all describe
*presenting* data, and without it a create/edit form and a read-only card require the same checks,
which by axis A's own rule would mean one of the two is not a type. A form and a card are not the
same surface, so the missing family was the defect.

## Axis A × B — the UI matrix

`partest/methodology/ui/matrix.py`, the same `CoveragePriority` as the API side — the same object,
re-exported from `partest.methodology.ui` as well, because P1 means "implement first" in both areas
and two enums with identical members would only make a report pick one at random. The rule for
filling this table is the opposite of completeness:

> a cell nobody can justify is `NA`, not "probably P2".

On the API side priorities come from a written methodology. Here the only justification available is
"suites write this, and it finds defects" — so more than half the table is `NA`, every non-`NA` cell
carries its reason on its line in the source, and the tempting empty ones are marked as deliberately
empty. `NA` is a statement about the evidence, not a ban: a project that knows its sidebar should
remember being collapsed tests it anyway. What it must not do is read a guess as a requirement.

```python
from partest.methodology import applicable_checks, p1_checks, priority_of, required_checks
```

`priority_of` raises on an unknown check name rather than answering `NA`, because `NA` reads as
"the methodology does not ask for this" and a typo must not be able to say that.

## Axis C — depth

`UiStep` in `partest/methodology/ui/steps.py`, in order:

1. `ELEMENT_VISIBLE` — the element is there.
2. `VALUE_CORRECT` — what it shows is right.
3. `SURVIVES_RELOAD` — it is still right after a reload of the same screen.
4. `MATCHES_BASELINE` — it matches an approved image.

`minimum_depth(check)` gives the shallowest step at which a family counts as covered: seeing a grid
is not a sorting test, and a value assert is not a persistence test. `MATCHES_BASELINE` is treated
as *different* evidence rather than deeper evidence — it satisfies `screen_visual` and nothing else,
because a screenshot that happens to contain sorted rows is not an assertion about sorting.

Related: [[concepts/coverage-honesty]] · [[howto/permissions]] · [[howto/ui]] · [[howto/reporting]] · [[howto/coverage-html]]
