"""FlMidiMsg, the event object FL hands to every MIDI callback.

Modelled after the official stubs (fl_classes FlMidiMsg, see tests/fl_api_surface.json -> classes.FlMidiMsg):

* controlNum / note / pressure / progNum are aliases of data1; controlVal / velocity are aliases of data2 (writing
  one changes the others).
* status, data1, data2, handled, sysex and the derived fields are writable; timestamp, port, pmeFlags are read-only.
* midiId / midiChan / midiChanEx are derived by FL. They are filled for OnMidiMsg (proved by Image-Line's own
  MackieCU script: faders are `event.midiId == midi.MIDI_PITCHBEND`). Whether they are filled inside OnMidiIn is
  hypothesis H1/H2 of docs/analysis/02-input-audit.md 3.3; `populated=False` builds an event the way H2 says OnMidiIn
  sees it (midiId == midiChan == midiChanEx == 0).

Assignments are type-checked like a native object would (a non-int raises TypeError: the F-06 `event.data1 = None`
case) and range-checked against 0..0x7F for the data bytes: an out-of-range write is recorded as an 'event-range'
violation on the host (F-05: `event.data2 = 144`); with Host(on_violation='raise') it raises ValueError instead.
"""
from __future__ import annotations


class FlEvent:
    __slots__ = ("_status", "_d1", "_d2", "_handled", "_midiId", "_midiChan", "_midiChanEx", "_pme", "_port",
                 "_ts", "_sysex", "_inEv", "_outEv", "_isIncrement", "_res", "_sink", "__weakref__")

    def __init__(self, status, data1=0, data2=0, *, populated=True, port=0, pmeFlags=0b101110, timestamp=0,
                 sysex=None, sink=None):
        self._sink = None
        if isinstance(status, (bytes, bytearray, list)):  # SysEx form: FlEvent(b'\xf0...\xf7')
            sysex, status = bytes(status), 0xF0
        self._status, self._d1, self._d2 = int(status), int(data1), int(data2)
        self._handled = False
        self._pme, self._port, self._ts = int(pmeFlags), int(port), int(timestamp)
        self._sysex = bytes(sysex) if sysex is not None else b""
        self._inEv, self._outEv, self._isIncrement, self._res = 0, 0, False, 0.0
        if populated:
            self._midiId = self._status & 0xF0 if self._status < 0xF0 else self._status
            self._midiChan = self._status & 0x0F if self._status < 0xF0 else 0
        else:
            self._midiId = 0
            self._midiChan = 0
        self._midiChanEx = self._midiChan
        self._sink = sink

    # ---- helpers --------------------------------------------------------------------------------------------
    def populate(self) -> "FlEvent":
        """Fill midiId/midiChan the way FL does before OnMidiMsg."""
        s = self._status
        self._midiId = s & 0xF0 if s < 0xF0 else s
        self._midiChan = s & 0x0F if s < 0xF0 else 0
        self._midiChanEx = self._midiChan
        return self

    def snapshot(self) -> tuple:
        return (self._status, self._d1, self._d2, self._handled, self._midiId, self._midiChan, self._sysex)

    def _int(self, name, v):
        if not isinstance(v, int) or isinstance(v, float):
            raise TypeError("FlMidiMsg.%s must be an int, not %s" % (name, type(v).__name__))
        return int(v)

    def _byte(self, name, v, limit):
        v = self._int(name, v)
        if not 0 <= v <= limit:
            msg = "FlMidiMsg.%s = %d is outside 0..%d" % (name, v, limit)
            if self._sink is not None:
                self._sink("event-range", "FlMidiMsg.%s" % name, msg)
        return v

    # ---- raw MIDI bytes ---------------------------------------------------------------------------------------
    @property
    def status(self): return self._status

    @status.setter
    def status(self, v): self._status = self._byte("status", v, 0xFF)

    @property
    def data1(self): return self._d1

    @data1.setter
    def data1(self, v): self._d1 = self._byte("data1", v, 0x7F)

    @property
    def data2(self): return self._d2

    @data2.setter
    def data2(self, v): self._d2 = self._byte("data2", v, 0x7F)

    # aliases (per the stubs) ------------------------------------------------------------------------------------
    @property
    def controlNum(self): return self._d1

    @controlNum.setter
    def controlNum(self, v): self._d1 = self._byte("controlNum", v, 0x7F)

    @property
    def note(self): return self._d1

    @note.setter
    def note(self, v): self._d1 = self._byte("note", v, 0x7F)

    @property
    def pressure(self): return self._d1

    @pressure.setter
    def pressure(self, v): self._d1 = self._byte("pressure", v, 0x7F)

    @property
    def progNum(self): return self._d1

    @progNum.setter
    def progNum(self, v): self._d1 = self._byte("progNum", v, 0x7F)

    @property
    def controlVal(self): return self._d2

    @controlVal.setter
    def controlVal(self, v): self._d2 = self._byte("controlVal", v, 0x7F)

    @property
    def velocity(self): return self._d2

    @velocity.setter
    def velocity(self, v): self._d2 = self._byte("velocity", v, 0x7F)

    # ---- plain writable fields ----------------------------------------------------------------------------------
    @property
    def handled(self): return self._handled

    @handled.setter
    def handled(self, v): self._handled = bool(v)

    @property
    def midiId(self): return self._midiId

    @midiId.setter
    def midiId(self, v): self._midiId = self._int("midiId", v)

    @property
    def midiChan(self): return self._midiChan

    @midiChan.setter
    def midiChan(self, v): self._midiChan = self._int("midiChan", v)

    @property
    def midiChanEx(self): return self._midiChanEx

    @midiChanEx.setter
    def midiChanEx(self, v): self._midiChanEx = self._int("midiChanEx", v)

    @property
    def sysex(self): return self._sysex

    @sysex.setter
    def sysex(self, v):
        if not isinstance(v, (bytes, bytearray)):
            raise TypeError("FlMidiMsg.sysex must be bytes, not %s" % type(v).__name__)
        self._sysex = bytes(v)

    @property
    def inEv(self): return self._inEv

    @inEv.setter
    def inEv(self, v): self._inEv = self._int("inEv", v)

    @property
    def outEv(self): return self._outEv

    @outEv.setter
    def outEv(self, v): self._outEv = self._int("outEv", v)

    @property
    def isIncrement(self): return self._isIncrement

    @isIncrement.setter
    def isIncrement(self, v): self._isIncrement = bool(v)

    @property
    def res(self): return self._res

    @res.setter
    def res(self, v): self._res = float(v)

    # ---- read-only fields ---------------------------------------------------------------------------------------
    @property
    def timestamp(self): return self._ts

    @property
    def port(self): return self._port

    @property
    def pmeFlags(self): return self._pme

    @property
    def pitchBend(self):
        raise NotImplementedError("FlMidiMsg.pitchBend is a real FL field that flsim does not model "
                                  "(tests/flsim/events.py); model it and add a test before relying on it")

    def __repr__(self):
        return "FlEvent(0x%02X, %d, %d, handled=%s, midiId=0x%02X, midiChan=%d)" % (
            self._status, self._d1, self._d2, self._handled, self._midiId, self._midiChan)
