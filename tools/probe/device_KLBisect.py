# name=KL Bisect
"""
Crash bisector for FL Studio script attach. Writes a STEP line to the log BEFORE each risky operation
(open/append/close per line, so the last line on disk names the call that killed FL).
Log: C:\\ProgramData\\DeLoMIDI\\bisect.log
"""
LOG = r'C:\ProgramData\DeLoMIDI\bisect.log'


def L(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(msg + '\n')
    except Exception:
        pass


L('MODULE-START')
L('STEP import time')
import time
L('STEP import device')
import device
L('STEP import general')
import general
L('MODULE-END')


def OnInit():
    L('OnInit ENTER')
    for name, fn in (
        ('device.getPortNumber', lambda: device.getPortNumber()),
        ('device.getName', lambda: device.getName()),
        ('general.getVersion', lambda: general.getVersion()),
        ('device.isAssigned', lambda: device.isAssigned()),
        ('device.isMidiOutAssigned', lambda: device.isMidiOutAssigned()),
        ('device.getDeviceID', lambda: device.getDeviceID()),
    ):
        L('STEP ' + name)
        try:
            L('  -> %r' % (fn(),))
        except Exception as ex:
            L('  -> EXC %r' % (ex,))
    L('STEP device.midiOutSysex (LCD greeting)')
    try:
        device.midiOutSysex(bytes([0xF0, 0x00, 0x20, 0x6B, 0x7F, 0x42, 0x04, 0x00, 0x60, 0x01]) + b'KL Bisect' + bytes([0x00, 0x02]) + b'ok' + bytes([0x00, 0x7F, 0xF7]))
        L('  -> sent')
    except Exception as ex:
        L('  -> EXC %r' % (ex,))
    L('OnInit EXIT')


def OnDeInit():
    L('OnDeInit')


def OnMidiIn(event):
    L('IN st=0x%02X d1=%d d2=%d' % (event.status, event.data1, event.data2))


def OnMidiMsg(event):
    L('MSG st=0x%02X d1=%d d2=%d' % (event.status, event.data1, event.data2))
