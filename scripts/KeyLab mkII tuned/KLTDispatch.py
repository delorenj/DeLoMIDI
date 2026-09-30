# MIT License
# Copyright (c) 2020 Ray Juang

import time                # KLT O-02: the sliding budget windows are measured in monotonic time
from collections import deque

import device
import KLTConfig as CFG   # KLT O-01: output-layer switches
import KLTLog             # KLT O-15: the output layer reports what it does



# This class is a dispatcher. It will send the MIDI event to the appropriate fonction


# MIDI event dispatcher transforms the MIDI event into a value through a transform function provided at construction
# time. This value is then used as a key into a lookup table that provides a dispatcher and filter function. If the
# filter function returns true, then the event is sent to the dispatcher function.

class MidiEventDispatcher:


    def __init__(self, transform_fn):
        self._transform_fn = transform_fn
        # Table contains a mapping of status code -> (callback_fn, filter_fn)
        self._dispatch_map = {}


    def NewHandler(self, key, callback_fn, filter_fn =None):
   

        # param key: the result value of transform_fn(event) to match against.
        # param callback_fn: function that is called with the event in the event the transformed event matches.
        # param filter_fn: function that takes an event and returns true if the event should be dispatched. If false
        # is returned, then the event is dropped and never passed to callback_fn. Not specifying means that callback_fn
        # is always called if transform_fn matches the key.

        
        def _default_true_fn(_): return True
        if filter_fn is None:
            filter_fn = _default_true_fn
        self._dispatch_map[key] = (callback_fn, filter_fn)
        return self


    def NewHandlerForKeys(self, keys, callback_fn, filter_fn=None):
        
        # Same function but for a group of controls
        
        for k in keys:
            self.NewHandler(k, callback_fn, filter_fn=filter_fn)
        return self


    def Dispatch(self, event):
        key = self._transform_fn(event)
        processed = False
        if key in self._dispatch_map:
            callback_fn, filter_fn = self._dispatch_map[key]
            if filter_fn(event):
                callback_fn(event)
                processed = True
            else:
                processed = True

        return processed



# KLT O-01, O-02, O-05, O-06: everything below replaces stock's one-line send_to_device (an unconditional
# device.midiOutSysex). All output of the scripts funnels through OutputLayer; nothing else may call midiOutSysex.
#
#   gate        device.isAssigned() (and isMidiOutAssigned()) is asked before every send; not assigned, unanswerable,
#               disabled or closed means nothing is sent (O-01: the leading hypothesis for the FL 26.1.6 crash is a
#               midiOutSysex without an assigned output)
#   shadow      what the keyboard is believed to show, per LED id / LCD; an unchanged frame is never re-sent (O-02)
#   pending     the newest wanted frame per LED id / LCD, delivered within the budgets, latest wins (O-06)
#   budgets     hard frames-per-second cap, frames-per-OnIdle-tick cap, LCD minimum gap (O-02, O-06)
#   keep-alive  one known frame re-sent per OUT_TRICKLE_S so a keyboard that lost its state heals (O-05)

# KLT O-01: the SysEx framing is byte-identical to stock: F0 00 20 6B 7F 42 <payload> F7
HEADER = bytes([0xF0, 0x00, 0x20, 0x6B, 0x7F, 0x42])
_EPS = 1e-6
_MAX_PAYLOAD = 96           # the longest frame we build is the 40-byte LCD frame
_LCD = 'lcd'
_FAIL_LIMIT = 5             # consecutive midiOutSysex exceptions before backing off


def _cfg(name, default):
    """Read a KLTConfig switch as the type of its default; a missing or malformed value falls back to the default."""
    try:
        v = getattr(CFG, name)
        if isinstance(default, bool):
            return bool(v)
        if isinstance(default, (int, float)):
            return type(default)(v)
        return v
    except Exception:
        return default


def frame_key(data):
    """What a frame addresses: (type byte, LED id) for LEDs, 'lcd' for the display, None for anything else."""
    if data[:3] in (b'\x02\x00\x10', b'\x02\x00\x16') and len(data) >= 4:
        return (data[2], data[3])
    if data[:3] == b'\x04\x00\x60':
        return _LCD
    return None


class _Batch:
    """`with batch():` collects the frames of one callback and delivers only the final state per LED (no flicker,
    no intermediate frames) when the outermost batch exits."""

    def __init__(self, layer):
        self._layer = layer

    def __enter__(self):
        self._layer._batch += 1
        return self

    def __exit__(self, *exc):
        L = self._layer
        L._batch = max(0, L._batch - 1)
        if L._batch == 0:
            L.pump()
        return False


