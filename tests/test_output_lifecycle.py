"""Lifecycle of the tuned entry script: OnInit that neither sleeps nor bursts, the staged LED init advanced from OnIdle,
the welcome splash, exception isolation in every callback, OnDeInit/OnSysEx robustness, re-init and helper-state reset
(O-04, O-05, O-08, O-09, O-12, O-15, O-16; F-17)."""
from __future__ import annotations

import ast
from types import SimpleNamespace

import pytest

from tests import kl
from tests.conftest import BOOT_ORDER
from tests.flsim.sysex import decode, led_rgb_frame
from tests.test_output_support import boot, entry_module, log_lines, module, printed, sent, tuned_only  # noqa: F401


def _lcd_timeline(rig, since=None):
    return [(round(t - since, 2), l1, l2) for t, l1, l2 in rig.host.device_model().lcd_frames]


# ================================================================================================ OnInit does not block

def test_oninit_sleeps_nothing_and_sends_at_most_the_welcome_frames(make_rig):
    rig = boot(make_rig)                                     # OnInit + OnRefresh
    h = rig.host
    assert h.clock.slept_total == 0 and h.clock.sleeps == []
    assert len(h.sysex) <= 2, "OnInit+OnRefresh sent %d frames; the LED paint belongs to the staged init" % len(h.sysex)


def test_oninit_is_safe_with_the_device_absent(make_rig):
    rig = boot(make_rig, output_assigned=False)
    assert rig.host.errors == [] and rig.host.clock.slept_total == 0
    rig.idle(5.0)
    assert rig.host.sysex == [] and rig.host.errors == []


def test_oninit_twice_without_deinit_is_harmless(rig):
    rig.settle(3.0)
    rig.entry.call("OnInit")
    rig.entry.call("OnRefresh", 0x1FFFF)
    rig.settle(3.0)
    assert rig.host.errors == [] and rig.host.device_model().lcd == ("1 - Kick", "Pattern 1")


# ================================================================================================ the staged init

def _stock_animation():
    """Arturia's init sequence (KeyLabmk2Return.init): black, 6 colours on then off, white, black."""
    colours = [(0x7F, 0, 0), (0, 0, 0x7F), (0, 0x7F, 0), (0x7F, 0, 0x7F), (0, 0x7F, 0x7F), (0x7F, 0x7F, 0)]
    out = [(i, (0, 0, 0)) for i in range(16)]
    for c in colours:
        out += [(i, c) for i in range(16)] + [(i, (0, 0, 0)) for i in range(16)]
    return out + [(i, (0x7F,) * 3) for i in range(16)] + [(i, (0, 0, 0)) for i in range(16)]


def _pad_frames(host):
    return [(f.fields["id"] - 0x70, f.fields["rgb"]) for f in sent(host) if f.kind == "led_rgb" and 0x70 <= f.fields["id"] < 0x80]


def test_the_stock_animation_is_a_switch_and_is_byte_identical(make_rig):
    rig = boot(make_rig, cfg={"INIT_ANIMATION": 2})
    rig.settle(6.0)
    assert rig.host.clock.slept_total == 0
    frames = _pad_frames(rig.host)
    assert frames[:240] == _stock_animation()
    # ...and then the normal paint: drum-mode pads are red
    assert all(rig.host.device_model().rgb[p] == kl.RED for p in kl.PAD_LEDS)


def test_the_short_animation_is_a_pad_wipe_of_32_frames(make_rig):
    rig = boot(make_rig, cfg={"INIT_ANIMATION": 1})
    rig.settle(3.0)
    frames = _pad_frames(rig.host)
    assert frames[:32] == [(i, (0x7F,) * 3) for i in range(16)] + [(i, (0, 0, 0)) for i in range(16)]
    assert all(rig.host.device_model().rgb[p] == kl.RED for p in kl.PAD_LEDS)


