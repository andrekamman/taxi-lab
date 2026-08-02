"""Turn normalized-parquet bytes into SQL Server file sizes. Pure arithmetic."""
from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path

GB = 1024 ** 3
GRANULARITY_GB = 10
WARN_THRESHOLD = 1.25


def parquet_bytes(root: Path, types: Iterable[str]) -> int:
    """Total bytes of *.parquet under root/<type>/ for the selected types only.

    Only the selected types are summed: the directory may still hold types from
    an earlier, broader run, and only these types will reach the database.
    """
    total = 0
    for data_type in types:
        type_dir = root / data_type
        if not type_dir.is_dir():
            continue
        for f in type_dir.rglob("*.parquet"):
            total += f.stat().st_size
    return total


def data_size_mb(parquet_bytes: int, factor: float,
                 granularity_gb: int = GRANULARITY_GB) -> int:
    """Estimated mdf size in MB, rounded up to the next granularity boundary.

    Floors at one granule so a tiny or empty mirror still gets a usable file.
    """
    raw_gb = parquet_bytes * factor / GB
    granules = max(1, math.ceil(raw_gb / granularity_gb))
    return granules * granularity_gb * 1024


def log_size_mb(log_size_gb: int) -> int:
    return log_size_gb * 1024


def needs_growth_warning(implied_mb: int, allocated_mb: int,
                         threshold: float = WARN_THRESHOLD) -> bool:
    """True when the existing mdf is materially smaller than this run implies.

    allocated_mb == 0 means the allocation could not be read; stay silent rather
    than warn on missing information.
    """
    if allocated_mb <= 0:
        return False
    return implied_mb > allocated_mb * threshold
