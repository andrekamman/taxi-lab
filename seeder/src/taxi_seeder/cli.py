"""The seven-step sequence, and the exit code that summarises it.

Exit codes mirror taxi-seed: 0 clean, 1 needs-review, 2 operational failure.
A step that returns 1 or 2 stops the run -- no type is loaded whose normalize
halted, and no database is backed up whose load failed. Partial progress is
always safe because every step resumes from an observable.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Iterable

from taxi_seeder import backup, mssql, ola, preflight, provision, report, sql, stages
from taxi_seeder.config import ConfigError, from_env

CLEAN = 0
NEEDS_REVIEW = 1
FAILURE = 2


def worst(codes: Iterable[int]) -> int:
    return max(codes, default=CLEAN)


def _halt_label(rc: int) -> str:
    """1 is an expected, non-catastrophic halt (e.g. unacknowledged schema
    drift) -- label it distinctly from a genuine operational failure so log
    skimmers don't mistake one for the other."""
    return "needs-review" if rc == NEEDS_REVIEW else "error"


def main(argv=None) -> int:
    try:
        settings = from_env(os.environ)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return FAILURE

    codes: list[int] = []
    try:
        preflight.run(settings)

        for data_type in settings.types:
            rc = stages.mirror(settings, data_type)
            codes.append(rc)
            if rc != CLEAN:
                print(f"{_halt_label(rc)}: mirror stage for {data_type} exited {rc}; "
                      f"stopping", file=sys.stderr)
                return worst(codes)

        provision.run(settings)
        ola.run(settings)

        for data_type in settings.types:
            rc = stages.load(settings, data_type)
            codes.append(rc)
            if rc != CLEAN:
                print(f"{_halt_label(rc)}: load stage for {data_type} exited {rc}; "
                      f"stopping", file=sys.stderr)
                return worst(codes)

        backup.run(settings)

    except (mssql.MssqlError, sql.SqlIdentifierError, ola.OlaScriptMissingError) as e:
        print(f"error: {e}", file=sys.stderr)
        return FAILURE

    print(report.render(
        settings,
        backup_path=backup.newest_backup(settings),
        rows_by_type=report.loaded_rows(settings),
    ))
    return worst(codes)


if __name__ == "__main__":
    sys.exit(main())