class OutputLayer:
    def __init__(self):
        self._closed = False        # after OnDeInit: FL may be tearing the port down, never touch it again
        self._shutdown = False      # OnDeInit in progress: burst/LCD-gap limits are waived so goodbye frames get out
        self._hold = False          # init sequence running: LED frames wait (LCD does not)
        self._hold_since = 0.0
        self._batch = 0
        self._shadow = {}           # key -> payload last delivered to the keyboard
        self._pending = {}          # key -> newest payload we want the keyboard to show
        self._win_s = deque()       # send times inside the last second
        self._win_b = deque()       # send times inside the last OUT_TICK_S
        self._last_lcd = -1e9
        self._gate_open = None      # None = never asked, then the last answer
        self._unassigned_until = 0.0
        self._backoff_until = 0.0
        self._fail_streak = 0
        self._resync_flag = False
        self._trickle_at = None
        self._trickle_i = 0
        self._stats_at = None
        self._stats_last = -1
        self._asked = set()         # native queries already announced in the log (breadcrumbs for a crash post-mortem)
        self.stats = {'sent': 0, 'deduped': 0, 'gated': 0, 'invalid': 0, 'errors': 0, 'defer_sec': 0,
                      'defer_burst': 0, 'defer_gap': 0, 'keepalive': 0}

    # ---- lifecycle ----------------------------------------------------------------------------------------
    def reset(self):
        """OnInit: forget everything about the keyboard and reopen the layer (Reload keeps module state in FL)."""
        self._closed = self._shutdown = self._hold = False
        self._batch = 0
        self._shadow.clear()
        self._pending.clear()
        self._gate_open = None
        self._unassigned_until = self._backoff_until = 0.0
        self._fail_streak = 0
        self._resync_flag = False
        self._trickle_at = None
        self._trickle_i = 0
        self._stats_at = None
        self._asked.clear()
        for k in self.stats:
            self.stats[k] = 0
        self._stats_last = -1

    def begin_shutdown(self):
        self._shutdown = True
        self._hold = False
        self._pending.clear()

    def close(self):
        self._closed = True
        self._shutdown = False
        self._hold = False
        self._pending.clear()

    def resync(self):
        """The keyboard may have lost what it shows (memory switch, power cycle): believe nothing, re-send on demand."""
        self._shadow.clear()

    def take_resync(self):
        """True once after the output (re)appeared: the caller must repaint everything it owns."""
        f, self._resync_flag = self._resync_flag, False
        return f

    def set_hold(self, on):
        self._hold = bool(on)
        self._hold_since = time.monotonic()

    @property
    def holding(self):
        return self._hold

    @property
    def closed(self):
        return self._closed

    # ---- the gate -----------------------------------------------------------------------------------------
    def _breadcrumb(self, name):
        """KLT O-15: say in klt.log, once per OnInit, that a native call is about to be made. The log is appended line by
        line, so if FL dies inside the call (the tom crash is a native null read) the last line on disk names it."""
        if name not in self._asked:
            self._asked.add(name)
            KLTLog.log('gate: about to call %s' % name)

    def _query(self):
        try:
            self._breadcrumb('device.isAssigned()')
            assigned = device.isAssigned()
        except Exception as e:
            return False, 'device.isAssigned() raised %r' % (e,)
        if not assigned:
            return False, 'device.isAssigned() is False'
        if _cfg('OUT_REQUIRE_MIDIOUT_ASSIGNED', True):
            fn = getattr(device, 'isMidiOutAssigned', None)
            if fn is not None:
                try:
                    self._breadcrumb('device.isMidiOutAssigned()')
                    out = fn()
                except Exception as e:
                    return False, 'device.isMidiOutAssigned() raised %r' % (e,)
                if not out:
                    return False, 'device.isAssigned() is True but device.isMidiOutAssigned() is %r' % (out,)
        return True, ''

    def ready(self):
        """True only if calling device.midiOutSysex is safe right now. Asks FL every time it answers yes; a 'no' is
        remembered for OUT_UNASSIGNED_RECHECK_S. Never raises."""
        try:
            now = time.monotonic()
            if self._closed and not self._shutdown:
                return False
            if not _cfg('OUT_ENABLED', True):
                self._observe(False, 'OUT_ENABLED is False in KLTConfig', now)
                return False
            if now < self._backoff_until:
                return False
            if self._gate_open is False and now < self._unassigned_until:
                return False
            ok, why = self._query()
            self._observe(ok, why, now)
            return ok
        except Exception:
            return False

    def _observe(self, ok, why, now):
        was = self._gate_open
        self._gate_open = ok
        if ok:
            if was is False:
                KLTLog.log('output: MIDI output is now assigned, repainting the keyboard')
                self._shadow.clear()
                self._resync_flag = True
            return
        self._unassigned_until = now + max(0.0, _cfg('OUT_UNASSIGNED_RECHECK_S', 0.5))
        if was is not False:
            self._pending.clear()
            if why.startswith('OUT_ENABLED'):
                msg = 'output is switched off (%s): nothing is sent to the keyboard' % why
            else:
                msg = ('no MIDI output for this script (%s): nothing is sent, the keyboard stays dark. In FL: Options > '
                       'MIDI settings > Output, enable the KeyLab DAW port and give it the same port number as its '
                       'input.' % why)
            if 'isMidiOutAssigned' in why:
                msg += (' If the output IS assigned in FL, set OUT_REQUIRE_MIDIOUT_ASSIGNED = False in KLTConfig.py (that '
                        'query is undocumented).')
            KLTLog.log('output: ' + msg)
            _print_once('KeyLab mkII (tuned): ' + msg, why)      # once per reason: the log file may be unwritable

    # ---- sending ------------------------------------------------------------------------------------------
    def _admit(self, now, key):
        """None if a frame may leave now, else why not: 'sec' / 'burst' (stop for this tick), 'gap' (LCD only)."""
        ws, wb = self._win_s, self._win_b
        while ws and now - ws[0] >= 1.0 - _EPS:
            ws.popleft()
        tick = _cfg('OUT_TICK_S', 0.02)
        while wb and now - wb[0] >= tick - _EPS:
            wb.popleft()
        if len(ws) >= max(1, int(_cfg('OUT_MAX_SYSEX_PER_SEC', 100))):
            return 'sec'
        if self._shutdown:
            return None
        if len(wb) >= max(1, int(_cfg('OUT_MAX_SYSEX_PER_TICK', 8))):
            return 'burst'
        if key == _LCD and now - self._last_lcd < _cfg('OUT_LCD_MIN_GAP_S', 0.035) - _EPS:
            return 'gap'
        return None

    def _transmit(self, key, data, now):
        """The one place that calls device.midiOutSysex. The caller has passed the gate and the budgets."""
        try:
            if self.stats['sent'] == 0:
                self._breadcrumb('device.midiOutSysex() for the first time (%d bytes)' % (len(data) + 7))
            device.midiOutSysex(HEADER + data + b'\xF7')
        except Exception as e:
            self.stats['errors'] += 1
            self._fail_streak += 1
            KLTLog.log_once(('out-exc', type(e).__name__), 'output: device.midiOutSysex raised %r' % (e,))
            if self._fail_streak >= _FAIL_LIMIT:
                self._backoff_until = now + max(0.0, _cfg('OUT_FAIL_BACKOFF_S', 5.0))
                KLTLog.log('output: %d midiOutSysex failures in a row, pausing output for %.1f s'
                           % (self._fail_streak, _cfg('OUT_FAIL_BACKOFF_S', 5.0)))
                self._fail_streak = 0
            return False
        self._fail_streak = 0
        self._win_s.append(now)
        self._win_b.append(now)
        if key == _LCD:
            self._last_lcd = now
        if key is not None:
            self._shadow[key] = data
        if self.stats['sent'] == 0:
            KLTLog.log('output: first frame delivered to the keyboard (%d bytes)' % (len(data) + 7))
        self.stats['sent'] += 1
        return True

    def _send_now(self, key, data):
        if not self.ready():
            self.stats['gated'] += 1
            return False
        now = time.monotonic()
        if self._admit(now, key) is not None:
            return False
        return self._transmit(key, data, now)

    def send(self, data, force=False):
        """Ask for `data` (an Arturia payload without header/F7) to be shown. True = accepted: delivered, already
        showing, or queued for the next budget slot. False = refused (no output, invalid) or, with force=True, no
        budget now (try again next tick). Never raises."""
        try:
            data = bytes(data)
            if not 2 <= len(data) <= _MAX_PAYLOAD or max(data) >= 0x80:
                self.stats['invalid'] += 1
                KLTLog.log_once(('out-invalid', data[:4]), 'output: refused malformed frame %s' % data.hex())
                return False
            key = frame_key(data)
            if self._closed and not self._shutdown:
                return False
            if not _cfg('OUT_ENABLED', True):
                self.stats['gated'] += 1
                return False
            if force or key is None:
                return self._send_now(key, data)
            if self._gate_open is not True and not self.ready():
                # never asked, or the last answer was no: ask (rate-limited) so True below means the output exists
                self.stats['gated'] += 1
                return False
            if self._shadow.get(key) == data:
                self._pending.pop(key, None)
                self.stats['deduped'] += 1
                return True
            self._pending[key] = data
            if self._batch == 0:
                self.pump()
            return True
        except Exception as e:
            KLTLog.log_once(('out-send-exc', type(e).__name__), 'output: send() failed: %r' % (e,))
            return False

    def _held(self, key):
        return self._hold and key != _LCD

    def pump(self):
        """Deliver pending frames, oldest first, inside the budgets. Returns the number sent. Never raises."""
        try:
            if self._batch or not self._pending:
                return 0
            now = time.monotonic()
            if self._hold and now - self._hold_since > _cfg('OUT_HOLD_TIMEOUT_S', 5.0):
                self._hold = False
                KLTLog.log('output: the init sequence did not finish in %.1f s, releasing held LEDs'
                           % _cfg('OUT_HOLD_TIMEOUT_S', 5.0))
            keys = [k for k in self._pending if not self._held(k)]
            if not keys or not self.ready():
                return 0
            sent = 0
            for k in keys:
                data = self._pending.get(k)
                if data is None:
                    continue
                if self._shadow.get(k) == data:
                    del self._pending[k]
                    continue
                why = self._admit(now, k)
                if why == 'gap':
                    self.stats['defer_gap'] += 1
                    continue
                if why is not None:
                    self.stats['defer_' + ('sec' if why == 'sec' else 'burst')] += 1
                    break
                if not self._transmit(k, data, now):
                    break
                self._pending.pop(k, None)
                sent += 1
            return sent
        except Exception as e:
            KLTLog.log_once(('out-pump-exc', type(e).__name__), 'output: pump() failed: %r' % (e,))
            return 0

    def service(self):
        """Once per OnIdle tick: deliver what is pending, notice the output appearing, keep-alive, statistics."""
        try:
            now = time.monotonic()
            if self._closed:
                return
            if self._gate_open is not True and now >= self._unassigned_until:
                self.ready()
            self.pump()
            self._keepalive(now)
            every = _cfg('OUT_STATS_LOG_S', 60.0)
            if every > 0:
                if self._stats_at is None:
                    self._stats_at = now
                elif now - self._stats_at >= every:
                    self._stats_at = now
                    if self.stats['sent'] != self._stats_last:
                        self._stats_last = self.stats['sent']
                        KLTLog.log('output stats: ' + ' '.join('%s=%d' % kv for kv in sorted(self.stats.items())))
        except Exception as e:
            KLTLog.log_once(('out-service-exc', type(e).__name__), 'output: service() failed: %r' % (e,))

    def _keepalive(self, now):
        """When nothing else is going on, re-send one already-delivered frame per OUT_TRICKLE_S (and the LCD per
        OUT_LCD_KEEPALIVE_S): a keyboard that lost its LEDs or text comes back without FL having to tell us."""
        if self._hold or self._pending or self._batch or not self._shadow or self._gate_open is not True:
            return
        lcd_every = _cfg('OUT_LCD_KEEPALIVE_S', 10.0)
        if lcd_every > 0 and _LCD in self._shadow and now - self._last_lcd >= lcd_every:
            self._resend(_LCD, now)
            return
        every = _cfg('OUT_TRICKLE_S', 1.0)
        if every <= 0:
            return
        if self._trickle_at is None:
            self._trickle_at = now
            return
        if now - self._trickle_at < every:
            return
        keys = [k for k in self._shadow if k != _LCD]
        if not keys:
            return
        self._trickle_at = now
        k = keys[self._trickle_i % len(keys)]
        self._trickle_i += 1
        self._resend(k, now)

    def _resend(self, key, now):
        if not self.ready() or self._admit(now, key) is not None:
            return
        data = self._shadow.get(key)
        if data is not None and self._transmit(key, data, now):
            self.stats['keepalive'] += 1


_printed = set()


def _print_once(text, key):
    """FL's Script output shows print(); the log file may be unwritable, so the important messages go there once."""
    try:
        if key in _printed:
            return
        _printed.add(key)
        print(text)
    except Exception:
        pass


_out = OutputLayer()


def send_to_device(data, force=False):
    """Show an Arturia payload on the keyboard (framing added here). Returns True if accepted (sent, already showing
    or queued), False if refused. Never raises. force=True skips the de-duplication (init animation, deinit frame)."""
    return _out.send(data, force)


def batch():
    """`with batch():` around a group of send_to_device calls (one callback): only the final state per LED is sent."""
    return _Batch(_out)


def service():
    _out.service()


def output_ready():
    return _out.ready()


def reset_output():
    _out.reset()


def begin_shutdown():
    _out.begin_shutdown()


def close_output():
    _out.close()


def resync():
    _out.resync()


def take_resync():
    return _out.take_resync()


def hold_leds(on):
    _out.set_hold(on)


def output_stats():
    return dict(_out.stats, pending=len(_out._pending), shadow=len(_out._shadow), holding=_out.holding,
                closed=_out.closed)
