"""Progress formatting and the heartbeat that drives it.

Nothing here waits on wall time: every collaborator that would -- the clock, the
sleeper, the sampler -- is injected, which is the reason progress.py splits pure
formatting from the thread in the first place.
"""
from taxi_seeder import progress


def test_utc_hms_formats_epoch_as_utc_clock_time():
    # 2026-08-15T07:13:42Z
    assert progress.utc_hms(1786778022.0) == "07:13:42"


def test_emit_prefixes_a_utc_timestamp():
    written = []
    progress.emit("load fhvhv: starting", now="07:13:42", out=written.append)
    assert written == ["[07:13:42] load fhvhv: starting"]
