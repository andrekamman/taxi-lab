# taxi-lab

The New York City Taxi and Limousine Commission (TLC) publishes a record of every taxi
and for-hire vehicle trip in the city. The records start in 2009 and arrive as monthly
parquet files. Together they are a large, real, public data set — useful for load tests,
query benchmarks, and demos.

This repo holds recipes that **consume** that data set.

A second repo, [`taxi-seed`](https://github.com/andrekamman/taxi-seed), **produces** it:
the downloader, the schema-drift analyzer, the normalizer, the loader, the pipeline
runner, and `taxi-mssql`, a Compose stack that turns one host folder into a complete,
backed-up SQL Server data set. taxi-lab installs taxi-seed from PyPI and builds on top.

> **Looking for the seeder?** It moved to taxi-seed as **`taxi-mssql`**. It produces the
> data set rather than consuming it, so it was on the wrong side of the line these two
> repos draw. Its design specs moved with it, to
> [`docs/superpowers/specs/`](https://github.com/andrekamman/taxi-seed/tree/main/docs/superpowers/specs)
> there. If you have a `seeder/.env`, its two required settings — `TAXI_DATA_DIR` and
> `MSSQL_PASSWORD` — are the same ones `mssql/.env` wants in taxi-seed.

## `k6-loadtest/` — drive load at a SQL Server

[`k6-loadtest/`](k6-loadtest/) is a K6 load tester for SQL Server, with a Python
preprocessor in front of it. The preprocessor reads parquet files (or a synthetic data
spec) and writes a K6 test bundle: `CREATE TABLE` DDL, chunked JSON payloads, a generated
`test.js`, and a bundle manifest. K6 then runs insert, update, and delete workloads
against your server under a virtual-user profile you configure.

The parquet it reads is whatever taxi-seed produced — the normalized output under
`raw-normalized/`, or a database `taxi-mssql` filled. That is the whole relationship
between the two repos: taxi-seed writes the data, this reads it.

See the [guide](docs/guides/k6-loadtest.md) to build the binary and run a first test.

## Install

```bash
uv sync --extra test
```

One dependency needs explaining, and its comment in [`pyproject.toml`](pyproject.toml)
has the detail:

- **`taxi-seed>=0.2.0`.** `k6_loadtest` imports `taxi_shared.type_mapping` and
  `taxi_shared.sql_generator` — pure functions, no database and no DuckDB extension — so
  taxi-seed is a hard dependency but a shallow one. The floor exists because release
  `0.1.0` shipped a `k6_loadtest` package of its own that shadows this repo's.

`duckdb` is deliberately **not** pinned here. It used to be `duckdb==1.4.4`, for a reason
that belonged to the seeder: taxi-seed's loader asserted one specific build of the DuckDB
community `mssql` extension. taxi-seed pins DuckDB itself and vendors that extension now,
so an exact pin here would conflict with it. This repo only reads parquet.

## Test

```bash
uv run pytest
```

The fast unit suite — no Docker, no network. The k6 preprocessor tests read a small
checked-in parquet fixture and never open a database or a socket. The suite generates a K6
test bundle but does not execute it; running one needs the custom xk6 binary from
[`k6-loadtest/build_k6.sh`](k6-loadtest/build_k6.sh) and a reachable SQL Server.

## Docs

- [`CONTEXT.md`](CONTEXT.md) — the project glossary. Read it before you write code,
  comments, or docs here, and use the words it picks. Terms shared with taxi-seed are
  defined in both and must stay in step.
- [`docs/guides/`](docs/guides/) — how to use each component.
- [`docs/specs/`](docs/specs/) — design specs.
- [`docs/plans/`](docs/plans/) — implementation plans, kept as a historical record.

## License

MIT. See [LICENSE](LICENSE).
