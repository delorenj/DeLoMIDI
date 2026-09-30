import device
import ui
import time
import transport
import mixer
import channels
import patterns
import KLTProcess as KLmk2Pr
import KLTCrossKeyboard as AKLmk2

from KLTDispatch import send_to_device
from KLTDispatch import output_ready, hold_leds   # KLT O-12: the init sequence waits for the output and holds LEDs
import KLTConfig as CFG                          # KLT O-10, O-13, O-17: hardware-dependent choices are switches
import KLTLog


# This class handles visual feedback functions.

## CONSTANT

COLOR_PLAY_ON = bytes([0x02, 0x00, 0x10, 0x6D, 0x7F]) 
COLOR_PLAY_OFF = bytes([0x02, 0x00, 0x10, 0x6D, 0x00])
NB_TRACK_MAX = 125
REFRESH_COUNT = 0
PASS = False
WidMixer = 0
WidChannelRack = 1
WidPlaylist = 2
WidBrowser = 4
WidPlugin = 5


# MAPS

PAD_MAP = [
        0x70, 0x71, 0x72, 0x73,
        0x74, 0x75, 0x76, 0x77,
        0x78, 0x79, 0x7A, 0x7B,
        0x7C, 0x7D, 0x7E, 0x7F]
        
COLOR_MAP = [
        [0x7F, 0x00, 0x00], # RED
        [0x00, 0x00, 0x7F], # BLUE   # KLT O-17: stock labelled this GREEN and the next BLUE; the bytes are R,G,B
        [0x00, 0x7F, 0x00], # GREEN
        [0x7F, 0x00, 0x7F], # MAGENTA
        [0x00, 0x7F, 0x7F], # CYAN
        [0x7F, 0x7F, 0x00]] # YELLOW

SELECT_MAP = [0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29]

# KLT O-19: monotonic time of the last real beat callback in Sequencer mode (None = start counting at the next tick)
_BEAT_AT = None


def _switch(name, default):
    """A KLTConfig switch, defaulting to `default` if missing or unreadable."""
    try:
        return getattr(CFG, name)
    except Exception:
        return default


def _mode(name):
    """A mode/offset global of the input-side helper modules (SEQ_MODE, MIXER_MODE, RECT_OFFSET live in KLTProcess,
    MX_OFFSET/CH_OFFSET in KLTCrossKeyboard), 0 if it is not there."""
    for mod in (KLmk2Pr, AKLmk2):
        if hasattr(mod, name):
            return getattr(mod, name)
    return 0


