import subprocess

import pytest

from taxi_seeder import mssql
from taxi_seeder.config import from_env

SETTINGS = from_env({"MSSQL_PASSWORD": "s3cret", "TAXI_DATA_DIR": "/data"})


def fake_runner(result_stdout="", returncode=0, record=None):
    def run(cmd, env, stdin_text):
        if record is not None:
            record.append((cmd, env, stdin_text))
        return subprocess.CompletedProcess(cmd, returncode, result_stdout, "")
    return run


def test_password_is_never_in_argv():
    cmd = mssql.build_cmd(SETTINGS, database="master", sql="SELECT 1")
    assert "s3cret" not in " ".join(cmd)


def test_password_is_passed_via_environment():
    record = []
    mssql.run(SETTINGS, "SELECT 1", runner=fake_runner(record=record))
    _cmd, env, _stdin = record[0]
    assert env["SQLCMDPASSWORD"] == "s3cret"


def test_cmd_targets_host_port_and_database():
    cmd = mssql.build_cmd(SETTINGS, database="taxi", sql="SELECT 1")
    assert "-S" in cmd and "mssql,1433" in cmd
    assert "-d" in cmd and "taxi" in cmd
    assert "-C" in cmd  # trust the container's self-signed certificate
    assert "-b" in cmd  # non-zero exit on SQL error


def test_run_raises_on_failure():
    with pytest.raises(mssql.MssqlError, match="exit 1"):
        mssql.run(SETTINGS, "SELECT 1", runner=fake_runner(returncode=1))


def test_scalar_strips_and_returns_value():
    assert mssql.scalar(SETTINGS, "SELECT 1", runner=fake_runner("  7  \n")) == "7"


def test_scalar_returns_none_for_sql_null():
    assert mssql.scalar(SETTINGS, "SELECT NULL", runner=fake_runner("NULL\n")) is None


def test_scalar_returns_none_for_empty_output():
    assert mssql.scalar(SETTINGS, "SELECT NULL", runner=fake_runner("\n")) is None


def test_wait_for_login_returns_once_the_server_answers():
    attempts = {"n": 0}

    def flaky(cmd, env, stdin_text):
        attempts["n"] += 1
        rc = 0 if attempts["n"] >= 3 else 1
        return subprocess.CompletedProcess(cmd, rc, "1", "")

    mssql.wait_for_login(SETTINGS, timeout_s=60, sleep_s=0,
                         runner=flaky, sleeper=lambda _s: None)
    assert attempts["n"] == 3


def test_wait_for_login_gives_up_and_raises():
    elapsed = {"t": 0.0}

    def clock():
        return elapsed["t"]

    def sleeper(seconds):
        elapsed["t"] += 10

    with pytest.raises(mssql.MssqlError, match="not accept a login"):
        mssql.wait_for_login(SETTINGS, timeout_s=30, sleep_s=10,
                             runner=fake_runner(returncode=1),
                             sleeper=sleeper, clock=clock)
