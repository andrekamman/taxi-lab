"""Step 6: take a verified compressed FULL backup, but only when stale."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from taxi_seeder import mssql, sql
from taxi_seeder.config import Settings


def newest_backup(settings: Settings) -> Path | None:
    """The most recent .bak anywhere under the Ola directory root.

    Searched recursively rather than at a fixed path because Ola's layout is
    <Directory>/<@@SERVERNAME>/<database>/<type>/, and the server name is the
    container hostname.
    """
    if not settings.backup_dir.is_dir():
        return None
    baks = list(settings.backup_dir.rglob("*.bak"))
    if not baks:
        return None
    return max(baks, key=lambda p: p.stat().st_mtime)


def backup_mtime(path: Path) -> datetime | None:
    if path is None:
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def max_loaded_at(settings: Settings, *, runner=None) -> datetime | None:
    """Newest loaded_at in taxi-seed's _load_manifest, as an aware UTC datetime.

    Returns None when the table does not exist yet (nothing has ever been
    loaded) or when it is empty.
    """
    try:
        raw = mssql.scalar(settings, sql.max_loaded_at(settings.schema),
                           database=settings.database, runner=runner)
    except mssql.MssqlError:
        return None
    if not raw:
        return None
    # loaded_at is written with SYSUTCDATETIME(); style 126 gives naive ISO-8601.
    return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)


def is_stale(max_loaded_at: datetime | None,
             newest_backup_mtime: datetime | None) -> bool:
    """Should this run take a backup?

    No .bak at all -> always, so a successful run never leaves the deliverable
    set incomplete. Otherwise back up only when a load is newer than the backup;
    that is what catches a previous run that loaded rows and then died before
    backing up.
    """
    if newest_backup_mtime is None:
        return True
    if max_loaded_at is None:
        return False
    return max_loaded_at > newest_backup_mtime


def run(settings: Settings, *, runner=None) -> bool:
    """Back up when stale. Returns True when a backup was taken."""
    loaded_at = max_loaded_at(settings, runner=runner)
    existing = newest_backup(settings)
    existing_mtime = backup_mtime(existing) if existing else None

    if not is_stale(loaded_at, existing_mtime):
        print(f"backup: current ({existing.name}), skipping")
        return False

    print(f"backup: taking a verified compressed FULL backup to {settings.backup_dir}")
    mssql.run(settings, sql.database_backup(settings.database, str(settings.backup_dir)),
              database="master", runner=runner)
    return True
