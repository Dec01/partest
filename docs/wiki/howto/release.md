---
title: Release checklist
status: current
verified: 2026-09-07
sources: [setup.py, MANIFEST.in, partest/__init__.py, tools/docs_build_wheel.py]
audience: maintainer
ships_in_wheel: false
allow_version_literals: false
---

# Release checklist

Version-agnostic procedure. What is in the current release and what is planned lives in
[[status]]; product notes live in `CHANGELOG.md`.

Artifacts go to **PyPI**, the source and its history to **GitHub** — see [[decisions/distribution]].

## 1. Decide the number

Only bump on an explicit release request. Semver as practiced here:

| Change | Bump |
|---|---|
| new opt-in API, new CLI flag, new subtype | minor |
| bug fix, doc-only, internal refactor | patch |
| removing a legacy alias (`type_*`, `aqa_*`, legacy TC names) | **major** |

Aliases live at least one full minor before removal.

## 2. Prepare

```bash
python tools/docs_build_wheel.py            # regenerate partest/docs from the wiki
python tools/check_all.py --strict-docs     # tests, docs lint, index, wheel drift
python -m partest.reports --help
python -m partest.ui.capture_baselines --dry-run
```

- [ ] `__version__` in `partest/__init__.py` bumped — this is the only place; `setup.py` reads it
- [ ] `CHANGELOG.md`: `Unreleased` folded into the new version section
- [ ] `docs/wiki/status.md`: current release, waves, what is next
- [ ] pages touched by the change have a fresh `verified:` date
- [ ] generator templates pin the new floor if they must (`partest>=X.Y`)
- [ ] no secrets, stand URLs, absolute local paths, or consumer project names in anything with
      `ships_in_wheel: true` — the linter checks this, but read the diff too

## 3. Build and inspect the artifact

```bash
python -m pip install -U build twine
python tools/check_all.py --package
python -m zipfile -l dist/partest-*.whl | grep "partest/docs"
```

The wheel must contain exactly the pages marked `ships_in_wheel: true` — no status page and no ADRs. Check the sdist as well: it carries `partest/**`, `CHANGELOG.md`,
`LICENSE` and the packaging files, and nothing else. `MANIFEST.in` prunes `tests/`, `docs/`, `tools/`, `.claude/` and `.grok/`; if you add a top-level directory, decide there whether it
ships before the next release does it for you.

```bash
python -c "import tarfile,glob; t=tarfile.open(glob.glob('dist/*.tar.gz')[0]); print('
'.join(sorted(t.getnames())))"
```

## 4. Publish

Publishing runs on GitHub with **trusted publishing**: PyPI authenticates the workflow by
its identity over OIDC. No API token exists — nothing to store, leak or rotate.

```bash
git push origin master
git tag -a vX.Y.Z -m "partest X.Y.Z — one line on what it is"
git push origin vX.Y.Z
```

The tag starts `release.yml`. It re-runs every check with `--strict-docs`, refuses to
continue if the tag and `__version__` disagree, then **waits for a review on the `pypi`
environment**. That review is the approval: nothing reaches PyPI until a human clicks it.

Verify afterwards from a clean environment:

```bash
python -m venv /tmp/verify && /tmp/verify/bin/pip install -U partest
/tmp/verify/bin/python -c "import partest; print(partest.__version__)"
/tmp/verify/bin/python -m partest.docs list
```

- [ ] version visible with `pip index versions partest`
- [ ] `python -m partest.docs list` shows the shipped pages
- [ ] PyPI project page renders (`twine check` passing is necessary, not sufficient — open it)

### If you have to publish by hand

Only when the workflow is unavailable. Credentials belong in your own keyring or
`~/.pypirc`, never on a command line and never in a message:

```bash
python tools/check_all.py --strict-docs --package
python -m twine upload dist/*
```

## 5. Record

- [ ] append a line to [[log]]
- [ ] update [[status]]: current release, and move closed items out of "what is next"
- [ ] if the release needed notable operational steps, fold them into this checklist so the
      next one inherits them

## 6. Rollback

PyPI does not allow re-uploading a version. To undo, yank the release and publish a patch:

```bash
python -m twine upload dist/partest-<next-patch>*
```

Consumers pinned to the bad version must move to the patch. Note in `CHANGELOG.md` what was wrong.

## Consumer bump (not library work)

A consuming suite pins the new version, drops whatever it had vendored locally, and keeps its
domain: entity paths and DTO, RBAC roles, SQL cleanup, page objects, visual scenes, baselines.
See [[decisions/no-domain]] and [[howto/migration]].
