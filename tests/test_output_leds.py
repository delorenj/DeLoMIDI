"""LED semantics of the tuned output side: byte-identity with the stock LED ids and colours, and the small fixes and
switches around them (O-08, O-10, O-13, O-14, O-17, O-19).

The stock-vs-tuned comparisons load Arturia's folder read-only ($KL_STOCK_DIR) and compare what the keyboard ends up
showing after the same FL state and the same button presses; timing and text scrolling legitimately differ, LED ids and
colours must not."""
from __future__ import annotations

import pytest

from tests import kl
from tests.conftest import BOOT_ORDER, STOCK_DIR
from tests.flsim.rig import Rig
from tests.flsim.state import FLState
from tests.flsim.sysex import decode
from tests.test_output_support import boot, module, sent, tuned_only  # noqa: F401


def _run(host, folder, build, drive):
    host.state = FLState()
    host.clear_trace()
    scripts = host.load(folder)
    build(host.state)
    scripts.boot(order=BOOT_ORDER)
    rig = Rig(host, scripts)
    drive(rig)
    rig.refresh()
    rig.settle(8.0)
    assert host.errors == [], [(e.callback, e.exc) for e in host.errors][:2]
    m = host.device_model()
    return m.state(), host.sysex[:]


# ================================================================================================ byte identity with stock

def _nothing(st):
    pass


def _many_channels(st):
    st.resize_channels(40)
    st.selected_channel = 21
    st.muted_channels.update({0, 21, 22})
    st.solo_channels.add(21)


def _sequencer(st):
    st.grid.update({(0, 0): 1, (0, 3): 1, (0, 9): 1, (0, 15): 1})
    st.step_params[(0, 1, 3, 1)] = 40
    st.step_params[(0, 1, 9, 1)] = 127


def _transport(st):
    st.recording, st.song_tick_pos, st.metronome, st.loop_rec = True, 480, True, True


def _mixer(st):
    st.current_track = 12
    st.muted_tracks.update({12, 13})
    st.solo_tracks.add(12)


SCENARIOS = {
    "drum-default": (_nothing, lambda r: None),
    "five-channels": (lambda st: st.resize_channels(5), lambda r: None),
    "forty-channels-third-bank": (_many_channels, lambda r: [r.tap(kl.BTN_NEXT) for _ in range(2)]),
    "sequencer-steps": (_sequencer, lambda r: r.tap(kl.BTN_SEQ_TOGGLE)),
    "sequencer-song-mode": (lambda st: setattr(st, "loop_mode", 1), lambda r: r.tap(kl.BTN_SEQ_TOGGLE)),
    "transport-leds": (_transport, lambda r: None),
    "mixer-mode": (_mixer, lambda r: r.tap(kl.BTN_MIXER_TOGGLE)),
    "mixer-mode-last-bank": (_mixer, lambda r: [r.tap(kl.BTN_MIXER_TOGGLE)] + [r.tap(kl.BTN_NEXT) for _ in range(20)]),
}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_keyboard_ends_up_showing_what_the_stock_script_shows(host, target, name):
    if not STOCK_DIR.is_dir():
        pytest.skip("stock folder not found: %s" % STOCK_DIR)
    build, drive = SCENARIOS[name]
    stock_state, _ = _run(host, STOCK_DIR, build, drive)
    tuned_state, _ = _run(host, target.path, build, drive)
    s_mono, s_rgb, _ = stock_state
    t_mono, t_rgb, _ = tuned_state
    assert dict(t_rgb) == dict(s_rgb), {k: (dict(s_rgb).get(k), dict(t_rgb).get(k)) for k in set(dict(s_rgb)) | set(dict(t_rgb)) if dict(s_rgb).get(k) != dict(t_rgb).get(k)}
    diff_mono = {k: (dict(s_mono).get(k), dict(t_mono).get(k)) for k in set(dict(s_mono)) | set(dict(t_mono)) if dict(s_mono).get(k) != dict(t_mono).get(k)}
    assert diff_mono == {}


