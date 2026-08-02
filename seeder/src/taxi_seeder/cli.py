"""The seven-step sequence, and the exit code that summarises it.

Exit codes mirror taxi-seed: 0 clean, 1 needs-review, 2 operational failure.
A step that returns 1 or 2 stops the run -- no type is loaded whose normalize
halted, and no database is backed up whose load failed. Partial progress is
always safe because every step resumes from an observable.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable

from taxi_seeder import backup, mssql, ola, preflight, provision, report, sql, stages
from taxi_seeder.config import ConfigError, from_env

CLEAN = 0
NEEDS_REVIEW = 1
FAILURE = 2

# The image's ENTRYPOINT is ["taxi-seeder"] with the mssql service started via
# depends_on: condition: service_healthy, so with no arg parsing at all,
# `taxi-seeder --help` used to start a real SQL Server and run the live
# seven-step pipeline against whatever data directory was mounted. Parsing
# argv -- and doing it before from_env, which touches the environment, not
# argv -- means -h/--help and unknown flags are handled before anything else
# runs.
_ENV_VARS_HELP = """\
environment variables:
  TAXI_DATA_DIR         bind-mounted data directory (default: /data)
  MSSQL_PASSWORD        SA password (required)
  TAXI_TYPES            comma-separated taxi types to mirror/normalize/load
                        (default: yellow,green,fhv,fhvhv)
  TAXI_RECENT           most recent N months to mirror; blank means full
                        history
  TAXI_DATA_FACTOR      mdf size = normalized parquet bytes x this factor,
                        rounded up to 10 GB (default: 3.0)
  MSSQL_DATA_SIZE_GB    skip the size estimate and use this instead; only
                        consulted at database creation
  MSSQL_LOG_SIZE_GB     ldf size in GB (default: 16)
  MSSQL_FILEGROWTH_MB   data/log filegrowth in MB (default: 1024)
  MSSQL_HOST            SQL Server host (default: mssql, the compose service)
  MSSQL_PORT            SQL Server port (default: 1433)
  MSSQL_DATABASE        database to create and load (default: taxi); must be a
                        plain identifier -- it is interpolated into T-SQL
  MSSQL_SCHEMA          schema holding the loaded tables (default: dbo); same
                        identifier rule
  MSSQL_USER            SQL login (default: sa)
"""


def _build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="taxi-seeder",
        description=(
            "Advance one bind-mounted data directory through mirror, "
            "provision, load, and backup. Configured entirely by "
            "environment variables -- there are no positional or optional "
            "arguments to set here."
        ),
        epilog=_ENV_VARS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def worst(codes: Iterable[int]) -> int:
    return max(codes, default=CLEAN)


def _halt_label(rc: int) -> str:
    """1 is an expected, non-catastrophic halt (e.g. unacknowledged schema
    drift) -- label it distinctly from a genuine operational failure so log
    skimmers don't mistake one for the other."""
    return "needs-review" if rc == NEEDS_REVIEW else "error"


def load_exit_code(child_rc: int) -> int:
    """Translate `taxi-load`'s exit code into this project's contract.

    `taxi-run` returns 1 only for normalize's schema-drift halt -- a decision a
    human genuinely has to make, which is what 1 means here. `taxi-load` returns
    1 for "failed mid-load" (a dropped connection, a duckdb error on one type),
    and taxi-seed's own orchestrator classifies that as PARTIAL and maps it to
    2. Passing it through as 1 tells CI and operators to go inspect a drift
    acknowledgment that does not exist, when a plain re-run is the remedy.
    """
    return FAILURE if child_rc == NEEDS_REVIEW else child_rc


def main(argv=None) -> int:
    # parse_args() itself calls sys.exit(0) after printing help for -h/--help,
    # and sys.exit(2) after printing usage to stderr for an unrecognised
    # argument -- 2 already matches this module's FAILURE convention.
    _build_parser().parse_args(argv)

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
            child_rc = stages.load(settings, data_type)
            rc = load_exit_code(child_rc)
            codes.append(rc)
            if rc != CLEAN:
                detail = (" (failed mid-load -- re-running resumes from the "
                          "manifest)" if rc != child_rc else "")
                print(f"{_halt_label(rc)}: load stage for {data_type} exited "
                      f"{child_rc}{detail}; stopping", file=sys.stderr)
                return worst(codes)

        backup.run(settings)

    except (mssql.MssqlError, sql.SqlIdentifierError, ola.OlaScriptMissingError,
            stages.StageCommandNotFoundError) as e:
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
