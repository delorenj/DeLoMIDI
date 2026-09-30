import channels
import general
import mixer
import patterns
import transport
import ui
import device
import plugins
import midi
import KLTCrossKeyboard as AKLmk2
import KLTSeqParam as KLmk2SQP
import KLTPlugin
import KLTConfig as CFG     # KLT F-03: input-side switches
import KLTLog               # KLT F-03: never raises; diagnostics for the hardware-dependent unknowns


# KLT F-17: stock also imported send_to_device, KeyLabDisplay and KeyLabPagedDisplay here without using them, which tied
# the input side to the output modules' import-time behaviour; only the dispatcher and the navigation are needed
from KLTDispatch import MidiEventDispatcher
from KLTNavigation import NavigationMode

## CONSTANT

PORT_MIDICC_ANALOGLAB = 10
WidMixer = 0
WidChannelRack = 1
WidPlaylist = 2
WidBrowser = 4
WidPlugin = 5
ANALOGLAB_KNOB_ID = [0x4A, 0x47, 0x4C, 0x4D, 0x5D, 0x49, 0x4B]

# ABS
ABSOLUTE_VALUE = 64

# Event code indicating stop event
SS_STOP = 0

# Event code indicating start start event
SS_START = 2

# SEQUENCER
SEQ_MODE = 0

# MIXER
MIXER_MODE = 0

# RECTANGLE OFFSET
RECT_OFFSET = 0

# KLT F-12: upper bound of the step window (32 bars of 16 steps = 512 steps, the largest FL grid); stock let << / >> run away
MAX_RECT_OFFSET = 31

# EDIT MODE
EDIT_MODE = 0

# SEQ PARAM
SEQ_PARAM = 0

# Max Tracks
MAX_TRACKS = 125

# STATE_MATRIX
STATE_MATRIX = [
                4*[0],
                4*[0],
                4*[0],
                4*[0],
                ]
# LED_MATRIX
LED_MATRIX = [
                4*[0],
                4*[0],
                4*[0],
                4*[0],
                ]
# INDEX PRESSED
INDEX_PRESSED = []

# FPC MAP
FPC_MAP = {
            "36":49,
            "37":55,
            "38":51,
            "39":53,
            "40":48,
            "41":47,
            "42":45,
            "43":43,
            "44":40,
            "45":38,
            "46":46,
            "47":44,
            "48":37,
            "49":36,
            "50":42,
            "51":54
            }

# KLT F-02: Analog Lab's fixed CC layout (8 knobs, then 9 faders); the position is the control's number on the keyboard
ANALOG_LAB_KNOBS = (74, 71, 76, 77, 93, 18, 19, 16)
ANALOG_LAB_FADERS = (73, 75, 79, 72, 80, 81, 82, 83, 17)


# ---- module-level helpers ----------------------------------------------------------------------------------------------
# KLT F-01, F-04, F-05, F-06, F-07: everything a pad or a keyboard-port CC needs is a plain function of the raw event
# (status/data1/data2) and the module state, so the Forward script can call it without building a second processor
# (stock: Forward -> KL.init() -> a second _mk2/_processor) and without midiId.

def _mid(status):
    """midiId derived from the raw status byte (what FL puts in event.midiId for OnMidiMsg)."""
    return status & 0xF0 if status < 0xF0 else status


def _safe(fn, *args):
    """A device.* call that must never take the callback down (KLT F-27)."""
    try:
        return fn(*args)
    except Exception as e:
        name = getattr(fn, '__name__', '?')
        KLTLog.log_once(('safe', name), 'FL call %s raised %r (later failures of it are not logged)' % (name, e))
        return None


def sync_mode_from_focus():
    """KLT F-12: faders/encoders/banks follow the window FL really has focused, so a mouse click on the Mixer or the
    Channel Rack cannot leave MIXER_MODE behind (Solo/Mute and the jog always followed the real focus). Plugin windows,
    the Browser, the Playlist... leave the mode alone. Also called by the output side on OnRefresh if it wants the LEDs to
    follow at once."""
    global MIXER_MODE
    if not CFG.MODE_FOLLOWS_FOCUS:
        return
    try:
        if MIXER_MODE == 0 and ui.getFocused(WidMixer):
            MIXER_MODE = 1
        elif MIXER_MODE == 1 and ui.getFocused(WidChannelRack):
            MIXER_MODE = 0
    except Exception:
        pass