def _pad_led(i):
    """LED id of pad i (0..15). KLT O-10: stock is 0x70+i; the community project found the pad LED rows vertically
    flipped on 49/88-key models. Unverified on the hardware, so PAD_LED_FLIP_ROWS defaults to stock."""
    if _switch('PAD_LED_FLIP_ROWS', False):
        return PAD_MAP[(3 - i // 4) * 4 + i % 4]
    return PAD_MAP[i]


def _rgb(led, r, g, b):
    return bytes([0x02, 0x00, 0x16, led, r, g, b, 0x7F])


def _selected_channel():
    """Index of the selected channel for the LED logic, None when the rack is empty or the index is not valid.
    KLT O-13: channels.selectedChannel() is group-relative like isChannelSolo/isChannelMuted/getGridBit (API 33+);
    stock's channelNumber() is global, so with a Channel Rack group filter it named another channel.
    KLT O-04: an empty rack answers 0 ("first channel") from both, and index 0 of an empty rack is invalid."""
    n = channels.channelCount()
    if n <= 0:
        return None
    if _switch('GROUP_RELATIVE_CHANNELS', True):
        idx = channels.selectedChannel()
    else:
        idx = channels.channelNumber()
    return idx if 0 <= idx < n else None


def _tempo_bpm():
    """Tempo in BPM. KLT O-19: the unit of mixer.getCurrentTempo(1) is unverified (the API stub says int, Novation's
    script formats it as BPM, Arturia's own mk3 script compares it to 99000, i.e. milli-BPM). FL's maximum is 522."""
    t = mixer.getCurrentTempo(1)
    if t > 1000:
        t = t / 1000.0
    return t if t > 0 else 120.0


def _animation_frames(level):
    """KLT O-12: the init animation as a list of frames the state machine sends a few per OnIdle tick.
    2 = Arturia's sequence (black, 6 colours on/off, white, black: 240 frames), 1 = a 32-frame pad wipe, 0 = none."""
    black = [_rgb(_pad_led(i), 0x00, 0x00, 0x00) for i in range(16)]
    if level >= 2:
        frames = list(black)
        for colour in COLOR_MAP:
            frames += [_rgb(_pad_led(i), colour[0], colour[1], colour[2]) for i in range(16)]
            frames += black
        frames += [_rgb(_pad_led(i), 0x7F, 0x7F, 0x7F) for i in range(16)]
        frames += black
        return frames
    if level == 1:
        return [_rgb(_pad_led(i), 0x7F, 0x7F, 0x7F) for i in range(16)] + black
    return []

class KeyLabLightReturn:

    def __init__(self):
        # KLT O-12: the init sequence is a small state machine advanced by InitStep() from OnIdle
        self._step = 0
        self._init_stage = 'idle'        # idle (never armed) -> wait (for the output) -> anim -> done
        self._init_frames = []
        self._init_pos = 0
        self._pad_mode = None            # KLT O-07: (SEQ_MODE, bank, loop mode) the pads were last painted for

    def init(self) :
        # KLT O-12: stock blocked FL's main thread here for 2.92 s (240 SysEx interleaved with time.sleep) and did it
        # again on every Reload. Now OnInit only arms the sequence; OnIdle advances it a few frames per tick, and only
        # once the output is assigned. LED frames requested meanwhile are held back and painted when it is done.

        # FOR METRONOME
        self._step = 0

        # KLT O-12: the animation frames are prepared here and sent by InitStep(), a few per OnIdle tick
        try:
            level = int(_switch('INIT_ANIMATION', 0))
        except Exception:
            level = 0
        self._init_frames = _animation_frames(level)
        self._init_pos = 0
        self._init_stage = 'wait'
        hold_leds(True)

    # KLT O-12: True while the staged init is finished (or was never armed)
    @property
    def init_done(self):
        return self._init_stage in ('idle', 'done')

    # KLT O-12: the staged init, one call per OnIdle tick
    def InitStep(self):
        """Advance the init sequence by one OnIdle tick (a few frames at most). True once it is finished.
        KLT O-12, O-01: safe with the keyboard absent: it waits, sends nothing, and blocks nothing."""
        if self._init_stage in ('idle', 'done'):
            return True
        hold_leds(True)                         # KLT O-12: alive: the hold timeout only fires if OnIdle stops calling us
        if self._init_stage == 'wait':
            if not output_ready():
                return False
            self._init_stage = 'anim'
            KLTLog.log('init: output ready, %d animation frames, then the LEDs paint' % len(self._init_frames))
        if self._init_stage == 'anim':
            try:
                per_tick = max(1, int(_switch('INIT_FRAMES_PER_TICK', 4)))
            except Exception:
                per_tick = 4
            sent = 0
            while sent < per_tick and self._init_pos < len(self._init_frames):
                if not send_to_device(self._init_frames[self._init_pos], force=True):
                    return False                # no budget right now (or the output went away): retry next tick
                self._init_pos += 1
                sent += 1
            if self._init_pos >= len(self._init_frames):
                self._init_stage = 'done'
                hold_leds(False)
                KLTLog.log('init: sequence complete')
                return True
        return False

    # KLT O-07: the pads only followed OnRefresh; a mode change repaints them by itself
    def PadModeChanged(self):
        """True once when the pad layout changed since the last call (drum/Sequencer mode, bar shown, loop mode). The
        stock repainted pads only from OnRefresh and relied on the button's fake Punch message to make FL send one."""
        mode = (_mode('SEQ_MODE'), max(0, _mode('RECT_OFFSET')), bool(transport.getLoopMode()))
        changed = self._pad_mode is not None and mode != self._pad_mode
        self._pad_mode = mode
        return changed

    # KLT O-16: optional black-out at shutdown
    def Clear(self):
        """KLT O-16: black out pads and select buttons (CLEAR_LEDS_ON_DEINIT). Forced frames: the caller is shutting down."""
        for i in range(16):
            send_to_device(_rgb(_pad_led(i), 0x00, 0x00, 0x00), force=True)
        for led in SELECT_MAP:
            send_to_device(_rgb(led, 0x00, 0x00, 0x00), force=True)
        send_to_device(_rgb(0x2A, 0x00, 0x00, 0x00), force=True)


    def MetronomeReturn(self) :
        if ui.isMetronomeEnabled() :
            send_to_device(bytes([0x02, 0x00, 0x10, 0x68, 0x7F]))
        else :
            send_to_device(bytes([0x02, 0x00, 0x10, 0x68, 0x09]))

            
    def CountdownReturn(self) :
        if ui.isPrecountEnabled() :
            send_to_device(bytes([0x02, 0x00, 0x10, 0x65, 0x7F]))
        else :
            send_to_device(bytes([0x02, 0x00, 0x10, 0x65, 0x09]))


    def LoopReturn(self) :
        if ui.isLoopRecEnabled() :
            send_to_device(bytes([0x02, 0x00, 0x10, 0x6F, 0x7F]))
        else :
            send_to_device(bytes([0x02, 0x00, 0x10, 0x6F, 0x09]))


    def RecordReturn(self) :
        if transport.isRecording() :
            send_to_device(bytes([0x02, 0x00, 0x10, 0x6E, 0x7F]))
        else :
            send_to_device(bytes([0x02, 0x00, 0x10, 0x6E, 0x09]))


    def PlayReturn(self) :
        if mixer.getSongTickPos() != 0 :
            send_to_device(bytes([0x02, 0x00, 0x10, 0x6D, 0x7F]))
            send_to_device(bytes([0x02, 0x00, 0x10, 0x6C, 0x09]))
        else :
            send_to_device(bytes([0x02, 0x00, 0x10, 0x6D, 0x09]))
            send_to_device(bytes([0x02, 0x00, 0x10, 0x6C, 0x7F]))


    def IsChannelSolo(self) :
        if ui.getFocused(WidChannelRack):
            ch = _selected_channel()      # KLT O-13, O-04: group-relative index; None for an empty rack (was index 0)
            if ch is not None and channels.isChannelSolo(ch) :
                send_to_device(bytes([0x02, 0x00, 0x10, 0x60, 0x7F]))              
            else :
                send_to_device(bytes([0x02, 0x00, 0x10, 0x60, 0x09]))
            
    def IsTrackSolo(self) :
        if ui.getFocused(WidMixer):
            if mixer.isTrackSolo(mixer.trackNumber()) :
                send_to_device(bytes([0x02, 0x00, 0x10, 0x60, 0x7F]))              
            else :
                send_to_device(bytes([0x02, 0x00, 0x10, 0x60, 0x09]))
    
 
    def IsChannelMuted(self) :
        if ui.getFocused(WidChannelRack):
            ch = _selected_channel()      # KLT O-13, O-04: group-relative index; None for an empty rack (was index 0)
            if ch is not None and channels.isChannelMuted(ch) :
                send_to_device(bytes([0x02, 0x00, 0x10, 0x61, 0x7F]))
            else :
                send_to_device(bytes([0x02, 0x00, 0x10, 0x61, 0x09]))
            
    def IsTrackMuted(self) :
        if ui.getFocused(WidMixer):
            if mixer.isTrackMuted(mixer.trackNumber()) :
                send_to_device(bytes([0x02, 0x00, 0x10, 0x61, 0x7F]))
            else :
                send_to_device(bytes([0x02, 0x00, 0x10, 0x61, 0x09]))

    
    def SetChannelMap(self) :
        if _mode('MIXER_MODE') :      # KLT O-08: helper globals read defensively
            ACTIVE_CHANNELS = NB_TRACK_MAX
            NB_BANK = (ACTIVE_CHANNELS//8)+1
            ITEMS = (ACTIVE_CHANNELS%8)
            CHANNEL_MAP = NB_BANK*[8*[0]]
            for i in range(NB_BANK-1) :
                CHANNEL_MAP[i] = 8*[1]
            for i in range(ITEMS) :
                CHANNEL_MAP[NB_BANK-1][i] = 1
            return CHANNEL_MAP
        else :
            ACTIVE_CHANNELS = channels.channelCount()
            NB_BANK = (ACTIVE_CHANNELS//8)+1
            ITEMS = (ACTIVE_CHANNELS%8)
            CHANNEL_MAP = NB_BANK*[8*[0]]
            for i in range(NB_BANK-1) :
                CHANNEL_MAP[i] = 8*[1]
            for i in range(ITEMS) :
                CHANNEL_MAP[NB_BANK-1][i] = 1
            return CHANNEL_MAP
    

    def SelectedChannel(self) :
        # KLT O-08, O-04: rewritten without changing a byte on the wire. Stock had four identical if/elif chains (the
        # "active bank" and "other bank" branches were the same code) and indexed CHANNEL_MAP[CH_OFFSET] with a stale
        # offset: IndexError on every idle tick after the rack shrank. The offset is clamped for the LEDs here (the input
        # side keeps its own); each FL query is made once per slot instead of up to four times.
        mixer_mode = _mode('MIXER_MODE')
        CHANNEL_MAP = self.SetChannelMap()
        BANK_SELECTED = _mode('MX_OFFSET') if mixer_mode else _mode('CH_OFFSET')
        BANK_SELECTED = max(0, min(BANK_SELECTED, len(CHANNEL_MAP) - 1))
        for j in range(len(CHANNEL_MAP[BANK_SELECTED])) :
            if CHANNEL_MAP[BANK_SELECTED][j] == 1 :
                if mixer_mode :
                    # KLT O-08: same colours as stock (blue available, yellow selected, red muted), one query per slot
                    index = j+(8*BANK_SELECTED)+1
                    selected = mixer.isTrackSelected(index)
                    muted = mixer.isTrackMuted(index)
                    unselected = [0x00, 0x00, 0x7F]         # blue: track available
                else :
                    index = j+(8*BANK_SELECTED)   # KLT O-08: same slot logic, channel index
                    selected = channels.isChannelSelected(index)
                    muted = channels.isChannelMuted(index)
                    unselected = [0x7F, 0x00, 0x7F]         # purple: channel available
                if muted :
                    colour = [0x7F, 0x00, 0x00]             # red: muted (selected or not)
                elif selected :
                    colour = [0x7F, 0x7F, 0x00]             # yellow: selected
                else :
                    colour = unselected   # KLT O-08: muted beats selected beats available, as stock
                send_to_device(_rgb(SELECT_MAP[j], colour[0], colour[1], colour[2]))
            else :
                send_to_device(_rgb(SELECT_MAP[j], 0x00, 0x00, 0x00))


    def SequencerReturn(self) :
        if _mode('SEQ_MODE') == 1 :   # KLT O-08: mode globals read through _mode()
            if not transport.getLoopMode() :
                # KLT O-04, O-13: group-relative selected channel; an empty rack shows every step as off
                ch = _selected_channel()
                offset = 16*max(0, _mode('RECT_OFFSET'))
                for i in range (len(PAD_MAP)) :
                    if ch is not None and channels.getGridBit(ch,i+offset) == 1 :
                        bit_velocity = channels.getCurrentStepParam( ch, i+offset, 1)
                        # KLT O-14: getCurrentStepParam can answer -1 (mk3 guards it); -1//4 made bytes() raise
                        bit_velocity = max(0, min(127, bit_velocity))
                        send_to_device(_rgb(_pad_led(i), bit_velocity//4, bit_velocity//4, 0x00))
                    else :
                        send_to_device(_rgb(_pad_led(i), 0x7F, 0x7F, 0x7F))   # KLT O-10: pad LED id through the O-10 switch
            else :
                for i in range(0,16) :
                    send_to_device(_rgb(_pad_led(i), 0x7F, 0x00, 0x7F))   # KLT O-10: pad LED id through the O-10 switch
        else :
            for i in range (len(PAD_MAP)) :
                    send_to_device(_rgb(_pad_led(i), 0x7F, 0x00, 0x00))   # KLT O-10: pad LED id through the O-10 switch



    def ProcessPlayBlink(self, value):
        COLOR_PLAY_ON = bytes([0x02, 0x00, 0x10, 0x6D, 0x7F]) 
        COLOR_PLAY_OFF = bytes([0x02, 0x00, 0x10, 0x6D, 0x09])

        if value == 0 :
            send_to_device(COLOR_PLAY_OFF)        
        else :
            send_to_device(COLOR_PLAY_ON)

        
    def ProcessRecordBlink(self, value) :
        if transport.isRecording() :            
            COLOR_RECORDING_ON = bytes([0x02, 0x00, 0x10, 0x6E, 0x7F]) 
            COLOR_RECORDING_OFF = bytes([0x02, 0x00, 0x10, 0x6E, 0x09])
            if value == 0 :
                send_to_device(COLOR_RECORDING_OFF)
            else :
                send_to_device(COLOR_RECORDING_ON)
                 
    
    def ProcessSequencerBlink(self, value) :
        if _mode('SEQ_MODE') == 1 :   # KLT O-08: mode globals read through _mode()
            if not transport.getLoopMode() :
                global REFRESH_COUNT
                global PASS
                global _BEAT_AT   # KLT O-19: time of the last real beat callback
                PASS = False
                REFRESH_COUNT = 0
                _BEAT_AT = time.monotonic()      # KLT O-19: RefreshTime measures real time from this beat
                actual_step = mixer.getSongStepPos()
                self.SequencerReturn()
                self._highlight(actual_step)

    def _highlight(self, actual_step) :
        # KLT O-10: the playhead pad (blue inside the shown bar, red outside it), pad LED id through the O-10 switch
        offset = 16*max(0, _mode('RECT_OFFSET'))
        if actual_step in range (offset,16+offset) :
            send_to_device(_rgb(_pad_led(actual_step%16), 0x00, 0x00, 0x7F))
        else :
            send_to_device(_rgb(_pad_led(actual_step%16), 0x7F, 0x00, 0x00))

    
    def RefreshTime(self) :
        # Triggers a Fake OnUpdateBeatIndicator for sixteen notes  
        if _mode('SEQ_MODE') == 1 and mixer.getSongTickPos() != 0 :   # KLT O-08: mode globals read through _mode()
            if not transport.getLoopMode() :
                global REFRESH_COUNT
                global PASS
                global _BEAT_AT   # KLT O-19: time of the last real beat callback
                REFRESH_COUNT += 1
                # KLT O-19: stock counted idle ticks and divided by 22 (a guess at the idle rate; FL documents ~50/s),
                # with a tempo whose unit is unverified. Real elapsed time and a normalised tempo do what it meant.
                now = time.monotonic()
                if _BEAT_AT is None:
                    _BEAT_AT = now
                    return
                tresh = (60/_tempo_bpm())/4
                if now - _BEAT_AT >= tresh and PASS == False :
                    PASS = True
                    actual_step = mixer.getSongStepPos()
                    self.SequencerReturn()
                    if actual_step % 2 != 0 :
                        self._highlight(actual_step)   # KLT O-10: playhead highlight, pad LED id through the O-10 switch
                    else :
                        self._highlight(actual_step+1)   # KLT O-10: playhead highlight, pad LED id through the O-10 switch


    def NotBlinkingLed(self) :
    
        # DAW CONTROL LED
        
        send_to_device(bytes([0x02, 0x00, 0x10, 0x62, 0x7F]))
        send_to_device(bytes([0x02, 0x00, 0x10, 0x63, 0x7F]))
        send_to_device(bytes([0x02, 0x00, 0x10, 0x64, 0x7F]))
        # KLT O-17: stock lights Save (65) all the time, so Sequencer mode had no indicator. Which polarity the hardware
        # expects is unverified, hence a switch: SAVE_LED_FOLLOWS_MODE lights it only in Sequencer mode.
        if _switch('SAVE_LED_FOLLOWS_MODE', False) and _mode('SEQ_MODE') != 1 :
            send_to_device(bytes([0x02, 0x00, 0x10, 0x65, 0x09]))
        else :
            send_to_device(bytes([0x02, 0x00, 0x10, 0x65, 0x7F]))
        send_to_device(bytes([0x02, 0x00, 0x10, 0x66, 0x7F]))
        send_to_device(bytes([0x02, 0x00, 0x10, 0x67, 0x7F]))
        send_to_device(bytes([0x02, 0x00, 0x10, 0x69, 0x7F]))
        send_to_device(bytes([0x02, 0x00, 0x10, 0x6A, 0x7F]))
        send_to_device(bytes([0x02, 0x00, 0x10, 0x6B, 0x7F]))
        
        # CENTER LED
        
        send_to_device(bytes([0x02, 0x00, 0x10, 0x1A, 0x7F]))
        send_to_device(bytes([0x02, 0x00, 0x10, 0x1B, 0x7F]))
        
        # CHANNELS LEDS
        
        send_to_device(bytes([0x02, 0x00, 0x16, 0x2A, 0x7F, 0x7F, 0x7F, 0x7F]))
        
    

        

        

        
