"""Virtual clock for the simulated FL host.

While a Host is active, time.monotonic / time.time / time.perf_counter (and the *_ns variants) return virtual time and
time.sleep does not block: it advances the clock and is recorded, so a script that sleeps in OnInit shows up in the
trace (O-12: the stock init animation blocks FL's main thread for 2.92 s).
"""
from __future__ import annotations

import time as _real_time
from typing import Callable, NamedTuple, Optional


class SleepRecord(NamedTuple):
    t: float            # virtual time before the sleep
    seconds: float
    script: Optional[str]
    callback: Optional[str]


class VirtualClock:
    def __init__(self, start: float = 1000.0, wall_start: float = 1_800_000_000.0):
        self.now = float(start)
        self._wall_offset = wall_start - start
        self.sleeps: list[SleepRecord] = []
        self.slept_total = 0.0
        self.context: Callable[[], tuple] = lambda: (None, None)   # -> (script role, callback name)
        self.on_sleep: Optional[Callable[[float], None]] = None     # hook for the Host trace

    # ---- the functions patched into the time module ------------------------------------------------------------
    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return self.now + self._wall_offset

    def sleep(self, seconds) -> None:
        if not isinstance(seconds, (int, float)):
            raise TypeError("sleep length must be a non-negative number, not %s" % type(seconds).__name__)
        if seconds < 0:
            raise ValueError("sleep length must be non-negative")
        script, cb = self.context()
        self.sleeps.append(SleepRecord(self.now, float(seconds), script, cb))
        self.slept_total += seconds
        if self.on_sleep is not None:
            self.on_sleep(float(seconds))
        self.now += seconds

    # ---- for drivers / tests ------------------------------------------------------------------------------------
    def advance(self, seconds: float) -> None:
        """Let time pass without a sleep (FL doing other work between callbacks)."""
        if seconds < 0:
            raise ValueError("cannot go back in time")
        self.now += seconds

    def sleeps_in(self, callback: str) -> list[SleepRecord]:
        return [s for s in self.sleeps if s.callback == callback]

    def patched_functions(self) -> dict:
        m = self.monotonic
        return {
            "monotonic": m, "perf_counter": m, "time": self.time, "sleep": self.sleep,
            "monotonic_ns": lambda: int(self.now * 1e9), "perf_counter_ns": lambda: int(self.now * 1e9),
            "time_ns": lambda: int(self.time() * 1e9),
        }


class TimePatch:
    """Patch/restore the real time module's clock functions (re-entrant safe: refuses double patching)."""

    def __init__(self, clock: VirtualClock):
        self.clock = clock
        self._saved: dict = {}

    def __enter__(self):
        if self._saved:
            raise RuntimeError("time already patched")
        for name, fn in self.clock.patched_functions().items():
            if hasattr(_real_time, name):
                self._saved[name] = getattr(_real_time, name)
                setattr(_real_time, name, fn)
        return self

    def __exit__(self, *exc):
        for name, fn in self._saved.items():
            setattr(_real_time, name, fn)
        self._saved.clear()
        return False
