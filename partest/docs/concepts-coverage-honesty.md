<!-- Part of the partest package: generated documentation, not hand-written.
     Read it with `python -m partest.docs`. Local edits are lost on upgrade. -->

# Coverage honesty

A coverage percentage is only useful if it fails loudly rather than quietly reading low or high.
Three ways the number currently lies, and what to do about each.

## 1. Parallel runs under pytest-xdist

`call_storage` is **per process** (`partest/call_storage.py`). Each xdist worker counts only its
own calls, so an unmerged parallel run reports one worker's slice as if it were the whole suite.
Measured on a live suite: `pytest -n 3` produced average 25.7% and 58 endpoints marked unseen,
while the same suite serial was green.

The bundled pytest plugin now closes this: every worker writes its counters to a shard when its
session ends, and the controller merges them before the run finishes. Nothing to configure.

One thing does **not** follow from the merge. A report produced by a test — the usual
`test_zorro` — runs on a worker, and merging happens on the controller afterwards, so that test
can never see the merged data. Two honest options:

* run the coverage pass serially, as before; or
* let the controller write the artifact:

```bash
PARTEST_COVERAGE_JSON=coverage.json PARTEST_COVERAGE_HTML=coverage_report.html pytest -n auto
```

The report then carries `meta.workers` and `meta.merged`, so a reader can tell what the number
describes. `PARTEST_COVERAGE_REQUIRE_MERGE=1` turns an unmerged parallel run into a failure, for
pipelines where coverage is a published artifact.

## 2. "Unseen" vs "no tests"

Zero recorded calls for an endpoint has two very different causes: no test exists, or tests exist
but did not run in this selection (`-k`, marker filter, failed fixture). Each endpoint now carries
a `kind` alongside the legacy `status`:

| `kind` | Means |
|---|---|
| `unseen` | nothing called this operation **in this run** — says nothing about whether tests exist |
| `empty` | it was called, but no required cell was executed |
| `partial` | some required cells present |
| `full` | the required set for the subtype is covered |
| `exception` | the endpoint is excluded from scoring |

`meta.unseenRatio` and `meta.partialRun` summarise it: a run is flagged partial when a fifth of
the endpoints went untouched, when workers were not merged, or when the run selected a subset
of the suite in the first place.

That last one is not measurable from the numbers, and the reason is worth understanding.

### A run with no endpoints measured nothing, and says so

`unseenRatio` is a share over the endpoints of the run, so a run that collected none has no
denominator: a fixture that failed before the specification was read, a worker shard that was
never merged, an empty specification. The field is **`null`** there, not `0.0` — a zero would
read as "not one endpoint went untouched", the most reassuring number in the artifact coming
out of the least informative run. A measured zero is still `0.0`, and the key is always
present, so `null` ("not measured") stays distinguishable from a missing key ("an artifact
older than the field"). Anything that multiplies or compares the value checks for `null`
first.

`partialRun` stays a bool and stays `false` for such a run. It answers a different question —
"did this run cover less of the suite than it should", with three measurable reasons — and
every message built on it says "some endpoints were never called", which is false, not true,
when there are no endpoints. Deciding whether a run that measured nothing may be compared at
all is the reader's call, and `unseenRatio: null` is the field that gives it the fact.

### A filter removes cells, not endpoints

Coverage is scored per test case, but `unseen` is a property of an *endpoint*. Run
`pytest -m "not rbac"` and the endpoint is still called — it just loses its
`RequestPermissions` cell. So the coverage of that endpoint drops while `unseenRatio` stays
near zero, and nothing in the payload reveals that half the suite never ran.

Measured on a real suite: a marker filter dropped 46% of the tests and 55% of the calls, and
`unseenRatio` moved from 0.009 to 0.018. Compared against a full run, every dropped cell was
reported as a regression, with the comparison marked sound.

Two things now prevent that:

- **The selection is recorded.** The pytest plugin writes `meta.selection` — the `-m` / `-k`
  expression and how many tests were deselected. Exact, and it comes from the only place that
  knows: the invocation. This is `PARTEST_RUN_METADATA` / `run_metadata`, on by default and
  **separate from `PARTEST_PYTEST_PLUGIN`**: the Allure switch is the one projects turn off to
  keep their own hooks, and it used to take this signal down with it. The deselected figure is
  a count of distinct node ids, so merging the shards of a parallel run does not double it —
  every worker deselects the same tests.
- **A call-volume collapse is caught even without it.** `compare` warns when a run made less
  than half the calls of the one before it while the share of never-called endpoints barely
  moved. That signature is what a cell-level filter looks like, and it reads from the endpoints
  themselves — so it also works against a snapshot written before `meta` existed, which is
  exactly when someone is upgrading and comparing.

`compare` reports this as `comparable: False` with the reason, and does **not** move the lost
cells out of `regressed`. Whether a cell was deselected or deleted cannot be known from two
payloads, and quietly reclassifying them would risk burying a real loss under a heuristic.

Practical consequence: a low number after a filtered run is not a coverage regression. Compare
only full runs; use `python -m partest.reports compare --strict` on two payloads rather than
eyeballing percentages, and treat a non-zero exit as "these two runs are not the same
experiment", not as "coverage fell".

## 3. Unmatched paths

Coverage keys a call by the OpenAPI path template, so the concrete URL a suite sends has to be
mapped back to the template that produced it. Until the resolver landed, this was a guess: the
first unused path parameter found anywhere in the whole specification was appended, which turned
`/orders/customer/5` into `/orders/customer/{id}` while the specification said
`{customerId}`. The strings did not match, the operation recorded zero calls, and the endpoint
read as uncovered with green tests behind it.

Now the concrete URL is matched per operation: same segment count, literal segments must be
equal, and among the candidates the template with the longest literal prefix wins — so
`/orders/customer/{customerId}` beats `/orders/{id}`, and a static `/orders/user` beats
`/orders/{id}`.

`defining_url` still wins over everything when you pass it, and it is still worth passing when a
path is genuinely ambiguous. Nothing else changed for suites that already used it.

## What to trust

| Question | Trust |
|---|---|
| Did this endpoint get its required P1 cases? | `report.endpoints[*].missing_p1` |
| Did the suite get better or worse? | `compare` of two full-run payloads |
| Single average percentage from a filtered or parallel run | no |
| `regressed` from a comparison whose `comparable` is `False` | no — read `warnings` first |

Comparing against a snapshot older than `kind` works: a missing `kind` is inferred from the
call count, so an endpoint that was never called in either run is not reported as one that
used to be covered.

Related: [Coverage methodology — two areas, three axes each](concepts-methodology.md) · [Interactive coverage report and CLI](howto-coverage-html.md) · [Enterprise notes — shared client, retries, redaction, xdist](howto-enterprise.md)
