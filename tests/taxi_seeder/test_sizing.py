from pathlib import Path

from taxi_seeder.sizing import (
    data_size_mb,
    log_size_mb,
    needs_growth_warning,
    parquet_bytes,
)

GB = 1024 ** 3


def _write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)


def test_parquet_bytes_sums_only_selected_types(tmp_path):
    _write(tmp_path / "yellow" / "2015" / "a.parquet", 100)
    _write(tmp_path / "yellow" / "2016" / "b.parquet", 50)
    _write(tmp_path / "green" / "2015" / "c.parquet", 999)
    assert parquet_bytes(tmp_path, ["yellow"]) == 150


def test_parquet_bytes_ignores_non_parquet(tmp_path):
    _write(tmp_path / "yellow" / "a.parquet", 100)
    _write(tmp_path / "yellow" / "notes.txt", 500)
    assert parquet_bytes(tmp_path, ["yellow"]) == 100


def test_parquet_bytes_tolerates_missing_type_dir(tmp_path):
    assert parquet_bytes(tmp_path, ["yellow", "fhvhv"]) == 0


def test_data_size_rounds_up_to_next_10gb():
    # 4 GB of parquet x 3.0 = 12 GB -> 20 GB
    assert data_size_mb(4 * GB, 3.0) == 20 * 1024


def test_data_size_exact_multiple_is_not_inflated():
    # 10 GB x 3.0 = 30 GB, already a multiple of 10
    assert data_size_mb(10 * GB, 3.0) == 30 * 1024


def test_data_size_has_a_one_granule_floor():
    assert data_size_mb(1, 3.0) == 10 * 1024


def test_data_size_of_empty_input_still_floors():
    assert data_size_mb(0, 3.0) == 10 * 1024


def test_log_size_mb():
    assert log_size_mb(16) == 16 * 1024


def test_growth_warning_fires_above_threshold():
    assert needs_growth_warning(implied_mb=1300, allocated_mb=1000) is True


def test_growth_warning_silent_at_threshold():
    assert needs_growth_warning(implied_mb=1250, allocated_mb=1000) is False


def test_growth_warning_silent_when_allocated_is_larger():
    assert needs_growth_warning(implied_mb=500, allocated_mb=1000) is False


def test_growth_warning_silent_when_allocation_unknown():
    assert needs_growth_warning(implied_mb=5000, allocated_mb=0) is False
