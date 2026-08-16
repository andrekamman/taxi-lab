"""Progress for a run that spends hours inside a single subprocess.

Everything above the Heartbeat class is pure: no clock, no database, no IO.
That is deliberate -- the formatting is the part worth testing, and it is
testable only while it stays free of the thread that drives it.
"""
from __future__ import annotations

import time


def utc_hms(epoch_s: float) -> str:
    return time.strftime("%H:%M:%S", time.gmtime(epoch_s))


def emit(message: str, *, now: str | None = None, out=print) -> None:
    """One progress line. `now` is injectable so tests never touch the clock."""
    stamp = now if now is not None else utc_hms(time.time())
    out(f"[{stamp}] {message}")
