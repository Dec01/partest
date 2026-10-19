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
| **L0** | one HTTP operation, the axes of [Coverage methodology — two areas, three axes each](concepts-methodology.md) | `coverage.json` |
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

### Waiting for a job to finish (`I5`)

`wait_for` is the small form: one synchronous probe, truthy means done (it runs on the same
loop as below). A background job is
a state machine, and when it does not finish, *where it stopped* is the finding — "did not
finish in 300 s" and "sat in `QUEUED` for 300 s" send you to different teams.
`partest.polling.poll_until` keeps the path:

```python
from partest.polling import PollTimeout, poll_until

async def fetch_job():
    # A long poll outlives a token: ask for it on every tick. TokenManager.get_token()
    # returns the cached one and goes to the identity provider only once it has expired.
    token = await tokens.get_token()
    return await api_client.make_request(
        "GET", "/jobs", add_url1=f"/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
        expected_status_code=200, type=types.request_default,
    )

result = await poll_until(
    fetch_job,
    lambda job: job["status"] in {"DONE", "FAILED"},
    timeout=300, interval=2,
    state=lambda job: job["status"],   # what the history records
    on_tick=lambda tick: allure.attach(str(tick.state), name=f"poll {tick.attempt}"),
    what=f"job {job_id}",
)
assert result.value["status"] == "DONE", result.history   # ('QUEUED', 'RUNNING', 'FAILED')
```

- `fetch`, `is_terminal`, `state` and `on_tick` may each be plain or async.
- `on_tick` gets a `PollTick(attempt, value, state, elapsed)` **after** every successful
  fetch. It is for observing — log, attach, count. Anything the *next* fetch needs, a fresh
  token above all, goes inside `fetch`: refreshed in `on_tick`, it arrives one request late,
  and the first fetch after expiry fails with 401 before `on_tick` ever runs.
- `PollResult` carries `value`, `history` (states seen, consecutive repeats collapsed),
  `attempts` and `elapsed`.
- On timeout `PollTimeout` is raised with `last`, `history`, `attempts`, `elapsed` and the
  `timeout`. The message shows the first and last five states with "… k more …" between,
  redacted — plain dicts and lists by key and no deeper than six levels, anything else by
  its `repr` through `partest.redact.redact_text`. **The attributes are not redacted:**
  without `state=` every `history` entry is a whole response body, tokens included if the
  API returns them; what reaches a report from there is your decision. It is an `AssertionError` —
  a failed test, like `wait_for` — and not a `TimeoutError`: that is an `OSError`, and a
  network `except OSError` around the poll would swallow it.
- The clock is monotonic. Between fetches the loop sleeps `interval` and never past the
  deadline, then looks once more *at* the deadline — a job that finished during the last
  sleep is not reported as stuck. No other pause is added.
- An exception from `fetch`, `state`, `is_terminal` or `on_tick` propagates unchanged: a
  failing request is its own finding, not a reason to keep waiting. It carries the poll so
  far — `poll_history`, `poll_attempts`, `poll_elapsed`, and on Python 3.11+ a note under
  the traceback.
- `poll_until_sync` is the same contract for synchronous code.

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

## Checking a computed value against its formula (`L2`)

A response says `total = 26.36` next to `rate = 3.14` and `count = 8.395`. The service
computed the total from unrounded numbers and then rounded everything it wrote, each to its
own scale; `3.14 × 8.395 = 26.3603` will not match exactly, and the question is whether the
gap is what rounding can produce.

`math.isclose(actual, expected, rel_tol=…)` answers a different question. The tolerance is
picked by eye and is the same for every formula, so it fails both ways at once: too loose
where the inputs were recorded precisely (a real 0.05 % defect passes), too tight where the
formula amplifies rounding — a division by a small rounded number, a difference of two close
ones — and a correct value fails. `partest.rounding` derives the tolerance instead:

```python
from partest.rounding import Rounded, agrees_with_formula, agrees_with_sum

check = agrees_with_formula(
    Rounded(body["total"], 2, "total"),          # value, scale it was rounded to, label
    lambda rate, count: rate * count,
    Rounded(body["rate"], 2, "rate"),
    Rounded(body["count"], 3, "count"),
)
assert check, str(check)

assert agrees_with_sum(Rounded(body["sum"], 2, "sum"), [Rounded(p, 2) for p in parts])
```

How it decides:

1. every input recorded at scale `s` stands for the interval `value ± ½·10^−s`
   (`scale=None` — an exact decimal, no width: a count, a constant, a number the test wrote.
   A float the service *computed* is not exact even unrounded — its last digits are binary
   noise — so give it the scale it is meaningful to rather than `None`);
2. the formula is evaluated over those intervals with interval arithmetic — `decimal`,
   rounded outward, so the interval is never narrower than the truth;
3. the result is widened by the output's own half unit;
4. the recorded output must lie inside. For a sum that is the sum of all the half units and
   nothing more: ten parts at two decimals may miss their total by `10 × 0.005 + 0.005`.

