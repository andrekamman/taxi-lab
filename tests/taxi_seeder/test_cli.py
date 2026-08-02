from taxi_seeder import cli


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
