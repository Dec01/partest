---
name: partest-docs
description: >
  Maintain the partest documentation wiki: ingest a new source snapshot, add or update a page,
  resolve contradictions between documents, and run the doc linter. Use when documentation is
  out of date, a new backlog snapshot arrived, a page must be added or archived, or the docs
  lint fails.
---

# Maintaining the documentation wiki

## When to use this

- A new backlog or spec snapshot arrived and its content must reach the wiki
- Code changed and a page's `verified:` date is now behind its `sources:`
- `tools/docs_lint.py` or `tests/test_docs.py` fails
- A page must be created, split, or archived

Conventions live in `docs/wiki/WIKI.md`; rationale in
`docs/wiki/decisions/docs-architecture.md`. Read those before restructuring anything.

## The three operations

### Ingest — a new source arrived

1. Put it under `docs/raw/<source>/<date>/`. **Never edit a raw source in place**; a newer
   snapshot goes in a new dated directory and the old one stays.
2. Check it for private data before committing: absolute local paths, stand URLs, credentials.
3. Distribute the conclusions into wiki pages — usually `status.md` plus one or two topic pages.
4. Append an entry to `docs/wiki/log.md` saying what was taken from the snapshot.

### Update — code moved ahead of the page

1. Read the code named in the page's `sources:`, not your memory of it.
2. Fix the page, refresh `verified:`, add any new files to `sources:`.
3. If the page ships in the wheel, run `python tools/docs_build_wheel.py`.

### Lint — periodic health check

```bash
python tools/docs_lint.py            # report
python tools/docs_lint.py --strict   # non-zero exit on any finding
python tools/docs_index.py           # rebuild docs/wiki/index.json
```

Checks: broken `[[wiki-links]]`, missing `sources:` paths, pages whose `sources` changed after
`verified`, version literals outside allowed pages, private markers or consumer names in pages
with `ships_in_wheel: true`, and drift between `docs/wiki` and generated `partest/docs`.

## Rules

1. **Nothing is deleted silently.** Move with `git mv`, or leave a stub in `docs/archive/`
   pointing at the successor.
2. **One fact, one place.** Status, version and "what is next" exist only in
   `docs/wiki/status.md`. Everything else links to it.
3. **Code beats documents.** When they disagree, fix the document.
4. **Later date beats earlier date.** When two documents disagree, take the newer source — and
   say so explicitly in `status.md` rather than quietly picking a side.
5. **Do not hand-edit `partest/docs/`.** It is generated.
6. **Every page that describes code needs a non-empty `sources:`.** A page without one has no
   protection against going stale.
7. Keep `AGENTS.md` under 60 lines. Status tables do not belong there.

## Adding a page

```yaml
---
title: <short noun phrase>
status: current
verified: <today>
sources: [partest/<the files this page describes>]
audience: user | maintainer | agent
ships_in_wheel: false
---
```

Then: add one line to `docs/wiki/index.md`, and a line to `docs/wiki/log.md`.

Pick the category by the question it answers — `concepts/` why, `components/` what exists,
`howto/` how to do it, `decisions/` why this way and not another.

## RAG

Not enabled. The corpus is small enough that the index plus grep beats embeddings, and an
embedding index would go stale faster than the pages during active development. The corpus is
kept RAG-ready (`docs/wiki/index.json`, heading-chunkable raw sources); the switch-on criteria
are written in `docs/wiki/WIKI.md`. Do not build a vector index without checking them.
