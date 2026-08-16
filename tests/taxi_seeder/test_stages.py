import os
import subprocess

import pytest

from taxi_seeder import shards, stages
from taxi_seeder.config import from_env


def settings_for(**env):
    return from_env({"MSSQL_PASSWORD": "pw", "TAXI_DATA_DIR": "/data", **env})


def test_mirror_omits_load_so_provisioning_can_interpose():
    cmd = stages.mirror_cmd(settings_for(), "yellow")
    assert cmd[:2] == ["taxi-run", "yellow"]
    assert "--data-dir" in cmd and "/data" in cmd
    assert "--load" not in cmd


def test_mirror_passes_recent_when_set():
    cmd = stages.mirror_cmd(settings_for(TAXI_RECENT="3"), "yellow")
    assert "--recent" in cmd
    assert cmd[cmd.index("--recent") + 1] == "3"


def test_mirror_omits_recent_for_full_history():
    assert "--recent" not in stages.mirror_cmd(settings_for(), "yellow")


def test_load_targets_the_compose_service():
    cmd = stages.load_cmd(settings_for(), "yellow")
    assert cmd[:2] == ["taxi-load", "yellow"]
    assert cmd[cmd.index("--host") + 1] == "mssql"
    assert cmd[cmd.index("--port") + 1] == "1433"
    assert cmd[cmd.index("--database") + 1] == "taxi"
    assert cmd[cmd.index("--data-dir") + 1] == "/data"


def test_password_reaches_the_subprocess_via_env_not_argv():
    captured = {}

    def runner(cmd, env, cwd):
        captured["cmd"] = cmd
        captured["env"] = env
        return subprocess.CompletedProcess(cmd, 0, "", "")

    stages.load(settings_for(), "yellow", runner=runner)

    assert "pw" not in " ".join(captured["cmd"])
    assert captured["env"]["MSSQL_PASSWORD"] == "pw"


def test_run_executes_with_cwd_data_dir_for_mapping_resolution():
    captured = {}

    def runner(cmd, env, cwd):
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    stages.mirror(settings_for(), "yellow", runner=runner)

    assert captured["cwd"] == "/data"


def test_run_returns_the_child_exit_code():
    def runner(cmd, env, cwd):
        return subprocess.CompletedProcess(cmd, 1, "", "")

    assert stages.mirror(settings_for(), "yellow", runner=runner) == 1


def test_load_passes_the_schema_and_user():
    cmd = stages.load_cmd(settings_for(), "yellow")
    assert cmd[cmd.index("--schema") + 1] == "dbo"
    assert cmd[cmd.index("--user") + 1] == "sa"


def test_the_child_env_is_a_full_environ_merge():
    """The child needs PATH to find taxi-run/taxi-load at all; a regression that
    replaced the merge with a bare dict would be maddening to diagnose from the
    resulting FileNotFoundError."""
    captured = {}

    def runner(cmd, env, cwd):
        captured["env"] = env
        return subprocess.CompletedProcess(cmd, 0, "", "")

    stages.mirror(settings_for(), "yellow", runner=runner)

    assert set(os.environ) <= set(captured["env"])
    assert captured["env"].get("PATH") == os.environ.get("PATH")


def test_a_missing_taxi_seed_cli_is_a_typed_error_not_a_traceback():
    """subprocess.run raises FileNotFoundError when the executable is not on
    PATH; untyped it escapes cli.main's mapping as a traceback with Python's
    exit code 1, which this project reserves for needs-review."""
    def runner(cmd, env, cwd):
        raise FileNotFoundError(2, "No such file or directory", cmd[0])

    with pytest.raises(stages.StageCommandNotFoundError, match="taxi-load"):
        stages.load(settings_for(), "yellow", runner=runner)


# --- month shards ----------------------------------------------------------

def _done(returncode=0):
    return subprocess.CompletedProcess([], returncode)


def test_load_cmd_omits_year_and_month_by_default():
    cmd = stages.load_cmd(settings_for(), "fhvhv")
    assert "--year" not in cmd and "--month" not in cmd


def test_load_cmd_includes_year_and_month():
    cmd = stages.load_cmd(settings_for(), "fhvhv", year=2019, month=3)
    assert cmd[cmd.index("--year") + 1] == "2019"
    assert cmd[cmd.index("--month") + 1] == "3"


def test_load_shard_passes_both():
    seen = {}

    def runner(cmd, env, cwd):
        seen["cmd"] = cmd
        return _done()

    rc = stages.load_shard(settings_for(), shards.Shard("fhvhv", 2019, 3, 1),
                           runner=runner)
    assert rc == 0
    assert seen["cmd"][seen["cmd"].index("--month") + 1] == "3"


def test_load_concurrent_runs_every_shard_and_returns_each_code():
    items = [shards.Shard("fhvhv", 2019, m, 1) for m in (1, 2, 3)]
    codes = {1: 0, 2: 2, 3: 0}

    def runner(cmd, env, cwd):
        return _done(codes[int(cmd[cmd.index("--month") + 1])])

    got = stages.load_concurrent(settings_for(), items, workers=3, runner=runner)
    assert {s.month: rc for s, rc in got} == codes


def test_load_concurrent_does_not_abandon_siblings_when_one_fails(capsys):
    """Fan-out cannot halt on the first failure -- siblings are already running."""
    items = [shards.Shard("fhvhv", 2019, m, 1) for m in (1, 2, 3)]

    def runner(cmd, env, cwd):
        if cmd[cmd.index("--month") + 1] == "1":
            raise RuntimeError("worker exploded")
        return _done()

    got = stages.load_concurrent(settings_for(), items, workers=3, runner=runner)
    assert len(got) == 3
    by_month = {s.month: rc for s, rc in got}
    assert by_month[1] == 2      # a crash maps to FAILURE
    assert by_month[2] == 0
    assert "fhvhv 2019-01" in capsys.readouterr().err


def test_load_concurrent_reraises_a_missing_taxi_load():
    """Not a shard problem: every shard would hit it, and main maps it to 2."""
    def runner(cmd, env, cwd):
        raise FileNotFoundError("taxi-load")

    with pytest.raises(stages.StageCommandNotFoundError):
        stages.load_concurrent(settings_for(), [shards.Shard("fhvhv", 2019, 1, 1)],
                               workers=2, runner=runner)


def test_load_concurrent_reports_each_completion():
    done = []
    items = [shards.Shard("fhvhv", 2019, m, 1) for m in (1, 2)]
    stages.load_concurrent(settings_for(), items, workers=2,
                           runner=lambda *a: _done(),
                           on_done=lambda s, rc: done.append(s.label))
    assert sorted(done) == ["fhvhv 2019-01", "fhvhv 2019-02"]


def test_load_concurrent_preserves_the_dispatch_order():
    items = [shards.Shard("fhvhv", 2019, m, 1) for m in (1, 2, 3)]
    got = stages.load_concurrent(settings_for(), items, workers=3,
                                 runner=lambda *a: _done())
    assert [s.month for s, _ in got] == [1, 2, 3]


def test_load_concurrent_of_nothing():
    assert stages.load_concurrent(settings_for(), [], workers=4, runner=None) == []
