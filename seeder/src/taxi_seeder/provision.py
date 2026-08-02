"""Step 3: create the presized database, or explain why it was skipped."""
from __future__ import annotations

from taxi_seeder import mssql, sizing, sql
from taxi_seeder.config import Settings


def implied_data_mb(settings: Settings) -> int:
    """The mdf size this run's scope implies, in MB."""
    if settings.data_size_gb is not None:
        return settings.data_size_gb * 1024
    measured = sizing.parquet_bytes(settings.raw_normalized_dir, settings.types)
    return sizing.data_size_mb(measured, settings.data_factor)


def _allocated_mb(settings: Settings, runner) -> int:
    raw = mssql.scalar(settings, sql.data_file_size_mb(settings.database),
                       database="master", runner=runner)
    try:
        return int(raw) if raw is not None else 0
    except ValueError:
        return 0


def _attach(settings: Settings, runner) -> None:
    print(
        f"provision: {settings.database!r} is not registered on this server, but "
        f"{settings.mdf_path} already exists -- attaching the existing files "
        f"instead of creating new ones"
    )
    mssql.run(
        settings,
        sql.attach_database(settings.database, str(settings.mdf_path),
                            str(settings.ldf_path)),
        database="master", runner=runner,
    )


def run(settings: Settings, *, runner=None) -> bool:
    """Create or attach the database if absent. True when it did either.

    The attach branch is the warm-start path: the mdf/ldf live on the bind mount
    and survive `docker compose down`, but the system databases that record them
    live in the container. Creating over an existing file fails with Msg 5170
    and keeps failing on every subsequent run, so an orphaned mdf is attached,
    not recreated.
    """
    exists = mssql.scalar(settings, sql.database_exists(settings.database),
                          database="master", runner=runner) == "1"

    data_mb = implied_data_mb(settings)

    if exists:
        allocated = _allocated_mb(settings, runner)
        if sizing.needs_growth_warning(data_mb, allocated):
            print(
                f"provision: WARNING database {settings.database!r} already exists with "
                f"{allocated / 1024:.0f} GB allocated, but this run's scope implies "
                f"{data_mb / 1024:.0f} GB.\n"
                f"           Sizing only runs at creation, so the file will autogrow in "
                f"{settings.filegrowth_mb} MB steps -- the fragmentation presizing exists "
                f"to avoid.\n"
                f"           Set MSSQL_DATA_SIZE_GB on a fresh database, or "
                f"re-presize: run DROP DATABASE [{settings.database}], then delete "
                f"{settings.mdf_path} and {settings.ldf_path}, then re-run to "
                f"re-presize and reload from parquet.\n"
                f"           Deleting the files first is not enough -- the server "
                f"still has {settings.database!r} registered, so the next run skips "
                f"provisioning and then fails reading the file sizes of a database "
                f"it cannot open."
            )
        else:
            print(f"provision: database {settings.database!r} exists, skipping")
        return False

    if settings.mdf_path.exists():
        _attach(settings, runner)
        mssql.run(settings, sql.set_recovery_simple(settings.database),
                  database="master", runner=runner)
        return True

    log_mb = sizing.log_size_mb(settings.log_size_gb)
    print(
        f"provision: creating {settings.database!r} with "
        f"{data_mb / 1024:.0f} GB data + {log_mb / 1024:.0f} GB log"
    )
    mssql.run(
        settings,
        sql.create_database(
            settings.database, str(settings.mdf_path), str(settings.ldf_path),
            data_mb, log_mb, settings.filegrowth_mb,
        ),
        database="master", runner=runner,
    )
    mssql.run(settings, sql.set_recovery_simple(settings.database),
              database="master", runner=runner)
    return True