def test_tuned_sends_no_led_id_or_colour_that_stock_never_sends(host, target):
    """A broad session through both; the set of (LED id, value) the tuned script uses must be a subset of stock's."""
    if not STOCK_DIR.is_dir():
        pytest.skip("stock folder not found: %s" % STOCK_DIR)

    def broad(rig):
        rig.tap(kl.BTN_METRO)
        rig.tap(kl.BTN_LOOP)
        rig.tap(kl.BTN_SEQ_TOGGLE)
        rig.state.playing = True
        rig.state.song_tick_pos = 5
        rig.driver.run(3, playback=True)
        rig.tap(kl.BTN_MIXER_TOGGLE)
        rig.state.recording = True
        for _ in range(3):
            rig.tap(kl.BTN_NEXT)

    def used(folder):
        _, msgs = _run(host, folder, _sequencer, broad)
        ids = set()
        for m in msgs:
            f = decode(m.data)
            if f.kind == "led_mono":
                ids.add(("mono", f.fields["id"], f.fields["value"]))
            elif f.kind == "led_rgb":
                ids.add(("rgb", f.fields["id"], f.fields["rgb"], f.fields["trailer"]))
        return ids
    stock, tuned = used(STOCK_DIR), used(target.path)
    assert tuned <= stock, sorted(tuned - stock)[:10]


# ================================================================================================ pad LED orientation (O-10)

def test_pad_led_ids_are_stock_by_default(make_rig):
    rig = boot(make_rig)
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.state.grid[(0, 0)] = 1
    rig.state.grid[(0, 5)] = 1
    rig.refresh()
    rig.settle(2.0)
    m = rig.host.device_model()
    assert m.rgb[0x70] == (25, 25, 0) and m.rgb[0x75] == (25, 25, 0)


def test_flipped_pad_rows_map_pad_0_to_the_top_row_of_leds(make_rig):
    rig = boot(make_rig, cfg={"PAD_LED_FLIP_ROWS": True})
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.state.grid[(0, 0)] = 1
    rig.state.grid[(0, 5)] = 1
    rig.refresh()
    rig.settle(2.0)
    m = rig.host.device_model()
    assert m.rgb[0x7C] == (25, 25, 0) and m.rgb[0x79] == (25, 25, 0)
    assert sorted(p for p in kl.PAD_LEDS if m.rgb[p] == (25, 25, 0)) == [0x79, 0x7C]
    assert all(m.rgb[p] == kl.WHITE for p in kl.PAD_LEDS if p not in (0x79, 0x7C))


def test_flipped_pad_rows_still_cover_all_16_leds_in_drum_mode(make_rig):
    rig = boot(make_rig, cfg={"PAD_LED_FLIP_ROWS": True, "INIT_ANIMATION": 1})
    rig.settle(3.0)
    m = rig.host.device_model()
    assert sorted(m.rgb_history) == sorted(kl.PAD_LEDS + kl.SELECT_LEDS + [kl.LED_MULTI])
    assert all(m.rgb[p] == kl.RED for p in kl.PAD_LEDS)


# ================================================================================================ Save LED (O-17)

def test_the_save_led_is_always_lit_by_default_like_stock(rig):
    rig.settle(2.0)
    assert rig.host.device_model().mono[0x65] == kl.LED_ON
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.settle(1.0)
    assert rig.host.device_model().mono[0x65] == kl.LED_ON


def test_the_save_led_can_follow_the_sequencer_mode(make_rig):
    rig = boot(make_rig, cfg={"SAVE_LED_FOLLOWS_MODE": True})
    rig.settle(2.0)
    assert rig.host.device_model().mono[0x65] == kl.LED_OFF
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.settle(1.0)
    assert rig.host.device_model().mono[0x65] == kl.LED_ON
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.settle(1.0)
    assert rig.host.device_model().mono[0x65] == kl.LED_OFF


# ================================================================================================ channel index (O-13)

def _cb_calls(rig, qual, cb):
    return [c for c in rig.host.calls if c.qual == qual and c.cb == cb]


def test_the_led_logic_uses_the_group_relative_selected_channel_by_default(rig):
    rig.settle(2.0)
    n_sel = len(_cb_calls(rig, "channels.selectedChannel", "OnIdle"))
    assert n_sel > 0 and _cb_calls(rig, "channels.channelNumber", "OnIdle") == []
    assert _cb_calls(rig, "channels.channelNumber", "OnRefresh") == []


def test_the_global_index_of_stock_is_a_switch(make_rig):
    rig = boot(make_rig, cfg={"GROUP_RELATIVE_CHANNELS": False})
    rig.state.muted_channels.add(0)
    rig.settle(2.0)
    assert _cb_calls(rig, "channels.channelNumber", "OnIdle") != [] and _cb_calls(rig, "channels.selectedChannel", "OnIdle") == []
    assert rig.host.device_model().mono[kl.LED_MUTE] == kl.LED_ON and rig.host.errors == []


# ================================================================================================ step velocity (O-14)

