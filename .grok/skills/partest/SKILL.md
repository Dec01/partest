---
name: partest
description: >
  Pointer to the canonical partest skills. Build and grow API/UI autotest suites with partest:
  OpenAPI coverage, methodology (subtypes × test cases × steps), ApiClient, zorro reports,
  partest-gen scaffold.
---

# partest — pointer

The canonical skills live in `.claude/skills/`. Load the one that matches the task and follow it
instead of this file:

| Task | Skill |
|---|---|
| Write or extend API tests, raise coverage, pick test-case types | `.claude/skills/partest-cover-api/SKILL.md` |
| Generate a suite from OpenAPI, add a UI suite, sync after spec changes | `.claude/skills/partest-scaffold/SKILL.md` |
| Publish a version to PyPI | `.claude/skills/partest-release/SKILL.md` |
| Update documentation, ingest a backlog snapshot, fix the docs lint | `.claude/skills/partest-docs/SKILL.md` |

Repository rules: `AGENTS.md`. Documentation catalog: `docs/wiki/index.md`.

This file is kept only so agents that read `.grok/skills/` find their way. Do not add content
here — it will drift from the canonical skills.
