"""End-to-end against the real Compose stack.

Run:  uv run pytest -m integration -v
Skip: uv run pytest -m 'not integration'

NEVER EXECUTED. These tests have not been run, not even once, and cannot pass
yet. Two independent blockers, neither fixable from this repo:

1. test_loaded_tables_are_page_compressed asserts PAGE compression on the
   loaded tables. That requires taxi-seed's generate_create_table_sql to emit
   WITH (DATA_COMPRESSION = PAGE), plus a PyPI release. That is owned by the
   taxi-seed maintainer and has not shipped.
2. taxi-seed 0.1.0 -- the only release on PyPI, and what the seeder image
   installs -- has a broken downloader: the mirror stage fails with
   "download_taxi_data.sh: No such file or directory". The pipeline cannot
   complete end-to-end regardless of compression until that is fixed
   upstream.

Do not treat a green run of this file as verification until both blockers
are resolved and someone has actually run `uv run pytest -m integration -v`
against a live Docker daemon.

Disk cleanup is manual. `down -v` removes containers and the one compose-declared
volume (`mssql-system`, holding SQL Server's system databases), but the data
itself is a host bind mount of `data_dir`, so a full run leaves several GB of `raw/`,
`raw-normalized/`, and `mssql/` data behind under pytest's temp tree
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
    try:
        return subprocess.run(
            ["docker", "compose", *args], cwd=COMPOSE_DIR, env=env,
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


def sqlcmd(data_dir, query):
    proc = compose(
        "exec", "-T", "mssql",
        "/opt/mssql-tools18/bin/sqlcmd", "-S", "localhost", "-U", "sa",
        "-P", PASSWORD, "-C", "-b", "-h", "-1", "-W", "-Q", query,
        data_dir=data_dir,
    )
    return proc.stdout.strip()


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
