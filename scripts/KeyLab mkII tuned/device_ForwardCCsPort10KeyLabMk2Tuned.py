# name=Forward CCs Port 10 KEYLAB MKII (tuned)
# receiveFrom=Forward CCs Port 10 KEYLAB MKII (tuned)

"""
[[
	Surface:	KeyLab mkII
	Developer:	Farès MEZDOUR
	Version:	Beta 1.0
]]
"""

# This script allows the KeyLab mkII to communicate
# with plugins by forwarding CCs to port 10 ( Arturia's Software )

# KLT F-01: this script sits on the KEYBOARD port (keybed, wheels, and, depending on the DAW preset, more). Its default
# path is raw filtering/forwarding on status/data1/data2 only, in OnMidiIn, where the FL manual says only those fields
# exist. Stock ran the whole DAW command processor from OnMidiIn for every event, relying on midiId: if FL fills it in
# there (H1) 15 keybed keys became transport/window buttons (91/92 scrubbed forever), if not (H2) the Analog Lab CCs
# raised a TypeError and were swallowed. The processor path is behind KLTConfig.FORWARD_USE_PROCESSOR and runs from
# OnMidiMsg. Every FL call below is guarded: nothing here can raise into FL, and no device.* call is made at import time
# or in OnInit.

import ui
import midi
import device
import channels
import plugins                            # KLT F-15: the plugin a channel hosts is part of the Arturia-instrument test
import KLTConfig as CFG                  # KLT F-01: switches (raw path by default)
import KLTLog                            # KLT F-01: never raises; PROBE / UNMAPPED lines
import KLTVCOL
import KLTCrossKeyboard as AKLmk2        # KLT F-13: light shared helpers (probe, sel_channel); KLTProcess is imported lazily

_process_module = None
_process_import_failed = False


def _processing():
    # KLT F-01, F-17: KLTProcess (pads, keyboard-port CCs) is imported on first use, so a fault in it can never take the
    # Analog Lab forwarding and the pitch wheel down with it; and this script no longer builds a second processor
    # (stock: OnInit -> device_KeyLabmkII.init(), replacing the DAW script's display and processor objects)
    global _process_module, _process_import_failed
    if _process_module is None and not _process_import_failed:
        try:
            import KLTProcess
            _process_module = KLTProcess
        except Exception:
            _process_import_failed = True
            KLTLog.exception('Forward: import KLTProcess')
    return _process_module


def _v_collection_focused():
    # KLT F-15: set lookup on the focused plugin's name, only asked for CC events (stock: a 32-name loop on EVERY event)
    try:
        return KLTVCOL.is_v_collection(ui.getFocusedPluginName())
    except Exception:
        return False


def _forward_to_plugin(event):
    # Manage Analog Lab Plugin
    # KLT F-01: port and mode are KLTConfig switches (stock: 10 and 2, hard-coded); a failing call is logged, not raised
    msg = event.status + (event.data1 << 8) + (event.data2 << 16) + (CFG.FORWARD_TARGET_PORT << 24)
    try:
        device.forwardMIDICC(msg, CFG.FORWARD_MODE)
    except Exception as e:
        KLTLog.log_once('forward-failed', 'device.forwardMIDICC raised %r (later failures are not logged)' % (e,))
    event.handled = False


def OnInit():
    # KLT F-17: no KL.init() and no FL call here; only a line in klt.log
    KLTLog.log('Forward script OnInit (pads=%s plugin_ccs=%s processor=%s%s)' % (
        CFG.FORWARD_PADS, CFG.FORWARD_PLUGIN_CCS, CFG.FORWARD_USE_PROCESSOR,
        ' kinds=%s' % (CFG.FORWARD_PROCESSOR_KINDS,) if CFG.FORWARD_USE_PROCESSOR else ''))


def OnDeInit():
    # KLT F-17: nothing to tear down; stock's OnMidiMsg wrapper (forcing handled = False) is replaced by the one below
    return


