"""Drives a booted ScriptSet over virtual time the way FL does: OnIdle at a fixed rate, transport playback with
beat-indicator callbacks, and scheduled FL state changes followed by the OnRefresh FL would send."""
from __future__ import annotations

import math
from typing import Callable, Optional

from .loader import ScriptSet

PPQ = 96                      # FL's internal resolution: song ticks per beat
BEATS_PER_BAR = 4
HW_DIRTY_LEDS = 256
HW_DIRTY_MIXER_SEL = 1
HW_DIRTY_FOCUSED_WINDOW = 32
HW_DIRTY_PATTERNS = 1024


class SessionDriver:
    """`tick()` = one FL idle period: time passes, playback advances, every script gets OnIdle."""

    def __init__(self, scripts: ScriptSet, hz: float = 50.0):
        self.scripts = scripts
        self.host = scripts.host
        self.hz = hz
        self.dt = 1.0 / hz
        self._beat_pos = 0.0          # in beats since start of playback
        self._last_beat = -1
        self._beat_off_at: Optional[float] = None
        self.ticks = 0

    # ---- one idle period ---------------------------------------------------------------------------------------------
    def tick(self, n: int = 1, playback: bool = True) -> None:
        for _ in range(n):
            self.host.advance(self.dt)
            self.ticks += 1
            if playback:
                self._advance_playback()
            for s in self.scripts.scripts:
                if s.has("OnIdle"):
                    s.call("OnIdle")

    def _advance_playback(self) -> None:
        st = self.host.state
        if not st.playing:
            self._beat_pos = 0.0
            self._last_beat = -1
            self._beat_off_at = None
            return
        self._beat_pos += self.dt * st.tempo / 60.0
        st.song_tick_pos = int(self._beat_pos * PPQ) + 1          # != 0 while playing
        st.song_step_pos = int(self._beat_pos * 4)                # 16th steps
        beat = int(self._beat_pos)
        if beat != self._last_beat:
            self._last_beat = beat
            self._call_beat(1 if beat % BEATS_PER_BAR == 0 else 2)     # 1 = bar, 2 = beat
            self._beat_off_at = self.host.clock.now + 30.0 / st.tempo  # indicator off half a beat later
        elif self._beat_off_at is not None and self.host.clock.now >= self._beat_off_at:
            self._beat_off_at = None
            self._call_beat(0)

    def _call_beat(self, value: int) -> None:
        for s in self.scripts.scripts:
            if s.has("OnUpdateBeatIndicator"):
                s.call("OnUpdateBeatIndicator", value)

    # ---- FL state change + refresh ---------------------------------------------------------------------------------
    def refresh(self, flags: int = HW_DIRTY_LEDS | HW_DIRTY_MIXER_SEL) -> None:
        for s in self.scripts.scripts:
            if s.has("OnRefresh"):
                s.call("OnRefresh", flags)

    def change(self, fn: Callable, flags: int = HW_DIRTY_LEDS | HW_DIRTY_MIXER_SEL) -> None:
        """Apply a change to host.state, then send the OnRefresh FL would."""
        fn(self.host.state)
        self.refresh(flags)

    def run(self, seconds: float, schedule: Optional[list] = None, playback: bool = True) -> None:
        """Idle for `seconds`; `schedule` = [(time offset s, fn(state) or (fn, flags))] applied when due."""
        end = self.host.clock.now + seconds
        pending = sorted(schedule or [], key=lambda x: x[0])
        t0 = self.host.clock.now
        while self.host.clock.now < end - 1e-9:
            while pending and self.host.clock.now - t0 >= pending[0][0]:
                _, item = pending.pop(0)
                fn, flags = item if isinstance(item, tuple) else (item, HW_DIRTY_LEDS | HW_DIRTY_MIXER_SEL)
                self.change(fn, flags)
            self.tick(playback=playback)


def sysex_per_second(host, t0: float, t1: float, role: Optional[str] = None) -> list[int]:
    """SysEx messages per whole virtual second in [t0, t1)."""
    n = int(round(t1 - t0))
    buckets = [0] * max(n, 0)
    for m in host.sysex:
        if role is not None and m.script != role:
            continue
        i = math.floor(m.t - t0 + 1e-9)
        if 0 <= i < n:
            buckets[i] += 1
    return buckets
