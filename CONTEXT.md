# taxi-lab

taxi-lab holds the recipes that *consume* the NYC TLC taxi data set. A separate repo,
[`taxi-seed`](https://github.com/andrekamman/taxi-seed), produces it and is installed here
from PyPI. This file is the glossary — use these words in code, comments, commit messages,
and docs.

Only the terms this repo actually uses live here. The vocabulary of producing the data set
— provisioning, presizing, the deliverable set, the load manifest, the three-state exit
contract — belongs to taxi-seed and is defined in
[its `CONTEXT.md`](https://github.com/andrekamman/taxi-seed/blob/main/CONTEXT.md). The few
terms defined in both are marked below and must stay in step.

## The data set

**Trip record**:
One row of the NYC Taxi and Limousine Commission's public data — a single taxi or
for-hire vehicle journey. The full set starts in 2009 and is published as monthly parquet
files.
_Avoid_: ride, journey, trip event

**Trip type**:
One of the four services the TLC publishes separately: `yellow`, `green`, `fhv`, `fhvhv`.
_Avoid_: data type, taxi type, service type, category
_Note_: the code identifier is `data_type`, inherited from taxi-seed's CLI. Keep that
identifier, but write "trip type" in prose — "data type" is already taken by its ordinary
programming meaning in k6-loadtest's column specs.

**Mirror**:
The local copy of the published parquet, under `raw/`. Produced by taxi-seed; read here as
one possible data source. Also the verb for making it.
_Avoid_: download folder, cache, sync, raw dump
_Note_: defined in both repos; keep in step.

**Normalize**:
Reconcile a trip type's parquet across years into one stable set of columns and types,
writing `raw-normalized/`. Owned by taxi-seed, and the usual input to a parquet data
source here.
_Avoid_: clean, transform, conform
_Note_: defined in both repos; keep in step.

## k6-loadtest

**Test bundle**:
The four things the preprocessor writes for K6 to consume: the `CREATE TABLE` DDL, the
chunked JSON payloads, the generated `test.js`, and the bundle manifest.
_Avoid_: output, generated files, test package, payload

**Bundle manifest**:
The `manifest.json` inside a test bundle. It summarizes every scenario, its connection
string, and its data source.
_Avoid_: manifest (unqualified — taxi-seed has a *load manifest*, which is a
different thing entirely), index, summary

**Data source**:
A named block in `config.yaml` that says where rows come from. It has a source mode and
the keys that mode needs.
_Avoid_: source, dataset, input, feed

**Source mode**:
Either `parquet` (read real rows from files) or `synthetic` (K6 makes rows at run time
from declared ranges).
_Avoid_: mode, data mode, generation mode

**Target**:
A named block in `config.yaml` describing one SQL Server to drive load at: host, port,
database, user, password reference, table.
_Avoid_: server, destination, endpoint, connection

**Scenario**:
A named block in `config.yaml` that ties one data source to one target and sets the
workload mix and the K6 executor profile.
_Avoid_: test, run, workload (on its own — the workload is one field of a scenario)

**Chunk**:
One JSON file of rows from a parquet data source. Each chunk becomes one bulk-insert batch
at run time.
_Avoid_: batch, partition, slice, page

## Exit codes

taxi-lab has no three-state exit contract. `k6-preprocess` exits `0` or `1`.

The **Clean / Needs review / Operational failure** contract (`0` / `1` / `2`) is
taxi-seed's, and is defined in
[its `CONTEXT.md`](https://github.com/andrekamman/taxi-seed/blob/main/CONTEXT.md) and
[exit-codes reference](https://andrekamman.github.io/taxi-seed/reference/exit-codes/). Use
those words when talking about a taxi-seed run; do not reinvent them here.
