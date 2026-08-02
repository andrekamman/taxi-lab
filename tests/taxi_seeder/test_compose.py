"""Invariants of the Compose stack that the Python tests cannot otherwise see.

These are cheap YAML assertions, not a Docker run: they pin the properties of
docker-compose.yml that silently break the seeder's contracts -- the password
never reaching argv, and `/var/opt/mssql` staying un-persisted so `master`
resets on every start.
"""
from pathlib import Path

import pytest
import yaml

COMPOSE_FILE = Path(__file__).resolve().parents[2] / "seeder" / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load(COMPOSE_FILE.read_text())


def test_healthcheck_keeps_the_password_out_of_argv(compose):
    """mssql.py refuses to put the password in argv and test_mssql pins it; the
    healthcheck runs sqlcmd every 10s for the container's lifetime, so a -P
    there leaks it just as widely -- to `docker top`, to `ps`, to any process in
    the container."""
    test = " ".join(compose["services"]["mssql"]["healthcheck"]["test"])
    assert "SQLCMDPASSWORD=" in test
    assert " -P" not in test


def test_system_databases_are_not_persisted(compose):
    """A named volume on /var/opt/mssql was tried and reverted: it kept master
    around across restarts, which broke a moved TAXI_DATA_DIR (stale path in
    the old master) and a rotated MSSQL_PASSWORD (SQL Server only consumes
    MSSQL_SA_PASSWORD on first init of /var/opt/mssql, so a persisted master
    means "first init" never happens again). Ephemeral master makes every
    start a first init and pushes provision.py's FOR ATTACH branch onto the
    normal warm-start path instead of only the `down -v` case -- exercised
    every restart, not almost never. Do not reintroduce this volume."""
    mssql = compose["services"]["mssql"]
    assert not any(v.split(":")[1] == "/var/opt/mssql" for v in mssql["volumes"])
    assert not compose.get("volumes")


# Every variable config.from_env reads. A variable the CLI honours but Compose
# never forwards is silently ignored inside the container.
SEEDER_ENV_VARS = (
    "TAXI_DATA_DIR", "MSSQL_PASSWORD", "TAXI_TYPES", "TAXI_RECENT",
    "TAXI_DATA_FACTOR", "MSSQL_DATA_SIZE_GB", "MSSQL_LOG_SIZE_GB",
    "MSSQL_FILEGROWTH_MB", "MSSQL_HOST", "MSSQL_PORT", "MSSQL_DATABASE",
    "MSSQL_SCHEMA", "MSSQL_USER",
)


@pytest.mark.parametrize("var", SEEDER_ENV_VARS)
def test_compose_forwards_every_configuration_variable(compose, var):
    assert var in compose["services"]["seeder"]["environment"]


def test_the_seeder_runs_once_and_does_not_restart(compose):
    assert compose["services"]["seeder"]["restart"] == "no"


def test_the_readme_documents_an_invocation_that_returns_the_seeders_exit_code():
    """`docker compose up` alone never returns -- the mssql service runs
    indefinitely -- so the whole 0/1/2 contract is invisible to anyone following
    the README. The integration test already uses the flags that fix that."""
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text()
    for line in readme.splitlines():
        if line.strip().startswith("docker compose up"):
            assert "--abort-on-container-exit" in line
            assert "--exit-code-from seeder" in line
            break
    else:
        pytest.fail("README documents no `docker compose up` invocation")
