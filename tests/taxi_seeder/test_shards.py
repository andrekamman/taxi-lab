from taxi_seeder import shards
from taxi_seeder.config import from_env


def settings_for(tmp_path, types="green,fhvhv", **env):
    return from_env({"MSSQL_PASSWORD": "pw", "TAXI_DATA_DIR": str(tmp_path),
                     "TAXI_TYPES": types, **env})


def _tree(root, spec):
    for data_type, years in spec.items():
        for year, months in years.items():
            d = root / "raw-normalized" / data_type / str(year)
            d.mkdir(parents=True, exist_ok=True)
            for m in months:
                (d / f"{data_type}_tripdata_{year}-{m:02d}.parquet").touch()


def test_discover_finds_one_shard_per_month(tmp_path):
    _tree(tmp_path, {"green": {2025: [1, 2]}, "fhvhv": {2019: [2]}})
    found = shards.discover(settings_for(tmp_path), footer_reader=lambda p: 100)
    assert {(s.data_type, s.year, s.month) for s in found} == {
        ("green", 2025, 1), ("green", 2025, 2), ("fhvhv", 2019, 2)
    }
    assert all(s.rows == 100 for s in found)


def test_discover_honours_the_selected_types(tmp_path):
    _tree(tmp_path, {"green": {2025: [1]}, "fhvhv": {2019: [2]}})
    found = shards.discover(settings_for(tmp_path, types="green"),
                            footer_reader=lambda p: 1)
    assert [s.data_type for s in found] == ["green"]


def test_discover_ignores_directories_that_are_not_years(tmp_path):
    _tree(tmp_path, {"green": {2025: [1]}})
    stray = tmp_path / "raw-normalized" / "green" / "scratch"
    stray.mkdir()
    (stray / "green_tripdata_2025-01.parquet").touch()
    found = shards.discover(settings_for(tmp_path), footer_reader=lambda p: 1)
    assert [(s.year, s.month) for s in found] == [(2025, 1)]


def test_discover_ignores_files_without_a_month_stamp(tmp_path):
    _tree(tmp_path, {"green": {2025: [1]}})
    (tmp_path / "raw-normalized" / "green" / "2025" / "notes.parquet").touch()
    found = shards.discover(settings_for(tmp_path), footer_reader=lambda p: 1)
    assert len(found) == 1


def test_discover_is_empty_when_nothing_is_normalized(tmp_path):
    assert shards.discover(settings_for(tmp_path), footer_reader=lambda p: 1) == []


def test_discover_reads_a_real_parquet_footer(tmp_path):
    """Guards the default reader against a duckdb API change."""
    import duckdb

    d = tmp_path / "raw-normalized" / "green" / "2025"
    d.mkdir(parents=True)
    con = duckdb.connect()
    con.execute(f"COPY (SELECT range FROM range(41)) "
                f"TO '{d / 'green_tripdata_2025-01.parquet'}' (FORMAT PARQUET)")
    con.close()

    found = shards.discover(settings_for(tmp_path, types="green"))
    assert [s.rows for s in found] == [41]


def test_order_is_year_major_biggest_year_first():
    items = [
        shards.Shard("green", 2025, 1, 10),
        shards.Shard("fhvhv", 2019, 2, 500),
        shards.Shard("fhvhv", 2019, 1, 400),
        shards.Shard("green", 2025, 2, 20),
    ]
    ordered = shards.order(items)
    # fhvhv 2019 totals 900 vs green 2025's 30, so it goes first, months ascending.
    assert [(s.data_type, s.year, s.month) for s in ordered] == [
        ("fhvhv", 2019, 1), ("fhvhv", 2019, 2),
        ("green", 2025, 1), ("green", 2025, 2),
    ]


def test_order_keeps_a_year_contiguous():
    """Crash recovery is year-granular, so a kill must expose one year, not six."""
    items = [
        shards.Shard("fhvhv", 2020, 1, 100),
        shards.Shard("fhvhv", 2019, 1, 90),
        shards.Shard("fhvhv", 2020, 2, 100),
        shards.Shard("fhvhv", 2019, 2, 90),
    ]
    ordered = shards.order(items)
    assert [s.year for s in ordered] == [2020, 2020, 2019, 2019]


def test_order_of_nothing():
    assert shards.order([]) == []


def test_years_lists_each_type_year_once_in_order():
    items = [
        shards.Shard("green", 2025, 1, 10),
        shards.Shard("fhvhv", 2019, 2, 500),
        shards.Shard("fhvhv", 2019, 1, 400),
    ]
    assert shards.years(items) == [("fhvhv", 2019), ("green", 2025)]


def test_label_is_readable():
    assert shards.Shard("fhvhv", 2019, 3, 1).label == "fhvhv 2019-03"
