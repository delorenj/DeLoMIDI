# name= KeyLab mkII (tuned)

"""
[[
	Surface:	KeyLab mkII
	Developer:	Farès MEZDOUR
	Version:	Beta 1.0
]]
"""

import ui
import time
import channels
import patterns
import midi
import KLTCrossKeyboard

import sys            # KLT O-15: the init banner
import traceback      # KLT O-04: failures of single routines are reported once, not raised
import device         # KLT O-15: banner only (guarded); every send goes through KLTDispatch (O-01)
import general        # KLT O-15: banner (FL API version)


from KLTProcess import KeyLabMidiProcessor
from KLTReturn import KeyLabLightReturn
from KLTDisplay import KeyLabDisplay
from KLTPages import KeyLabPagedDisplay
from KLTDispatch import send_to_device

import KLTConfig as CFG      # KLT O-01, O-18: switches
import KLTLog                # KLT O-04, O-15: guarded callbacks, one-line diagnostics
import KLTDispatch           # KLT O-01, O-02: the output layer (gate, shadow state, budgets)
import KLTProcess            # KLT O-08: helper-module state is reset at OnInit
import KLTReturn

## CONSTANT

TEMP = 0.5
HW_Flag = {"Select" : [295, 263, 256]} 

# KLT O-15: what the tuned script calls itself in the LCD splash, the log and the Script output
KLT_NAME = 'KeyLab mkII (tuned)'
KLT_VERSION = '0.1.0'

# KLT O-04: the objects exist (as None) from import on, so a callback that runs before OnInit, or after an OnInit that
# failed half-way, does nothing instead of raising NameError on every call. init() is the only place that binds them.
_mk2 = None
_processor = None
_deinitialized = False       # OnDeInit ran: FL may be closing the port, nothing is sent until the next OnInit
_led_due = 0.0               # KLT O-02: monotonic time the next polled-LED pass is due
_reported = set()            # KLT O-04: (routine, exception type, 30 s window) already written to the log
_full_at = -1e9              # KLT O-08: monotonic time of the last OnDoFullRefresh that forgot the keyboard's state

# KLT O-05: the memory-switch SysEx (payload 02 00 00 15 00) after which the keyboard has to be repainted
MEMORY_SWITCH = b'\xf0\x00 k\x7fB\x02\x00\x00\x15\x00\xf7'


#-----------------------------------------------------------------------------------------

# This is the master class. It will run the init lights pattern 
# and call the others class to process MIDI events


class MidiControllerConfig :

    def __init__(self):
        self._lightReturn = KeyLabLightReturn()
        self._display = KeyLabDisplay()
        self._paged_display = KeyLabPagedDisplay(self._display)
        self._main_text = None        # KLT O-04: last text of the main page that FL answered for


    def LightReturn(self) :
        return self._lightReturn
        
    def display(self):
        return self._display

    def paged_display(self):
        return self._paged_display
        
    def Idle(self):
        self._paged_display.Refresh()
        

        
    def Sync(self):
        
        # Update display
        
        # KLT O-03, O-04: stock read the selected channel and pattern without checking anything: an empty Channel Rack
        # (getChannelName(0) on nothing), a -1 selection or an FL call that fails aborted OnInit/OnRefresh and left the
        # LCD without its main page. Each half of the text is now fetched on its own, bad indices are never passed on,
        # and a failing call keeps the last good text.
        old = self._main_text or ('?', '?')
        line1, line2 = old
        try:
            count = channels.channelCount()
            if count <= 0:
                line1 = 'No channel'
            else:
                active_index = channels.selectedChannel()
                if 0 <= active_index < count:
                    line1 = '%d - %s' % (active_index + 1, channels.getChannelName(active_index))
                else:
                    line1 = 'No selection'
        except Exception:
            KLTLog.log_once('sync-channel', 'Sync: channel name unavailable:\n' + traceback.format_exc().rstrip())
        try:
            pattern_number = patterns.patternNumber()
            line2 = '%s' % patterns.getPatternName(pattern_number) if pattern_number >= 1 else ''
        except Exception:
            KLTLog.log_once('sync-pattern', 'Sync: pattern name unavailable:\n' + traceback.format_exc().rstrip())
        self._main_text = (line1, line2)
        
        self._paged_display.SetPageLines(
            'main',
            line1=line1,   # KLT O-03: text checked per half in Sync
            line2=line2)






