"""device: the script's own MIDI ports. Output goes to the *executing* script's device (host.current)."""
from __future__ import annotations

from ..events import FlEvent
from ..host import FLCrash
from .base import Impl

_DEVICE_NAMES = {"entry": "MIDIIN2 (KeyLab mkII 88)", "forward": "KeyLab mkII 88"}


class DeviceImpl(Impl):
    def _guard(self, fn, output=False):
        h = self.host
        if h.current is None:
            raise FLCrash("device.%s called outside every script callback: an interpreter not associated with a "
                          "device (stubs device/__device.py:53)" % fn, "device." + fn)
        if h.phase == "import" and h.crash_on_import_device_calls:
            raise FLCrash("device.%s called at import time (interpreter not associated with a device yet)" % fn,
                          "device." + fn)
        if output and h.crash_on_unassigned_output and not h.output_assigned(h.current.role):
            raise FLCrash("device.%s with no MIDI output assigned to script '%s': null read in FLEngine_x64.dll "
                          "(hypothesis behind docs/incidents/2026-09-29)" % (fn, h.current.role), "device." + fn)

    def isAssigned(self):
        self._guard("isAssigned")
        return self.host.output_assigned(self.host.current.role)

    def isMidiOutAssigned(self):
        self._guard("isMidiOutAssigned")
        return self.host.output_assigned(self.host.current.role)

    def getPortNumber(self):
        self._guard("getPortNumber")
        role = self.host.current.role
        return self.host.port_numbers.get(role, 0) if self.host.output_assigned(role) else -1

    def getName(self):
        self._guard("getName")
        return _DEVICE_NAMES.get(self.host.current.role, "KeyLab mkII 88")

    def getDeviceID(self):
        self._guard("getDeviceID")
        return b""

    def midiOutSysex(self, message):
        self._guard("midiOutSysex", output=True)
        if not self.host.output_assigned(self.host.current.role):
            # Host(crash_on_unassigned_output=False): the other hypothesis, a silent no-op
            self.host.dropped_sysex.append(bytes(message))
            return
        self.host.record_sysex(bytes(message))

    def midiOutMsg(self, message, channel=None, data1=None, data2=None):
        self._guard("midiOutMsg", output=True)
        if not self.host.output_assigned(self.host.current.role):
            return
        self.host.midi_out.append((message, channel, data1, data2))

    def forwardMIDICC(self, message, mode=1):
        self._guard("forwardMIDICC")
        self.host.forwarded.append((message, mode))

    def processMIDICC(self, eventData):
        self._guard("processMIDICC")
        if not isinstance(eventData, FlEvent):
            raise TypeError("device.processMIDICC() argument must be a FlMidiMsg, not %s" % type(eventData).__name__)
        self.host.processed.append(eventData.snapshot())

    def dispatch(self, ctrlIndex, message, sysex=b""):
        self._guard("dispatch")
        self.host.dispatched.append((ctrlIndex, message, sysex))

    def dispatchReceiverCount(self):
        self._guard("dispatchReceiverCount")
        return 0

    def setHasMeters(self):
        self._guard("setHasMeters")

    def fullRefresh(self):
        self._guard("fullRefresh")

    def hardwareRefreshMixerTrack(self, index):
        self._guard("hardwareRefreshMixerTrack")
