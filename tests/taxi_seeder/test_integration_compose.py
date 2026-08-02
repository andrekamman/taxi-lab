"""End-to-end against the real Compose stack.

Run:  uv run pytest -m integration -v
Skip: uv run pytest -m 'not integration'

These have now been run for real against a live Docker daemon, and the seeder
produced a complete deliverable set: raw parquet, normalized parquet, presized
mdf/ldf, and a compressed, Ola-verified backup at
mssql/backup/taxi-sql/taxi/FULL/. The second run was a near no-op producing no
new backup, which is the resumability premise this file exists to prove.

Requires taxi-seed >= 0.2.0 (page-compressed DDL) and duckdb pinned to the
version whose community mssql extension taxi-seed asserts -- see the comments
on both in pyproject.toml. The pipeline cannot complete without either.

Running these is not free: a first run pulls the SQL Server image, builds the
seeder image, and downloads a month of taxi data, so budget several minutes and
a few GB.

Disk cleanup is manual. `down -v` removes containers (there is no named volume
to go with them -- `/var/opt/mssql` is deliberately left unpersisted, see
docker-compose.yml), but the data itself is a host bind mount of `data_dir`,
so a full run leaves several GB of `raw/`, `raw-normalized/`, and `mssql/`
data behind under pytest's temp tree
(`tmp_path_factory.mktemp("taxi-integration")`, i.e. under
`/tmp/pytest-of-$USER/pytest-<N>/taxi-integration0/` by default, or
`$PYTEST_DEBUG_TEMPROOT`/`--basetemp` if set). Deliberately not auto-removed
here: the mssql container runs as root inside the container and leaves
root-owned files on the bind mount, so `rm -rf` from the test process would
either fail or require privilege escalation, neither of which belongs in a
test. Clean it up by hand, e.g.
`sudo rm -rf /tmp/pytest-of-$USER/pytest-*/taxi-integration*`.
"""
import os
import subprocess
from pathlib import Path

import pytest

from taxi_seeder import mssql

pytestmark = pytest.mark.integration

COMPOSE_DIR = Path(__file__).resolve().parents[2] / "seeder"
PASSWORD = "Integration-Str0ng!"


# Default timeout for short commands (exec, down). The long-running "up" calls
# pass their own, larger timeout explicitly -- image build, SQL Server startup,
# and the data download can legitimately take several minutes.
DEFAULT_TIMEOUT = 120


