# partest

Python harness for **methodology-driven API (+ optional UI) autotests** with OpenAPI coverage.

**PyPI:** https://pypi.org/project/partest/  
**Version:** 1.5.0

## Features

- Async `ApiClient` (JSON, form, files, raw `content`, multi-status, GraphQL)
- OpenAPI coverage + methodology matrix + HTML/Allure `zorro`
- Tracking client, TokenManager, reporting checks, payloads/validation
- Security: `SecHttp`, JWT craft, `RiskProfile`; `http.Config` / `HeadersBind`
- UI extra: `partest[ui]` — BasePage, PageMonitor, visual compare, capture_baselines
- Scaffold: `partest-gen` monorepo API+UI (G1–G6)
- Multi-project safety: soft-disable pytest plugin, confpartest helpers

## Install

```bash
pip install partest
pip install partest[ui]
```

## Scaffold

```bash
partest-gen from-openapi ./my-suite --file openapi.yaml --depth p1 --force --with-ui
partest-gen init-ui ./my-suite --force
```

## Docs

| Doc | For |
|-----|-----|
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | Greenfield &lt; 30 min |
| [docs/MIGRATION.md](docs/MIGRATION.md) | 0.3 / 1.x / aqa switch |
| [docs/REPORTING.md](docs/REPORTING.md) | check_* / Allure cookbook |
| [docs/COVERAGE_REPORT.md](docs/COVERAGE_REPORT.md) | Interactive HTML / CLI extras |
| [docs/LIBRARY_ROADMAP.md](docs/LIBRARY_ROADMAP.md) | Library waves through 1.5.0 |
| [docs/RELEASE_1.5.0.md](docs/RELEASE_1.5.0.md) | Publish + aqa W4 bump checklist |
| [docs/SECURITY.md](docs/SECURITY.md) | SecHttp / JWT / IncorrectBody |
| [docs/UI_QUICKSTART.md](docs/UI_QUICKSTART.md) | partest[ui] isolation |
| [docs/RECIPES.md](docs/RECIPES.md) | Keycloak, tracking, monorepo |
| [docs/ENTERPRISE.md](docs/ENTERPRISE.md) | Retry, xdist merge, redaction |
| [docs/README.md](docs/README.md) | Users: config, harness, generator |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Maintainers / agents |
| [docs/PROJECT_GEN_ROADMAP.md](docs/PROJECT_GEN_ROADMAP.md) | Generator design |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Status board (1.5.0 on PyPI; public GitHub out of scope) |
| [AGENTS.md](AGENTS.md) | Agent rules |

## License

MIT (see package classifiers)
