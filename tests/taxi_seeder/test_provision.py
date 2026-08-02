import subprocess

from taxi_seeder import provision
from taxi_seeder.config import from_env

GB = 1024 ** 3


def settings_for(tmp_path, **env):
    return from_env({"MSSQL_PASSWORD": "pw", "TAXI_DATA_DIR": str(tmp_path), **env})


def write_parquet(tmp_path, data_type, size):
    d = tmp_path / "raw-normalized" / data_type / "2015"
    d.mkdir(parents=True, exist_ok=True)
    # Sparse file: sizing.parquet_bytes only reads stat().st_size, never the
    # contents, so a hole-punched file gives the same result as materializing
    # `size` zero bytes without the multi-GB in-memory allocation.
    path = d / "a.parquet"
    with path.open("wb") as f:
        f.truncate(size)


def sqlcmd_output(value, rows=1):
    """Real sqlcmd -h -1 -W output: the value, a blank line, and the row-count
    trailer that -h -1 does not suppress."""
    return f"{value}\n\n({rows} rows affected)\n"


class Recorder:
    """Answers scalar queries from a script of raw values, formatted the way
    sqlcmd formats them, and records every statement."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.statements = []

    def __call__(self, cmd, env, stdin_text):
        sql = cmd[cmd.index("-Q") + 1] if "-Q" in cmd else ""
        self.statements.append(sql)
        out = sqlcmd_output(self.answers.pop(0)) if self.answers else ""
        return subprocess.CompletedProcess(cmd, 0, out, "")


def test_creates_a_presized_database_when_absent(tmp_path):
    s = settings_for(tmp_path)
    write_parquet(tmp_path, "yellow", 4 * GB)
    rec = Recorder(["0"])  # database_exists -> 0

    created = provision.run(s, runner=rec)

    assert created is True
    joined = "\n".join(rec.statements)
    assert "CREATE DATABASE [taxi]" in joined
    assert "SIZE = 20480MB" in joined      # 4 GB x 3.0 = 12 -> 20 GB
    assert "SIZE = 16384MB" in joined      # log default
    assert "SET RECOVERY SIMPLE" in joined


def test_explicit_size_wins_over_the_estimate(tmp_path):
    s = settings_for(tmp_path, MSSQL_DATA_SIZE_GB="500")
    write_parquet(tmp_path, "yellow", 4 * GB)
    rec = Recorder(["0"])

    provision.run(s, runner=rec)

    assert "SIZE = 512000MB" in "\n".join(rec.statements)


def test_sizing_counts_only_selected_types(tmp_path):
    s = settings_for(tmp_path, TAXI_TYPES="yellow")
    write_parquet(tmp_path, "yellow", 4 * GB)
    write_parquet(tmp_path, "green", 40 * GB)
    rec = Recorder(["0"])

    provision.run(s, runner=rec)

    assert "SIZE = 20480MB" in "\n".join(rec.statements)


def make_existing_files(settings):
    """The mdf/ldf a previous run left on the bind mount."""
    settings.mssql_data_dir.mkdir(parents=True, exist_ok=True)
    settings.mssql_log_dir.mkdir(parents=True, exist_ok=True)
    settings.mdf_path.write_bytes(b"mdf")
    settings.ldf_path.write_bytes(b"ldf")


def test_attaches_when_the_files_survive_but_the_server_forgot_the_database(tmp_path):
    """`docker compose down` destroys master while the mdf/ldf survive on the
    bind mount. Creating over them fails with Msg 5170 on every run forever."""
    s = settings_for(tmp_path)
    make_existing_files(s)
    write_parquet(tmp_path, "yellow", 4 * GB)
    rec = Recorder(["0"])  # database_exists -> 0

    assert provision.run(s, runner=rec) is True

    joined = "\n".join(rec.statements)
    assert "FOR ATTACH" in joined
    assert "SIZE =" not in joined            # never re-size an existing file
    assert "SET RECOVERY SIMPLE" in joined


def test_creates_rather_than_attaches_when_no_mdf_is_on_disk(tmp_path):
    s = settings_for(tmp_path)
    write_parquet(tmp_path, "yellow", 4 * GB)
    rec = Recorder(["0"])

    provision.run(s, runner=rec)

    joined = "\n".join(rec.statements)
    assert "FOR ATTACH" not in joined
    assert "SIZE = 20480MB" in joined


def test_skips_creation_when_the_database_exists(tmp_path):
    s = settings_for(tmp_path)
    write_parquet(tmp_path, "yellow", 1 * GB)
    rec = Recorder(["1", "10240"])  # exists -> 1, allocated 10 GB

    created = provision.run(s, runner=rec)

    assert created is False
    assert "CREATE DATABASE" not in "\n".join(rec.statements)


def test_warns_when_the_existing_file_is_too_small(tmp_path, capsys):
    s = settings_for(tmp_path)
    write_parquet(tmp_path, "yellow", 40 * GB)  # implies 120 GB
    rec = Recorder(["1", "10240"])              # allocated 10 GB

    provision.run(s, runner=rec)

    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "autogrow" in out.lower()
    assert "MSSQL_DATA_SIZE_GB" in out


def test_stays_quiet_when_the_existing_file_is_ample(tmp_path, capsys):
    s = settings_for(tmp_path)
    write_parquet(tmp_path, "yellow", 1 * GB)   # implies 10 GB
    rec = Recorder(["1", "102400"])             # allocated 100 GB

    provision.run(s, runner=rec)

    assert "WARNING" not in capsys.readouterr().out


def test_stays_quiet_when_the_allocation_cannot_be_read(tmp_path, capsys):
    s = settings_for(tmp_path)
    write_parquet(tmp_path, "yellow", 40 * GB)
    rec = Recorder(["1", "NULL"])

    provision.run(s, runner=rec)

    assert "WARNING" not in capsys.readouterr().out