def compose(*args, data_dir, check=True, timeout=DEFAULT_TIMEOUT):
    env = {
        **os.environ,
        "TAXI_DATA_DIR": str(data_dir),
        "MSSQL_PASSWORD": PASSWORD,
        "TAXI_TYPES": "yellow",
        "TAXI_RECENT": "1",
    }
    # --env-file with an empty file suppresses Compose's automatic loading of
    # seeder/.env. That file is gitignored, so whether it exists and what it
    # contains varies per machine -- and a stale one silently overrode the
    # sizing this test exists to exercise, making the run pass or fail for
    # reasons that had nothing to do with the code. Only the env set above may
    # influence the stack.
    empty_env_file = COMPOSE_DIR / ".env.integration-empty"
    empty_env_file.write_text("")
    try:
        return subprocess.run(
            ["docker", "compose", "--env-file", str(empty_env_file), *args],
            cwd=COMPOSE_DIR, env=env,
            capture_output=True, text=True, check=check, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        # Without this, a stalled download or an mssql container that never
        # reports healthy (see the healthcheck retries/interval in
        # docker-compose.yml) hangs the test process indefinitely -- the
        # module-scoped fixture's teardown only runs once the test returns.
        pytest.fail(
            f"`docker compose {' '.join(args)}` timed out after {timeout}s.\n"
            f"stdout so far: {exc.stdout}\nstderr so far: {exc.stderr}"
        )


def _raw_sqlcmd(data_dir, query, check=True):
    # -e rather than -P keeps the password out of sqlcmd's own argv, matching
    # what mssql.build_cmd does in production.
    return compose(
        "exec", "-T", "-e", f"SQLCMDPASSWORD={PASSWORD}", "mssql",
        "/opt/mssql-tools18/bin/sqlcmd", "-S", "localhost", "-U", "sa",
        "-C", "-b", "-h", "-1", "-W", "-Q", query,
        data_dir=data_dir, check=check,
    )


def sqlcmd(data_dir, query):
    """Query the seeded database, bringing the server back up if needed.

    Two things make this less trivial than `docker compose exec`:

    1. `up --abort-on-container-exit` stops the whole stack once the seeder
       finishes, so by the time these assertions run there is no container to
       exec into at all.
    2. `master` is deliberately not persisted (see docker-compose.yml), so if
       Compose *recreates* the mssql container rather than restarting it, the
       server comes back with no record of `taxi` even though the mdf/ldf are
       sitting on the bind mount.

    So: bring the database service up, wait for its healthcheck, and attach the
    files if the server does not already know about them -- which is exactly
    what provision.py does on a warm start, exercised here rather than mocked.
    """
    compose("up", "-d", "--wait", "mssql", data_dir=data_dir)
    _raw_sqlcmd(data_dir, (
        "IF DB_ID('taxi') IS NULL "
        "CREATE DATABASE [taxi] ON (FILENAME = N'/data/mssql/data/taxi.mdf'), "
        "(FILENAME = N'/data/mssql/log/taxi_log.ldf') FOR ATTACH"
    ))
    # first_value, not .strip(): sqlcmd appends "(1 rows affected)" to stdout,
    # so a naive strip returns "SIMPLE\n\n(1 rows affected)" and every equality
    # assertion fails on output that is actually correct. This is the same
    # detail that broke mssql.scalar in production; reuse that parser rather
    # than re-derive it here and get it wrong a second time.
    return mssql.first_value(_raw_sqlcmd(data_dir, query).stdout)


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("taxi-integration")
    yield d
    compose("down", "-v", data_dir=d, check=False)


def test_first_run_produces_the_full_deliverable_set(data_dir):
    result = compose("up", "--build", "--abort-on-container-exit",
                     "--exit-code-from", "seeder", data_dir=data_dir, check=False,
                     timeout=1800)
    assert result.returncode == 0, result.stdout + result.stderr

    assert list((data_dir / "raw" / "yellow").rglob("*.parquet"))
    assert list((data_dir / "raw-normalized" / "yellow").rglob("*.parquet"))
    assert (data_dir / "mssql" / "data" / "taxi.mdf").exists()
    assert (data_dir / "mssql" / "log" / "taxi_log.ldf").exists()

    baks = list((data_dir / "mssql" / "backup").rglob("*.bak"))
    assert len(baks) == 1
    # Ola's layout, with the hostname pinned so the path is stable across runs.
    assert baks[0].parent == data_dir / "mssql" / "backup" / "taxi-sql" / "taxi" / "FULL"


def test_loaded_tables_are_page_compressed(data_dir):
    """Requires taxi-seed >= 0.2.0 (Task 1)."""
    out = sqlcmd(data_dir, (
        "SELECT COUNT(*) FROM taxi.sys.partitions p "
        "JOIN taxi.sys.tables t ON t.object_id = p.object_id "
        "WHERE t.name LIKE 'yellow[_]%' AND p.data_compression_desc <> 'PAGE'"
    ))
    assert out == "0"


def test_database_is_in_simple_recovery(data_dir):
    assert sqlcmd(data_dir, "SELECT recovery_model_desc FROM sys.databases "
                            "WHERE name = 'taxi'") == "SIMPLE"


def test_second_run_is_a_near_noop(data_dir):
    """The real test of resumability: every skip condition must hold."""
    before = {p: p.stat().st_mtime
              for p in (data_dir / "mssql" / "backup").rglob("*.bak")}

    result = compose("up", "--abort-on-container-exit",
                     "--exit-code-from", "seeder", data_dir=data_dir, check=False,
                     timeout=1800)
    assert result.returncode == 0, result.stdout + result.stderr

    after = {p: p.stat().st_mtime
             for p in (data_dir / "mssql" / "backup").rglob("*.bak")}
    assert after == before, "a no-op run must not produce a new backup"
    assert "0 row(s) loaded" in result.stdout or "skip" in result.stdout.lower()
