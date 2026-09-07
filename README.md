# partest

Python harness for **methodology-driven API (and optional UI) autotests** with OpenAPI coverage.

The `partest-gen` scaffold that generates a suite from an OpenAPI file lives in its own
repository: **https://github.com/Dec01/partest-gen**. It depends on this package; the
dependency never points the other way.

**PyPI:** https://pypi.org/project/partest/ — install from here.
**Source:** you are looking at it — see [docs/wiki/index.md](docs/wiki/index.md) for how it works and why.

```bash
pip install partest
pip install 'partest[ui]'
```

## Working in this repository

| Start here | For |
|---|---|
| [AGENTS.md](AGENTS.md) | rules and red lines for anyone (human or agent) changing this repo |
| [docs/wiki/index.md](docs/wiki/index.md) | documentation catalog — one line per page |
| [docs/wiki/status.md](docs/wiki/status.md) | current version, waves, what is next |
| [docs/wiki/howto/contribute.md](docs/wiki/howto/contribute.md) | invariants, tests, how to make a change |
| [docs/wiki/WIKI.md](docs/wiki/WIKI.md) | how the documentation itself is organized |
| [.claude/skills/](.claude/skills/) | procedures: cover an API, release, maintain docs |

```bash
python -m pytest tests/ -q          # units + docs lint + the partest-gen bridge
python tools/docs_lint.py           # documentation health
python tools/docs_build_wheel.py    # regenerate partest/docs from the wiki
```

## Layout

```text
partest/          library source (see docs/wiki/components/overview.md)
  docs/           generated user docs shipped in the wheel — do not hand-edit
docs/
  PYPI.md         long_description for the PyPI page
  wiki/           documentation: concepts, components, howto, decisions
  raw/            immutable source snapshots
  archive/        superseded documents
tools/            documentation tooling
tests/            library tests
```

## License

MIT.
