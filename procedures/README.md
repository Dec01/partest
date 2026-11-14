# Maintainer procedures

These are plain Markdown instructions for Kimi and other maintainers. Read the matching file
explicitly before starting the task; nothing in this directory is registered as an automatic extension.

| Procedure | When to read it |
|---|---|
| [cover-api.md](cover-api.md) | writing or extending API tests, choosing case types, raising coverage |
| [release.md](release.md) | the user explicitly requested a version or publication |
| [docs.md](docs.md) | adding, updating, ingesting or linting documentation |

Detailed references live beside the procedures in `references/`. The repository rules in
`AGENTS.md` and documentation contract in `docs/wiki/WIKI.md` still take precedence in their
respective areas.

The generator is a separate repository. Its procedures are in `../partest_gen/procedures/`;
in particular, scaffolding belongs to `../partest_gen/procedures/scaffold.md`, not here.