`Agreement` is truthy when the value agrees. `str()` is the full protocol (actual, computed,
deviation, the intervals, every input with its half unit); `as_dict()` is the same for an
attachment. **`resolution`** is half the width of the accepted interval relative to the
computed value — how sharp the check was. `±0.002 %` means a real check; `±4 %` means the
inputs are recorded too coarsely for the comparison to catch much, which is worth knowing
before trusting the green. `notes` flags a value carrying more decimals than its declared
scale: either the scale is wrong or the value was not rounded to it. Each note is also
emitted as a `RoundingNoteWarning`, so it reaches pytest's warnings summary on a green run
where nobody prints the protocol; `-W error::partest.rounding.RoundingNoteWarning` turns
them into failures.

**A float the service computed and did not round** is good to a number of *significant*
digits, not decimals: `0.1 + 0.2` arrives as `0.30000000000000004`. `scale=None` demands more
than the arithmetic gave, a scale picked by hand gives a note on every run. Say what it is:

```python
Rounded(body["ratio"], significant=12, label="ratio")   # unit of the 12th significant digit
```

The unit follows the magnitude (`123456.0` at three significant digits is `±500`), digits
beyond it are not a note — nobody claimed the value was rounded — and zero is exact. In the
protocol: `ratio = 0.3  (12 significant digits → scale 12, ±0.0000000000005)`.

**A value rounded in one direction** says so with `rounding=` — the specification says
"amounts are rounded down", and `10.009` is written `10.00`, which round-to-nearest would
reject:

```python
Rounded(body["amount"], 2, "amount", rounding="toward_zero")
```

| `rounding=` | the record `r` stands for |
|---|---|
| `"half"` (default) | `[r − ½ unit, r + ½ unit]` — to nearest, any tie rule |
| `"toward_zero"` (the extra digits dropped) | `[r, r + unit]` for a positive `r`, `[r − unit, r]` for a negative one, `[−unit, unit]` for zero |
| `"floor"` (toward −∞) | `[r, r + unit]` |
| `"ceiling"` (toward +∞) | `[r − unit, r]` |

"Rounded down" in a specification nearly always means the digits are dropped: a refund of
`-12.349` is written `-12.34`. That is `"toward_zero"`; `"floor"` would write `-12.35` and
reject the correct record. The two agree only for values that cannot be negative — use
`"floor"` when the specification really says toward −∞.

The `decimal` constants are accepted too: `ROUND_DOWN` is `"toward_zero"`, as in `decimal`
(not "floor"), every `ROUND_HALF_*` is `"half"`; `ROUND_UP` (away from zero) and `ROUND_05UP`
are not modelled and raise `ValueError`. An input rounded that way contributes its
one-sided interval; an output is accepted when some value the formula allows rounds to it in
that direction. Both work with `significant=`.

**Several values of one response** go through one call — the protocol of all of them, one
failure listing every disagreement instead of stopping at the first:

```python
from partest.rounding import assert_all_agree

assert_all_agree([
    agrees_with_formula(Rounded(body["total"], 2, "total"), lambda r, c: r * c, rate, count),
    agrees_with_sum(Rounded(body["sum"], 2, "sum"), parts),
], name="invoice totals")
```

With Allure available the protocol is attached on a pass and on a failure — `invoice totals`
(JSON, every `as_dict()`) and `invoice totals.txt` (every `str()`); without it nothing is
attached and the check works the same. The `AssertionError` names the failed checks and holds
each one's full protocol. An empty list is a `ValueError`: no check is not a pass.

Limits, on purpose:

- the formula receives `Interval` objects and may use `+ − × ÷`, unary minus, `abs` and
  integer powers, with plain numbers mixed in (a float constant is read as the decimal it
  prints as). `if`, `max`, `round`, `math.*`, and `==`/`!=` against a number (`x != 0`)
  raise `TypeError` — each would silently pick one end of an interval or one branch.
  Powers above 64 are refused, and so is a scale beyond ±10000; arithmetic that leaves the
  range `decimal` represents becomes a `ValueError` naming the cause;
- a divisor whose interval contains zero raises `ZeroDivisionError`: at those scales the
  formula cannot be checked at all;
- the rounding is declared, not guessed: a value truncated or rounded down but declared with
  the default `"half"` is off by up to a whole unit in one direction, and the check can fail
  on a correct value — give it `rounding=`;
- interval arithmetic can over-estimate when one input appears several times in the formula
  (`x − x` is not `0` over an interval). That makes the check more lenient, never wrong, and
  the `resolution` shows it.

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

Related: [Coverage methodology — two areas, three axes each](concepts-methodology.md) · [Testing file upload endpoints](howto-upload.md) · [UI quickstart (partest[ui])](howto-ui.md) · [Coverage honesty — when the number lies](concepts-coverage-honesty.md)
