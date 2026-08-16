"""The pre-pass that makes every year a clean append before any fan-out."""
import subprocess

from taxi_seeder import integrity, shards
from taxi_seeder.config import from_env


def settings_for(tmp_path, **env):
    return from_env({"MSSQL_PASSWORD": "pw", "TAXI_DATA_DIR": str(tmp_path), **env})


def _proc(returncode, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_resets_only_the_years_the_server_reports(tmp_path):
    sent = []

    def runner(cmd, env, stdin_text):
        sent.append(cmd)
        if "FULL OUTER JOIN" in " ".join(cmd):
            return _proc(0, "2019\n2021\n")
        return _proc(0, "")

    items = [shards.Shard("fhvhv", y, 1, 1) for y in (2019, 2020, 2021)]
    reset = integrity.reset_inconsistent_years(settings_for(tmp_path), items,
                                               runner=runner)
    assert reset == [("fhvhv", 2019), ("fhvhv", 2021)]
    assert any("TRUNCATE TABLE dbo.fhvhv_2019" in " ".join(c) for c in sent)
    assert not any("TRUNCATE TABLE dbo.fhvhv_2020" in " ".join(c) for c in sent)


def test_resets_nothing_when_everything_agrees(tmp_path):
    items = [shards.Shard("fhvhv", 2019, 1, 1)]
    assert integrity.reset_inconsistent_years(
        settings_for(tmp_path), items, runner=lambda *a: _proc(0, "")) == []


def test_ignores_a_reported_year_no_shard_covers(tmp_path):
    """The server may hold years this run is not loading; leave them alone."""
    sent = []

    def runner(cmd, env, stdin_text):
        sent.append(cmd)
        if "FULL OUTER JOIN" in " ".join(cmd):
            return _proc(0, "1999\n")
        return _proc(0, "")

    items = [shards.Shard("fhvhv", 2019, 1, 1)]
    assert integrity.reset_inconsistent_years(
        settings_for(tmp_path), items, runner=runner) == []
    assert not any("TRUNCATE" in " ".join(c) for c in sent)


def test_queries_each_trip_type_once(tmp_path):
    queried = []

    def runner(cmd, env, stdin_text):
        joined = " ".join(cmd)
        if "FULL OUTER JOIN" in joined:
            queried.append("fhvhv" if "fhvhv" in joined else "green")
        return _proc(0, "")

    items = [shards.Shard("fhvhv", 2019, 1, 1), shards.Shard("fhvhv", 2020, 1, 1),
             shards.Shard("green", 2025, 1, 1)]
    integrity.reset_inconsistent_years(settings_for(tmp_path), items, runner=runner)
    assert sorted(queried) == ["fhvhv", "green"]


def test_an_empty_shard_list_is_a_no_op(tmp_path):
    assert integrity.reset_inconsistent_years(settings_for(tmp_path), [],
                                              runner=None) == []
