import json
import pytest
from pathlib import Path

import duckdb

from k6_loadtest.data_export import export_chunks, get_schema


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_parquet(tmp_path):
    """Create a small parquet file for testing."""
    db = duckdb.connect()
    db.sql(f"""
        COPY (
            SELECT
                '2026-01-15 08:30:00'::TIMESTAMP AS tpep_pickup_datetime,
                '2026-01-15 09:15:00'::TIMESTAMP AS tpep_dropoff_datetime,
                2::INTEGER AS passenger_count,
                3.4::DOUBLE AS trip_distance,
                15.50::DOUBLE AS fare_amount,
                3.00::DOUBLE AS tip_amount
            FROM range(25)
        ) TO '{tmp_path}/test.parquet' (FORMAT PARQUET)
    """)
    return tmp_path


def test_export_chunks_creates_files(sample_parquet, tmp_path):
    output_dir = tmp_path / "output"
    columns = {
        "pickup_time": "tpep_pickup_datetime",
        "dropoff_time": "tpep_dropoff_datetime",
        "passenger_count": "passenger_count",
        "trip_distance": "trip_distance",
        "fare_amount": "fare_amount",
        "tip_amount": "tip_amount",
    }
    num_chunks = export_chunks(
        parquet_glob=str(sample_parquet / "*.parquet"),
        columns=columns,
        chunk_size=10,
        output_dir=output_dir / "yellow_trips",
    )
    assert num_chunks == 3  # 25 rows / 10 per chunk = 3 chunks
    assert (output_dir / "yellow_trips" / "chunk_0000.json").exists()
    assert (output_dir / "yellow_trips" / "chunk_0001.json").exists()
    assert (output_dir / "yellow_trips" / "chunk_0002.json").exists()


def test_export_chunks_json_format(sample_parquet, tmp_path):
    output_dir = tmp_path / "output"
    columns = {
        "pickup_time": "tpep_pickup_datetime",
        "fare_amount": "fare_amount",
    }
    export_chunks(
        parquet_glob=str(sample_parquet / "*.parquet"),
        columns=columns,
        chunk_size=100,
        output_dir=output_dir / "data",
    )
    with open(output_dir / "data" / "chunk_0000.json") as f:
        rows = json.load(f)
    assert len(rows) == 25
    assert "pickup_time" in rows[0]
    assert "fare_amount" in rows[0]
    # Should only have mapped columns, not originals
    assert "tpep_pickup_datetime" not in rows[0]


def test_export_chunks_max_rows(sample_parquet, tmp_path):
    output_dir = tmp_path / "output"
    columns = {
        "pickup_time": "tpep_pickup_datetime",
        "fare_amount": "fare_amount",
    }
    num_chunks = export_chunks(
        parquet_glob=str(sample_parquet / "*.parquet"),
        columns=columns,
        chunk_size=10,
        output_dir=output_dir / "data",
        max_rows=15,
    )
    assert num_chunks == 2  # 15 rows / 10 per chunk = 2 chunks
    with open(output_dir / "data" / "chunk_0000.json") as f:
        rows0 = json.load(f)
    with open(output_dir / "data" / "chunk_0001.json") as f:
        rows1 = json.load(f)
    assert len(rows0) == 10
    assert len(rows1) == 5


def test_export_chunks_no_matching_files(tmp_path):
    with pytest.raises(FileNotFoundError, match="No parquet files"):
        export_chunks(
            parquet_glob=str(tmp_path / "nonexistent" / "*.parquet"),
            columns={"a": "b"},
            chunk_size=10,
            output_dir=tmp_path / "output",
        )


def test_get_schema(sample_parquet):
    schema = get_schema(str(sample_parquet / "*.parquet"))
    assert "tpep_pickup_datetime" in schema
    assert "TIMESTAMP" in schema["tpep_pickup_datetime"].upper()


# --- DECIMAL handling -------------------------------------------------------
#
# The checked-in fixture uses DECIMAL columns while the tmp_path fixture above
# uses DOUBLE, so until these tests existed the DECIMAL path was never exercised
# and export_chunks raised "Object of type Decimal is not JSON serializable" on
# the repo's own sample.parquet.


@pytest.fixture
def decimal_parquet(tmp_path):
    """Parquet whose DECIMAL values have no exact binary floating-point form."""
    db = duckdb.connect()
    db.sql(f"""
        COPY (
            SELECT * FROM (VALUES
                (15.10::DECIMAL(4,2), 0.29::DECIMAL(3,2)),
                (8.15::DECIMAL(4,2),  2.67::DECIMAL(3,2)),
                (1234.56::DECIMAL(6,2), 0.10::DECIMAL(3,2))
            ) AS t(fare_amount, tip_amount)
        ) TO '{tmp_path}/decimal.parquet' (FORMAT PARQUET)
    """)
    return tmp_path


def test_export_chunks_serializes_decimal_exactly(decimal_parquet, tmp_path):
    output_dir = tmp_path / "output"
    export_chunks(
        parquet_glob=str(decimal_parquet / "*.parquet"),
        columns={"fare_amount": "fare_amount", "tip_amount": "tip_amount"},
        chunk_size=10,
        output_dir=output_dir / "data",
    )
    with open(output_dir / "data" / "chunk_0000.json") as f:
        rows = json.load(f)

    # Strings, not JSON numbers: k6's JSON.parse would turn a number into a
    # double, losing the exact value before it is bound to a DECIMAL column.
    assert [r["fare_amount"] for r in rows] == ["15.10", "8.15", "1234.56"]
    assert [r["tip_amount"] for r in rows] == ["0.29", "2.67", "0.10"]
    for row in rows:
        for value in row.values():
            assert isinstance(value, str)


def test_export_chunks_preserves_decimal_scale(decimal_parquet, tmp_path):
    """Trailing zeros survive: 0.10 must not collapse to 0.1."""
    output_dir = tmp_path / "output"
    export_chunks(
        parquet_glob=str(decimal_parquet / "*.parquet"),
        columns={"tip_amount": "tip_amount"},
        chunk_size=10,
        output_dir=output_dir / "data",
    )
    with open(output_dir / "data" / "chunk_0000.json") as f:
        rows = json.load(f)
    assert rows[2]["tip_amount"] == "0.10"


def test_export_chunks_from_checked_in_fixture(tmp_path):
    """The DECIMAL-typed sample.parquet must round-trip, not raise."""
    output_dir = tmp_path / "output"
    num_chunks = export_chunks(
        parquet_glob=str(FIXTURES / "sample.parquet"),
        columns={
            "pickup_time": "tpep_pickup_datetime",
            "trip_distance": "trip_distance",
            "fare_amount": "fare_amount",
            "tip_amount": "tip_amount",
        },
        chunk_size=100,
        output_dir=output_dir / "data",
    )
    assert num_chunks == 1
    with open(output_dir / "data" / "chunk_0000.json") as f:
        rows = json.load(f)
    assert len(rows) == 2
    assert rows[0]["fare_amount"] == "12.50"
    assert rows[0]["tip_amount"] == "2.50"
    assert rows[0]["trip_distance"] == "3.5"
    # Timestamps still serialize as ISO 8601 alongside the decimals.
    assert rows[0]["pickup_time"] == "2024-01-01T08:00:00"
