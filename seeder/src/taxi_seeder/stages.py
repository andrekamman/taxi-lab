"""Steps 2 and 5: shell out to taxi-seed's CLIs.

Coupled to the documented interface and exit codes, not to taxi-seed internals.
"""
from __future__ import annotations

import os
import subprocess

from taxi_seeder.config import Settings


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
    proc = runner(cmd, env, str(settings.data_dir))
    return proc.returncode


def mirror(settings: Settings, data_type: str, *, runner=None) -> int:
    return run(mirror_cmd(settings, data_type), settings, runner=runner)


def load(settings: Settings, data_type: str, *, runner=None) -> int:
    return run(load_cmd(settings, data_type), settings, runner=runner)
