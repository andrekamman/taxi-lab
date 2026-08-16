"""Step 1: make /data safe to work in, then prove SQL Server accepts a login."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from taxi_seeder import mssql
from taxi_seeder.config import DATA_TYPES, Settings

BAKED_MAPPINGS_DIR = Path("/opt/taxi-seed/mappings")


class TaxiLoadTooOldError(Exception):
    """The installed taxi-load predates --month. Maps to exit code 2."""


def _default_helper(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def taxi_load_supports_months(*, helper=None) -> bool:
    """Whether the installed taxi-load can load a single (year, month).

    Asked once, from the help text, because the alternative is discovering it
    once per shard as an argparse error after the fan-out has already started.
    """
    helper = helper or _default_helper
    try:
        proc = helper(["taxi-load", "--help"])
    except OSError:
        return False
    return "--month" in (proc.stdout or "") + (proc.stderr or "")


def require_month_support(*, helper=None) -> None:
    """Fail fast, and say what to do about it."""
    if taxi_load_supports_months(helper=helper):
        return None
    raise TaxiLoadTooOldError(
        "the installed taxi-load has no --month option, so the loader cannot "
        "fan out across month shards. Install a taxi-seed release that "
        "includes --year/--month (and rebuild the seeder image), or pin the "
        "seeder to a revision that loads serially."
    )


def ensure_directories(settings: Settings) -> None:
    for d in (
        settings.data_dir / "raw",
        settings.raw_normalized_dir,
        settings.mssql_data_dir,
        settings.mssql_log_dir,
        settings.backup_dir,
        settings.data_dir / "normalize" / "mappings",
    ):
        d.mkdir(parents=True, exist_ok=True)


def seed_mappings(settings: Settings,
                  baked_dir: Path = BAKED_MAPPINGS_DIR) -> list[str]:
    """Copy pristine mappings onto the volume, never overwriting existing ones.

    `normalize` resolves mappings from the relative path
    normalize/mappings/<type>.yaml and amends them on schema drift. They live on
    the volume so those amendments survive the container; overwriting one would
    discard a drift acknowledgment and re-halt every run.
    """
    target_dir = settings.data_dir / "normalize" / "mappings"
    target_dir.mkdir(parents=True, exist_ok=True)
    if not baked_dir.is_dir():
        return []

    copied: list[str] = []
    for data_type in DATA_TYPES:
        source = baked_dir / f"{data_type}.yaml"
        target = target_dir / f"{data_type}.yaml"
        if source.is_file() and not target.exists():
            shutil.copyfile(source, target)
            copied.append(data_type)
    return copied


def run(settings: Settings, *, baked_dir: Path = BAKED_MAPPINGS_DIR,
        runner=None) -> None:
    ensure_directories(settings)
    copied = seed_mappings(settings, baked_dir=baked_dir)
    if copied:
        print(f"preflight: seeded mappings for {', '.join(copied)}")
    print(f"preflight: waiting for {settings.host}:{settings.port} to accept a login")
    mssql.wait_for_login(settings, runner=runner)
    print("preflight: SQL Server is reachable")
