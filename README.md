# taxi-lab

Recipes for things to *do* with the NYC TLC taxi data set.

This repo is a consumer of [`taxi-seed`](https://github.com/andrekamman/taxi-seed), not a
fork of it. taxi-seed produces the data — it owns the downloader, the schema-drift
analyzer, the normalizer, the loader, and the orchestrator, and is installed here from
PyPI. Anything that *uses* the resulting data set lives in this repo.

## Components

- [`k6-loadtest/`](k6-loadtest/) — K6-based SQL Server load tester with a Python
  preprocessor. Turns parquet (or synthetic data specs) into a K6 test bundle: `CREATE
  TABLE` DDL, chunked JSON payloads, a generated `test.js`, and a manifest.
  See the [guide](docs/guides/k6-loadtest.md).
- `seeder/` — *(designed, not yet built)* a Docker Compose stack that advances one
  bind-mounted folder toward a complete deliverable set: raw parquet, normalized parquet, a
  presized page-compressed SQL Server database, and a verified compressed Ola Hallengren
  backup. See the [design spec](docs/specs/2026-08-01-seeder-container-design.md).

## Install

```bash
uv sync --extra test
```

`taxi-seed` comes from PyPI. `k6_loadtest` imports `taxi_shared` from it, so it is a hard
dependency rather than an optional one.

## Test

```bash
uv run pytest
```

The k6 preprocessor tests are self-contained — they use a small checked-in parquet fixture
and never touch a database or the network. The generated K6 test bundle is *not* executed
by the suite; running it needs the custom xk6 binary from
[`k6-loadtest/build_k6.sh`](k6-loadtest/build_k6.sh) and a reachable SQL Server.

## Docs

- [`docs/guides/`](docs/guides/) — how to use each component.
- [`docs/specs/`](docs/specs/) — design specs.
- [`docs/plans/`](docs/plans/) — implementation plans, kept as a historical record.

## License

MIT. See [LICENSE](LICENSE).
