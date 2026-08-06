# taxi-lab

taxi-lab holds the recipes that *consume* the NYC TLC taxi data set. A separate repo,
[`taxi-seed`](https://github.com/andrekamman/taxi-seed), produces it and is installed here
from PyPI. This file is the glossary both repos' terms are read against — use these words
in code, comments, commit messages, and docs.

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

**Data folder**:
The one host folder that holds everything for a run. The seeder bind-mounts it at `/data`.
_Avoid_: data dir, workspace, mount, volume, output folder
_Note_: the identifiers are `TAXI_DATA_DIR` and `--data-dir`.

## Seeder

**Deliverable set**:
The five artifacts a complete seeder run leaves in the data folder: the raw parquet
mirror, the normalized parquet, the data file, the log file, and the backup.
_Avoid_: output, artifacts, results, bundle

**Deliverable**:
One member of that set. Each is wanted in its own right — the data file and log file are
deliverables, not by-products of the backup.
_Avoid_: artifact, output file

**Mirror**:
The local copy of the published parquet, under `raw/`. Also the verb for making it.
_Avoid_: download folder, cache, sync, raw dump

**Normalize**:
Reconcile a trip type's parquet across years into one stable set of columns and types,
writing `raw-normalized/`. Owned by taxi-seed.
_Avoid_: clean, transform, conform

**Schema drift**:
A month whose published columns disagree with the curated mapping for that trip type.
Normalize halts on unacknowledged drift, and the run exits `1`.
_Avoid_: schema change, mismatch, drift detection

**Provision**:
Create the `taxi` database with its files at a chosen path and a chosen size, or attach
the files if they already exist.
_Avoid_: setup, init, prepare, bootstrap

**Presize**:
Create a database file at its intended final size instead of letting it autogrow there.
_Avoid_: preallocate, size up, pre-provision

**Warm start**:
A run that finds an existing data file and attaches it, rather than creating and reloading
the database. This is the normal path for every run after the first.
_Avoid_: reattach, resume, restart

**Load manifest**:
The `dbo._load_manifest` table inside the `taxi` database. It records which months are
loaded and when, and it is what makes both resumability and backup staleness answerable.
_Avoid_: manifest (unqualified — see *bundle manifest*), load table, tracking table

**Step**:
One of the seven things a run does in order: preflight, mirror, provision, ola, load,
backup, report.
_Avoid_: stage, phase, task
_Note_: the module is named `stages.py` and some error strings say "stage". Those are the
outliers; new text should say "step".

**Skip condition**:
The observable a step checks to decide it has no work to do — a file on disk, a database
object, a row in the load manifest. The seeder keeps no state file of its own.
_Avoid_: guard, idempotency check, short-circuit

## k6-loadtest

**Test bundle**:
The four things the preprocessor writes for K6 to consume: the `CREATE TABLE` DDL, the
chunked JSON payloads, the generated `test.js`, and the bundle manifest.
_Avoid_: output, generated files, test package, payload

**Bundle manifest**:
The `manifest.json` inside a test bundle. It summarizes every scenario, its connection
string, and its data source.
_Avoid_: manifest (unqualified — see *load manifest*), index, summary

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

The seeder and taxi-seed share one contract. Use these words for them.

**Clean** (`0`):
Everything was already current, or the run advanced the data folder without incident.

**Needs review** (`1`):
A human must make a decision before the run can continue. Schema drift is the usual cause.
_Avoid_: warning, soft failure, partial

**Operational failure** (`2`):
Something broke that a person does not need to adjudicate — an unreachable server, a full
disk, a backup that failed verification. Re-running is often the whole remedy.
_Avoid_: error, hard failure, fatal
