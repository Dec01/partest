<!-- Part of the partest package: generated documentation, not hand-written.
     Read it with `python -m partest.docs`. Local edits are lost on upgrade. -->

# Beyond a single HTTP call

The subtype × test-case matrix covers **one operation against its contract**. Plenty of
real behaviour does not fit in one call: a path across three resources, a rule linking
two of them, an upload whose effect lands in a worker, a screen that must show what the
API stored.

Those are not extra cells in the coverage matrix. Putting them there makes the
percentage meaningless in both directions.

## Layers

| Layer | What it covers | Where it is scored |
|---|---|---|
| **L0** | one HTTP operation, the axes of [Coverage methodology — three axes](concepts-methodology.md) | `coverage.json` |
| **L1** | user case / journey — a path that must stay consistent | a checklist, not the matrix |
| **L2** | logic invariant across resources | checklist |
| **L3** | integration — a write left a trace outside HTTP | checklist |
| **L4** | end to end: UI and API agree | checklist |

**Do not mix the percentages.** Only L0 belongs in the coverage number. A suite with
90% L0 and no journeys is not 90% tested, and a suite with rich journeys does not get
to inflate its L0 figure with them.

## Choosing the class

| Class | The question it answers | Write one when |
|---|---|---|
| `atomic` | does this one method honour its contract? | always — this is L0 |
| `user_case` | can a role reach one goal in a step or three? | a short user story |
| `user_journey` | does a path A→B→C stay consistent? | two or more resources, or three or more writes |
| `logic` | does an invariant hold across the chain? | a rule ties two resources, or a write to a later read |
| `integration` | did the write leave a trace outside HTTP? | upload, background job, event |
| `e2e` | does the screen show the same fact the API holds? | a screen creates or changes a resource |

A journey does not replace field-level Elements cases on the individual operations, and
Elements cases do not add up to a journey. Sketch the journey before writing it — which
resources, which order, which invariant at the end.

## Surfaces for an integration test

| Code | Where you look | Rule |
|---|---|---|
| `I0` | HTTP status and body | always |
| `I1` | locator in the body: key prefix, status enum, job id | required for an async create |
| `I2` | object store GET/HEAD | read-only; no credentials means hold, not a skipped endpoint |
| `I3` | bus consume | without committing the consumer group, or hold |
| `I4` | database | **SELECT only**; any mutating SQL stays in the project |
| `I5` | polling a status endpoint | when such an endpoint exists |
| `I6` | UI | the assertion is a state, not merely "an element is visible" |

**2xx is not persistence.** Assert in order: `I0` → `I1` → `I5` → `I2`/`I3`/`I4`.

An integration test needs `I0` and `I1` plus at least one of `I2`–`I5`, or an explicit
hold saying which surface is unavailable and why. A hold is a recorded step with a
reason; it does not cancel the response-contract assertions that precede it.

## Observing a side effect

`partest.sideeffects` gives the surfaces a shape. Everything in it is read-only:
stores are only ever read, brokers are polled without committing an offset, and the
database probe rejects anything that is not a single SELECT — including
`WITH x AS (DELETE ... RETURNING *) SELECT * FROM x`, which PostgreSQL would otherwise
run happily. Cleanup belongs to the API and the tracking registry.

Start with what needs no credentials at all — the API already told you where it put the
thing:

```python
from partest.sideeffects import assert_locator, assert_status_enum, wait_for

body = await api_client.make_request(
    "POST", "/imports", files=case.files_kwarg,
    expected_status_code=201, type=types.request_user_journey,
)
key = assert_locator(body, field="storageKey", prefix="imports/")
assert_status_enum(body, field="state", allowed=["ACCEPTED", "PROCESSING"])
```

Then the surface itself, when you can reach it:

```python
from partest.sideeffects import observe_or_hold

observation = observe_or_hold(
    store_probe,                     # None until the project has credentials
    "object-store",
    "no read credentials for the bucket on this stand",
    lambda probe: wait_for(
        lambda: probe.observe(key).found,
        timeout=60, interval=2, description="object appears in the store",
    ),
)
```

When `store_probe` is `None` the surface is **held**: the assertions above keep their
value, and the gap is recorded and reported. That is the difference from skipping the
test, which silently throws away the HTTP contract too.

### A fake cannot stand in for the real thing

`InMemoryObjectStore` and `InMemoryBus` exist so you can build the test before the
credentials arrive. They mark everything they report as simulated, and
`Observation.require()` refuses a simulated observation:

```python
store.observe(key).require("uploaded file")
# AssertionError: ... was only observed on a simulated object-store.
# A fake proves the test wiring, never the system — point the probe at the real
# surface or hold it.
```

Develop against the fake, swap in a real probe, and the report says which one ran. A
green test backed by a fake is exactly the false coverage the rest of this methodology
is built to prevent.

### Implementing a real probe

```python
from partest.sideeffects import ObjectStoreProbe

class S3Probe(ObjectStoreProbe):
    simulated = False

    def __init__(self, client, bucket):
        self._client, self._bucket = client, bucket

    def head(self, key):
        try:
            return self._client.head_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.ClientError:
            return None
```

The client, the bucket, the connection string and the schema stay in the project.

## Steps between the HTTP calls

| Step | Type to record |
|---|---|
| seed the data you need | `request_new_object` |
| the business write under test | `request_user_journey` |
| response contract: status → schema → values | part of the same call |
| locator or poll | no separate cell |
| store / bus / database observation | no cell — this is not a coverage claim |
| invariant assertion | no cell |
| cleanup | tracking registry, LIFO |

Reads against an object store, a broker or a database are **not** coverage cells. They
are how the test proves its point; the coverage matrix stays about HTTP operations.

Fail fast on the HTTP contract: if the response is already wrong, a held integration
step tells you nothing.

## End to end

The minimum that earns the name:

1. seed through the API, or create through the UI, with marked test data;
2. a real user action in the UI;
3. assert the UI state;
4. **assert the same fact through the API** — get it by id, or find it in a list;
5. clean up through the API.

Without step 4 it is a screen test. Without step 2 it is an API journey. Both are
useful; neither is end to end, and calling them that hides which risk is actually
covered.

Related: [Coverage methodology — three axes](concepts-methodology.md) · [Testing file upload endpoints](howto-upload.md) · [UI quickstart (partest[ui])](howto-ui.md) · [Coverage honesty — when the number lies](concepts-coverage-honesty.md)
