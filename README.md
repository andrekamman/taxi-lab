# taxi-lab

The New York City Taxi and Limousine Commission (TLC) publishes a record of every taxi
and for-hire vehicle trip in the city. The records start in 2009 and arrive as monthly
parquet files. Together they are a large, real, public data set — useful for load tests,
query benchmarks, and demos.

This repo holds recipes that *use* that data set.

A second repo, [`taxi-seed`](https://github.com/andrekamman/taxi-seed), produces it.
taxi-seed owns the downloader, the schema-drift analyzer, the normalizer, the loader, and
the orchestrator. taxi-lab installs taxi-seed from PyPI and builds on top of it.

## Components

### `seeder/` — one command, one folder, a complete SQL Server data set

[`seeder/`](seeder/) is a Docker Compose stack. Give it one folder on your host. It fills
that folder with a **deliverable set**:

| Deliverable | Path in the folder |
|---|---|
| Raw parquet mirror | `raw/<type>/<year>/` |
| Normalized parquet | `raw-normalized/<type>/<year>/` |
| Presized SQL Server data file | `mssql/data/taxi.mdf` |
| Presized SQL Server log file | `mssql/log/taxi_log.ldf` |
| Compressed, verified backup | `mssql/backup/taxi-sql/taxi/FULL/*.bak` |

Run it again on the same folder and it continues from where the last run stopped. Each
step reads the folder to decide whether it has work to do, so there is no state file to
go stale.

Two settings are required. Put them in `seeder/.env`, which is gitignored:

```bash
cat > seeder/.env <<'ENV'
TAXI_DATA_DIR=/srv/taxi
MSSQL_PASSWORD=change-me-Str0ng!
ENV
```

`TAXI_DATA_DIR` is the host folder to fill, and it must exist first. `MSSQL_PASSWORD` must
satisfy SQL Server's complexity policy, or the `mssql` container exits during startup.
Every other variable has a working default — the
[design spec](docs/specs/2026-08-01-seeder-container-design.md#configuration) lists all of
them.

Then run the stack:

```bash
cd seeder
docker compose up --build --abort-on-container-exit --exit-code-from seeder
```

Keep both flags. They make Compose stop the whole stack as soon as the seeder exits, and
they make `$?` the seeder's own exit code:

| Code | Meaning |
|---|---|
| 0 | Clean. Everything is current, or the run advanced the folder. |
| 1 | Needs review. Usually schema drift you must acknowledge. |
| 2 | Operational failure. For example, SQL Server was unreachable. |

Without the flags, the `mssql` service keeps running after the seeder finishes. You are
left watching the SQL Server log, with no signal that the run ended and no exit code.

The default run covers the complete data set: all four trip types, full history. Expect
several hours and a large database on the first run. Later runs are incremental.

#### Watching a run

The command above runs in the foreground, which is what you want in CI: it is the form
that gives you the exit code. For a multi-hour interactive run, start the stack detached
and follow the logs instead. A foreground run is tied to your terminal — if the terminal
dies the containers keep going, but you lose the output, and running `docker compose up` a
second time **recreates the seeder and discards whatever it was loading**.

```bash
cd seeder
docker compose up -d --build     # start detached
docker compose logs -f seeder    # follow; Ctrl-C detaches, nothing is killed
```

The seeder announces every stage, and during mirror and load it prints a progress line
every 60 seconds:

```
[07:12:56] mirror yellow: starting
[07:13:56] mirror yellow: 37 files, 12 files/min, elapsed 1m00s
[07:13:42] load fhvhv: starting (1.61B rows expected)
[07:14:42] load fhvhv: 2.1M/1.61B rows (0.1%), 2.06M rows/min, elapsed 1m00s, eta 13h01m
```

Load progress is sampled from the tables themselves, so it keeps moving even inside the
single multi-hour `COPY` a full year takes. Set `TAXI_PROGRESS_INTERVAL_S` in `.env` to
change the cadence, or `0` to switch the heartbeat off.

To check on a run from another shell without touching it:

```bash
docker compose ps
docker compose logs --tail 20 seeder
```

#### Load performance

Loading runs one `taxi-load` process per (trip type, year, month) — one process
per normalized parquet file. Several processes load different months into the same
year table at once: `TABLOCK` takes a BU (bulk update) lock, and BU locks are
compatible with each other, which is what SQL Server's parallel bulk import is
built on. The table layout is unchanged — no month tables, no views.

A single stream is CPU-bound, not disk-bound. Measured on 2026-08-15: `dop=1`,
87% on-CPU, 3 MB/s against a disk that does 1.3 GB/s, with the host 85% idle and
one core of eight busy. Parallelism is process-level because the duckdb `mssql`
extension keeps its ATTACH context process-global — two loads in one process
would collide on it.

```bash
TAXI_LOAD_WORKERS=6 docker compose up -d   # default: CPU count - 2, capped at 6
TAXI_LOAD_WORKERS=1 docker compose up -d   # serial, the pre-parallel behaviour
```

Before any shard runs, an integrity pass resets any year whose committed rows
disagree with its manifest. That is also the recovery granularity: a bulk load
commits per 100,000 rows and is not atomic, so a run killed mid-shard leaves rows
the year-level check has to clear. Shards are ordered year-major so the workers
finish one year before starting the next, which keeps a kill to one or two years
rather than six.

Because fan-out cannot halt on the first failure — the siblings are already
running — every dispatched shard finishes, every failure is reported, the worst
exit code wins, and the backup is skipped unless everything was clean.

SQL Server's memory is capped before provisioning to host RAM minus the larger of
4 GB and 25%. Override it for a differently-sized box:

```bash
MSSQL_MAX_MEMORY_MB=24576   # in .env
```

> **Requires a taxi-seed with `taxi-load --year/--month`.** The seeder checks for
> it and stops with exit 2 before dispatching anything if the installed
> `taxi-load` is older. Speed-up figures are not quoted here yet: the before
> numbers above are measured, and the after numbers will be filled in from a real
> parallel run rather than a projection.

See the [design spec](docs/specs/2026-08-01-seeder-container-design.md) for the
configuration variables and the decisions behind them.

### `k6-loadtest/` — drive load at a SQL Server

[`k6-loadtest/`](k6-loadtest/) is a K6 load tester for SQL Server, with a Python
preprocessor in front of it. The preprocessor reads parquet files (or a synthetic data
spec) and writes a K6 test bundle: `CREATE TABLE` DDL, chunked JSON payloads, a generated
`test.js`, and a bundle manifest. K6 then runs insert, update, and delete workloads
against your server under a virtual-user profile you configure.

See the [guide](docs/guides/k6-loadtest.md) to build the binary and run a first test.

## Install

```bash
uv sync --extra test
```

Two dependencies are pinned tightly, and both pins have a comment in
[`pyproject.toml`](pyproject.toml) that explains the failure they prevent:

- **`taxi-seed>=0.2.0`.** `k6_loadtest` imports `taxi_shared` from taxi-seed, so taxi-seed
  is a hard dependency. Release `0.1.0` shipped a `k6_loadtest` package of its own that
  shadows this repo's. `0.2.0` also emits page-compressed DDL, which the seeder needs.
- **`duckdb==1.4.4`.** taxi-seed's loader asserts one specific build of the DuckDB
  community `mssql` extension, and the registry serves one build per DuckDB version.

## Test

```bash
uv run pytest
```

This runs the fast unit suite. It needs no Docker and no network. `addopts` in
`pyproject.toml` deselects the `integration` marker.

The k6 preprocessor tests read a small checked-in parquet fixture. They never open a
database or a socket. The suite generates the K6 test bundle but does not execute it — to
run the bundle you need the custom xk6 binary from
[`k6-loadtest/build_k6.sh`](k6-loadtest/build_k6.sh) and a reachable SQL Server.

The seeder's end-to-end test is opt-in, because it needs Docker:

```bash
uv run pytest -m integration -v
```

It runs the real Compose stack twice against one data folder. The first run must produce
the full deliverable set; the second must be close to a no-op. That second run is what
proves the resumability claim. Budget several minutes and a few GB — the test pulls the
SQL Server image, builds the seeder image, and downloads a month of trip data. It leaves
that data behind on purpose; see the module docstring in
[`tests/taxi_seeder/test_integration_compose.py`](tests/taxi_seeder/test_integration_compose.py)
for how to clean it up.

## Docs

- [`CONTEXT.md`](CONTEXT.md) — the project glossary. Read it before you write code,
  comments, or docs here, and use the words it picks.
- [`docs/guides/`](docs/guides/) — how to use each component.
- [`docs/specs/`](docs/specs/) — design specs.
- [`docs/plans/`](docs/plans/) — implementation plans, kept as a historical record.

## License

MIT. See [LICENSE](LICENSE).