def reset_pad_state():
    """KLT F-04: forget every held pad (a release that never arrives left EDIT_MODE stuck: every encoder then edited step 0)."""
    global EDIT_MODE, INDEX_PRESSED
    for row in STATE_MATRIX:
        row[:] = 4*[0]
    EDIT_MODE = 0
    INDEX_PRESSED = []


def reset_state():
    """KLT F-12: every mutable module global back to its power-on value (for OnInit after an FL script reload)."""
    global SEQ_MODE, MIXER_MODE, RECT_OFFSET, EDIT_MODE, SEQ_PARAM
    SEQ_MODE = MIXER_MODE = RECT_OFFSET = EDIT_MODE = SEQ_PARAM = 0
    reset_pad_state()
    AKLmk2.MX_OFFSET = 0
    AKLmk2.CH_OFFSET = 0
    KLmk2SQP.PAGE = 0


def fpc_selected():
    """KLT F-07: are the pads playing FPC? The selected channel's plugin decides (that is what receives the notes); the
    focused plugin window is only the fallback when FL cannot name the channel's plugin."""
    try:
        sel = AKLmk2.sel_channel()
        if sel >= 0:
            name = plugins.getPluginName(sel)
            if name:
                return name.strip().lower() == 'fpc'
        return ui.getFocusedPluginName().strip().lower() == 'fpc'
    except Exception:
        return False


def _pad_bit(event):
    """0..15 for the pad notes 36..51, else -1 (KLT F-06: stock indexed a dict with None for any other note)."""
    n = event.controlNum - 36
    return n if 0 <= n <= 15 else -1


