"""mixer: tracks 0 (master) .. trackCount()-1 (trackCount() includes the "current track" pseudo track)."""
from __future__ import annotations

from .base import Impl


class MixerImpl(Impl):
    def _ok(self, index, fn):
        n = self.s.track_count
        if 0 <= index < n:
            return True
        self.host.violation("index", "mixer.%s" % fn, "mixer track %d outside 0..%d" % (index, n - 1))
        return False

    def trackCount(self):
        return self.s.track_count

    def trackNumber(self):
        return self.s.current_track

    def setTrackNumber(self, trackNumber, flags=0):
        if self._ok(trackNumber, "setTrackNumber"):
            self.s.current_track = trackNumber

    def getTrackVolume(self, index, mode=0):
        return self.s.track_volume.get(index, 0.8) if self._ok(index, "getTrackVolume") else 0.8

    def setTrackVolume(self, index, volume, pickupMode=0):
        if not self._ok(index, "setTrackVolume"):
            return
        if not 0.0 <= volume <= 1.0:
            self.host.violation("value", "mixer.setTrackVolume", "volume %r outside 0..1" % (volume,))
            volume = min(1.0, max(0.0, volume))
        self.s.track_volume[index] = volume

    def getTrackPan(self, index):
        return self.s.track_pan.get(index, 0.0) if self._ok(index, "getTrackPan") else 0.0

    def setTrackPan(self, index, pan, pickupMode=0):
        if not self._ok(index, "setTrackPan"):
            return
        if not -1.0 <= pan <= 1.0:
            self.host.violation("value", "mixer.setTrackPan", "pan %r outside -1..1" % (pan,))
            pan = min(1.0, max(-1.0, pan))
        self.s.track_pan[index] = pan

    def getTrackName(self, index):
        if not self._ok(index, "getTrackName"):
            return ""
        return "Master" if index == 0 else "Insert %d" % index

    def getTrackPluginId(self, index, plugIndex):
        """Event id of a plugin slot on a track; opaque here (real ids are FL-internal). MackieCU adds midi.REC_Mixer_Vol
        to slot 0 to address a track's volume for automateEvent."""
        return (index << 16) | (plugIndex << 8)

    def automateEvent(self, index, value, flags, speed=0, isIncrement=0, res=0.0):
        """Recorded only (FL records automation and smooths); returns the value like FL does for a plain set."""
        return value

    def armTrack(self, index):
        if self._ok(index, "armTrack"):
            self.s.armed_tracks ^= {index}

    def isTrackArmed(self, index):
        return self._ok(index, "isTrackArmed") and index in self.s.armed_tracks

    def soloTrack(self, index, value=-1, mode=-1):
        if self._ok(index, "soloTrack"):
            self.s.solo_tracks ^= {index}

    def muteTrack(self, index, value=-1):
        if self._ok(index, "muteTrack"):
            m = self.s.muted_tracks
            if value == -1:
                m ^= {index}
            elif value:
                m.add(index)
            else:
                m.discard(index)

    def isTrackSelected(self, index):
        return self._ok(index, "isTrackSelected") and index == self.s.current_track

    def isTrackMuted(self, index):
        return self._ok(index, "isTrackMuted") and index in self.s.muted_tracks

    def isTrackSolo(self, index):
        return self._ok(index, "isTrackSolo") and index in self.s.solo_tracks

    def getCurrentTempo(self, asInt=False):
        # asInt: milli-BPM (Novation-style reading); which unit real FL uses is UNVERIFIED (O-19)
        t = self.s.tempo
        return int(round(t * 1000)) if asInt else t

    def getSongTickPos(self, mode=0):
        return self.s.song_tick_pos

    def getSongStepPos(self):
        return self.s.song_step_pos
