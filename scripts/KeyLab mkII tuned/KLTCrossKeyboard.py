import sys                  # KLT F-17: interpreter id in the PROBE-VERDICT lines
import midi
import channels
import mixer
import KLTConfig as CFG     # KLT F-03: input-side switches
import KLTLog               # KLT F-03: unmapped/probe lines go to klt.log (never raises)

# This script contains big fonctions that can be shared with other scripts


MX_OFFSET = 0
CH_OFFSET = 0

# KLT F-09: mixer.trackCount() is 127 = master (0) + inserts 1..125 + the "current track" pseudo track (126); the stock
# bank limit stopped at offset 15 (tracks 121..128) but pan/select then addressed 126, 127 and 128.
MAX_TRACK = 125


def track_ok(track):
    # KLT F-09: one guard for every mixer index the input side is about to touch (True = safe to address)
    try:
        return 0 <= track <= MAX_TRACK and track < mixer.trackCount()
    except Exception:
        return False


def sel_channel():
    # KLT F-13: the selected channel as a group-relative index, the indexing every channels.*/plugins.* call defaults to
    # (channels.channelNumber() is GLOBAL, so it addressed the wrong channel once Channel Rack groups are used).
    # KLT O-13: same switch as the output side, so LEDs and controls agree. -1 = nothing to address (empty rack).
    try:
        n = channels.channelCount()
        if n <= 0:
            return -1
        if getattr(CFG, 'GROUP_RELATIVE_CHANNELS', True):
            c = channels.selectedChannel()
        else:
            c = channels.channelNumber()
        return c if 0 <= c < n else -1
    except Exception:
        return -1


def rel_ticks(d2):
    # KLT F-10: signed movement of a relative sign-magnitude encoder value: 1..63 = clockwise by n, 65..127 = counter
    # clockwise by n, 0 and 64 = none. Stock read only the direction for pan/step edit (0 counted as +1) and only
    # the exact values 1 / 65 for the jog. Capped so an unexpected encoding cannot make a control jump.
    if not CFG.ENCODER_USE_TICKS:
        return 0 if d2 == 0x40 else (-1 if d2 > 0x40 else 1)
    n = d2 & 0x3F
    if n == 0:
        return 0
    n = min(n, max(1, CFG.ENCODER_MAX_TICKS))
    return -n if d2 & 0x40 else n


