import subprocess

from taxi_seeder import stages
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
