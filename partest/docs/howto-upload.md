<!-- Part of the partest package: generated documentation, not hand-written.
     Read it with `python -m partest.docs`. Local edits are lost on upgrade. -->

# Testing file upload endpoints

## Two loops, and the cost of mixing them

| Loop | Where | What it catches |
|---|---|---|
| **Gate** | the synchronous HTTP response | empty file, extension, MIME, size, part name, parent id, authentication |
| **Pipeline** | a worker, an object store, a broker | broken archive, wrong column layout, entities actually persisted |

```text
client --multipart--> API gate --201--> object store
                           \--event--> worker --> persisted rows
```

A 201 from the gate is **not** "the file was imported". A 400 on a `.txt` is **not**
"the parser rejected the columns". Most wasted effort on upload endpoints comes from
one test trying to prove both.

This page covers the gate. For the pipeline, assert the **response contract** first —
status value in its enum, locator prefix, reported size matching what you sent — and
only reach into the store or the broker when you actually have credentials for them.
Without them, mark the step held with a reason; do not skip the whole endpoint.

## Required cases

An upload endpoint is a `post_upload_file` subtype, and its P1 set is not one happy
path:

| Cell | Cases |
|---|---|
| `request_default` | your own POST of a valid file, not a fixture side effect |
| `request_new_object` | a second accepted format |
| `request_compare_benchmark` | reported size equals what you sent; status in its enum; locator prefix |
| `request_elements` | empty; no file part; missing required form or query field; formats; name mutations; parent id |
| `request_incorrect_body` | JSON instead of multipart; raw `content=` with a foreign content type |
| `request_extra_data` | an extra form field or a second part — should not become a 4xx |
| `request_permissions` | four cells, and the unauthenticated one on a **write** — see [Permissions — four cells, not one 401](howto-permissions.md) |
| `request_not_found` | unknown parent id |
| `request_not_allowed` | GET/PUT/DELETE when the API is POST-only |

Cells that genuinely do not apply — no read-by-id endpoint, for instance — belong in
the suite marked as not applicable, not quietly missing.

## The corpus

```python
from partest.files import mutation_cases, minimal_xlsx_bytes

@pytest.mark.parametrize("case", mutation_cases("report"), ids=lambda c: c.id)
async def test_upload_gate(api_client, case, parent_id):
    """Upload gate accepts or rejects a mutated file."""
    expected = {"accept": 201, "reject": (400, 415)}.get(case.gate_expect)
    if expected is None:
        pytest.skip(f"{case.id}: establish the fact for this API first")
    await api_client.make_request(
        "POST", "/imports",
        add_url1=f"/{parent_id}",
        files=case.files_kwarg,
        expected_status_code=expected,
        type=types.request_elements,
    )
```

Files are generated, never committed — real workbooks carry real data. Only the
standard library is involved.

### `gate_expect` has three values, and the third one matters

`accept` and `reject` are what a working gate should do. **`fact`** means the answer
genuinely depends on the product: a gate that checks only the extension will happily
accept a PNG named `.xlsx`, and that is a legitimate design when a downstream parser
does the real validation.

For those cases: find out what your API does, write the assertion down, and say in the
report that this covers the gate rather than the parser. Do not guess a status code,
and do not file a bug purely because the gate is extension-only. If the product
genuinely must reject non-Excel at upload, that is `xfail(strict=True)` with a bug
reference — never a permanent skip.

What the corpus deliberately does not contain: zip bombs, exploit payloads, macros with
a payload. A corpus that can take a stand down is not a test corpus.

## Multipart specifics

```python
# not multipart at all → IncorrectBody, usually 400 or 415
await api_client.make_request(
    "POST", "/imports",
    content=b'{"file": "report.xlsx"}',
    content_type="application/json",
    expected_status_code=(400, 415),
    type=types.request_incorrect_body,
)
```

- A part named something other than what the API expects is usually 4xx or 415.
- An extra part or an extra query parameter is `request_extra_data` and normally stays 2xx.
- Always go through `ApiClient` with `files=`. A raw httpx call carries no `type=` and
  is invisible to coverage — see [Coverage honesty — when the number lies](concepts-coverage-honesty.md).

## Size

Empty is a required case. A modest payload of tens of kilobytes proves the happy path.

An **over-limit** case belongs in the suite only when the limit is documented. Hammering
a stand with a hundred megabytes to discover a limit nobody wrote down gives you a flaky
test and an unhappy platform team. No limit in the specification means a question, not
an invented 400.

## Building blocks

```python
from partest.files import (
    minimal_xlsx_bytes, minimal_ole_xls_bytes, png_bytes, pdf_bytes,
    empty_zip_bytes, truncated_zip_bytes, zip_without_content_types, zip_with_extra_part,
    format_cases, spoof_cases, filename_cases, size_cases,
)
```

Related: [Permissions — four cells, not one 401](howto-permissions.md) · [Recipes — consumer-side adapters](howto-recipes.md) · [Coverage methodology — three axes](concepts-methodology.md)