def clamp_banks():
    # KLT F-12: the bank offsets were only ever bounded when the button was pressed; a project with fewer channels
    # left them pointing past the end. Cheap enough to run before every input event (and callable from OnRefresh).
    global MX_OFFSET, CH_OFFSET
    try:
        last_channel_bank = max(0, (channels.channelCount() - 1) // 8)
        if CH_OFFSET > last_channel_bank:
            CH_OFFSET = last_channel_bank
        last_track = min(MAX_TRACK, mixer.trackCount() - 1)
        last_mixer_bank = max(0, (last_track - 1) // 8)
        if MX_OFFSET > last_mixer_bank:
            MX_OFFSET = last_mixer_bank
    except Exception:
        pass
    if CH_OFFSET < 0:
        CH_OFFSET = 0
    if MX_OFFSET < 0:
        MX_OFFSET = 0


def SetVolumeTrack(track, value):
    # KLT F-08, F-09: pure helper (stock rewrote the event into a CC-shaped body and left event.handled False, so the
    # same movement also went on to FL); the caller passes the mixer track and the fader position 0.0..1.0.
    # 0.8 is 0 dB on FL's mixer fader (no boost above unity, as before).
    if not track_ok(track):
        return False
    mixer.setTrackVolume(track, 0.8 * value)
    return True


def SetPanTrack(track, ticks):
    # KLT F-08, F-09, F-10: pure helper; ticks = signed encoder movement (rel_ticks), 1/20 of the pan range per tick
    if not track_ok(track):
        return False
    pan = mixer.getTrackPan(track) + ticks / 20
    mixer.setTrackPan(track, max(-1.0, min(1.0, pan)))
    return True


# ---- diagnostics shared by the DAW-port processor and the keyboard-port script ---------------------------------------

_PROBE_SEEN = {}
_UNMAPPED_SEEN = {}


def _kind_name(st):
    if st >= 0xF8:
        return 'realtime'
    if st == 0xF0:
        return 'sysex'
    if st >= 0xF0:
        return 'system'
    return {0x80: 'note-off', 0x90: 'note-on', 0xA0: 'key-aftertouch', 0xB0: 'cc', 0xC0: 'program',
            0xD0: 'chan-aftertouch', 0xE0: 'pitch-bend'}.get(st & 0xF0, 'other')


def _hx(v):
    return '0x%02X' % v if isinstance(v, int) else str(v)


def probe(where, event):
    # KLT F-01: which MIDI fields does FL fill in this callback, on this port? The first few events of every
    # (callback, port, kind) are logged with what midiId/midiChan/controlNum contain next to what they should contain,
    # plus one PROBE-VERDICT line per (callback, port) - that settles H1 (populated in OnMidiIn) vs H2 (zero) on tom.
    # Nothing here is needed for the scripts to work: they only ever read status/data1/data2.
    try:
        if not (CFG.PROBE_MIDI_FIELDS and CFG.LOG_ENABLED):
            return
        st = event.status
        port = getattr(event, 'port', -1)
        kind = _kind_name(st)
        key = (where, port, kind)
        n = _PROBE_SEEN.get(key, 0)
        if n >= CFG.PROBE_SAMPLES_PER_KIND or (n == 0 and len(_PROBE_SEEN) >= 400):
            return
        _PROBE_SEEN[key] = n + 1
        exp_id = (st & 0xF0) if st < 0xF0 else st
        exp_ch = (st & 0x0F) if st < 0xF0 else 0
        mid = getattr(event, 'midiId', None)
        chn = getattr(event, 'midiChan', None)
        KLTLog.log('PROBE %s port=%s %s st=0x%02X d1=%d d2=%d midiId=%s (want %s) midiChan=%s (want %d%s) '
                   'controlNum=%s controlVal=%s handled=%s pme=%s' % (
                       where, port, kind, st, event.data1, event.data2, _hx(mid), _hx(exp_id), chn, exp_ch,
                       '' if exp_ch else ', ambiguous on channel 1', getattr(event, 'controlNum', None),
                       getattr(event, 'controlVal', None), getattr(event, 'handled', None), getattr(event, 'pmeFlags', None)))
        if 0x80 <= st < 0xF0:
            # interpreter/module ids: equal in the lines of the two device scripts = one shared interpreter (F-17)
            KLTLog.log_once(('verdict', where, port), 'PROBE-VERDICT %s port=%s: midiId is %s [interpreter %x, module %x]' % (
                where, port, 'POPULATED (H1)' if mid == exp_id else 'NOT populated, reads %s (H2)' % _hx(mid),
                id(sys.modules), id(_PROBE_SEEN)))
    except Exception:
        pass


def raw_log(where, event):
    # KLT F-03: KLTConfig.LOG_RAW_EVENTS (shared) = a full protocol capture of everything that reaches the input side
    try:
        if CFG.LOG_RAW_EVENTS:
            KLTLog.log('RAW %s port=%s st=0x%02X d1=%d d2=%d' % (where, getattr(event, 'port', -1), event.status,
                                                               event.data1, event.data2))
    except Exception:
        pass


def note_unmapped(event, where):
    # KLT F-03: an event no handler claimed. Logged once per distinct (port, status, data1) and again at x10/x100/x1000;
    # what happens to it is KLTConfig.PASS_UNMAPPED (the callers apply it).
    try:
        st = event.status
        if st >= 0xF0 or not (CFG.LOG_UNMAPPED and CFG.LOG_ENABLED):
            return
        key = (getattr(event, 'port', -1), st, event.data1)
        n = _UNMAPPED_SEEN.get(key)
        if n is None:
            if len(_UNMAPPED_SEEN) >= CFG.LOG_UNMAPPED_MAX_KEYS:
                return
            n = 0
        n += 1
        _UNMAPPED_SEEN[key] = n
        if n in (1, 10, 100, 1000):
            KLTLog.log('UNMAPPED %s port=%s %s st=0x%02X d1=%d d2=%d (seen %d time%s, %s)' % (
                where, key[0], _kind_name(st), st, event.data1, event.data2, n, '' if n == 1 else 's',
                'passed to FL' if CFG.PASS_UNMAPPED else 'swallowed'))
    except Exception:
        pass