@pytest.mark.parametrize("velocity,expected", [(-1, 0), (0, 0), (3, 0), (4, 1), (100, 25), (127, 31), (128, 31), (500, 31)])
def test_the_step_velocity_is_clamped_before_it_becomes_a_colour(rig, velocity, expected):
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.state.grid[(0, 1)] = 1
    rig.state.step_param_forced = velocity
    a = rig.refresh()
    rig.settle(1.0)
    assert a.errors == [] and rig.host.errors == []
    assert rig.host.device_model().rgb[0x71] == (expected, expected, 0)


# ================================================================================================ stale bank offsets (O-08)

def test_a_stale_channel_bank_shows_the_last_bank_and_never_indexes_past_the_rack(rig):
    module("KLTCrossKeyboard").CH_OFFSET = 7             # a Reload left this behind; the rack has 10 channels
    rig.refresh()
    rig.settle(2.0)
    m = rig.host.device_model()
    assert rig.host.errors == [] and [v for v in rig.host.violations if v.kind == "index"] == []
    assert [m.rgb[s] for s in kl.SELECT_LEDS] == [kl.PURPLE, kl.PURPLE] + [kl.OFF] * 6      # channels 9, 10 of bank 1


def test_a_stale_mixer_bank_shows_the_last_bank(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    module("KLTCrossKeyboard").MX_OFFSET = 99
    rig.refresh()
    rig.settle(2.0)
    m = rig.host.device_model()
    assert rig.host.errors == [] and [v for v in rig.host.violations if v.kind == "index"] == []
    assert [m.rgb[s] for s in kl.SELECT_LEDS] == [kl.BLUE] * 5 + [kl.OFF] * 3                # tracks 121..125


# ================================================================================================ empty rack (O-04)

def test_an_empty_rack_lights_no_select_button_and_shows_step_off_pads(make_rig):
    rig = make_rig(boot=False)
    rig.state.set_channels([])
    rig.scripts.boot(order=BOOT_ORDER)
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.refresh()
    rig.settle(3.0)
    m = rig.host.device_model()
    assert [m.rgb[s] for s in kl.SELECT_LEDS] == [kl.OFF] * 8
    assert all(m.rgb[p] == kl.WHITE for p in kl.PAD_LEDS)
    assert m.mono[kl.LED_SOLO] == kl.LED_OFF and m.mono[kl.LED_MUTE] == kl.LED_OFF
    assert [v for v in rig.host.violations if v.kind == "index" and v.callback in ("OnIdle", "OnRefresh", "OnInit")] == []


def test_a_selection_of_minus_one_does_not_light_the_solo_or_mute_led(make_rig):
    rig = make_rig(boot=False)
    rig.state.selected_channel = -1
    rig.state.solo_channels.add(0)
    rig.scripts.boot(order=BOOT_ORDER)
    rig.settle(3.0)
    m = rig.host.device_model()
    assert m.mono[kl.LED_SOLO] == kl.LED_OFF and rig.host.errors == []


# ================================================================================================ playhead timing (O-19)

def _blue_times(rig, pad):
    return [round(t, 2) for t, rgb in rig.host.device_model().rgb_history.get(pad, []) if rgb == kl.BLUE]


@pytest.mark.parametrize("tempo_api", ["milli-bpm", "bpm", "zero"])
def test_the_fake_sixteenth_highlight_fires_a_sixteenth_after_the_beat_whatever_the_tempo_unit(make_rig, tempo_api):
    """Stock counted idle ticks / 22 and used getCurrentTempo(1) whose unit is unverified. At 120 BPM a sixteenth is
    0.125 s; a tempo of 0 must not divide by zero (it falls back to 120)."""
    rig = boot(make_rig)
    import mixer
    if tempo_api == "bpm":
        mixer.getCurrentTempo = lambda asInt=False: 120.0
    elif tempo_api == "zero":
        mixer.getCurrentTempo = lambda asInt=False: 0
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.state.tempo = 120.0
    rig.state.song_tick_pos = 1
    rig.state.song_step_pos = 4
    rig.refresh()
    rig.settle(2.0)
    t_beat = rig.host.clock.now
    rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 2))
    assert rig.host.device_model().rgb[0x74] == kl.BLUE                 # the playhead pad, at once
    rig.idle(0.5)
    later = [t for t, rgb in rig.host.device_model().rgb_history[0x75] if rgb == kl.BLUE and t >= t_beat]
    assert later and 0.10 <= later[0] - t_beat <= 0.2, "fake 16th highlight after %s s" % [round(t - t_beat, 3) for t in later]
    assert rig.host.errors == []
