"""Progress for a run that spends hours inside a single subprocess.

Everything above the Heartbeat class is pure: no clock, no database, no IO.
That is deliberate -- the formatting is the part worth testing, and it is
testable only while it stays free of the thread that drives it.
"""
from __future__ import annotations

import time

from taxi_seeder.config import Settings


def utc_hms(epoch_s: float) -> str:
    return time.strftime("%H:%M:%S", time.gmtime(epoch_s))


def emit(message: str, *, now: str | None = None, out=print) -> None:
    """One progress line. `now` is injectable so tests never touch the clock."""
    stamp = now if now is not None else utc_hms(time.time())
    out(f"[{stamp}] {message}")


def humanize_count(n: int) -> str:
    """Row counts in the billions are unreadable in full, and the exact digit
    never matters in a progress line -- the final report prints it exactly.

    Three significant digits, and `#` keeps the trailing zeros: without it a
    steady rate renders as "2M" one minute and "2.06M" the next, which reads
    like the load fell off a cliff. The rstrip drops the bare trailing point
    `#` leaves on a three-digit value ("100." -> "100").
    """
    for limit, suffix, div in (
        (1_000_000_000, "B", 1_000_000_000.0),
        (1_000_000, "M", 1_000_000.0),
        (1_000, "K", 1_000.0),
    ):
        if n >= limit:
            return f"{n / div:#.3g}".rstrip(".") + suffix
    return str(n)


def humanize_duration(seconds: float) -> str:
    """The largest two units, the smaller one zero-padded so consecutive
    heartbeat lines stay column-aligned."""
    total = int(seconds)
    if total >= 3600:
        return f"{total // 3600}h{(total % 3600) // 60:02d}m"
    if total >= 60:
        return f"{total // 60}m{total % 60:02d}s"
    return f"{total}s"


def rows_per_min(delta_rows: int, delta_s: float) -> float | None:
    if delta_s <= 0:
        return None
    return delta_rows * 60.0 / delta_s


def eta_seconds(remaining: int, per_min: float | None) -> float | None:
    if not per_min or per_min <= 0 or remaining <= 0:
        return None
    return remaining * 60.0 / per_min


def format_progress(label: str, *, rows: int | None, total: int | None,
                    per_min: float | None, elapsed_s: float,
                    unit: str = "rows") -> str:
    """One heartbeat line.

    `unit` exists because mirror has no row count to sample: it counts
    normalized parquet files, and the arithmetic is otherwise identical.
    """
    if rows is None:
        return f"{label}: {unit} unavailable, elapsed {humanize_duration(elapsed_s)}"

    parts = [humanize_count(rows)]
    if total:
        parts[0] += f"/{humanize_count(total)} {unit} ({rows * 100.0 / total:.1f}%)"
    else:
        parts[0] += f" {unit}"
    if per_min:
        parts.append(f"{humanize_count(int(per_min))} {unit}/min")
    parts.append(f"elapsed {humanize_duration(elapsed_s)}")
    remaining = eta_seconds((total or 0) - rows, per_min)
    if remaining is not None:
        parts.append(f"eta {humanize_duration(remaining)}")
    return f"{label}: " + ", ".join(parts)


def _duckdb_footer_rows(paths: list[str]) -> int:
    """Sum num_rows from the parquet footers. Metadata only -- no row scan."""
    import duckdb

    con = duckdb.connect()
    try:
        row = con.execute(
            "SELECT SUM(num_rows) FROM parquet_file_metadata(?)", [paths]
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        con.close()


def expected_rows(settings: Settings, data_type: str, *, reader=None) -> int | None:
    """Total rows the normalized parquet holds for one trip type.

    This is what makes a percentage and an ETA possible at all. None when the
    tree is missing or unreadable -- the heartbeat then simply omits both rather
    than failing.
    """
    reader = reader or _duckdb_footer_rows
    base = settings.raw_normalized_dir / data_type
    if not base.is_dir():
        return None
    paths = [str(p) for p in sorted(base.rglob("*.parquet"))]
    if not paths:
        return None
    try:
        return reader(paths)
    except Exception:
        # The one place this module allows a bare except: the caller is a
        # progress line, the reader is duckdb, and no duckdb failure justifies
        # aborting a 13-hour load.
        return None


def normalized_files(settings: Settings, data_type: str) -> int | None:
    """Normalized parquet files on disk for one trip type -- mirror's sample.

    Mirror has no row count to read: the rows are not in the database yet, and
    the months still to download are not on disk to be counted. The file count
    is the only thing that moves, so the mirror line carries a count and a rate
    but no percentage and no ETA.

    Zero rather than None for an absent directory: a mirror that has not written
    its first file is at zero, which is an observation, not a failure to observe.
    """
    base = settings.raw_normalized_dir / data_type
    try:
        return sum(1 for _ in base.rglob("*.parquet")) if base.is_dir() else 0
    except OSError:
        return None
