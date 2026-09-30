"""OnInit / OnRefresh / OnIdle / OnDeInit lifecycle, import-time purity, partial init and unassigned output.

Characterization tests describe what the keyboard must show and what must never happen; @tuned_fix tests assert
the fixed behaviour of documented stock bugs (docs/analysis/03-output-audit.md: O-xx, 02-input-audit.md: F-xx)."""
from __future__ import annotations

import importlib.util
import re
import sys

import pytest

from tests import kl
from tests.conftest import BOOT_ORDER
from tests.flsim import FLCrash
from tests.flsim.rig import Rig
from tests.flsim.sysex import DEINIT_PAYLOAD, HEADER, decode, lcd_frame, led_mono_frame, led_rgb_frame


# ================================================================================================ import-time purity

def test_importing_every_module_makes_no_fl_api_call(host, scripts, target):
    """No FL API call (and no sleep) at import time: an interpreter that is not yet associated with a device must not
    be asked anything (docs/incidents: FL 26.1.6 crash, stubs device/__device.py:53). Every .py in the folder is
    imported, including helpers the entry scripts might not pull in."""
    host.current, host.phase, host.cb = scripts.entry, "import", "import"
    try:
        for p in sorted(target.path.glob("*.py")):
            name = re.sub(r"\W", "_", p.stem)
            if name in sys.modules:
                continue
            spec = importlib.util.spec_from_file_location(name, str(p))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
    finally:
        host.current, host.phase, host.cb = None, "test", None
    assert host.calls == [], "FL API used at import time: %s" % [c.short() for c in host.calls]
    assert host.sysex == [] and host.clock.slept_total == 0


def test_loading_the_scripts_records_no_calls_at_all(host, scripts):
    assert host.calls == [] and host.sysex == [] and host.violations == []


# ================================================================================================ healthy boot

def test_boot_completes_without_an_exception_or_a_rule_violation(rig):
    assert rig.host.errors == []
    assert rig.host.violations == []


def test_boot_shows_the_welcome_page_then_the_main_page(rig):
    rig.settle(3.0)
    m = rig.host.device_model()
    first = m.lcd_frames[0]
    assert (first[1], first[2][:9]) == ("KeyLab mkII", "FL Studio")          # welcome page: title on line 2
    assert m.lcd == ("1 - Kick", "Pattern 1")                                  # main page: selected channel + pattern


def test_lcd_lines_are_ascii_and_at_most_16_characters(rig):
    rig.settle(3.0)
    rig.button(kl.BTN_PLAY)
    rig.idle(0.2)
    for _, l1, l2 in rig.host.device_model().lcd_frames:
        for line in (l1, l2):
            assert len(line) <= 16 and line.isascii(), line


def test_boot_leaves_the_documented_led_state(rig):
    """After attach: pads red (drum mode), Select buttons purple with the selected channel yellow, transport LEDs
    reflect a stopped, non-recording transport; steady backlights on (docs/analysis/03 section 2.3-2.4)."""
    rig.settle(3.0)
    m = rig.host.device_model()
    assert all(m.rgb[p] == kl.RED for p in kl.PAD_LEDS)
    assert m.rgb[kl.SELECT_LEDS[0]] == kl.YELLOW
    assert all(m.rgb[s] == kl.PURPLE for s in kl.SELECT_LEDS[1:])
    assert m.rgb[kl.LED_MULTI] == kl.WHITE
    assert all(m.mono[i] == kl.LED_ON for i in kl.LED_STEADY)
    assert {i: m.mono[i] for i in (kl.LED_SOLO, kl.LED_MUTE, kl.LED_METRO, kl.LED_PLAY, kl.LED_RECORD, kl.LED_LOOP)} == {
        kl.LED_SOLO: kl.LED_OFF, kl.LED_MUTE: kl.LED_OFF, kl.LED_METRO: kl.LED_OFF, kl.LED_PLAY: kl.LED_OFF,
        kl.LED_RECORD: kl.LED_OFF, kl.LED_LOOP: kl.LED_OFF}
    assert m.mono[kl.LED_STOP] == kl.LED_ON                                    # stopped: the Stop LED is lit


def test_select_leds_off_for_slots_without_a_channel(rig):
    rig.state.resize_channels(5)
    rig.refresh()
    rig.settle(3.0)
    m = rig.host.device_model()
    assert [m.rgb[s] for s in kl.SELECT_LEDS] == [kl.YELLOW] + [kl.PURPLE] * 4 + [kl.OFF] * 3


