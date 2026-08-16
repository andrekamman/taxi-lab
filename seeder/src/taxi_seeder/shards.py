"""What to load, in what order. Pure: no database, no subprocess.

A shard is one (trip type, year, month) -- one normalized parquet file. Shards
write into the existing per-year tables, not a table each: build_copy_sql passes
TABLOCK, which takes a BU lock, and BU locks are compatible with one another, so
several processes may bulk-load different months of one year concurrently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from taxi_seeder.config import Settings

_YEAR_DIR_RE = re.compile(r"\A\d{4}\Z")
_MONTH_RE = re.compile(r"(\d{4})-(\d{2})")


@dataclass(frozen=True)
class Shard:
    data_type: str
    year: int
    month: int
    rows: int          # expected rows, from the parquet footer; drives ordering

    @property
    def label(self) -> str:
        return f"{self.data_type} {self.year}-{self.month:02d}"


def _footer_rows(path: str) -> int:
    import duckdb

    con = duckdb.connect()
    try:
        row = con.execute(
            "SELECT num_rows FROM parquet_file_metadata(?)", [path]
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        con.close()


def discover(settings: Settings, *, footer_reader=None) -> list[Shard]:
    """Every (trip type, year, month) with a normalized parquet file on disk."""
    footer_reader = footer_reader or _footer_rows
    found: list[Shard] = []
    for data_type in settings.types:
        base = settings.raw_normalized_dir / data_type
        if not base.is_dir():
            continue
        for year_dir in sorted(base.iterdir()):
            if not year_dir.is_dir() or not _YEAR_DIR_RE.match(year_dir.name):
                continue
            for path in sorted(year_dir.glob("*.parquet")):
                m = _MONTH_RE.search(path.name)
                if not m:
                    continue
                found.append(Shard(data_type, int(m.group(1)), int(m.group(2)),
                                   footer_reader(str(path))))
    return found


def order(items: list[Shard]) -> list[Shard]:
    """Year-major: biggest year first, months ascending inside it.

    Deliberately not per-shard longest-first. Crash recovery is year-granular --
    a bulk load commits per FLUSH_ROWS and is not atomic, so a killed shard
    leaves orphan rows that only the year-level integrity gate can spot. Keeping
    a year contiguous means the workers finish one before starting the next, so
    a kill exposes one or two years rather than six.
    """
    totals: dict[tuple[str, int], int] = {}
    for s in items:
        totals[(s.data_type, s.year)] = totals.get((s.data_type, s.year), 0) + s.rows
    return sorted(
        items,
        key=lambda s: (-totals[(s.data_type, s.year)], s.data_type, s.year, s.month),
    )


def years(items: list[Shard]) -> list[tuple[str, int]]:
    """Each (trip type, year) once, in the order `order` would load them."""
    seen: list[tuple[str, int]] = []
    for s in order(items):
        key = (s.data_type, s.year)
        if key not in seen:
            seen.append(key)
    return seen
