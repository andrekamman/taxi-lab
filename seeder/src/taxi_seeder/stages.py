"""Steps 2 and 5: shell out to taxi-seed's CLIs.

Coupled to the documented interface and exit codes, not to taxi-seed internals.
"""
from __future__ import annotations

import os
import subprocess

from taxi_seeder.config import Settings


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


def load_cmd(settings: Settings, data_type: str) -> list[str]:
    return [
        "taxi-load", data_type,
        "--data-dir", str(settings.data_dir),
        "--host", settings.host,
        "--port", str(settings.port),
        "--database", settings.database,
        "--schema", settings.schema,
        "--user", settings.user,
    ]


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