def test_every_sysex_is_well_framed_and_decodes_to_a_known_message(rig):
    rig.settle(3.0)
    rig.tap(kl.BTN_METRO)
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.refresh()
    rig.settle(1.0)
    m = rig.host.device_model()
    assert rig.host.violations == []
    assert all(x.valid for x in rig.host.sysex)
    assert m.unknown == [] and m.invalid == []
    assert set(m.counts) <= {"led_mono", "led_rgb", "lcd"}
    assert all(x.data[:6] == HEADER for x in rig.host.sysex)


def test_led_state_follows_fl_state(rig):
    st = rig.state
    rig.settle(1.0)
    rig.tap(kl.BTN_METRO)                                                      # Metro: globalTransport(FPT_Metronome)
    rig.tap(kl.BTN_LOOP)
    st.muted_channels.add(0)
    st.song_tick_pos = 480
    st.recording = True
    rig.refresh()
    rig.settle(1.0)
    m = rig.host.device_model()
    assert m.mono[kl.LED_METRO] == kl.LED_ON and m.mono[kl.LED_LOOP] == kl.LED_ON
    assert m.mono[kl.LED_MUTE] == kl.LED_ON
    assert m.mono[kl.LED_PLAY] == kl.LED_ON and m.mono[kl.LED_STOP] == kl.LED_OFF and m.mono[kl.LED_RECORD] == kl.LED_ON
    assert m.rgb[kl.SELECT_LEDS[0]] == kl.RED                                  # muted channel: red


def test_beat_indicator_blinks_the_play_and_record_leds(rig):
    rig.state.recording = True
    rig.settle(1.0)
    for value, want in ((1, kl.LED_ON), (0, kl.LED_OFF), (2, kl.LED_ON), (0, kl.LED_OFF)):
        rig.capture(lambda v=value: rig.entry.call("OnUpdateBeatIndicator", v))
        m = rig.host.device_model()
        assert m.mono[kl.LED_PLAY] == want and m.mono[kl.LED_RECORD] == want, value


def test_select_leds_in_mixer_mode_are_blue_with_the_selected_track_yellow(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    rig.refresh()
    rig.settle(1.0)
    m = rig.host.device_model()
    assert m.rgb[kl.SELECT_LEDS[0]] == kl.YELLOW                              # current track 1 = slot 1 of bank 0
    assert all(m.rgb[s] == kl.BLUE for s in kl.SELECT_LEDS[1:])


def test_sequencer_mode_paints_the_pads_by_step_state(rig):
    st = rig.state
    rig.tap(kl.BTN_SEQ_TOGGLE)
    st.grid[(0, 2)] = 1
    rig.refresh()
    rig.settle(1.0)
    m = rig.host.device_model()
    assert m.rgb[0x70 + 2] == (25, 25, 0)                                      # step on: yellow scaled by velocity 100 // 4
    assert m.rgb[0x70] == kl.WHITE and m.rgb[0x70 + 3] == kl.WHITE            # step off


def test_frames_use_the_documented_byte_layouts(rig):
    """Byte-exact protocol (docs/analysis/03 section 2): the RGB frames keep Arturia's trailing 7F, the LCD frame is
    04 00 60 01 <line1> 00 02 <line2> 00 7F, mono LEDs use 7F (on) and 09 (off), never 00, in steady state."""
    rig.settle(3.0)
    rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 1))
    rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 0))
    sent = [m.data for m in rig.host.sysex]
    assert lcd_frame("KeyLab mkII", "FL Studio 2026") in sent                   # the welcome frame
    assert lcd_frame("1 - Kick", "Pattern 1") in sent                           # the main page
    assert led_mono_frame(kl.LED_PLAY, 0x7F) in sent and led_mono_frame(kl.LED_PLAY, 0x09) in sent
    frames = [decode(d) for d in sent]
    assert all(f.fields["trailer"] == 0x7F for f in frames if f.kind == "led_rgb")
    assert len(led_rgb_frame(0x70, 0x7F, 0, 0)) == 15 and len(led_mono_frame(0x6D, 0x7F)) == 12
    assert all(f.fields["value"] in (0x7F, 0x09) for f in frames if f.kind == "led_mono"
               and f.fields["id"] in (kl.LED_METRO, kl.LED_LOOP, kl.LED_SOLO, kl.LED_MUTE, kl.LED_STOP, kl.LED_PLAY, kl.LED_RECORD))