def test_no_animation_by_default(rig):
    rig.settle(2.0)
    frames = _pad_frames(rig.host)
    assert all(rgb == kl.RED for _, rgb in frames)          # the first pad frames are the red drum-mode paint


def test_animation_frames_advance_a_few_per_tick_within_the_budget(make_rig):
    rig = boot(make_rig, cfg={"INIT_ANIMATION": 2, "INIT_FRAMES_PER_TICK": 3, "OUT_MAX_SYSEX_PER_SEC": 1000})
    h = rig.host
    t0 = h.clock.now
    rig.settle(6.0)
    from collections import Counter
    per_tick = Counter(round((m.t - t0) / 0.02) for m in h.sysex if decode(m.data).kind == "led_rgb")
    anim_ticks = [n for tick, n in sorted(per_tick.items())][:70]
    assert max(anim_ticks) <= 8 and anim_ticks[0] <= 3
    assert h.errors == []


def test_leds_are_held_back_until_the_animation_has_finished(make_rig):
    rig = boot(make_rig, cfg={"INIT_ANIMATION": 2})
    rig.state.muted_channels.add(1)
    h = rig.host
    t0 = h.clock.now
    rig.idle(2.0)                                            # the 240 frames need about 2.4 s at 100/s
    early = [f for f in sent(h) if f.kind == "led_mono" or (f.kind == "led_rgb" and f.fields["id"] not in range(0x70, 0x80))]
    assert early == [], "LED frames leaked into the init animation: %s" % [(f.kind, f.fields) for f in early][:3]
    rig.settle(4.0)
    assert rig.host.device_model().rgb[kl.SELECT_LEDS[1]] == kl.RED


def test_an_init_that_never_gets_idle_ticks_releases_the_leds_after_the_timeout(make_rig):
    rig = boot(make_rig, cfg={"INIT_ANIMATION": 2, "OUT_HOLD_TIMEOUT_S": 5.0})
    h = rig.host
    h.advance(6.0)                                           # FL never called OnIdle
    a = rig.refresh()
    assert any(decode(m.data).kind == "led_rgb" for m in a.sysex), "held LEDs were never released"
    assert any("did not finish" in l for l in log_lines(h))


def test_the_init_waits_for_a_late_output_and_then_runs_the_whole_sequence(make_rig):
    rig = boot(make_rig, cfg={"INIT_ANIMATION": 1}, output_assigned=False)
    rig.idle(8.0)                                            # longer than the hold timeout: still nothing
    assert rig.host.sysex == []
    rig.host.set_output_assigned("entry", True)
    rig.settle(4.0)
    frames = _pad_frames(rig.host)
    assert frames[:16] == [(i, (0x7F,) * 3) for i in range(16)]           # the animation ran after the output appeared
    m = rig.host.device_model()
    assert all(m.rgb[p] == kl.RED for p in kl.PAD_LEDS) and m.lcd == ("1 - Kick", "Pattern 1")


def test_the_staged_init_completes_within_a_second_by_default(make_rig):
    rig = boot(make_rig)
    rig.idle(1.0)
    m = rig.host.device_model()
    assert all(m.rgb[p] == kl.RED for p in kl.PAD_LEDS) and m.rgb[kl.SELECT_LEDS[0]] == kl.YELLOW
    assert all(m.mono[i] == kl.LED_ON for i in kl.LED_STEADY)
    assert any("init: sequence complete" in l for l in log_lines(rig.host))


# ================================================================================================ the splash

def test_the_splash_shows_the_welcome_then_the_script_tag_then_the_main_page(make_rig):
    rig = boot(make_rig)
    t0 = rig.host.clock.now
    rig.settle(4.0)
    tl = _lcd_timeline(rig, t0)
    version = entry_module().KLT_VERSION
    assert tl[0] == (0.0, "KeyLab mkII", "FL Studio 2026")
    assert tl[1][1:] == ("KeyLab mkII", "tuned v" + version) and 1.5 <= tl[1][0] <= 1.6
    assert tl[2][1:] == ("1 - Kick", "Pattern 1") and 2.5 <= tl[2][0] <= 2.6
    assert rig.host.clock.slept_total == 0


