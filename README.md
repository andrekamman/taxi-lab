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
- [`seeder/`](seeder/) — Docker Compose stack that advances one bind-mounted folder toward
  a complete deliverable set: raw parquet, normalized parquet, a presized page-compressed
  SQL Server database, and a verified compressed Ola Hallengren backup. Re-running resumes
  from wherever the last run stopped.
  See the [design spec](docs/specs/2026-08-01-seeder-container-design.md).

  ```bash
  cd seeder && cp .env.example .env   # set TAXI_DATA_DIR and MSSQL_PASSWORD
  docker compose up --build
  ```

## Install

```bash
uv sync --extra test
```

`k6_loadtest` imports `taxi_shared` from `taxi-seed`, so taxi-seed is a hard dependency
rather than an optional one.

**taxi-seed currently resolves from a sibling checkout, not PyPI.** Clone the two repos
side by side:

```
~/git/
  taxi-seed/
  taxi-lab/
```

The reason is a packaging collision: taxi-seed `v0.1.0` — the only release on PyPI —
predates the k6 removal and still ships its own `k6_loadtest` package. Installed from
PyPI it lands in `site-packages` as a real directory and *shadows* this repo's
`k6_loadtest`, so taxi-lab's code silently never runs and its tests exercise taxi-seed's
frozen copy instead. The removal is on taxi-seed `main` but has never been tagged.

Once a taxi-seed release drops `k6_loadtest`, delete the `[tool.uv.sources]` block in
`pyproject.toml` and pin that version instead.

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