def test_deinit_says_goodbye_and_sends_the_deinit_frame(rig):
    rig.settle(3.0)
    m0 = rig.host.mark()
    rig.entry.call("OnDeInit")
    v = rig.host.since(m0)
    m = rig.host.device_model(since=m0)
    assert m.lcd == ("KeyLab mkII", "Disconnected")
    assert any(x.data == HEADER + DEINIT_PAYLOAD + b"\xf7" for x in v.sysex)   # byte-exact: meaning UNVERIFIED
    assert v.errors == []


def test_reload_runs_init_again_without_error(rig):
    """FL's Reload button: OnDeInit, then a fresh load and OnInit."""
    rig.settle(3.0)
    rig.scripts.deinit()
    rig.host.clear_trace()
    scripts = rig.host.load(rig.scripts.folder)
    scripts.boot(order=BOOT_ORDER)
    Rig(rig.host, scripts).settle(3.0)
    assert rig.host.errors == []
    assert rig.host.device_model().lcd == ("1 - Kick", "Pattern 1")


def test_memory_switch_sysex_focuses_the_channel_rack_and_refreshes(rig):
    rig.state.focus(kl.WID_MIXER)
    rig.settle(1.0)
    a = rig.capture(lambda: rig.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH))
    assert a.called("ui.setFocused", kl.WID_CHANNEL_RACK) and a.errors == []
    assert rig.state.focused == kl.WID_CHANNEL_RACK
    a = rig.capture(lambda: rig.entry.deliver_sysex(b"\xf0\x7e\x7f\x06\x02\xf7"))    # any other SysEx is ignored
    assert a.effects == [] and a.errors == []


def test_forward_first_boot_order_ends_with_the_main_page_on_the_lcd(make_rig):
    rig = make_rig(order=("forward", "entry"))
    rig.settle(3.0)
    assert rig.host.device_model().lcd == ("1 - Kick", "Pattern 1")


# ================================================================================================ tuned fixes

@pytest.mark.tuned_fix("O-01")
@pytest.mark.parametrize("crash_mode", ["crash", "noop"])
def test_unassigned_output_is_never_written_to(make_rig, crash_mode):
    """No MIDI output assigned to the script: the scripts must notice (device.isAssigned) and not call
    device.midiOutSysex at all, whatever FL does in that case (crash: the tom hypothesis; or a silent no-op)."""
    rig = make_rig(boot=False, output_assigned=False, crash_on_unassigned_output=(crash_mode == "crash"))
    h = rig.host
    try:
        rig.scripts.boot(order=BOOT_ORDER)
        rig.idle(2.0)
        rig.refresh()
        rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 1))
        rig.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH)
        rig.tap(kl.BTN_PLAY)
        rig.fader(1, 100)
        rig.capture(lambda: rig.forward.deliver_midi(0xB0, 74, 64))
        rig.scripts.deinit()
    except FLCrash as c:
        pytest.fail("FL would have crashed: %s" % c.reason)
    sends = h.calls_to("device.midiOutSysex")
    assert sends == [], "midiOutSysex called %d times with no output assigned" % len(sends)
    assert h.errors == []


@pytest.mark.tuned_fix("O-01")
def test_the_output_assignment_is_checked_before_the_first_sysex(make_rig):
    rig = make_rig(boot=False)
    rig.scripts.boot(order=BOOT_ORDER)
    rig.idle(1.0)                                    # review RA-10: the tuned scripts send from the first OnIdle tick, not from OnInit
    calls = rig.host.api_calls()
    first_send = next(i for i, c in enumerate(calls) if c.qual == "device.midiOutSysex")
    assert any(c.qual in ("device.isAssigned", "device.isMidiOutAssigned") for c in calls[:first_send]), \
        "midiOutSysex sent before device.isAssigned()/isMidiOutAssigned() was consulted"


@pytest.mark.tuned_fix("O-01")
def test_assigning_the_output_later_brings_the_display_up(make_rig):
    """Attached without an output, then the user assigns it (FL Reload): the keyboard must end up initialised."""
    rig = make_rig(boot=False, output_assigned=False)
    try:
        rig.scripts.boot(order=BOOT_ORDER)
    except FLCrash as c:
        pytest.fail("FL would have crashed: %s" % c.reason)
    rig.host.set_output_assigned("entry", True)
    rig.host.set_output_assigned("forward", True)
    rig.refresh()
    rig.settle(3.0)
    assert rig.host.device_model().lcd == ("1 - Kick", "Pattern 1")