@pytest.mark.parametrize("splash,tag,expect", [
    (0, 0, [(0.0, "1 - Kick")]),
    (1500, 0, [(0.0, "KeyLab mkII"), (1.5, "1 - Kick")]),
    (0, 1000, [(0.0, "KeyLab mkII"), (1.0, "1 - Kick")]),
    (800, 400, [(0.0, "KeyLab mkII"), (0.8, "KeyLab mkII"), (1.2, "1 - Kick")]),
])
def test_the_splash_timings_are_switches(make_rig, splash, tag, expect):
    rig = boot(make_rig, cfg={"SPLASH_MS": splash, "SPLASH_TAG_MS": tag})
    t0 = rig.host.clock.now
    rig.settle(3.0)
    tl = _lcd_timeline(rig, t0)
    assert len(tl) == len(expect), tl
    for (t, l1, _), (et, el1) in zip(tl, expect):
        assert l1 == el1 and et <= t <= et + 0.1, tl


def test_an_lcd_page_from_a_button_press_during_the_splash_wins(rig):
    rig.tap(kl.BTN_PLAY)
    rig.idle(0.3)
    assert rig.host.device_model().lcd[0] in ("Play", "Pause")


# ================================================================================================ every callback is guarded

def test_every_on_callback_of_the_entry_script_is_wrapped_in_klt_log_guarded(target):
    src = (target.path / "device_KeyLabmk2Tuned.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("On"):
            names = [ast.unparse(d) for d in node.decorator_list]
            if "KLTLog.guarded" not in names:
                bad.append(node.name)
    assert not bad, "unguarded callbacks: %s" % bad


ROUTINE_FAULTS = [
    # (failing FL call, an LED that must still work, how to provoke it)
    ("ui.isMetronomeEnabled", kl.LED_LOOP, lambda st: setattr(st, "loop_rec", True)),
    ("ui.isLoopRecEnabled", kl.LED_METRO, lambda st: setattr(st, "metronome", True)),
    ("channels.isChannelMuted", kl.LED_METRO, lambda st: setattr(st, "metronome", True)),
    ("channels.isChannelSolo", kl.LED_MUTE, lambda st: st.muted_channels.add(0)),
    ("channels.isChannelSelected", kl.LED_MUTE, lambda st: st.muted_channels.add(0)),
    ("ui.getFocused", kl.LED_METRO, lambda st: setattr(st, "metronome", True)),
    ("channels.channelCount", kl.LED_LOOP, lambda st: setattr(st, "loop_rec", True)),
    ("transport.isRecording", kl.LED_METRO, lambda st: setattr(st, "metronome", True)),
    ("mixer.getSongTickPos", kl.LED_LOOP, lambda st: setattr(st, "loop_rec", True)),
    ("patterns.patternNumber", kl.LED_LOOP, lambda st: setattr(st, "loop_rec", True)),
]


@pytest.mark.parametrize("failing,led,provoke", ROUTINE_FAULTS, ids=[r[0] for r in ROUTINE_FAULTS])
def test_one_failing_fl_call_does_not_stop_the_other_leds(rig, failing, led, provoke):
    rig.settle(2.0)
    rig.host.inject_fault(failing, RuntimeError)
    provoke(rig.state)
    a = rig.refresh()
    b = rig.idle(3.0)
    c = rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 1))
    assert a.errors == [] and b.errors == [] and c.errors == [], [(e.callback, e.exc) for e in a.errors + b.errors + c.errors][:2]
    assert rig.host.device_model().mono[led] == kl.LED_ON


