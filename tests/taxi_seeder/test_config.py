import pytest
from pathlib import Path

from taxi_seeder.config import ConfigError, Settings, from_env

BASE = {"MSSQL_PASSWORD": "pw", "TAXI_DATA_DIR": "/data"}


def test_defaults():
    s = from_env(BASE)
    assert s.types == ("yellow", "green", "fhv", "fhvhv")
    assert s.recent is None
    assert s.data_factor == 3.0
    assert s.log_size_gb == 16
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


def test_derived_paths():
    s = from_env(BASE)
    assert s.raw_normalized_dir == Path("/data/raw-normalized")
    assert s.mdf_path == Path("/data/mssql/data/taxi.mdf")
    assert s.ldf_path == Path("/data/mssql/log/taxi_log.ldf")
    assert s.backup_dir == Path("/data/mssql/backup")
