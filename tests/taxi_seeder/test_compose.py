"""Invariants of the Compose stack that the Python tests cannot otherwise see.

These are cheap YAML assertions, not a Docker run: they pin the two properties
of docker-compose.yml that silently break the seeder's contracts -- the password
never reaching argv, and SQL Server's system databases outliving `down`.
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


def test_system_databases_live_on_a_named_volume(compose):
    """master records where taxi.mdf is. If it dies with the container while the
    mdf survives on the bind mount, the next run tries to CREATE over the file
    and fails with Msg 5170 -- permanently."""
    mssql = compose["services"]["mssql"]
    assert any(v.split(":")[1] == "/var/opt/mssql" for v in mssql["volumes"])
    volume_name = next(v.split(":")[0] for v in mssql["volumes"]
                       if v.split(":")[1] == "/var/opt/mssql")
    assert volume_name in (compose.get("volumes") or {})


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
