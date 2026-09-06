---
name: partest-release
description: >
  Publish a new partest version to PyPI: pick the version, regenerate the docs that ship in the
  wheel, run the checks, build, inspect the artifact, upload, and record the release. Use when
  asked to release, publish, cut a version, or bump partest on PyPI.
---

# Releasing partest

## When to use this

The user explicitly asked to release, publish, or cut a version.

**Never bump `__version__` outside such a request.** A version bump is not part of a feature.

## Procedure

The authoritative checklist is `docs/wiki/howto/release.md` — follow it. This skill exists so you
load it at the right moment and do not skip the parts that are easy to forget.

## The parts that get skipped

1. **Regenerate the wheel docs.** `python tools/docs_build_wheel.py`. `partest/docs/` is
   generated from `docs/wiki/` pages marked `ships_in_wheel: true`. Hand-editing it, or forgetting
   to regenerate, is how internal notes reached PyPI before.
2. **Inspect what is actually in the wheel:**
   ```bash
   python -m zipfile -l dist/partest-*.whl | grep "partest/docs"
   ```
   No status page, no ADRs, no consumer project names.
3. **One version source.** `partest/__init__.py`; `setup.py` reads it. Do not add the number
   anywhere else.
4. **Update `docs/wiki/status.md`** — current release, and remove what just shipped from
   "what is next".
5. **Open the rendered PyPI page.** `twine check` passing does not mean the page reads well.

## Commands

```bash
python tools/docs_build_wheel.py           # regenerate first: the checks compare against it
python tools/check_all.py --strict-docs --package
git tag -a vX.Y.Z -m "partest X.Y.Z — …"   # the tag is what publishes
git push origin master vX.Y.Z
```

`--strict-docs` makes a stale page fail rather than warn. CI does not use it, because a
page going stale should not block ordinary work — but a release publishes those pages, so
here it does.

## Red lines

- **Ask before pushing the tag.** The tag starts the publishing workflow. Publishing is
  irreversible — PyPI never lets a version number be reused — so confirm the version and
  the artifact contents with the user first. The `pypi` environment also requires their
  review, but do not treat that as the place to think: get agreement before tagging.
- **Never handle a PyPI token.** Publishing uses trusted publishing, so no token exists.
  If someone offers one, decline, and tell them to revoke it if it was sent in a message.
- Push the release commit and tag to GitHub as well; PyPI carries the artifact, the
  repository carries how it was built.
- Do not release with failing tests or a failing docs lint. Report the failure instead.

## If it went wrong

A published version cannot be replaced — yank it and publish a patch. Say in `CHANGELOG.md` what
was wrong so pinned consumers know why they must move.