#----------------------------------------------------------------------------------------

# Function called for each event 


# KLT O-04: every FL callback below is wrapped in KLTLog.guarded, so one failing routine cannot stop the others and FL's
# Script output is not flooded by the same traceback every 20 ms (the log keeps one per site and second).

@KLTLog.guarded
def OnMidiMsg(event) :
    if _processor is not None and not _deinitialized :   # KLT O-04: no processor before OnInit, none after OnDeInit
        _processor.ProcessEvent(event)



# KLT O-04, O-15: helpers -----------------------------------------------------------------------------------------

def _step(name, fn, *args):
    """Run one routine on its own: an exception is logged (once per 30 s per routine and type) and printed once to FL's
    Script output, and the routines after it still run. FL crashes (BaseException) are not swallowed."""
    try:
        return fn(*args)
    except Exception as e:
        try:
            KLTLog.log_once((name, type(e).__name__, int(time.monotonic() // 30)),
                            'EXC in %s:\n%s' % (name, traceback.format_exc().rstrip()))
            if (name, type(e).__name__) not in _reported:
                _reported.add((name, type(e).__name__))
                print('KeyLab mkII (tuned): %s raised %s: %s (further repeats only in klt.log)' % (name, type(e).__name__, e))
        except Exception:
            pass
        return None


def _num(name, default):
    try:
        return float(getattr(CFG, name))
    except Exception:
        return default


def _probe(fn, name=None):
    """Call an FL function for the banner. With `name` the call is announced in klt.log first (KLT O-15: if FL dies inside
    a native call, the last line on disk names it)."""
    if name:
        KLTLog.log('probe: about to call %s' % name)
    try:
        return fn()
    except AttributeError:
        return 'n/a'
    except Exception as e:
        return 'ERR(%s)' % (e,)


def _banner():
    """KLT O-15: one line that tells klt.log (and FL's Script output) what FL 2026 did to this script. The stock printed
    three lines that said nothing about the output. Device queries beyond isAssigned() are made only when the script
    has an output: the FL 26.1.6 crash on tom (docs/incidents) is a native null read from a device.* call."""
    parts = ['%s v%s' % (KLT_NAME, KLT_VERSION), 'python %s' % sys.version.split()[0],
             'FL api %s' % _probe(general.getVersion, 'general.getVersion()')]
    assigned = _probe(device.isAssigned, 'device.isAssigned()')
    parts.append('device.isAssigned=%s' % (assigned,))
    port = None
    if assigned is True and getattr(CFG, 'LOG_DEVICE_DETAILS', True):
        parts.append('isMidiOutAssigned=%s' % _probe(lambda: device.isMidiOutAssigned(), 'device.isMidiOutAssigned()'))
        port = _probe(device.getPortNumber, 'device.getPortNumber()')
        parts.append('port=%s' % (port,))
        parts.append('name=%r' % (_probe(device.getName, 'device.getName()'),))
        if getattr(CFG, 'LOG_DEVICE_ID', False):
            did = _probe(device.getDeviceID, 'device.getDeviceID()')
            parts.append('deviceID=%s' % (did.hex() if isinstance(did, (bytes, bytearray)) else did,))
    elif assigned is True:
        parts.append('port/name/isMidiOutAssigned not queried: LOG_DEVICE_DETAILS is off')
    else:
        parts.append('port/name/isMidiOutAssigned not queried: no output')
    parts.append('output=%s' % ('on' if getattr(CFG, 'OUT_ENABLED', True) else 'DISABLED by KLTConfig.OUT_ENABLED'))
    line = ' | '.join(parts)
    KLTLog.log(line)
    print(line)
    KLTLog.log('cfg: %s' % ' '.join('%s=%s' % (k, getattr(CFG, k, '?')) for k in (
        'OUT_MAX_SYSEX_PER_SEC', 'OUT_MAX_SYSEX_PER_TICK', 'OUT_LCD_MIN_GAP_S', 'OUT_LED_PASS_S', 'OUT_TRICKLE_S',
        'INIT_ANIMATION', 'SPLASH_MS', 'SPLASH_TAG_MS', 'LCD_SCROLL_MS', 'PAD_LED_FLIP_ROWS', 'SAVE_LED_FOLLOWS_MODE',
        'GROUP_RELATIVE_CHANNELS')))
    if port == 10:
        KLTLog.log('WARNING: this script is on port 10, the port Arturia Analog Lab listens on for forwarded CCs; '
                   'the guide puts the DAW script on port 0 and the MIDI script on port 1 (docs/analysis O-11)')


def _reset_helper_state():
    """KLT O-08: FL may keep the script's modules loaded across OnDeInit/OnInit (Reload), and the helper modules' globals
    (modes, bank offsets, held pads) then survive: a stale bank offset indexed past the rack on every idle tick.
    A fresh OnInit starts like the first one."""
    if not getattr(CFG, 'RESET_HELPER_STATE_ON_INIT', True):
        return
    reset = getattr(KLTProcess, 'reset_state', None)      # the input side resets what it owns (modes, offsets, held pads)
    if callable(reset):
        reset()
    scalars = ((KLTProcess, {'SEQ_MODE': 0, 'MIXER_MODE': 0, 'RECT_OFFSET': 0, 'EDIT_MODE': 0, 'SEQ_PARAM': 0}),
               (KLTCrossKeyboard, {'MX_OFFSET': 0, 'CH_OFFSET': 0}),
               (KLTReturn, {'REFRESH_COUNT': 0, 'PASS': False, '_BEAT_AT': None}))
    for mod, values in scalars:
        for name, value in values.items():
            if hasattr(mod, name):
                setattr(mod, name, value)
    for name in ('STATE_MATRIX', 'LED_MATRIX'):
        for row in getattr(KLTProcess, name, ()):
            row[:] = [0] * len(row)
    pressed = getattr(KLTProcess, 'INDEX_PRESSED', None)
    if isinstance(pressed, list):
        del pressed[:]


def _start_splash():
    """KLT O-12: the welcome page, without blocking. "KeyLab mkII" / <FL window title> for SPLASH_MS (stock: 1500), then
    "KeyLab mkII" / "tuned <version>" for SPLASH_TAG_MS so the LCD says which script is running, then the main page.
    The page's second line is a callable, so the change of text needs no timer and no sleep."""
    pd = _mk2.paged_display()
    splash, tag = _num('SPLASH_MS', 1500.0), _num('SPLASH_TAG_MS', 1000.0)
    if splash <= 0 and tag <= 0:
        return
    title = _probe(ui.getProgTitle)
    if not isinstance(title, str) or title.startswith('ERR('):
        title = 'FL Studio'
    t0 = time.monotonic() * 1000

    def line2():
        if tag > 0 and time.monotonic() * 1000 - t0 >= splash:
            return 'tuned v' + KLT_VERSION
        return title
    pd.SetPageLines('welcome', line1='KeyLab mkII', line2=line2)
    pd.SetActivePage('welcome', expires=max(splash, 0) + max(tag, 0))


def _repaint():
    """KLT O-05: show everything again (memory switch, output re-assigned, FL asked for a full refresh). The LCD forgets
    what it believes it shows; the LED routines run now and their frames go through the shadow state."""
    global _led_due
    if _mk2 is None or _deinitialized:
        return
    _led_due = 0.0
    _step('Display.Invalidate', _mk2.display().Invalidate)
    _refresh_leds()


def _refresh_leds():
    lr = _mk2.LightReturn()
    with KLTDispatch.batch():
        _step('Sync', _mk2.Sync)
        _step('SequencerReturn', lr.SequencerReturn)
        _step('PlayReturn', lr.PlayReturn)
        _step('RecordReturn', lr.RecordReturn)


def _noisy_only(flags):
    """KLT O-07: True for a refresh that only carries HW_Dirty_Mixer_Controls / HW_Dirty_ControlValues, which fire while
    faders and knobs move and change neither an LED nor the text (mk3 filters them too, but by exact equality)."""
    try:
        if not getattr(CFG, 'REFRESH_IGNORE_NOISY_FLAGS', False):
            return False
        noisy = getattr(midi, 'HW_Dirty_Mixer_Controls', 4) | getattr(midi, 'HW_Dirty_ControlValues', 4096)
        flags = int(flags)
        return flags != 0 and (flags & ~noisy) == 0
    except Exception:
        return False


# Functions called when FL Studio is starting


@KLTLog.guarded   # KLT O-04: every callback is guarded
def OnInit():
    global _deinitialized, _led_due
    print("### %s v%s: OnInit start ###" % (KLT_NAME, KLT_VERSION))    # KLT O-15: stock's lines claimed success before it
    _deinitialized = False
    _step('banner', _banner)
    KLTDispatch.reset_output()               # KLT O-05: believe nothing about what the keyboard shows
    _step('reset helper state', _reset_helper_state)
    init(force=True)
    _led_due = 0.0
    if _mk2 is None:
        print("### %s: OnInit FAILED, the objects could not be created (see klt.log) ###" % KLT_NAME)
        return
    # KLT O-04: each step on its own; the stock aborted at the first exception and never activated the main page
    _step('Sync', _mk2.Sync)
    _step('splash', _start_splash)
    _step('main page', _mk2.paged_display().SetActivePage, 'main')
    _step('init sequence', _mk2.LightReturn().init)      # KLT O-12: arms the staged init; sends and sleeps nothing
    print("### %s: OnInit done (the LED init sequence runs from OnIdle; %d frames sent so far) ###" % (
        KLT_NAME, KLTDispatch.output_stats()['sent']))


def init(force=False) :
    # KLT F-17, O-09: the Forward script calls init() from its own OnInit. Stock rebuilt the DAW script's objects each time,
    # so with the DAW script initialised first the rebuilt display had no active page and the LCD stayed blank.
    # init() now only creates what is missing; OnInit passes force=True to start from scratch.
    global _mk2, _processor
    if force:
        _mk2 = None
        _processor = None
    if _mk2 is None:
        try:
            _mk2 = MidiControllerConfig()
        except Exception:
            KLTLog.exception('init: MidiControllerConfig')
            return
    if _processor is None:
        try:
            _processor = KeyLabMidiProcessor(_mk2)
        except Exception:
            KLTLog.exception('init: KeyLabMidiProcessor')
  

# Handles the script when FL Studio closes

@KLTLog.guarded   # KLT O-04: every callback is guarded
def OnDeInit():
    global _deinitialized
    if _mk2 is None or _deinitialized:
        _deinitialized = True
        KLTDispatch.close_output()
        return
    # KLT O-16: goodbye frames go out through the same gate and budgets; afterwards the output layer is closed, so a late
    # OnIdle/OnRefresh cannot touch a port FL is already tearing down.
    KLTDispatch.begin_shutdown()
    _step('goodbye lines', _mk2.paged_display().SetPageLines, 'goodbye', 'KeyLab mkII', 'Disconnected')
    _step('goodbye page', _mk2.paged_display().SetActivePage, 'goodbye')
    if getattr(CFG, 'SEND_DEINIT_FRAME', True):
        _step('deinit frame', send_to_device, bytes([0x02, 0x7D, 0x7D, 0x0B, 0x00]), True)
    if getattr(CFG, 'CLEAR_LEDS_ON_DEINIT', False):
        _step('clear LEDs', _mk2.LightReturn().Clear)
    KLTLog.log('OnDeInit: goodbye sent, output closed (%s)' % KLTDispatch.output_stats())
    _deinitialized = True
    KLTDispatch.close_output()
    return

  
# Function called when Play/Pause button is ON

@KLTLog.guarded   # KLT O-04: every callback is guarded
def OnUpdateBeatIndicator(value):
    if _mk2 is None or _deinitialized:
        return
    lr = _mk2.LightReturn()
    with KLTDispatch.batch():       # KLT O-02: only the final state per LED leaves (no flicker, no burst)
        _step('ProcessPlayBlink', lr.ProcessPlayBlink, value)
        _step('ProcessRecordBlink', lr.ProcessRecordBlink, value)
        _step('ProcessSequencerBlink', lr.ProcessSequencerBlink, value)
 


# Function called at refresh, flag value changes depending on the refresh type 

@KLTLog.guarded   # KLT O-04: every callback is guarded
def OnRefresh(flags) :
    if _mk2 is None or _deinitialized:
        return
    if _noisy_only(flags):
        return
    _refresh_leds()


# Function called for a full refresh (everything should be updated)

@KLTLog.guarded
def OnDoFullRefresh():
    # KLT O-08, O-05: FL asks for everything again (device reconnected, Refresh from the menu). The shadow state is forgotten
    # (every LED is re-sent, spread over the budgets) at most once a second, so a flood of these cannot become a flood of SysEx
    global _full_at
    if _mk2 is None or _deinitialized:
        return
    now = time.monotonic()
    if now - _full_at >= 1.0:
        _full_at = now
        KLTDispatch.resync()
    _repaint()


# Function called when a project is loaded

@KLTLog.guarded
def OnProjectLoad(status):
    # KLT O-08: a new project has other channels/patterns; repaint once it is loaded (midi.PL_LoadOk = 100)
    if _mk2 is None or _deinitialized:
        return
    if status >= 100:
        _repaint()

    

# Function called time to time mainly to update the beat indicator

@KLTLog.guarded   # KLT O-04: every callback is guarded
def OnIdle():
    global _led_due
    if _mk2 is None or _deinitialized:
        return
    # KLT O-02: the stock ran nine LED routines and re-sent 22-24 frames on every tick (~1,200 SysEx/s). Now: the output
    # layer delivers what is pending within its budgets, the LEDs are polled OUT_LED_PASS_S apart and only changes are sent.
    KLTDispatch.service()
    lr = _mk2.LightReturn()
    with KLTDispatch.batch():
        _step('InitStep', lr.InitStep)      # first: it holds the LEDs again if the output only just appeared
        if KLTDispatch.take_resync():
            _step('repaint after reconnect', _repaint)
        _step('Idle', _mk2.Idle)
        _step('RefreshTime', lr.RefreshTime)
        now = time.monotonic()
        if lr.init_done and now >= _led_due:
            _led_due = now + _num('OUT_LED_PASS_S', 0.1)
            for name in ('MetronomeReturn', 'LoopReturn', 'NotBlinkingLed', 'IsChannelSolo', 'IsChannelMuted',
                         'IsTrackSolo', 'IsTrackMuted', 'SelectedChannel'):
                _step(name, getattr(lr, name))
            # KLT O-07: a change of pad layout (Drum/Sequencer, bar, loop mode) is painted now, not at the next OnRefresh
            if _step('PadModeChanged', lr.PadModeChanged):
                _step('SequencerReturn', lr.SequencerReturn)
    
    
    
# Function called on a memory switch

@KLTLog.guarded   # KLT O-04: every callback is guarded
def OnSysEx(event) :
    # KLT O-04: the event may lack .sysex, or carry anything; only the exact memory-switch message acts
    data = getattr(event, 'sysex', None)
    try:
        data = bytes(data) if data is not None else None
    except Exception:
        data = None
    if data is not None:
        KLTLog.log_once(('sysex', data[:24]), 'OnSysEx %d bytes: %s%s' % (len(data), data[:48].hex(), '...' if len(data) > 48 else ''))
    if data == MEMORY_SWITCH :
        # KLT O-05: after a memory switch the keyboard shows its own screen. Stock called OnRefresh(32), which could
        # repaint LEDs but never the LCD (its payload cache said "already shown"): forget both caches first.
        KLTDispatch.resync()
        ui.setFocused(1)
        _repaint()          # KLT O-05: LCD invalidated, LED pass forced, Sync + pads + transport LEDs (what OnRefresh(32) did)
