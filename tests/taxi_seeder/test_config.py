import pytest
from pathlib import Path

from taxi_seeder.config import ConfigError, Settings, from_env

BASE = {"MSSQL_PASSWORD": "pw", "TAXI_DATA_DIR": "/data"}


def test_defaults():
    s = from_env(BASE)
    assert s.types == ("yellow", "green", "fhv", "fhvhv")
    assert s.recent is None
    assert s.data_factor == 3.0
    assert s.log_size_gb is None
    assert s.filegrowth_mb == 1024
    assert s.data_size_gb is None
    assert s.database == "taxi"
    assert s.host == "mssql"


def test_password_is_required():
    with pytest.raises(ConfigError, match="MSSQL_PASSWORD"):
        from_env({})


def test_types_are_parsed_and_ordered_canonically():
    s = from_env({**BASE, "TAXI_TYPES": "fhv, yellow"})
    assert s.types == ("yellow", "fhv")


def test_unknown_type_rejected():
    with pytest.raises(ConfigError, match="banana"):
        from_env({**BASE, "TAXI_TYPES": "banana"})


def test_recent_parsed():
    assert from_env({**BASE, "TAXI_RECENT": "3"}).recent == 3


def test_blank_recent_means_full_history():
    assert from_env({**BASE, "TAXI_RECENT": ""}).recent is None


def test_recent_must_be_positive():
    with pytest.raises(ConfigError, match="TAXI_RECENT"):
        from_env({**BASE, "TAXI_RECENT": "0"})


def test_factor_must_be_positive():
    with pytest.raises(ConfigError, match="TAXI_DATA_FACTOR"):
        from_env({**BASE, "TAXI_DATA_FACTOR": "0"})


def test_explicit_data_size_overrides_estimate():
    assert from_env({**BASE, "MSSQL_DATA_SIZE_GB": "500"}).data_size_gb == 500


def test_data_size_must_be_positive():
    with pytest.raises(ConfigError, match="MSSQL_DATA_SIZE_GB"):
        from_env({**BASE, "MSSQL_DATA_SIZE_GB": "0"})


def test_explicit_log_size_overrides_default():
    assert from_env({**BASE, "MSSQL_LOG_SIZE_GB": "4"}).log_size_gb == 4


def test_blank_log_size_means_unset():
    assert from_env({**BASE, "MSSQL_LOG_SIZE_GB": ""}).log_size_gb is None


def test_log_size_must_be_positive():
    with pytest.raises(ConfigError, match="MSSQL_LOG_SIZE_GB"):
        from_env({**BASE, "MSSQL_LOG_SIZE_GB": "0"})


def test_database_name_is_validated_at_config_time():
    """`taxi-db` is legal in SQL Server but not a plain identifier. Unvalidated
    it passes preflight, mirrors for hours, and only then dies in provision --
    as a SqlIdentifierError, which cli.main's config block does not catch."""
    with pytest.raises(ConfigError, match="MSSQL_DATABASE"):
        from_env({**BASE, "MSSQL_DATABASE": "taxi-db"})


def test_schema_name_is_validated_at_config_time():
    with pytest.raises(ConfigError, match="MSSQL_SCHEMA"):
        from_env({**BASE, "MSSQL_SCHEMA": "dbo; DROP DATABASE taxi--"})


def test_connection_overrides_are_honoured():
    s = from_env({**BASE, "MSSQL_HOST": "db.internal", "MSSQL_PORT": "14330",
                  "MSSQL_DATABASE": "taxi_2026", "MSSQL_SCHEMA": "staging",
                  "MSSQL_USER": "loader"})
    assert (s.host, s.port) == ("db.internal", 14330)
    assert (s.database, s.schema, s.user) == ("taxi_2026", "staging", "loader")


def test_derived_paths():
    s = from_env(BASE)
    assert s.raw_normalized_dir == Path("/data/raw-normalized")
    assert s.mdf_path == Path("/data/mssql/data/taxi.mdf")
    assert s.ldf_path == Path("/data/mssql/log/taxi_log.ldf")
    assert s.backup_dir == Path("/data/mssql/backup")