def test_a_persistent_failure_is_reported_once_not_ten_times_a_second(rig):
    rig.settle(2.0)
    rig.host.inject_fault("ui.isMetronomeEnabled", RuntimeError)
    rig.idle(10.0)
    h = rig.host
    assert h.errors == []
    assert 1 <= len(log_lines(h, "EXC in MetronomeReturn")) <= 2
    assert len(printed(h, "MetronomeReturn raised RuntimeError")) == 1


def test_a_failing_routine_in_the_beat_callback_does_not_stop_the_others(rig):
    rig.settle(2.0)
    rig.state.recording = True
    rig.host.inject_fault("transport.isRecording", RuntimeError)
    a = rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 1))
    assert a.errors == [] and rig.host.device_model().mono[kl.LED_PLAY] == kl.LED_ON


# ================================================================================================ init that fails

def test_a_processor_that_cannot_be_built_leaves_the_leds_and_the_lcd_working(make_rig):
    rig = make_rig(boot=False)
    mod = entry_module()

    def boom(_mk2):
        raise RuntimeError("processor constructor failed")
    mod.KeyLabMidiProcessor = boom
    rig.scripts.boot(order=BOOT_ORDER)
    assert rig.host.errors == [] and mod._processor is None and mod._mk2 is not None
    rig.settle(4.0)
    m = rig.host.device_model()
    assert m.lcd == ("1 - Kick", "Pattern 1") and all(m.rgb[p] == kl.RED for p in kl.PAD_LEDS)
    assert rig.button(kl.BTN_PLAY).errors == []                 # events find no processor and do nothing
    assert any("KeyLabMidiProcessor" in l for l in log_lines(rig.host))


def test_display_objects_that_cannot_be_built_make_every_callback_a_no_op(make_rig):
    rig = make_rig(boot=False)
    mod = entry_module()

    class Boom:
        def __init__(self):
            raise RuntimeError("config constructor failed")
    mod.MidiControllerConfig = Boom
    rig.scripts.boot(order=BOOT_ORDER)
    assert rig.host.errors == [] and mod._mk2 is None
    rig.idle(2.0)
    rig.refresh()
    rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 1))
    rig.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH)
    rig.tap(kl.BTN_PLAY)
    rig.scripts.deinit()
    assert rig.host.errors == [] and rig.host.sysex == []
    assert any("OnInit FAILED" in l for l in printed(rig.host))


# ================================================================================================ OnDeInit / OnSysEx

def test_ondeinit_before_any_init_is_safe_and_silent(host, scripts):
    _, exc = scripts.entry.call("OnDeInit")
    assert exc is None and host.sysex == [] and host.errors == []


def test_ondeinit_after_a_boot_without_output_is_safe(make_rig):
    rig = boot(make_rig, output_assigned=False)
    rig.scripts.deinit()
    assert rig.host.errors == [] and rig.host.sysex == []


@pytest.mark.parametrize("event", [
    SimpleNamespace(), SimpleNamespace(sysex=None), SimpleNamespace(sysex=b""), SimpleNamespace(sysex=b"\xf0\xf7"),
    SimpleNamespace(sysex=bytearray(b"\xf0\x7e\x7f\x06\x02\xf7")), SimpleNamespace(sysex=b"\xf0" + bytes(5000) + b"\xf7"),
    SimpleNamespace(sysex="not bytes"), SimpleNamespace(sysex=12345), None, object()],
    ids=["no-attr", "none", "empty", "f0f7", "bytearray", "huge", "str", "int", "None", "object"])
def test_onsysex_survives_anything_and_only_acts_on_the_memory_switch(rig, event):
    rig.settle(2.0)
    m0 = rig.host.mark()
    _, exc = rig.entry.call("OnSysEx", event)
    assert exc is None and rig.host.errors == []
    assert not any(c.qual == "ui.setFocused" for c in rig.host.since(m0).calls)


