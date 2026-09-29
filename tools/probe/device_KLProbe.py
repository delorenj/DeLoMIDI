# name=KL Probe
"""
Raw MIDI + environment probe for the Arturia KeyLab mkII. Diagnostic only.

Logs to C:\\ProgramData\\DeLoMIDI\\probe.log (and FL's Script output). Never sets event.handled,
so FL still processes every event normally. Assign it to the keyboard's input ports in
Options > MIDI settings, press things on the keyboard, then read the log.
"""
import time

import device
import general

LOG = r'C:\ProgramData\DeLoMIDI\probe.log'
_t0 = time.monotonic()
_idle = 0
_last_beat = 0.0


def _log(msg):
    line = '%9.3f %s' % (time.monotonic() - _t0, msg)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass
    try:
        print(line)
    except Exception:
        pass


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as ex:
        return 'ERR(%s)' % ex


def _who():
    return 'port=%s name=%r' % (_safe(device.getPortNumber), _safe(device.getName))


def _dump(tag, e):
    try:
        sysex = ''
        if getattr(e, 'status', 0) == 0xF0 or getattr(e, 'sysex', None):
            try:
                sysex = ' sysex=' + bytes(e.sysex).hex()
            except Exception as ex:
                sysex = ' sysex=ERR(%s)' % ex
        _log('%s [%s] st=0x%02X d1=%3d d2=%3d evport=%s midiId=%s midiChan=%s ctrlNum=%s ctrlVal=%s pme=%s inc=%s%s' % (
            tag, _who(), e.status, e.data1, e.data2, getattr(e, 'port', '?'), getattr(e, 'midiId', '?'),
            getattr(e, 'midiChan', '?'), getattr(e, 'controlNum', '?'), getattr(e, 'controlVal', '?'),
            getattr(e, 'pmeFlags', '?'), getattr(e, 'isIncrement', '?'), sysex))
    except Exception as ex:
        _log('%s DUMP-ERR %s' % (tag, ex))


def _lcd(line1, line2):
    # Same framing as Arturia's stock KeyLabmk2Display: F0 00 20 6B 7F 42 04 00 60 01 <l1> 00 02 <l2> 00 7F F7
    try:
        pay = bytes([0xF0, 0x00, 0x20, 0x6B, 0x7F, 0x42, 0x04, 0x00, 0x60, 0x01])
        pay += line1[:16].encode('ascii', 'replace') + bytes([0x00, 0x02]) + line2[:16].encode('ascii', 'replace')
        pay += bytes([0x00, 0x7F, 0xF7])
        device.midiOutSysex(pay)
        return 'sent'
    except Exception as ex:
        return 'ERR(%s)' % ex


def OnInit():
    _log('=' * 70)
    _log('INIT %s' % _who())
    _log('INIT general.getVersion()=%r' % _safe(general.getVersion))
    _log('INIT device.isAssigned()=%r isMidiOutAssigned()=%r getDeviceID()=%r' % (
        _safe(device.isAssigned), _safe(device.isMidiOutAssigned), _safe(device.getDeviceID)))
    _log('INIT lcd=%s' % _lcd('KL Probe', 'port %s' % _safe(device.getPortNumber)))


def OnDeInit():
    _log('DEINIT %s idle_ticks=%d' % (_who(), _idle))


def OnMidiIn(event):
    _dump('IN ', event)


def OnMidiMsg(event):
    _dump('MSG', event)


def OnSysEx(event):
    _dump('SYX', event)


def OnRefresh(flags):
    _log('REFRESH [%s] flags=%s' % (_who(), flags))


def OnIdle():
    global _idle, _last_beat
    _idle += 1
    now = time.monotonic()
    if now - _last_beat > 30:
        _last_beat = now
        _log('IDLE-BEAT [%s] ticks=%d' % (_who(), _idle))