def hold_bit(event):
    global EDIT_MODE
    bit = _pad_bit(event)
    if bit < 0:
        return
    EDIT_MODE = 1
    STATE_MATRIX[bit//4][bit%4] = 1


def release_bit(event):
    global EDIT_MODE
    bit = _pad_bit(event)
    if bit < 0:
        return
    if STATE_MATRIX[bit//4][bit%4] != 1:
        return          # KLT F-04: a release whose press was forgotten (mode toggled while held) must not toggle a step
    STATE_MATRIX[bit//4][bit%4] = 0
    EDIT_MODE = 0

    # While at least one pad is pressed, stay in edit mode
    hold_num = 0
    for i in STATE_MATRIX :
        for j in i :
            if j == 1 :
                hold_num += 1
    if hold_num != 0 :
        EDIT_MODE = 1
    else :
        channels.closeGraphEditor(1)

    # If a parameter changed, let the pad on
    if SEQ_PARAM == 1 :
        return
    if transport.getLoopMode() :
        return          # KLT F-04: song mode never toggled steps (stock ignored the whole release, leaving EDIT_MODE stuck)
    channel = AKLmk2.sel_channel()      # KLT F-13, O-08: group-relative index, -1 = nothing to address
    if channel < 0 :
        return
    step = bit + (16*RECT_OFFSET)
    if channels.getGridBit(channel, step) == 0 :
        channels.setGridBit(channel, step, 1)
        LED_MATRIX[bit//4][bit%4] = 1
    else :
        channels.setGridBit(channel, step, 0)
        LED_MATRIX[bit//4][bit%4] = 0


def press_sequencer(event):
    global SEQ_PARAM
    SEQ_PARAM = 0
    if channels.isGraphEditorVisible() :
        SEQ_PARAM = 1
    hold_bit(event)


def handle_pad(event):
    """The 16 pads (0x99 / 0x89, channel 10), from raw status/data1/data2 only. True if the event was a pad event.
    Drum mode: remap to FPC's layout (FPC only, KLT F-07), velocity untouched (KLT F-05), let FL play the note.
    Sequencer mode: the pad is a step button and is consumed. Used by the DAW port's processor and by the Forward script."""
    st = event.status
    release = (st == 137) or (st == 153 and CFG.PADS_NOTE_ON_ZERO_IS_RELEASE and event.data2 == 0)
    press = (st == 153) and not release
    if not (press or release) :
        return False
    if SEQ_MODE == 1 :
        if _pad_bit(event) >= 0 :                       # KLT F-06: other notes are not step pads, leave them to FL
            event.handled = True
            if press :
                _safe(device.processMIDICC, event)      # KLT F-27: device.* guarded; lets FL's link system see the pad
                press_sequencer(event)
            else :
                release_bit(event)                      # KLT F-04: always, in song mode too
    else :
        # KLT F-05: stock also overwrote event.data2 with 144 / 128 (MIDI_NOTEON / MIDI_NOTEOFF): the velocity was
        # destroyed and left the 0..127 range. KLT F-06: FPC_MAP.get() returned None outside 36..51 and was assigned.
        # KLT F-07: the FPC layout only makes sense for FPC (stock scrambled every other instrument's pads)
        if fpc_selected() or not CFG.PADS_REMAP_ONLY_FOR_FPC :
            mapped = FPC_MAP.get(str(event.data1))
            if mapped is not None :
                event.data1 = mapped
        event.handled = False
    return True


def _analog_lab_clef(cc):
    """KLT F-02: the plugin database key of an Analog Lab knob/fader CC (knob i -> '16'+i, fader j -> '224'+j), or None."""
    if cc in ANALOG_LAB_KNOBS:
        return str(16 + ANALOG_LAB_KNOBS.index(cc))
    if cc in ANALOG_LAB_FADERS:
        j = ANALOG_LAB_FADERS.index(cc)
        return str(224 + j) if j < 8 else None          # fader 9 is the master fader: no database row
    return None


def handle_keyboard_cc(event):
    """Channel-1 CCs on the KEYBOARD port while no Arturia V Collection plugin is focused, from raw fields only.
    True if the CC is one of ours (the event itself is never consumed: FL still delivers it to the instrument).
      CC28 / CC29    previous / next preset of the focused plugin (press only), as Arturia's OnPluginEvent intended
      CC1            mod wheel -> the focused plugin's database parameter, absolute (stock: read as a relative tick count)
      Analog Lab CCs (74, 71, ...) -> only with KLTConfig.ANALOG_LAB_CC_TO_PLUGIN_DB
    KLT F-02: stock bound these through a dispatcher that called self.Plugin(event) without its required `clef`
    argument (TypeError on all 17 Analog Lab CCs, the CC left consumed) and that was only reachable if midiId was 0 in
    OnMidiIn (H2); nothing here needs midiId."""
    if event.status != midi.MIDI_CONTROLCHANGE :
        return False
    cc = event.controlNum
    if cc == 28 or cc == 29 :
        if event.data2 != 0 and ui.getFocused(WidPlugin) :
            channel = AKLmk2.sel_channel()
            if channel >= 0 :
                if cc == 28 :
                    plugins.prevPreset(channel)
                else :
                    plugins.nextPreset(channel)
        return True
    if cc == 1 :
        # KLT F-02, F-09: stock reached SetPanTrack from here, which computed mixer track (1 - 15) = -14 in mixer mode
        if MIXER_MODE == 0 and EDIT_MODE == 0 and ui.getFocused(WidPlugin) :
            KLTPlugin.Plugin(event, 1)
        return True
    if CFG.ANALOG_LAB_CC_TO_PLUGIN_DB :
        clef = _analog_lab_clef(cc)
        if clef is not None :
            if MIXER_MODE == 0 and EDIT_MODE == 0 and ui.getFocused(WidPlugin) :
                KLTPlugin.Plugin(event, clef, True)
            return True
    return False


# This class processes all CC coming from the controller
# The class creates new handler for each function
# The class calls the right fonction depending on the incoming CC

class KeyLabMidiProcessor:

    @staticmethod
    def _is_pressed(event):
        # KLT F-23: a note-off (0x80) is a release whatever its velocity says (stock only knew note-on velocity 0)
        if CFG.NOTE_OFF_IS_RELEASE and (event.status & 0xF0) == 0x80 :
            return False
        return event.controlVal != 0

    def __init__(self, mk2):
        # KLT F-01: dispatch on the raw status byte; stock used event.midiId, which FL may leave at 0 outside OnMidiMsg
        def by_midi_id(event) : return _mid(event.status)
        def by_control_num(event) : return event.controlNum
        def by_status(event) : return event.status
        def ignore_release(event): return self._is_pressed(event)
        def ignore_press(event): return not self._is_pressed(event)

        self._mk2 = mk2
        self._mapped = False
        self._scrubbing = {1 : False, -1 : False}      # KLT F-23: << / >> currently scrubbing the transport
        self._editors = set()                          # KLT F-14: channels whose editor this script opened

        self._midi_id_dispatcher = (
            MidiEventDispatcher(by_midi_id)
            .NewHandler(144, self.OnCommandEvent)
            .NewHandler(128, self.OnCommandEvent)       # KLT F-23: note-off releases are routed too
            .NewHandler(176, self.OnKnobEvent)
            .NewHandler(224, self.OnSliderEvent)   # KLT F-01: keys are derived from the raw status byte (by_midi_id)
            )


        # KLT F-02: the status dispatcher's 176 -> OnPluginEvent entry and the whole _plugin_dispatcher are gone; the
        # keyboard-port CC handling is handle_keyboard_cc() above
        self._status_dispatcher = (
            MidiEventDispatcher(by_status)
            # KLT F-02: no 176 -> OnPluginEvent entry here any more (unreachable from OnMidiMsg, wrong signature)
            .NewHandler(153, self.OnDrumSeqEvent)
            .NewHandler(137, self.OnDrumSeqEvent)
            )


        self._midi_command_dispatcher = (
            MidiEventDispatcher(by_control_num)


            .NewHandler(95, self.Record, ignore_release)
            .NewHandler(94, self.Start, ignore_release)
            .NewHandler(93, self.Stop, ignore_release)
            .NewHandler(89, self.SetClick, ignore_press)
            .NewHandler(74, self.DrumSeqToggle, ignore_release)
            .NewHandler(56, self.TapTempo, ignore_release)
            .NewHandler(88, self.Overdub, ignore_press)
            .NewHandler(86, self.Loop, ignore_release)
            .NewHandler(81, self.Undo, ignore_press)
            .NewHandler(57, self.Cut, ignore_press)
            .NewHandler(0x5B, self.RewindORprevBar)
            .NewHandler(0x5C, self.FastForwardORnextBar)
            .NewHandler(84, self.SwitchWindow, ignore_release)
            .NewHandler(46, self.BankSelect, ignore_release)
            .NewHandler(47, self.BankSelect, ignore_release)
            .NewHandler(98, self.previousPattern, ignore_release)
            .NewHandler(99, self.nextPattern, ignore_release)
            .NewHandler(87, self.ToggleBrowserChannelRack, ignore_release)
            .NewHandler(51, self.ToggleMixerChannelRack, ignore_release)
            .NewHandlerForKeys(range(8, 16), self.SoloChannel, ignore_press)
            .NewHandlerForKeys(range(16, 24), self.MuteChannel, ignore_press)
            .NewHandlerForKeys(range(24, 32), self.TrackSelect,ignore_press)
            .NewHandlerForKeys(range(0, 8), self.SnapMode, ignore_release)

        )

        self._knob_dispatcher = (
            MidiEventDispatcher(by_control_num)
            .NewHandler(60, self.OnKnobNavEvent)     # KLT F-10: registered once (stock twice); _knob_nav_dispatcher is gone, ticks are decoded
            .NewHandlerForKeys(range(16,25), self.SetPanTrack)
        )

        # MAPPING SLIDERS
        # KLT F-08: the fader handler is pure and consumed by _consume

        self._slider_dispatcher = (
            MidiEventDispatcher(by_status)
            .NewHandlerForKeys(range(224,233), self.SetVolumeTrack)
        )

            # NAVIGATION

        self._navigation = NavigationMode(self._mk2.paged_display())




    # DISPATCH


    def ProcessEvent(self, event, where = 'DAW.OnMidiMsg') :
        # KLT F-01, F-03: never raises (FL prints a traceback and drops the callback's work); True = the event was one of ours
        try :
            return self._process(event, where)
        except Exception :
            KLTLog.exception('KeyLabMidiProcessor.ProcessEvent')
            return False

    def _process(self, event, where) :
        if where :
            AKLmk2.raw_log(where, event)
            AKLmk2.probe(where, event)
        self._mapped = False
        sync_mode_from_focus()          # KLT F-12: mode follows the focused window
        AKLmk2.clamp_banks()            # KLT F-12: offsets stay inside the live counts
        status = event.status
        mid = _mid(status)              # KLT F-01: from the raw status, not event.midiId
        if mid == 128 and not CFG.NOTE_OFF_IS_RELEASE :
            return False                # KLT F-23: stock never routed note-offs
        if status == mid or mid == 224 :
            self._midi_id_dispatcher.Dispatch(event)
        else :
            self._status_dispatcher.Dispatch(event)
        return self._mapped

    def _consume(self, dispatcher, event, where) :
        # KLT F-03: stock set event.handled = True BEFORE looking at the table, so every unmapped note / CC / bend on
        # channel 1 was swallowed without a trace. Now only an event a handler exists for is consumed; the rest is logged
        # and (KLTConfig.PASS_UNMAPPED) left to FL. A mapped control whose handler failed stays consumed (as before).
        try :
            mapped = dispatcher.Dispatch(event)
        except Exception :
            KLTLog.exception('KeyLabMidiProcessor.%s' % where)
            mapped = True
        if mapped :
            self._mapped = True
            event.handled = True
        else :
            AKLmk2.note_unmapped(event, where)
            if not CFG.PASS_UNMAPPED and (event.status & 0xF0) != 0x80 :
                event.handled = True

    def OnCommandEvent(self, event):
        self._consume(self._midi_command_dispatcher, event, 'button')     # KLT F-03: consumed only when mapped


    def OnKnobEvent(self, event):
        self._consume(self._knob_dispatcher, event, 'cc')     # KLT F-03: consumed only when mapped

    def OnKnobNavEvent(self, event) :
        # KLT F-10: any tick count moves the selection (stock: only the exact values 1 and 65, a fast spin did nothing)
        if not CFG.ENCODER_USE_TICKS and event.data2 not in (1, 65) :
            return
        self.TrackSelectMainKnob(event)


    def OnSliderEvent(self, event):
        self._consume(self._slider_dispatcher, event, 'fader')     # KLT F-03: consumed only when mapped

    def OnPluginEvent(self, event):
        # KLT F-02: kept as a name for the keyboard-port CC handling (see handle_keyboard_cc)
        handle_keyboard_cc(event)

    def OnSeqEvent(self, event):
        # KLT F-27: device.* guarded
        _safe(device.processMIDICC, event)
        if _pad_bit(event) >= 0 :
            self.PressSequencer(event)

    def OnDrumSeqEvent(self, event) :
        # KLT F-04, F-05, F-06, F-07: see handle_pad
        if handle_pad(event) :
            self._mapped = True



  # WINDOW



    def _show_and_focus(self, window):
        if not ui.getVisible(window):
            ui.showWindow(window)
        if not ui.getFocused(window):
            ui.setFocused(window)


    def _hideAll(self, event) :
        # KLT F-14: stock looped channels.showEditor(i, 0) over EVERY channel, on every jog tick (300 API calls at 300
        # channels). The editors that can be open are the selected channel's and the ones this script opened.
        try :
            count = channels.channelCount()
            todo = set(self._editors)
            selected = AKLmk2.sel_channel()
            if selected >= 0 :
                todo.add(selected)
            self._editors = set()
            for i in sorted(todo) :
                if 0 <= i < count :
                    channels.showEditor(i,0)
        except Exception :
            KLTLog.exception('KeyLabMidiProcessor._hideAll')


    def SwitchWindow(self, event) :
        if (ui.getFocused(WidChannelRack) or ui.getFocused(WidPlugin)) :
            self.showPlugin(event)
        elif ui.getFocused(WidMixer) :
            track = mixer.trackNumber()
            if AKLmk2.track_ok(track) :     # KLT F-09: only real tracks
                mixer.armTrack(track)
                self._navigation.ArmRefresh(track)
            #plugin = channels.channelNumber()
            # for i in range(plugins.getParamCount(plugin)) :
                # print(i, plugins.getParamName(i,plugin), plugins.getParamValue(i,plugin))
        elif ui.getFocused(WidBrowser) :
            nodeFileType = ui.getFocusedNodeFileType()
            if nodeFileType == -1:
                return
            if nodeFileType <= -100:
                transport.globalTransport(midi.FPT_Enter, 1)
            else:
                ui.selectBrowserMenuItem()
                if not ui.isInPopupMenu() :
                    self._navigation.PressRefresh()



    def showPlugin(self, event) :
        channel = AKLmk2.sel_channel()      # KLT F-13, O-08: group-relative index, nothing to show in an empty rack
        if channel >= 0 :
            channels.showEditor(channel)
            self._editors.add(channel)      # KLT F-14: _hideAll closes it later


    def ToggleBrowserChannelRack(self, event) :
        self.FakeMIDImsg()
        if ui.getFocused(4) != True :
            self._show_and_focus(4)
            self._navigation.BrowserRefresh()
        else :
            self._show_and_focus(1)
            self._navigation.ChannelRackRefresh()


    def ToggleMixerChannelRack(self, event) :
        self.FakeMIDImsg()
        self._hideAll(event)
        global MIXER_MODE
        if MIXER_MODE == 0 :
            MIXER_MODE = 1
            self._show_and_focus(WidMixer)
        else :
            MIXER_MODE = 0
            self._show_and_focus(WidChannelRack)
        self._navigation.MixerToggleRefresh()

    def DrumSeqToggle(self, event) :
        self.FakeMIDImsg()
        self._hideAll(event)
        global SEQ_MODE
        if SEQ_MODE == 0 :
            SEQ_MODE = 1
        else :
            SEQ_MODE = 0
        reset_pad_state()       # KLT F-04: a pad held (or its release lost) across the mode change must not stick
        self._navigation.DrumSeqToggleRefresh()



    # NAVIGATION



    def _follow_channel_in_mixer(self, channel) :
        # KLT F-09: getTargetFxTrack() is -1 for a channel that routes nowhere, and setTrackNumber(-1) is out of range
        track = channels.getTargetFxTrack(channel)
        if AKLmk2.track_ok(track) :
            mixer.setTrackNumber(track,3)

    def _step_selection(self, previous, count) :
        for _ in range(count) :
            if previous :
                ui.previous()
            else :
                ui.next()

    def TrackSelectMainKnob(self, event):
        ticks = AKLmk2.rel_ticks(event.data2)      # KLT F-10: sign = direction, magnitude = how many steps
        if ticks == 0 :
            return
        previous = ticks < 0
        count = abs(ticks)
        if ui.getFocused(WidPlugin) :
            self._hideAll(event)
            self._show_and_focus(WidChannelRack)
        elif ui.getFocused(WidBrowser) :
            if ui.isInPopupMenu() :
                for _ in range(count) :      # KLT F-10: one step per tick
                    if previous :
                        ui.up()
                    else :
                        ui.down()
                self._navigation.HintRefresh(ui.getFocusedNodeCaption())
            else :
                self._step_selection(previous, count)      # KLT F-10: one step per tick
                self._navigation.HintRefresh(ui.getFocusedNodeCaption())
        elif ui.getFocused(WidMixer) :
            self._show_and_focus(WidMixer)
            self._hideAll(event)
            self._step_selection(previous, count)      # KLT F-10: one step per tick
        elif ui.getFocused(WidChannelRack) :
            self._hideAll(event)
            self._show_and_focus(WidChannelRack)
            self._step_selection(previous, count)      # KLT F-10: one step per tick
            channel = AKLmk2.sel_channel()      # KLT F-13: group-relative selection
            if channel >= 0 :
                self._follow_channel_in_mixer(channel)      # KLT F-09: only a real mixer track
        else :
            self._show_and_focus(WidChannelRack)

    def BankSelect(self, event) :
        if MIXER_MODE == 1 :
            self.FakeMIDImsg()
            if event.controlNum == 46 :
                AKLmk2.MX_OFFSET -= 1
                if AKLmk2.MX_OFFSET < 0 :
                    AKLmk2.MX_OFFSET = 0
                self._navigation.BankMixRefresh()
            elif event.controlNum == 47 :
                if (AKLmk2.MX_OFFSET + 1)*8 < MAX_TRACKS :
                    AKLmk2.MX_OFFSET += 1
                    self._navigation.BankMixRefresh()
        else :
            self.FakeMIDImsg()
            if event.controlNum == 46 :
                AKLmk2.CH_OFFSET -= 1
                if AKLmk2.CH_OFFSET < 0 :
                    AKLmk2.CH_OFFSET = 0
                self._navigation.BankChanRefresh()
            elif event.controlNum == 47 :
                if (AKLmk2.CH_OFFSET + 1)*8 < channels.channelCount() :
                    AKLmk2.CH_OFFSET += 1
                    self._navigation.BankChanRefresh()


    def TrackSelect(self, event):
        if MIXER_MODE :
            track = (event.controlNum - 23) + 8*AKLmk2.MX_OFFSET
            if AKLmk2.track_ok(track) :     # KLT F-09: the last bank has slots 126..128 that are not tracks
                mixer.setTrackNumber(track,3)
                self._hideAll(event)
        else :
            channel = (event.controlNum - 24) + 8*AKLmk2.CH_OFFSET
            if channel < channels.channelCount():
                channels.selectOneChannel(channel)
                self._follow_channel_in_mixer(channel)     # KLT F-13: the channel just selected, group-relative
                self._hideAll(event)
                ui.setFocused(WidChannelRack)


    def previousPattern(self, event) :
        if ui.getFocused(5) :
            self.previousPreset(event)
        else :
            pattern = patterns.patternNumber()
            if pattern > 1 :        # KLT F-21: stock jumped to pattern 0 from pattern 1
                patterns.jumpToPattern(pattern - 1)


    def nextPattern(self, event) :
        if ui.getFocused(5) :
            self.nextPreset(event)
        else :
            pattern = patterns.patternNumber()
            # KLT F-21: Next on the last pattern creates a new one (stock, KLTConfig.PATTERN_NEXT_CREATES), never past FL's limit
            if pattern + 1 <= patterns.patternMax() and (CFG.PATTERN_NEXT_CREATES or pattern < patterns.patternCount()) :
                patterns.jumpToPattern(pattern + 1)



    # PLUGIN



    def nextPreset(self, event) :
        if ui.getFocused(5) :
            channel = AKLmk2.sel_channel()      # KLT F-13, O-08: group-relative index, -1 = nothing to address
            if channel >= 0 :
                plugins.nextPreset(channel)


    def previousPreset(self, event) :
        if ui.getFocused(5) :
            channel = AKLmk2.sel_channel()      # KLT F-13, O-08: group-relative index, -1 = nothing to address
            if channel >= 0 :
                plugins.prevPreset(channel)


    def Plugin(self, event, clef, absolute = False) :     # KLT F-02: `absolute` for controls that send absolute values
        if ui.getFocused(5) :
            param, value = KLTPlugin.Plugin(event, clef, absolute)
            if clef != 1 :      # KLT F-02: stock tested event.controlNum, which for a fader is the pitch-bend LSB
                self._navigation.PluginRefresh(param, value)



    # FUNCTIONS



    def Record(self, event) :
        transport.record()
        self._navigation.RecordRefresh()


    def Start(self, event) :
        transport.start()
        self._navigation.PlayRefresh()


    def Stop(self, event) :
        transport.stop()
        self._navigation.StopRefresh()


    def _scrub_or_bar(self, event, direction) :
        # KLT F-23: one place for << and >>. A release always stops a scrub that its press started, whatever the
        # Sequencer mode is by then (stock decided on release from the CURRENT mode, so toggling Save while << was
        # held left FL scrubbing until the next press), and the release may be a note-off.
        global RECT_OFFSET
        if self._is_pressed(event) :
            if SEQ_MODE == 1 :
                self.FakeMIDImsg()
                RECT_OFFSET = min(MAX_RECT_OFFSET, max(0, RECT_OFFSET + direction))     # KLT F-12: bounded both ways
                top = AKLmk2.sel_channel()
                left = RECT_OFFSET*16
                if top >= 0 :
                    ui.crDisplayRect(left,top,16,1,1000)
                self._navigation.BarRefresh()
            else :
                transport.continuousMove(direction, SS_START)
                self._scrubbing[direction] = True
                self._scrub_refresh(direction)
        elif self._scrubbing[direction] or SEQ_MODE == 0 :
            transport.continuousMove(direction, SS_STOP)
            self._scrubbing[direction] = False
            self._scrub_refresh(direction)

    def _scrub_refresh(self, direction) :
        if direction > 0 :
            self._navigation.FastForwardRefresh()
        else :
            self._navigation.RewindRefresh()

    def FastForwardORnextBar(self, event) :
        self._scrub_or_bar(event, 1)      # KLT F-23: shared scrub/bar logic


    def RewindORprevBar(self, event) :
        self._scrub_or_bar(event, -1)      # KLT F-23: shared scrub/bar logic



    def Loop(self, event) :
        transport.globalTransport(midi.FPT_LoopRecord,1)
        self._navigation.LoopRefresh()


    def Cut(self, event) :
        if not CFG.CUT_ENABLED :       # KLT F-18: ui.cut() is destructive and its effect is unverified on this setup
            return
        self._show_and_focus(midi.widChannelRack)
        ui.cut()
        self._navigation.CutRefresh()

    def Undo(self, event) :
        # KLT F-22: Image-Line's own scripts pass 2 for "pressed" (MackieCU: int(pressed) * 2); stock passed FPT_Undo (20)
        transport.globalTransport(midi.FPT_Undo, 2, event.pmeFlags)
        self._navigation.UndoRefresh()

    def Overdub(self, event) :
        transport.globalTransport(midi.FPT_Overdub,1)
        self._navigation.OverdubRefresh()


    def SetClick(self, event) :
        transport.globalTransport(midi.FPT_Metronome,1)
        self._navigation.MetronomeRefresh()


    def SoloChannel(self, event) :
        if ui.getFocused(WidChannelRack) :
            channel = AKLmk2.sel_channel()      # KLT F-13, O-08: group-relative index, -1 = nothing to address
            if channel >= 0 :
                channels.soloChannel(channel)
        elif ui.getFocused(WidMixer) :
            if AKLmk2.track_ok(mixer.trackNumber()) :     # KLT F-09: only real tracks
                mixer.soloTrack(mixer.trackNumber())
        self.FakeMIDImsg()


    def MuteChannel(self, event) :
        if ui.getFocused(WidChannelRack) :
            channel = AKLmk2.sel_channel()      # KLT F-13, O-08: group-relative index, -1 = nothing to address
            if channel >= 0 :
                channels.muteChannel(channel)
        elif ui.getFocused(WidMixer) :
            if AKLmk2.track_ok(mixer.trackNumber()) :     # KLT F-09: only real tracks
                mixer.muteTrack(mixer.trackNumber())
        self.FakeMIDImsg()


    def TapTempo(self, event) :
        transport.globalTransport(midi.FPT_TapTempo,1)
        self._navigation.TapTempoRefresh()


    def SnapMode(self, event) :
        ui.snapMode(1)
        self._navigation.SnapModeRefresh()


    def SetVolumeTrack(self, event) :
        # KLT F-01, F-08: fader n (0..8) comes from the raw status (pitch bend channel n+1); the event is no longer
        # rewritten into a CC-shaped body, and the movement is consumed by the caller (stock left handled False)
        n = event.status - 224
        value = event.data2/127
        if MIXER_MODE == 1 :
            track = 0 if n == 8 else n + 1 + (8*AKLmk2.MX_OFFSET)
            if AKLmk2.SetVolumeTrack(track, value) :        # KLT F-09: False for the slots past track 125
                perc = str(round(mixer.getTrackVolume(track) * 100))
                self._navigation.VolumeMixerRefresh(track, perc)
        else :
            if n != 8 :      # KLT F-01: fader number from the raw status
                self.Plugin(event, clef = event.status)
                self._navigation.NoPlugin()
            else :
                track = mixer.trackNumber()      # KLT F-09: guarded by SetVolumeTrack
                if AKLmk2.SetVolumeTrack(track, value) :
                    perc = str(round(mixer.getTrackVolume(track) * 100))
                    self._navigation.VolumeChRefresh(perc)


    def SetPanTrack(self, event) :

        if EDIT_MODE == 1 :
            global SEQ_PARAM
            global INDEX_PRESSED
            INDEX_PRESSED = []
            for i in range(4) :
                for j in range(4) :
                    if STATE_MATRIX[i][j] == 1 :
                        INDEX_PRESSED += [4*i+j]
            KLmk2SQP.Param(event)
            self.FakeMIDImsg()
            SEQ_PARAM = 1

        else :
            ticks = AKLmk2.rel_ticks(event.data2)      # KLT F-10: by magnitude, 0 and 64 move nothing
            if MIXER_MODE == 1 :
                n = event.controlNum - 16
                track = 0 if n == 8 else n + 1 + (8*AKLmk2.MX_OFFSET)
                if AKLmk2.SetPanTrack(track, ticks) :       # KLT F-08, F-09: pure helper, guarded index
                    perc = str(round(mixer.getTrackPan(track) * 100))
                    self._navigation.PanMixerRefresh(track, perc)
            else :
                if event.controlNum != 24 :
                    self.Plugin(event, clef = event.controlNum)
                    self._navigation.NoPlugin()
                else :
                    track = mixer.trackNumber()      # KLT F-09: guarded by SetPanTrack
                    if AKLmk2.SetPanTrack(track, ticks) :
                        perc = str(round(mixer.getTrackPan(track) * 100))
                        self._navigation.PanChRefresh(perc)



    # SEQUENCER



    def PressSequencer(self, event) :
        press_sequencer(event)      # KLT F-04: module-level, shared with the Forward script


    def HoldBit(self, event) :
        hold_bit(event)      # KLT F-04: module-level, shared with the Forward script


    def ReleaseBit(self, event) :
        release_bit(event)      # KLT F-04: module-level, shared with the Forward script


    # UTILITY



    def FakeMIDImsg(self) :
        transport.globalTransport(midi.FPT_Punch,1)
