import pytest

from taxi_seeder import backup, cli, mssql, ola, preflight, provision, report, stages


def test_help_exits_0_and_prints_usage_without_touching_pipeline(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "run", _never_called("preflight.run"))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "usage: taxi-seeder" in out
    assert "TAXI_DATA_DIR" in out
    assert "MSSQL_PASSWORD" in out


def test_unknown_flag_exits_2_without_touching_pipeline(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "run", _never_called("preflight.run"))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--bogus"])

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "usage: taxi-seeder" in err


def test_worst_prefers_failure():
    assert cli.worst([0, 1, 2]) == 2


def test_worst_prefers_needs_review_over_clean():
    assert cli.worst([0, 1, 0]) == 1


def test_worst_of_nothing_is_clean():
    assert cli.worst([]) == 0


def test_missing_password_is_an_operational_failure(monkeypatch, capsys):
    monkeypatch.delenv("MSSQL_PASSWORD", raising=False)
    assert cli.main([]) == 2
    assert "MSSQL_PASSWORD" in capsys.readouterr().err


def _base_env(monkeypatch, tmp_path, types):
    monkeypatch.setenv("MSSQL_PASSWORD", "pw")
    monkeypatch.setenv("TAXI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TAXI_TYPES", types)


def _never_called(name):
    def fake(*args, **kwargs):
        raise AssertionError(f"{name} should not have been called")
    return fake


def test_main_runs_the_seven_steps_in_order(monkeypatch, tmp_path):
    _base_env(monkeypatch, tmp_path, "yellow,green")
    calls: list = []

    def fake_preflight(settings, **kw):
        calls.append("preflight")
    monkeypatch.setattr(preflight, "run", fake_preflight)

    def fake_mirror(settings, data_type, **kw):
        calls.append(("mirror", data_type))
        return 0
    monkeypatch.setattr(stages, "mirror", fake_mirror)

    def fake_provision(settings, **kw):
        calls.append("provision")
        return True
    monkeypatch.setattr(provision, "run", fake_provision)

    def fake_ola(settings, **kw):
        calls.append("ola")
        return True
    monkeypatch.setattr(ola, "run", fake_ola)

    def fake_load(settings, data_type, **kw):
        calls.append(("load", data_type))
        return 0
    monkeypatch.setattr(stages, "load", fake_load)

    def fake_backup(settings, **kw):
        calls.append("backup")
        return True
    monkeypatch.setattr(backup, "run", fake_backup)

    monkeypatch.setattr(backup, "newest_backup", lambda settings: None)
    monkeypatch.setattr(report, "loaded_rows", lambda settings, **kw: {})
    monkeypatch.setattr(report, "render", lambda settings, **kw: "report")

    assert cli.main([]) == 0
    assert calls == [
        "preflight",
        ("mirror", "yellow"), ("mirror", "green"),
        "provision",
        "ola",
        ("load", "yellow"), ("load", "green"),
        "backup",
    ]


def test_main_stops_after_mirror_halts_and_labels_it_needs_review(
    monkeypatch, tmp_path, capsys
):
    _base_env(monkeypatch, tmp_path, "yellow,green,fhv")
    calls: list = []

    monkeypatch.setattr(preflight, "run", lambda settings, **kw: calls.append("preflight"))

    def fake_mirror(settings, data_type, **kw):
        calls.append(("mirror", data_type))
        return 1 if data_type == "green" else 0
    monkeypatch.setattr(stages, "mirror", fake_mirror)

    monkeypatch.setattr(provision, "run", _never_called("provision.run"))
    monkeypatch.setattr(ola, "run", _never_called("ola.run"))
    monkeypatch.setattr(stages, "load", _never_called("stages.load"))
    monkeypatch.setattr(backup, "run", _never_called("backup.run"))

    assert cli.main([]) == 1
    # fhv is never reached: the loop stops at the first non-clean return.
    assert calls == ["preflight", ("mirror", "yellow"), ("mirror", "green")]
    err = capsys.readouterr().err
    assert "needs-review:" in err
    assert "error:" not in err


def test_main_stops_after_load_fails_and_never_backs_up(monkeypatch, tmp_path, capsys):
    _base_env(monkeypatch, tmp_path, "yellow,green")
    calls: list = []

    monkeypatch.setattr(preflight, "run", lambda settings, **kw: calls.append("preflight"))

    def fake_mirror(settings, data_type, **kw):
        calls.append(("mirror", data_type))
        return 0
    monkeypatch.setattr(stages, "mirror", fake_mirror)

    def fake_provision(settings, **kw):
        calls.append("provision")
        return True
    monkeypatch.setattr(provision, "run", fake_provision)

    def fake_ola(settings, **kw):
        calls.append("ola")
        return True
    monkeypatch.setattr(ola, "run", fake_ola)

    def fake_load(settings, data_type, **kw):
        calls.append(("load", data_type))
        return 2 if data_type == "yellow" else 0
    monkeypatch.setattr(stages, "load", fake_load)

    monkeypatch.setattr(backup, "run", _never_called("backup.run"))

    assert cli.main([]) == 2
    assert calls == [
        "preflight", ("mirror", "yellow"), ("mirror", "green"),
        "provision", "ola", ("load", "yellow"),
    ]
    err = capsys.readouterr().err
    assert "error:" in err


def test_main_maps_missing_ola_script_to_exit_2(monkeypatch, tmp_path, capsys):
    _base_env(monkeypatch, tmp_path, "yellow")

    monkeypatch.setattr(preflight, "run", lambda settings, **kw: None)
    monkeypatch.setattr(stages, "mirror", lambda settings, data_type, **kw: 0)
    monkeypatch.setattr(provision, "run", lambda settings, **kw: True)

    def fake_ola(settings, **kw):
        raise ola.OlaScriptMissingError("vendored MaintenanceSolution.sql not found")
    monkeypatch.setattr(ola, "run", fake_ola)

    monkeypatch.setattr(stages, "load", _never_called("stages.load"))
    monkeypatch.setattr(backup, "run", _never_called("backup.run"))

    assert cli.main([]) == 2
    err = capsys.readouterr().err
    assert "vendored MaintenanceSolution.sql not found" in err


def test_main_maps_mssql_error_to_exit_2(monkeypatch, tmp_path, capsys):
    _base_env(monkeypatch, tmp_path, "yellow")

    monkeypatch.setattr(preflight, "run", lambda settings, **kw: None)
    monkeypatch.setattr(stages, "mirror", lambda settings, data_type, **kw: 0)

    def fake_provision(settings, **kw):
        raise mssql.MssqlError("sqlcmd failed (exit 1): connection refused")
    monkeypatch.setattr(provision, "run", fake_provision)

    monkeypatch.setattr(ola, "run", _never_called("ola.run"))
    monkeypatch.setattr(stages, "load", _never_called("stages.load"))
    monkeypatch.setattr(backup, "run", _never_called("backup.run"))

    assert cli.main([]) == 2
    err = capsys.readouterr().err
    assert "connection refused" in err
