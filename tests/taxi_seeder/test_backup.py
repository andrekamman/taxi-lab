import os
import subprocess
from datetime import datetime, timedelta, timezone

from taxi_seeder import backup
from taxi_seeder.config import from_env

UTC = timezone.utc
T0 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def settings_for(tmp_path):
    return from_env({"MSSQL_PASSWORD": "pw", "TAXI_DATA_DIR": str(tmp_path)})


class Recorder:
    def __init__(self, answers):
        self.answers = list(answers)
        self.statements = []

    def __call__(self, cmd, env, stdin_text):
        if "-Q" in cmd:
            self.statements.append(cmd[cmd.index("-Q") + 1])
        out = self.answers.pop(0) if self.answers else ""
        return subprocess.CompletedProcess(cmd, 0, out, "")


def make_bak(settings, when: datetime, name="taxi-sql_taxi_FULL_20260801_120000.bak"):
    d = settings.backup_dir / "taxi-sql" / "taxi" / "FULL"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(b"bak")
    os.utime(p, (when.timestamp(), when.timestamp()))
    return p


# --- the staleness rule ---

def test_no_backup_is_always_stale():
    assert backup.is_stale(T0, None) is True


def test_no_backup_and_nothing_loaded_is_still_stale():
    """The invariant: a successful run always leaves a .bak, even for an empty DB."""
    assert backup.is_stale(None, None) is True


def test_backup_newer_than_the_last_load_is_current():
    assert backup.is_stale(T0, T0 + timedelta(minutes=1)) is False


def test_load_newer_than_the_backup_is_stale():
    """The died-before-backup case: a run loaded rows then crashed. The next run
    loads nothing, so 'did this run load anything?' would never back up again."""
    assert backup.is_stale(T0, T0 - timedelta(minutes=1)) is True


def test_nothing_ever_loaded_but_a_backup_exists_is_current():
    assert backup.is_stale(None, T0) is False


def test_equal_timestamps_are_not_stale():
    assert backup.is_stale(T0, T0) is False


# --- discovery ---

def test_newest_backup_picks_the_latest_of_several(tmp_path):
    s = settings_for(tmp_path)
    make_bak(s, T0 - timedelta(hours=2), "a.bak")
    newest = make_bak(s, T0, "b.bak")
    assert backup.newest_backup(s) == newest


def test_newest_backup_is_none_when_absent(tmp_path):
    assert backup.newest_backup(settings_for(tmp_path)) is None


def test_backup_mtime_is_utc_aware(tmp_path):
    s = settings_for(tmp_path)
    p = make_bak(s, T0)
    assert backup.backup_mtime(p).tzinfo is not None


# --- manifest reading ---

def test_max_loaded_at_parses_iso_as_utc(tmp_path):
    rec = Recorder(["2026-08-01T12:00:00.000"])
    got = backup.max_loaded_at(settings_for(tmp_path), runner=rec)
    assert got == T0


def test_max_loaded_at_is_none_when_the_manifest_is_missing(tmp_path):
    def failing(cmd, env, stdin_text):
        return subprocess.CompletedProcess(cmd, 1, "", "Invalid object name")

    assert backup.max_loaded_at(settings_for(tmp_path), runner=failing) is None


def test_max_loaded_at_is_none_when_the_manifest_is_empty(tmp_path):
    assert backup.max_loaded_at(settings_for(tmp_path), runner=Recorder(["NULL"])) is None


# --- the step ---

def test_run_backs_up_when_stale(tmp_path):
    s = settings_for(tmp_path)
    rec = Recorder(["2026-08-01T12:00:00.000"])  # loaded, no .bak on disk
    assert backup.run(s, runner=rec) is True
    assert "DatabaseBackup" in "\n".join(rec.statements)


def test_run_skips_when_current(tmp_path):
    s = settings_for(tmp_path)
    make_bak(s, T0 + timedelta(hours=1))
    rec = Recorder(["2026-08-01T12:00:00.000"])
    assert backup.run(s, runner=rec) is False
    assert "DatabaseBackup" not in "\n".join(rec.statements)