@pytest.mark.tuned_fix("O-12")
def test_oninit_does_not_sleep(make_rig):
    """OnInit runs on FL's main thread; the stock LED animation blocks it for 2.92 s (240 sends + sleeps)."""
    rig = make_rig(boot=False)
    rig.scripts.boot(order=BOOT_ORDER)
    slept = rig.host.clock.sleeps_in("OnInit")
    assert slept == [] and rig.host.clock.slept_total == 0, "slept %.2fs in %d calls" % (
        rig.host.clock.slept_total, len(rig.host.clock.sleeps))


@pytest.mark.tuned_fix("O-04")
@pytest.mark.parametrize("cb,args", [("OnDeInit", ()), ("OnIdle", ()), ("OnRefresh", (0,)), ("OnRefresh", (0x1FFFF,)),
                                     ("OnUpdateBeatIndicator", (1,))])
def test_callbacks_before_oninit_do_not_raise(scripts, cb, args):
    """FL can call callbacks before init completed (or after it failed): the stock scripts raise NameError."""
    _, exc = scripts.entry.call(cb, *args)
    assert exc is None, "%s before OnInit raised %r" % (cb, exc)


@pytest.mark.tuned_fix("O-04")
def test_sysex_and_midi_events_before_oninit_do_not_raise(scripts):
    assert scripts.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH).exceptions == []
    for role in ("entry", "forward"):
        s = getattr(scripts, role)
        for st, d1, d2 in ((0x90, 94, 127), (0xB0, 16, 1), (0xE0, 0, 100), (0x99, 36, 100), (0xB0, 74, 64)):
            d = s.deliver_midi(st, d1, d2)
            assert d.exceptions == [], (role, hex(st), d.exceptions)


@pytest.mark.tuned_fix("O-04")
@pytest.mark.parametrize("failing", ["ui.getProgTitle", "channels.getChannelName", "patterns.getPatternName"])
def test_partial_init_leaves_the_scripts_usable(make_rig, failing):
    """An FL API call fails once inside OnInit: no exception may escape any later callback, and once FL recovers the
    display comes up (the stock OnInit aborts before it activates the main LCD page, which then stays blank)."""
    rig = make_rig(boot=False)
    h = rig.host
    h.inject_fault(failing, RuntimeError, times=1)                               # fails once, during OnInit/Sync
    rig.scripts.boot(order=BOOT_ORDER)
    h.errors.clear()
    h.clear_faults()
    rig.capture(lambda: rig.entry.call("OnRefresh", 0x1FFFF))
    rig.idle(3.0)
    rig.tap(kl.BTN_PLAY)
    rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 1))
    rig.idle(3.0)
    assert h.errors == [], [(e.callback, e.exc) for e in h.errors]
    assert h.device_model().lcd == ("1 - Kick", "Pattern 1")
    rig.scripts.deinit()
    assert h.errors == []


@pytest.mark.tuned_fix("O-04")
def test_a_failing_api_call_in_one_led_routine_does_not_take_down_the_rest(rig):
    """OnIdle/OnRefresh must isolate failures per routine: the other LEDs still update."""
    rig.settle(2.0)
    rig.host.inject_fault("ui.isMetronomeEnabled", RuntimeError)
    rig.state.muted_channels.add(0)
    a = rig.idle(1.0)
    assert a.errors == [], [(e.callback, e.exc) for e in a.errors][:2]
    assert rig.host.device_model().mono[kl.LED_MUTE] == kl.LED_ON


@pytest.mark.tuned_fix("O-03")
@pytest.mark.parametrize("what", ["prog_title", "channel_name", "pattern_name", "param_name"])
def test_non_ascii_text_does_not_break_the_display(make_rig, what):
    """A channel/pattern/project name with non-ASCII characters raised UnicodeEncodeError inside the LCD code and,
    because the bad string was stored first, killed every later OnIdle (O-03)."""
    rig = make_rig(boot=False)
    st = rig.state
    if what == "prog_title":
        st.prog_title = "FL Studio - Café ♪"
    elif what == "channel_name":
        st.channel_names[0] = "Kick ♪ ドラム"
    elif what == "pattern_name":
        st.pattern_names[1] = "Pattern – über"
    rig.scripts.boot(order=BOOT_ORDER)
    if what == "param_name":
        st.focus(kl.WID_PLUGIN, "FPC")
        st.select_channel_plugin("FPC")
        st.param_names[(0, 8)] = "Cuté ∞"
        rig.cc(16, 1)
    rig.settle(3.0)
    rig.refresh()
    rig.settle(1.0)
    assert rig.host.errors == [], [(e.callback, str(e.exc)[:60]) for e in rig.host.errors][:3]
    m = rig.host.device_model()
    assert m.invalid == [] and all(x.valid for x in rig.host.sysex)
    for _, l1, l2 in m.lcd_frames:
        assert l1.isascii() and l2.isascii()
    # the LED pass keeps running after the text problem: a mute is still reflected
    st.open_editors.clear()
    st.focus(kl.WID_CHANNEL_RACK)
    st.muted_channels.add(0)
    rig.refresh()
    rig.settle(1.0)
    assert rig.host.device_model().mono[kl.LED_MUTE] == kl.LED_ON


