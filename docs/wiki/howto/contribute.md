---
title: Developing partest
status: current
verified: 2026-09-07
sources: [partest/__init__.py, setup.py, tests/test_docs.py, tools/docs_lint.py]
audience: maintainer
ships_in_wheel: false
---

# Developing partest

Entry point for maintainers and agents working **on** the library (working **with** it starts at
[[howto/quickstart]]). Package layout: [[components/overview]]. Current state: [[status]].

## Invariants

1. No product domain in the library — [[decisions/no-domain]].
2. No private absolute paths, stand URLs or secrets in anything that ships — [[decisions/distribution]].
3. Consumer configuration stays in the suite's `confpartest.py` / `.env`, never here.
4. Canonical TC names in new code; legacy aliases kept for at least one minor —
   [[decisions/explicit-type]].
5. Read-only against databases. Only test data carrying `TEST_MARKER`
   (`partest/data_marker.py`) may ever be deleted, and the deleting SQL lives in the consumer.

## Working on a change

1. Read `AGENTS.md`, then the relevant module. Methodology questions: `partest/methodology/*` is
   the source of truth, not any document.
2. Add or adjust tests under `tests/`.
3. Run `python -m pytest tests/ -q`.
4. If the public API or CLI changed: update the matching `docs/wiki/components/` page,
   `CHANGELOG.md`, and the affected skill under `.claude/skills/`.
5. Refresh `verified:` on any wiki page whose `sources` you touched.
6. Bump the version only when releasing — [[howto/release]].

## Tests

```bash
python tools/check_all.py           # everything below, in one command
python tools/check_all.py --package # plus build the distribution and twine check

python -m pytest tests/ -q          # units, docs lint, the partest-gen bridge
python -m partest.ui.capture_baselines --dry-run
```

The generator has its own repository and its own suite. Touched `partest/methodology/*`?
That is a cross-package change — `partest_gen` reads those functions, so run the generator's
golden test against this working tree before calling it done:

```bash
cd ../partest_gen
PYTHONPATH=../partest_client python -m pytest tests/test_golden_suite.py -q
```

`tests/test_ui_isolation.py` guards that `import partest.ui` needs no network, no OpenAPI and no
confpartest — a monorepo UI job must not pull the API session. Do not weaken it.

## Documentation

Structure and conventions: `docs/wiki/WIKI.md`. Rationale: [[decisions/docs-architecture]].

```bash
python tools/docs_lint.py            # links, staleness, version literals, wheel drift
python tools/docs_index.py           # rebuild docs/wiki/index.json
python tools/docs_build_wheel.py     # regenerate partest/docs from ships_in_wheel pages
```

`partest/docs/` is generated. Editing it by hand is a mistake the linter will report —
[[decisions/docs-in-wheel]].

## The generator is a separate package

`partest-gen` lives in its own repository and depends on this one. What stays here is a
deprecated bridge (`partest.project_gen`) and the methodology it reads — see
[[components/project-gen]].

Two consequences for work in this repository:

- `classify_endpoint` and `p1_test_cases` are **not** internal. They have a second consumer,
  so changing their signature is a cross-package change with its own release order.
- Never import `partest_gen` outside the bridge. It is an optional dependency; a hard one
  would make the two packages circular.

## Where things are decided

| Question | Source of truth |
|---|---|
| Which TC types are required for a subtype | `partest/methodology/matrix.py` |
| What a subtype is | `partest/methodology/subtypes.py` |
| What the generator emits | the `partest-gen` repository, not this one |
| What version we are on | `partest/__init__.py` |
| What ships to PyPI users | `ships_in_wheel: true` frontmatter |
| What is planned | [[status]] |