def test_the_memory_switch_still_focuses_the_channel_rack_before_oninit(host, scripts):
    host.state.focus(kl.WID_MIXER)
    d = scripts.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH)
    assert d.exceptions == [] and host.state.focused == kl.WID_CHANNEL_RACK and host.sysex == []


def test_incoming_sysex_is_logged_once_per_distinct_message(rig):
    for _ in range(5):
        rig.entry.deliver_sysex(b"\xf0\x00\x20\x6b\x7f\x42\x01\xf7")
    rig.entry.deliver_sysex(b"\xf0\x7e\x7f\x06\x02\xf7")
    lines = log_lines(rig.host, "OnSysEx ")
    assert len(lines) == 2 and "f000206b7f4201f7" in lines[0]


# ================================================================================================ re-init and helper state (O-08, O-09)

def test_init_only_builds_what_is_missing_and_force_starts_over(rig):
    mod = entry_module()
    mk2, proc = mod._mk2, mod._processor
    mod.init()
    mod.init()
    assert mod._mk2 is mk2 and mod._processor is proc
    mod.init(force=True)
    assert mod._mk2 is not mk2 and mod._processor is not proc


def test_a_second_init_from_another_script_does_not_blank_the_lcd(make_rig):
    rig = boot(make_rig, order=("entry",))
    rig.settle(4.0)
    entry_module().init()                                     # what the stock Forward script's OnInit did
    rig.settle(1.0)
    assert rig.host.device_model().lcd == ("1 - Kick", "Pattern 1")


def _dirty_helpers():
    P, X, R = module("KLTProcess"), module("KLTCrossKeyboard"), module("KLTReturn")
    P.SEQ_MODE, P.MIXER_MODE, P.RECT_OFFSET, P.EDIT_MODE, P.SEQ_PARAM = 1, 1, 2, 1, 3
    X.CH_OFFSET, X.MX_OFFSET = 3, 4
    P.STATE_MATRIX[1][2] = 1
    P.INDEX_PRESSED.append(5)
    R.REFRESH_COUNT, R.PASS = 9, True
    return P, X, R


def test_oninit_resets_the_stale_state_of_the_helper_modules(make_rig):
    rig = make_rig(boot=False)
    P, X, R = _dirty_helpers()
    rig.scripts.boot(order=BOOT_ORDER)
    assert (P.SEQ_MODE, P.MIXER_MODE, P.RECT_OFFSET, P.EDIT_MODE, P.SEQ_PARAM) == (0, 0, 0, 0, 0)
    assert (X.CH_OFFSET, X.MX_OFFSET) == (0, 0) and P.STATE_MATRIX[1][2] == 0 and P.INDEX_PRESSED == []
    assert (R.REFRESH_COUNT, R.PASS) == (0, False)
    rig.settle(3.0)
    assert rig.host.device_model().rgb[kl.PAD_LEDS[0]] == kl.RED       # drum mode, as after a first start


def test_the_helper_reset_is_a_switch(make_rig):
    rig = make_rig(boot=False)
    rig.host.set_config(RESET_HELPER_STATE_ON_INIT=False)
    P, X, R = _dirty_helpers()
    rig.scripts.boot(order=BOOT_ORDER)
    assert (P.SEQ_MODE, X.CH_OFFSET) == (1, 3)


def test_a_reload_after_a_session_in_sequencer_mode_starts_in_drum_mode(rig):
    rig.settle(2.0)
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.tap(kl.BTN_MIXER_TOGGLE)
    rig.settle(1.0)
    rig.scripts.deinit()
    rig.host.clear_trace()
    rig.entry.call("OnInit")                                  # FL keeps the modules loaded across Reload
    rig.entry.call("OnRefresh", 0x1FFFF)
    rig.settle(3.0)
    m = rig.host.device_model()
    assert all(m.rgb[p] == kl.RED for p in kl.PAD_LEDS) and m.rgb[kl.SELECT_LEDS[1]] == kl.PURPLE