@pytest.mark.tuned_fix("O-05")
def test_lcd_is_repainted_after_a_memory_switch(rig):
    """The LCD payload cache was never invalidated: after the keyboard cleared its display (memory switch, power
    cycle) an unchanged text was not re-sent, so the LCD stayed blank."""
    rig.settle(3.0)
    m0 = rig.host.mark()
    rig.capture(lambda: rig.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH))
    rig.settle(1.0)
    assert rig.host.device_model(since=m0).lcd_frames, "no LCD frame after the memory-switch SysEx"


@pytest.mark.tuned_fix("O-08", "F-12")
def test_stale_bank_offset_after_the_channel_count_shrinks_does_not_break_idle(rig):
    """Bank to the 5th page of 40 channels, then the rack shrinks to 5 channels: the LED pass indexed past the map
    and raised IndexError on every idle tick."""
    rig.state.resize_channels(40)
    for _ in range(4):
        rig.button(kl.BTN_NEXT)
    rig.state.resize_channels(5)
    rig.refresh()
    a = rig.idle(2.0)
    assert a.errors == [], [(e.callback, e.exc) for e in a.errors][:2]
    assert all(v.kind != "index" for v in rig.host.violations)


@pytest.mark.tuned_fix("O-14")
def test_step_parameter_query_failing_does_not_break_the_sequencer_leds(rig):
    """getCurrentStepParam can return -1; bytes([... -1 // 4 ...]) raised ValueError in the LED code."""
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.state.grid[(0, 1)] = 1
    rig.state.step_param_forced = -1
    a = rig.refresh()
    b = rig.idle(1.0)
    assert a.errors == [] and b.errors == [], [(e.callback, e.exc) for e in a.errors + b.errors][:2]


@pytest.mark.tuned_fix("F-17", "O-09")
def test_daw_script_first_boot_order_also_ends_with_the_main_page_on_the_lcd(make_rig):
    """The stock Forward script's OnInit calls KL.init() again, replacing the DAW script's display objects: when the
    DAW script initialises first the LCD ends blank (only blank frames are sent afterwards)."""
    rig = make_rig(order=("entry", "forward"))
    rig.settle(3.0)
    assert rig.host.device_model().lcd == ("1 - Kick", "Pattern 1")


@pytest.mark.tuned_fix("O-08", "O-04")
def test_an_empty_channel_rack_makes_no_call_with_an_invalid_channel_index(make_rig):
    """Delete every channel: channelNumber() still answers 0 (canBeNone=False), so channel-indexed calls got index 0
    of an empty rack (docs/analysis/03 3.9b; FL's native side null-reads on invalid indices, cf. the tom crash)."""
    rig = make_rig(boot=False)
    rig.state.set_channels([])
    try:
        rig.scripts.boot(order=BOOT_ORDER)
        rig.settle(3.0)
        for note in (kl.BTN_PLAY, kl.BTN_SEQ_TOGGLE, kl.BTN_MIXER_TOGGLE, kl.BTN_MIXER_TOGGLE, kl.BTN_SEQ_TOGGLE,
                     kl.BTN_JOG_PUSH, kl.BTN_SELECT[0], kl.BTN_SOLO[0], kl.BTN_MUTE[0], kl.BTN_NEXT):
            rig.tap(note)
        rig.cc(60, 1)
        rig.cc(24, 1)
        rig.cc(16, 1)
        rig.fader(0, 90)
        rig.pad_on(36)
        rig.pad_off(36)
        rig.midi(0xE0, 0, 100, role="forward")
        rig.refresh()
        rig.settle(1.0)
    except FLCrash as c:
        pytest.fail("FL would have crashed: %s" % c.reason)
    assert rig.host.errors == [], [(e.callback, str(e.exc)[:60]) for e in rig.host.errors][:3]
    bad = [v for v in rig.host.violations if v.kind == "index"]
    assert bad == [], "%d invalid indices, e.g. %s" % (len(bad), bad[0].message if bad else "")
