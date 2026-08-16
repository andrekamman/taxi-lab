"""Steps 2 and 5: shell out to taxi-seed's CLIs.

Coupled to the documented interface and exit codes, not to taxi-seed internals.
"""
from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from taxi_seeder.config import Settings
from taxi_seeder.shards import Shard


class StageCommandNotFoundError(Exception):
    """A taxi-seed CLI is not on PATH. Maps to exit code 2."""


def _default_runner(cmd, env, cwd):
    return subprocess.run(cmd, env=env, cwd=cwd, check=False)


def mirror_cmd(settings: Settings, data_type: str) -> list[str]:
    """download -> normalize for one type. Deliberately no --load: the database
    must be created presized first, and taxi-run's own ensure_database would
    create it with server-default paths and sizes."""
    cmd = ["taxi-run", data_type, "--data-dir", str(settings.data_dir)]
    if settings.recent is not None:
        cmd += ["--recent", str(settings.recent)]
    return cmd


def load_cmd(settings: Settings, data_type: str, *, year: int | None = None,
             month: int | None = None) -> list[str]:
    cmd = [
        "taxi-load", data_type,
        "--data-dir", str(settings.data_dir),
        "--host", settings.host,
        "--port", str(settings.port),
        "--database", settings.database,
        "--schema", settings.schema,
        "--user", settings.user,
    ]
    if year is not None:
        cmd += ["--year", str(year)]
    if month is not None:
        cmd += ["--month", str(month)]
    return cmd


def run(cmd: list[str], settings: Settings, *, runner=None) -> int:
    runner = runner or _default_runner
    # CWD is the data dir because `normalize` resolves its mappings from the
    # relative path normalize/mappings/<type>.yaml.
    env = {**os.environ, "MSSQL_PASSWORD": settings.password}
    try:
        proc = runner(cmd, env, str(settings.data_dir))
    except FileNotFoundError as e:
        # subprocess.run raises this when the executable is not on PATH. Untyped
        # it escapes cli.main's exception-to-exit-code mapping as a traceback
        # with Python's exit code 1 -- which this project reserves for
        # needs-review. Same hardening ola.py already has.
        raise StageCommandNotFoundError(
            f"{cmd[0]!r} is not on PATH. The seeder image installs taxi-seed's "
            f"CLIs; a run outside that image needs `uv sync` (or an equivalent "
            f"install of taxi-seed) first."
        ) from e
    return proc.returncode


def mirror(settings: Settings, data_type: str, *, runner=None) -> int:
    return run(mirror_cmd(settings, data_type), settings, runner=runner)


def load(settings: Settings, data_type: str, *, runner=None) -> int:
    return run(load_cmd(settings, data_type), settings, runner=runner)


def load_shard(settings: Settings, shard: Shard, *, runner=None) -> int:
    return run(load_cmd(settings, shard.data_type, year=shard.year,
                        month=shard.month), settings, runner=runner)


def load_concurrent(settings: Settings, items, *, workers: int,
                    runner=None, on_done=None) -> list[tuple[Shard, int]]:
    """Load every shard with at most `workers` concurrent taxi-load processes.

    Threads here only supervise subprocesses -- they block in subprocess.run and
    release the GIL. The parallelism is process-level, which is forced: the
    duckdb mssql extension keeps its ATTACH context process-global, so two loads
    in one process would collide on it.

    A shard that raises is recorded as exit 2 rather than propagated, so one bad
    month cannot abandon its siblings. The next run's integrity pre-pass resets
    whatever year was left half-loaded.
    """
    if not items:
        return []

    def one(shard: Shard) -> tuple[Shard, int]:
        try:
            rc = load_shard(settings, shard, runner=runner)
        except StageCommandNotFoundError:
            # Not a shard problem: every shard would hit it, and cli.main
            # already maps it to exit 2 with an actionable message.
            raise
        except Exception as e:                       # noqa: BLE001 -- see docstring
            print(f"error: load stage for {shard.label} crashed: {e}",
                  file=sys.stderr)
            rc = 2
        if on_done is not None:
            on_done(shard, rc)
        return shard, rc

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, items))
