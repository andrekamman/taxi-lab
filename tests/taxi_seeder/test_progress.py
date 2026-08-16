"""Progress formatting and the heartbeat that drives it.

Nothing here waits on wall time: every collaborator that would -- the clock, the
sleeper, the sampler -- is injected, which is the reason progress.py splits pure
formatting from the thread in the first place.
"""
import pytest

from taxi_seeder import progress


def test_utc_hms_formats_epoch_as_utc_clock_time():
    # 2026-08-15T07:13:42Z
    assert progress.utc_hms(1786778022.0) == "07:13:42"


def test_emit_prefixes_a_utc_timestamp():
    written = []
    progress.emit("load fhvhv: starting", now="07:13:42", out=written.append)
    assert written == ["[07:13:42] load fhvhv: starting"]


@pytest.mark.parametrize("n,expected", [
    (0, "0"), (495, "495"), (34_622_078, "34.6M"),
    (1_607_275_004, "1.61B"), (83_295, "83.3K"),
    # Three significant digits, trailing zeros kept: a heartbeat whose rate
    # alternates between "2M" and "2.06M" reads as though the rate collapsed.
    (10_000_000, "10.0M"), (2_000_000, "2.00M"), (100_000_000, "100M"),
])
def test_humanize_count(n, expected):
    assert progress.humanize_count(n) == expected


@pytest.mark.parametrize("seconds,expected", [
    (5, "5s"), (90, "1m30s"), (764 * 60, "12h44m"), (0, "0s"),
    # Zero-padded below the leading unit, so consecutive lines stay aligned.
    (60, "1m00s"), (1020, "17m00s"), (3600, "1h00m"),
])
def test_humanize_duration(seconds, expected):
    assert progress.humanize_duration(seconds) == expected


def test_rows_per_min_is_none_without_elapsed_time():
    assert progress.rows_per_min(1000, 0) is None


def test_rows_per_min_scales_to_a_minute():
    assert progress.rows_per_min(4_114_432, 120.0) == pytest.approx(2_057_216)


def test_eta_seconds_is_none_without_a_rate():
    assert progress.eta_seconds(1000, None) is None
    assert progress.eta_seconds(1000, 0) is None


def test_eta_seconds_divides_remaining_by_rate():
    assert progress.eta_seconds(2_000_000, 1_000_000) == pytest.approx(120.0)


def test_format_progress_with_everything_known():
    line = progress.format_progress(
        "load fhvhv", rows=34_622_078, total=1_607_275_004,
        per_min=2_057_216, elapsed_s=1020,
    )
    assert line == (
        "load fhvhv: 34.6M/1.61B rows (2.2%), 2.06M rows/min, "
        "elapsed 17m00s, eta 12h44m"
    )


def test_format_progress_without_a_total_omits_percent_and_eta():
    line = progress.format_progress(
        "load fhvhv", rows=34_622_078, total=None,
        per_min=2_057_216, elapsed_s=1020,
    )
    assert line == "load fhvhv: 34.6M rows, 2.06M rows/min, elapsed 17m00s"


def test_format_progress_survives_an_unknown_sample():
    line = progress.format_progress(
        "load fhvhv", rows=None, total=None, per_min=None, elapsed_s=30,
    )
    assert line == "load fhvhv: rows unavailable, elapsed 30s"


def test_format_progress_counts_a_caller_supplied_unit():
    """Mirror has no row count to sample -- it counts normalized files."""
    line = progress.format_progress(
        "mirror yellow", rows=37, total=None, per_min=12, elapsed_s=60,
        unit="files",
    )
    assert line == "mirror yellow: 37 files, 12 files/min, elapsed 1m00s"


def test_format_progress_names_the_unit_when_the_sample_is_unknown():
    line = progress.format_progress(
        "mirror yellow", rows=None, total=None, per_min=None, elapsed_s=30,
        unit="files",
    )
    assert line == "mirror yellow: files unavailable, elapsed 30s"
