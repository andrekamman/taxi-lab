"""Step 4: install Ola Hallengren's MaintenanceSolution into master, once."""
from __future__ import annotations

import tempfile
from pathlib import Path

from taxi_seeder import mssql, sql
from taxi_seeder.config import Settings


def _resolve_vendored_script() -> Path:
    """seeder/sql is force-included into the wheel as taxi_seeder/sql (see
    pyproject.toml), so in a built wheel -- and thus in the container image,
    which installs the wheel, not an editable checkout -- this module and the
    vendored script are siblings on disk.

    hatchling's default *editable* dev install (what `uv sync` gives this
    repo) instead just points the taxi_seeder import straight at
    seeder/src/taxi_seeder without materializing force-included files there,
    so the sibling path doesn't exist locally. Empirically verified: building
    a real wheel and `pip install`-ing it non-editably resolves the sibling
    path with VENDORED_SCRIPT.is_file() == True; under `uv sync` it's False.
    Fall back to the repo-relative path so local dev and tests work too.
    """
    sibling = Path(__file__).resolve().parent / "sql" / "MaintenanceSolution.sql"
    if sibling.is_file():
        return sibling
    # seeder/src/taxi_seeder/ola.py -> parents[2] == seeder/
    return Path(__file__).resolve().parents[2] / "sql" / "MaintenanceSolution.sql"


VENDORED_SCRIPT = _resolve_vendored_script()


def is_installed(settings: Settings, *, runner=None) -> bool:
    return mssql.scalar(settings, sql.ola_installed(),
                        database="master", runner=runner) == "1"


def run(settings: Settings, *, script: Path = VENDORED_SCRIPT, runner=None) -> bool:
    """Install if dbo.DatabaseBackup is absent. Returns True when it installed."""
    if is_installed(settings, runner=runner):
        print("ola: MaintenanceSolution already installed, skipping")
        return False

    patched = sql.prepare_maintenance_solution(
        Path(script).read_text(), str(settings.backup_dir)
    )
    # sqlcmd -i is required: the script is batch-separated by GO, which only the
    # client understands. The patched copy is temporary; the vendored file on
    # disk stays pristine and diffable against upstream.
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as fh:
        fh.write(patched)
        temp_path = fh.name
    try:
        print("ola: installing MaintenanceSolution (@CreateJobs = 'N')")
        mssql.run_file(settings, temp_path, database="master", runner=runner)
    finally:
        Path(temp_path).unlink(missing_ok=True)
    return True