# KLT F-01: OnMidiIn = raw filtering / forwarding on status, data1, data2 only; never raises
def OnMidiIn(event):
    try:
        AKLmk2.raw_log('Forward.OnMidiIn', event)
        AKLmk2.probe('Forward.OnMidiIn', event)
        status = event.status
        if status == midi.MIDI_CONTROLCHANGE or status == 224:
            if status == 224 or _v_collection_focused():
                _forward_to_plugin(event)
                return
            # KLT F-02: focused plugin is not an Arturia one: mod wheel / preset buttons, from raw fields
            if CFG.FORWARD_PLUGIN_CCS:
                proc = _processing()
                if proc is not None and proc.handle_keyboard_cc(event):
                    return
            if not (CFG.FORWARD_USE_PROCESSOR and 'cc' in CFG.FORWARD_PROCESSOR_KINDS):
                AKLmk2.note_unmapped(event, 'forward-cc', swallowed=False)   # KLT F-03: logged, never swallowed (OnMidiMsg may still map it)
        elif (status == 153 or status == 137) and CFG.FORWARD_PADS:
            # KLT F-01, F-05, F-06, F-07: pads arriving on the keyboard port, raw fields only. handled is whatever the pad
            # logic decided (Sequencer mode consumes the pad; stock's `handled = False` afterwards let it also play a note)
            proc = _processing()
            if proc is not None:
                proc.handle_pad(event)
    except Exception:
        KLTLog.exception('Forward.OnMidiIn')


def _processor_kind(status):
    if status == 0x90 or status == 0x80:
        return 'note'
    if status == 0xB0:
        return 'cc'
    if 0xE0 <= status <= 0xE8:
        return 'bend'
    if status == 153 or status == 137:
        return None if CFG.FORWARD_PADS else 'pad'
    return None


def _entry_processor():
    try:
        import device_KeyLabmk2Tuned as KL
    except Exception:
        KLTLog.log_once('forward-no-entry', 'Forward: cannot import the DAW script module; processor path off')
        return None
    p = getattr(KL, '_processor', None)
    if p is None:
        KLTLog.log_once('forward-no-processor', 'Forward: the DAW script has not created its processor yet; event not routed')
    return p


def OnMidiMsg(event):
    # KLT F-01: OnMidiMsg is where FL documents "actual processing"; the processor path is opt-in
    try:
        AKLmk2.probe('Forward.OnMidiMsg', event)
        if CFG.FORWARD_USE_PROCESSOR:
            kind = _processor_kind(event.status)
            if kind is not None and (kind == 'pad' or kind in CFG.FORWARD_PROCESSOR_KINDS):
                proc = _entry_processor()
                if proc is not None:
                    proc.ProcessEvent(event, 'Forward.OnMidiMsg')
    except Exception:
        KLTLog.exception('Forward.OnMidiMsg')


def _v_collection_channel(channel):
    # KLT F-15: an Arturia instrument by the channel's name (stock) or by the plugin it hosts
    try:
        return KLTVCOL.is_v_collection(channels.getChannelName(channel)) or KLTVCOL.is_v_collection(plugins.getPluginName(channel))
    except Exception:
        return False


def OnPitchBend(event):
    try:
        AKLmk2.probe('Forward.OnPitchBend', event)
        channel = AKLmk2.sel_channel()      # KLT F-13, O-08: group-relative index; none in an empty rack
        if channel >= 0 and not _v_collection_channel(channel):
            # KLT F-15: the full 14 bits (stock used the MSB only: 3.1 cent steps) as a fraction of the channel's own pitch
            # range (mode 0; stock fixed +-200 cents). Centre = 8192, so a range of 2 semitones behaves as before.
            bend = (event.data2 << 7) | event.data1
            channels.setChannelPitch(channel, max(-1.0, min(1.0, (bend - 8192) / 8192)), 0)
    except Exception:
        KLTLog.exception('Forward.OnPitchBend')
    event.handled = True
