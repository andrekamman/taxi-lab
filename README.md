# taxi-lab

Recipes for things to *do* with the NYC TLC taxi data set.

This repo is a consumer of [`taxi-seed`](https://github.com/andrekamman/taxi-seed), not a
fork of it. taxi-seed produces the data — it owns the downloader, the schema-drift
analyzer, the normalizer, the loader, and the orchestrator, and is consumed here as a
dependency (currently resolved from a sibling checkout rather than PyPI — see
[Install](#install)). Anything that *uses* the resulting data set lives in this repo.

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
  docker compose up --build --abort-on-container-exit --exit-code-from seeder
  ```

  Both flags are load-bearing. The `mssql` service runs indefinitely, so a plain
  `docker compose up` never returns: the seeder finishes, and you are left tailing SQL
  Server's log with no signal that the run ended and no way to see its exit code. With
  these flags the stack stops when the seeder exits and `$?` is the seeder's own
  `0` clean / `1` needs-review / `2` operational failure.

## Install

```bash
uv sync --extra test
```

`k6_loadtest` imports `taxi_shared` from `taxi-seed`, so taxi-seed is a hard dependency
rather than an optional one.

taxi-seed comes from PyPI, pinned `>=0.2.0`. That floor is load-bearing rather than
cautious: `0.1.0` shipped its own `k6_loadtest` package, which installs into
`site-packages` as a real directory and *shadows* this repo's `k6_loadtest` — taxi-lab's
code then silently never runs and its tests exercise taxi-seed's frozen copy instead.
`0.2.0` dropped it, and is also the first release whose generated `CREATE TABLE` DDL is
page-compressed, which the seeder depends on.

## Test

```bash
uv run pytest
```

This runs the fast unit suite only (Docker not required) — the `integration` marker is
deselected by default via `addopts` in `pyproject.toml`. The k6 preprocessor tests are
self-contained — they use a small checked-in parquet fixture and never touch a database
or the network. The generated K6 test bundle is *not* executed by the suite; running it
needs the custom xk6 binary from [`k6-loadtest/build_k6.sh`](k6-loadtest/build_k6.sh) and
a reachable SQL Server.

The seeder's end-to-end test runs the real Compose stack twice against one data folder to
prove resumability. It needs Docker and is opt-in:

```bash
uv run pytest -m integration -v
```

Currently blocked: it cannot pass yet, because taxi-seed hasn't shipped PAGE compression
and the only PyPI release (`0.1.0`) has a broken downloader. See the module docstring in
[`tests/taxi_seeder/test_integration_compose.py`](tests/taxi_seeder/test_integration_compose.py).

## Docs

- [`docs/guides/`](docs/guides/) — how to use each component.
- [`docs/specs/`](docs/specs/) — design specs.
- [`docs/plans/`](docs/plans/) — implementation plans, kept as a historical record.

## License

MIT. See [LICENSE](LICENSE).
