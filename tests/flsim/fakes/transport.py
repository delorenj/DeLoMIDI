"""transport: play/stop/record state plus the few globalTransport commands with a visible effect."""
from __future__ import annotations

from .base import Impl

# numeric ids of midi.FPT_* (checked against the real midi.py by tests/test_flsim_harness.py)
FPT_METRONOME = 110
FPT_LOOP_RECORD = 113


class TransportImpl(Impl):
    def start(self):
        self.s.playing = not self.s.playing

    def stop(self):
        s = self.s
        s.playing = False
        s.song_tick_pos = 0
        s.song_step_pos = 0

    def record(self):
        self.s.recording = not self.s.recording

    def isPlaying(self):
        return self.s.playing

    def isRecording(self):
        return self.s.recording

    def getLoopMode(self):
        return self.s.loop_mode

    def setLoopMode(self):
        self.s.loop_mode = 1 - self.s.loop_mode

    def continuousMove(self, speed, startStop):
        pass

    def globalTransport(self, command, value, pmeflags=2, flags=15):
        s = self.s
        if command == FPT_METRONOME:
            s.metronome = not s.metronome
        elif command == FPT_LOOP_RECORD:
            s.loop_rec = not s.loop_rec
        return 0
