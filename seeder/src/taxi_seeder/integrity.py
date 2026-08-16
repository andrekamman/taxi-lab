"""Make every year table consistent with its manifest, before any fan-out.

Month shards load into shared per-year tables, so no worker may issue DDL that a
sibling could be loading through. taxi-seed's guard_month_mode refuses to run a
RELOAD plan under --month for exactly that reason. This module is what makes
that refusal never fire: it resets any year that fails the integrity gate first,
serially, while nothing else is running.

This is the only component permitted to truncate.
"""
from __future__ import annotations

from taxi_seeder import mssql, shards, sql
from taxi_seeder.config import Settings


def reset_inconsistent_years(settings: Settings, items: list[shards.Shard],
                             *, runner=None) -> list[tuple[str, int]]:
    """Truncate + clear the manifest for every inconsistent year. Returns them."""
    if not items:
        return []

    wanted = shards.years(items)
    reset: list[tuple[str, int]] = []
    for data_type in sorted({dt for dt, _ in wanted}):
        out = mssql.run(settings, sql.inconsistent_years(settings.schema, data_type),
                        database=settings.database, runner=runner)
        for line in out.splitlines():
            line = line.strip()
            if not line or not line.isdigit():
                continue
            year = int(line)
            # The server may hold years this run is not loading; they are not
            # this run's business to truncate.
            if (data_type, year) not in wanted:
                continue
            mssql.run(settings, sql.reset_year(settings.schema, data_type, year),
                      database=settings.database, runner=runner)
            print(f"integrity: {data_type} {year} disagreed with the manifest; "
                  f"truncated for a clean reload")
            reset.append((data_type, year))
    return reset
