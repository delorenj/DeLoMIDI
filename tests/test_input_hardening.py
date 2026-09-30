"""Input-side hardening of the DAW-port processor: F-01 (no midiId), F-04, F-08..F-14, F-18, F-21..F-23 and their switches.

Each @tuned_fix test asserts the fixed behaviour of a documented stock bug and fails on Arturia's stock scripts (see
docs/tuned/CHANGES-input.md for the finding -> change -> switch -> test table). Switch tests need the tuned folder."""
from __future__ import annotations

import pytest

from tests import kl
from tests.test_input_helpers import focus_plugin, fresh_second, fwd, log_lines, module, tuned_only

MIDI_FPT_UNDO = 20


def calls(action, qual):
    return [c for c in action.effects if c.qual == qual]


def pans(action):
    return [(c.args[0], round(c.args[1], 4)) for c in calls(action, "mixer.setTrackPan")]


def enter_sequencer(rig):
    rig.tap(kl.BTN_SEQ_TOGGLE)


# ================================================================================================ F-01: no midiId

@pytest.mark.tuned_fix("F-01")
def test_the_processor_dispatches_on_the_raw_status_not_on_midiid(rig):
    """Stock decided by event.midiId, which FL may leave at 0 outside OnMidiMsg."""
    ev = rig.host.make_event(0x90, kl.BTN_PLAY, 127, populated=False)
    assert ev.midiId == 0
    a = rig.capture(lambda: rig.entry.invoke("OnMidiMsg", ev))
    assert a.called("transport.start") and ev.handled is True
    fader = rig.host.make_event(0xE1, 0, 100, populated=False)
    b = rig.capture(lambda: rig.entry.invoke("OnMidiMsg", fader))
    assert fader.handled is True and b.errors == []


# ================================================================================================ F-08: pure helpers

@pytest.mark.tuned_fix("F-08")
def test_a_mixer_fader_event_is_not_rewritten_into_a_cc(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    a = rig.fader(2, 90)
    assert (a.event.status, a.event.data1, a.event.data2) == (0xE2, 0, 90)
    assert a.event.midiId == 0xE0


@pytest.mark.tuned_fix("F-08")
def test_mixer_lcd_names_the_master_as_track_zero_for_both_controls(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    rig.fader(8, 100)
    rig.idle(0.1)
    assert rig.host.device_model().lcd[0] == "Volume - 0"
    rig.cc(24, 1)
    rig.idle(0.1)
    assert rig.host.device_model().lcd[0] == "Pan - 0", "stock: 'Pan - 9'"


# ================================================================================================ F-09: track guard

@pytest.mark.tuned_fix("F-09")
def test_a_channel_that_routes_to_no_mixer_track_does_not_select_track_minus_one(rig):
    rig.state.channel_fx_track[3] = -1
    a = rig.button(kl.BTN_SELECT[3], False)
    assert a.called("channels.selectOneChannel", 3) and not a.called("mixer.setTrackNumber", -1)
    rig.cc(60, 1)
    rig.state.selected_channel = 3
    rig.cc(60, 1)
    assert [v for v in rig.host.violations if v.kind == "index"] == []


@pytest.mark.tuned_fix("F-09")
def test_solo_and_arm_never_address_an_invalid_mixer_track(rig):
    rig.state.focus(kl.WID_MIXER)
    rig.state.current_track = 126                                               # the "current track" pseudo track
    for note in (kl.BTN_SOLO[0], kl.BTN_MUTE[0], kl.BTN_JOG_PUSH):
        rig.tap(note)
    assert [v for v in rig.host.violations if v.kind == "index"] == []
    assert not [c for c in rig.host.calls if c.qual in ("mixer.soloTrack", "mixer.muteTrack", "mixer.armTrack")]


# ================================================================================================ F-10: relative encoders

FIX = pytest.mark.tuned_fix("F-10")


@pytest.mark.parametrize("value,n,fn", [
    (1, 1, "ui.next"), pytest.param(2, 2, "ui.next", marks=FIX), pytest.param(3, 3, "ui.next", marks=FIX),
    pytest.param(9, 4, "ui.next", marks=FIX), (65, 1, "ui.previous"), pytest.param(66, 2, "ui.previous", marks=FIX),
    pytest.param(67, 3, "ui.previous", marks=FIX), pytest.param(127, 4, "ui.previous", marks=FIX)])
def test_the_jog_moves_by_the_tick_count_capped_per_event(rig, value, n, fn):
    """Stock reacted to exactly 1 and 65: a fast spin did nothing at all."""
    a = rig.cc(60, value)
    assert len(calls(a, fn)) == n and a.handled is True, a.lines


@pytest.mark.parametrize("value", [0, 64])
def test_a_zero_movement_jog_value_does_nothing_and_is_consumed(rig, value):
    a = rig.cc(60, value)
    assert a.effects == [] and a.handled is True


def test_the_jog_reacts_to_exactly_one_and_sixty_five_when_ticks_are_switched_off(rig, target):
    tuned_only(target)
    rig.host.set_config(ENCODER_USE_TICKS=False)
    assert rig.cc(60, 3).effects == [] and rig.cc(60, 66).effects == []
    assert rig.cc(60, 1).called("ui.next") and rig.cc(60, 65).called("ui.previous")


@pytest.mark.tuned_fix("F-10")
def test_the_jog_steps_the_browser_by_the_tick_count(rig):
    rig.state.focus(kl.WID_BROWSER)
    assert len(calls(rig.cc(60, 3), "ui.next")) == 3
    rig.state.in_popup_menu = True
    assert len(calls(rig.cc(60, 66), "ui.up")) == 2 and len(calls(rig.cc(60, 2), "ui.down")) == 2


@pytest.mark.tuned_fix("F-10")
def test_encoder_nine_pans_by_the_tick_count(rig):
    rig.state.current_track = 4
    assert pans(rig.cc(24, 3)) == [(4, 0.15)]
    assert pans(rig.cc(24, 67)) == [(4, 0.0)]
    assert pans(rig.cc(24, 63)) == [(4, 0.2)], "capped at ENCODER_MAX_TICKS (4) per event"
    assert pans(rig.cc(24, 64)) == [(4, 0.2)], "0x40 = no movement (stock: -3, then a fixed step)"


@pytest.mark.tuned_fix("F-10")
def test_mixer_mode_encoders_pan_by_the_tick_count(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    assert pans(rig.cc(17, 2)) == [(2, 0.1)]
    assert pans(rig.cc(24, 66)) == [(0, -0.1)]


def test_pan_ticks_can_be_switched_back_to_one_step_per_event(rig, target):
    tuned_only(target)
    rig.host.set_config(ENCODER_USE_TICKS=False)
    rig.state.current_track = 4
    assert pans(rig.cc(24, 3)) == [(4, 0.05)]


@pytest.mark.tuned_fix("F-10")
def test_pan_never_leaves_its_range(rig):
    rig.state.current_track = 4
    for _ in range(40):
        rig.cc(24, 1)
    assert rig.state.track_pan[4] == pytest.approx(1.0)
    for _ in range(80):
        rig.cc(24, 65)
    assert rig.state.track_pan[4] == pytest.approx(-1.0)
    assert [v for v in rig.host.violations if v.kind == "value"] == []


@pytest.mark.tuned_fix("F-10")
def test_a_plugin_knob_moves_the_live_value_by_the_tick_count_without_truncation(rig):
    focus_plugin(rig, "FPC")
    rig.state.param_values[(0, 8)] = 0.5118
    a = rig.cc(16, 3)
    (c,) = calls(a, "plugins.setParamValue")
    assert c.args[0] == pytest.approx(0.5118 + 3 * 2 / 127) and c.args[1] == 8
    b = rig.cc(16, 67)
    assert calls(b, "plugins.setParamValue")[0].args[0] == pytest.approx(0.5118, abs=1e-9)


def test_a_plugin_knob_stays_inside_zero_and_one(rig):
    focus_plugin(rig, "FPC")
    rig.state.param_values[(0, 8)] = 0.99
    rig.cc(16, 63)
    assert rig.state.param_values[(0, 8)] == 1.0
    rig.state.param_values[(0, 8)] = 0.01
    rig.cc(16, 127)
    assert rig.state.param_values[(0, 8)] == 0.0
    assert [v for v in rig.host.violations if v.kind == "value"] == []


@pytest.mark.tuned_fix("F-10")
def test_a_plugin_parameter_the_plugin_does_not_have_is_skipped(rig, target):
    """The database's indices are unverified against the real plugins: a stale one must not reach plugins.*Param*."""
    tuned_only(target)
    fresh_second(rig)
    focus_plugin(rig, "FPC")
    rig.state.param_count = 8                                                   # FPC's knob 1 is parameter 8
    a = rig.cc(16, 1)
    assert not calls(a, "plugins.setParamValue") and a.errors == []
    assert log_lines(rig, "FPC parameter 8 does not exist")


# ================================================================================================ F-11: step edit

@pytest.mark.tuned_fix("F-11")
def test_encoder_eight_edits_the_documented_shift_parameter(rig):
    """Guide p.15 Fig.31 lists Shift as the 8th step parameter; stock's encoder 8 did nothing."""
    enter_sequencer(rig)
    rig.pad_on(36)
    up = rig.cc(23, 1)
    (c,) = calls(up, "channels.setStepParameterByIndex")
    assert c.args[:5] == (0, 1, 0, 7, 1) and up.called("channels.showGraphEditor", 1, 7)
    for _ in range(60):
        rig.cc(23, 1)
    assert rig.state.step_param(0, 1, 0, 7) == 24, "0 .. PPQN/4 at FL's default PPQN of 96"
    for _ in range(80):
        rig.cc(23, 65)
    assert rig.state.step_param(0, 1, 0, 7) == 0


@pytest.mark.tuned_fix("F-11")
def test_held_steps_change_relative_to_their_own_values(rig):
    enter_sequencer(rig)
    rig.state.step_params[(0, 1, 0, 1)] = 50
    rig.state.step_params[(0, 1, 1, 1)] = 100
    rig.pad_on(36)
    rig.pad_on(37)
    rig.cc(17, 1)
    assert (rig.state.step_param(0, 1, 0, 1), rig.state.step_param(0, 1, 1, 1)) == (53, 103)
    rig.cc(17, 66)
    assert (rig.state.step_param(0, 1, 0, 1), rig.state.step_param(0, 1, 1, 1)) == (47, 97)


@pytest.mark.tuned_fix("F-11")
def test_fine_pitch_covers_its_whole_range(rig):
    enter_sequencer(rig)
    rig.pad_on(36)
    for _ in range(80):
        rig.cc(19, 1)
    assert rig.state.step_param(0, 1, 0, 3) == 240, "stock stopped at 127 (one accumulator for every parameter)"
    assert [v for v in rig.host.violations if v.kind == "value"] == []


@pytest.mark.tuned_fix("F-11")
def test_the_graph_editor_is_shown_once_per_event_however_many_steps_are_held(rig):
    enter_sequencer(rig)
    for pad in (36, 37, 38):
        rig.pad_on(pad)
    a = rig.cc(17, 1)
    assert len(calls(a, "channels.showGraphEditor")) + len(calls(a, "channels.updateGraphEditor")) == 1, a.lines
    assert len(calls(a, "channels.setStepParameterByIndex")) == 3


@pytest.mark.tuned_fix("F-11")
def test_a_failing_step_query_starts_from_the_documented_default(rig):
    enter_sequencer(rig)
    rig.state.step_param_forced = -1
    rig.pad_on(36)
    a = rig.cc(17, 1)
    (c,) = calls(a, "channels.setStepParameterByIndex")
    assert c.args[4] == 103 and [v for v in rig.host.violations if v.kind == "value"] == []


def test_encoder_nine_in_step_edit_only_closes_the_graph_editor(rig):
    enter_sequencer(rig)
    rig.pad_on(36)
    rig.cc(17, 1)
    assert rig.state.graph_editor_visible
    a = rig.cc(24, 1)
    assert a.called("channels.closeGraphEditor") and not calls(a, "channels.setStepParameterByIndex") and not pans(a)


@pytest.mark.tuned_fix("F-10")
def test_a_zero_movement_step_edit_changes_nothing(rig):
    enter_sequencer(rig)
    rig.pad_on(36)
    a = rig.cc(17, 64)
    assert not calls(a, "channels.setStepParameterByIndex") and a.errors == []


# ================================================================================================ F-04 (pads), F-06, F-07 switches

@pytest.mark.tuned_fix("F-04")
def test_a_release_whose_press_was_forgotten_does_not_toggle_a_step(rig):
    """Press in Sequencer mode, toggle Save twice (the held-pad state is cleared), then the release arrives."""
    enter_sequencer(rig)
    rig.pad_on(36)
    enter_sequencer(rig)
    enter_sequencer(rig)
    a = rig.pad_off(36)
    assert not a.calls_to("channels.setGridBit") and a.errors == []


@pytest.mark.tuned_fix("F-04")
def test_song_mode_pads_release_their_state_without_toggling_a_step(rig):
    enter_sequencer(rig)
    rig.state.loop_mode = 1
    rig.pad_on(36)
    a = rig.pad_off(36)
    assert a.handled is True and not a.calls_to("channels.setGridBit")
    assert module("KLTProcess").EDIT_MODE == 0 and module("KLTProcess").STATE_MATRIX[0][0] == 0


def test_a_pad_note_on_with_velocity_zero_is_a_release(rig, target):
    tuned_only(target)
    enter_sequencer(rig)
    rig.pad_on(36, 100)
    a = rig.pad_on(36, 0)
    assert a.called("channels.setGridBit", 0, 0, 1) and a.handled is True
    rig.host.set_config(PADS_NOTE_ON_ZERO_IS_RELEASE=False)
    b = rig.pad_on(37, 0)
    assert not b.calls_to("channels.setGridBit"), "stock: a velocity-0 note-on is a press"


@pytest.mark.tuned_fix("F-06")
@pytest.mark.parametrize("note", [0, 35, 52, 60])
def test_notes_outside_the_pad_range_are_not_step_buttons(rig, note):
    enter_sequencer(rig)
    a = rig.pad_on(note, 90)
    assert a.handled is False and a.errors == [] and not a.calls_to("device.processMIDICC")


def test_the_fpc_remap_for_every_instrument_is_a_switch(rig, target):
    tuned_only(target)
    rig.host.set_config(PADS_REMAP_ONLY_FOR_FPC=False)
    rig.state.select_channel_plugin("Sampler")
    a = rig.pad_on(36, 100)
    assert (a.event.data1, a.event.data2) == (49, 100), "stock remapped everything; the velocity is kept regardless (F-05)"


@pytest.mark.parametrize("name", ["FPC", " fpc ", "Fpc"])
def test_fpc_is_recognised_by_the_selected_channels_plugin(rig, target, name):
    tuned_only(target)
    rig.state.select_channel_plugin(name)
    assert rig.pad_on(36, 100).event.data1 == 49


def test_the_focused_plugin_window_names_fpc_when_the_channels_plugin_is_unknown(rig, target):
    tuned_only(target)
    rig.state.select_channel_plugin("")
    rig.state.focus(kl.WID_PLUGIN, "FPC")
    assert rig.pad_on(36, 100).event.data1 == 49


# ================================================================================================ F-12: modes and banks follow reality

@pytest.mark.tuned_fix("F-12")
def test_the_bank_buttons_follow_the_window_the_user_focused_with_the_mouse(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    rig.state.focus(kl.WID_CHANNEL_RACK)
    rig.state.resize_channels(30)
    rig.tap(kl.BTN_NEXT)
    assert module("KLTCrossKeyboard").CH_OFFSET == 1 and module("KLTCrossKeyboard").MX_OFFSET == 0


@pytest.mark.tuned_fix("F-12")
def test_focusing_the_mixer_with_the_mouse_switches_the_faders_to_mixer_mode(rig):
    a = rig.fader(2, 100)
    assert not calls(a, "mixer.setTrackVolume")
    rig.state.focus(kl.WID_MIXER)
    b = rig.fader(2, 100)
    assert [c.args[0] for c in calls(b, "mixer.setTrackVolume")] == [3]


def test_a_plugin_window_or_the_browser_leaves_the_mode_alone(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    for window, name in ((kl.WID_PLUGIN, "FPC"), (kl.WID_BROWSER, None), (kl.WID_PLAYLIST, None)):
        rig.state.focus(window, name)
        assert [c.args[0] for c in calls(rig.fader(0, 100), "mixer.setTrackVolume")] == [1], window


def test_mode_following_the_focus_is_a_switch(rig, target):
    tuned_only(target)
    rig.host.set_config(MODE_FOLLOWS_FOCUS=False)
    rig.tap(kl.BTN_MIXER_TOGGLE)
    rig.state.focus(kl.WID_CHANNEL_RACK)
    assert [c.args[0] for c in calls(rig.fader(0, 100), "mixer.setTrackVolume")] == [1], "stock: only the Bank button"


@pytest.mark.tuned_fix("F-12")
def test_the_output_side_can_resync_the_mode_on_refresh(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    proc = module("KLTProcess")
    assert proc.MIXER_MODE == 1
    rig.state.focus(kl.WID_CHANNEL_RACK)
    proc.sync_mode_from_focus()
    assert proc.MIXER_MODE == 0


@pytest.mark.tuned_fix("F-12")
def test_a_stale_channel_bank_is_clamped_before_the_next_event(rig):
    rig.state.resize_channels(30)
    for _ in range(3):
        rig.tap(kl.BTN_NEXT)
    assert module("KLTCrossKeyboard").CH_OFFSET == 3
    rig.state.resize_channels(5)
    a = rig.button(kl.BTN_SELECT[0], False)
    assert module("KLTCrossKeyboard").CH_OFFSET == 0 and a.called("channels.selectOneChannel", 0)
    assert [v for v in rig.host.violations if v.kind == "index"] == []


@pytest.mark.tuned_fix("F-12")
def test_the_step_window_offset_is_bounded(rig):
    enter_sequencer(rig)
    for _ in range(60):
        rig.button(kl.BTN_FORWARD, True)
    assert module("KLTProcess").RECT_OFFSET == module("KLTProcess").MAX_RECT_OFFSET == 31


@pytest.mark.tuned_fix("F-12")
def test_reset_state_returns_every_mode_and_bank_to_power_on(rig):
    enter_sequencer(rig)
    rig.pad_on(36)
    rig.button(kl.BTN_FORWARD, True)
    rig.tap(kl.BTN_MIXER_TOGGLE)
    rig.tap(kl.BTN_NEXT)
    module("KLTProcess").reset_state()
    p, c = module("KLTProcess"), module("KLTCrossKeyboard")
    assert (p.SEQ_MODE, p.MIXER_MODE, p.RECT_OFFSET, p.EDIT_MODE, c.MX_OFFSET, c.CH_OFFSET) == (0, 0, 0, 0, 0, 0)
    assert all(v == 0 for row in p.STATE_MATRIX for v in row)


# ================================================================================================ F-13: group-relative channel index

# (kind, control, needs a focused plugin window): the Channel Rack stays focused where the control acts on the rack
SOME_EVENTS = [("btn", kl.BTN_SOLO[0], False), ("btn", kl.BTN_MUTE[0], False), ("btn", kl.BTN_JOG_PUSH, False),
               ("btn", kl.BTN_CUT, False), ("btn", kl.BTN_PATTERN_NEXT, True), ("cc", 60, False), ("cc", 16, True),
               ("fader", 0, True), ("pad", 36, False), ("wheel", 0, False)]


def play(rig, kind, n):
    if kind == "btn":
        return [rig.button(n, True), rig.button(n, False)]
    if kind == "cc":
        return [rig.cc(n, 1)]
    if kind == "fader":
        return [rig.fader(n, 90)]
    if kind == "pad":
        return [rig.pad_on(n), rig.pad_off(n)]
    return [fwd(rig, 0xE0, 0, 100)]


@pytest.mark.tuned_fix("F-13")
@pytest.mark.parametrize("kind,n,plugin", SOME_EVENTS)
def test_controls_ask_for_the_group_relative_selection_not_the_global_index(rig, kind, n, plugin):
    """channels.channelNumber() is documented as the GLOBAL index while soloChannel/muteChannel/showEditor/
    setStepParameterByIndex default to group-relative ones (API v33+): selectedChannel() is the matching call."""
    if plugin:
        focus_plugin(rig, "FPC")
    if kind == "pad":
        rig.state.select_channel_plugin("FPC")
        enter_sequencer(rig)
    for a in play(rig, kind, n):
        assert not a.calls_to("channels.channelNumber"), (kind, n, [c.short() for c in a.calls_to("channels.channelNumber")])


def test_the_selection_call_is_the_same_switch_as_the_output_side(rig, target):
    tuned_only(target)
    rig.host.set_config(GROUP_RELATIVE_CHANNELS=False)
    a = rig.button(kl.BTN_SOLO[0], False)
    assert a.calls_to("channels.channelNumber") and not a.calls_to("channels.selectedChannel")


# ================================================================================================ F-14: editors

@pytest.mark.tuned_fix("F-14")
def test_an_editor_the_script_opened_is_closed_again_even_if_the_selection_moved_on(rig):
    rig.tap(kl.BTN_JOG_PUSH)                                                    # opens channel 0's editor
    assert rig.state.open_editors == {0}
    rig.state.selected_channel = 5                                              # the user picks another channel
    a = rig.cc(60, 1)                                                           # plugin window focused: jog closes it
    assert rig.state.open_editors == set() and rig.state.focused == kl.WID_CHANNEL_RACK
    assert len(calls(a, "channels.showEditor")) <= 3


@pytest.mark.tuned_fix("F-14")
def test_the_save_and_bank_buttons_close_editors_without_touching_every_channel(make_rig):
    rig = make_rig()
    rig.state.resize_channels(300)
    for note in (kl.BTN_SEQ_TOGGLE, kl.BTN_MIXER_TOGGLE, kl.BTN_SELECT[2]):
        a = rig.button(note, note != kl.BTN_SELECT[2])
        assert len(calls(a, "channels.showEditor")) <= 3, (note, len(calls(a, "channels.showEditor")))


# ================================================================================================ F-18, F-21, F-22

def test_the_cut_button_can_be_disabled(rig, target):
    tuned_only(target)
    assert rig.button(kl.BTN_CUT, False).called("ui.cut")
    rig.host.set_config(CUT_ENABLED=False)
    assert rig.button(kl.BTN_CUT, False).effects == []


@pytest.mark.tuned_fix("F-21")
def test_next_pattern_stops_at_the_limit_of_fl_and_previous_at_the_first(rig):
    rig.state.pattern = 999
    a = rig.button(kl.BTN_PATTERN_NEXT)
    assert not a.calls_to("patterns.jumpToPattern") and a.errors == []
    rig.state.pattern = 1
    assert not rig.button(kl.BTN_PATTERN_PREV).calls_to("patterns.jumpToPattern")
    assert [v for v in rig.host.violations if v.kind == "index"] == []


def test_next_pattern_creates_a_new_pattern_unless_told_not_to(rig, target):
    tuned_only(target)
    rig.state.pattern = 3
    assert rig.button(kl.BTN_PATTERN_NEXT).called("patterns.jumpToPattern", 4) and rig.state.pattern_count == 4
    rig.host.set_config(PATTERN_NEXT_CREATES=False)
    assert not rig.button(kl.BTN_PATTERN_NEXT).calls_to("patterns.jumpToPattern")
    rig.state.pattern = 2
    assert rig.button(kl.BTN_PATTERN_NEXT).called("patterns.jumpToPattern", 3)


@pytest.mark.tuned_fix("F-22")
def test_undo_uses_the_press_value_image_line_uses_and_passes_the_pme_flags(rig):
    """MackieCU: globalTransport(FPT_Undo, int(pressed) * 2, event.pmeFlags); stock passed FPT_Undo (20) as the value."""
    a = rig.button(kl.BTN_UNDO, False)
    (c,) = calls(a, "transport.globalTransport")
    assert c.args == (MIDI_FPT_UNDO, 2, a.event.pmeFlags), c.args


# ================================================================================================ F-23: releases

@pytest.mark.tuned_fix("F-23")
@pytest.mark.parametrize("note,fn", [(kl.BTN_SOLO[0], "channels.soloChannel"), (kl.BTN_MUTE[0], "channels.muteChannel"),
                                     (kl.BTN_SELECT[2], "channels.selectOneChannel"), (kl.BTN_CUT, "ui.cut"),
                                     (kl.BTN_UNDO, "transport.globalTransport"), (kl.BTN_METRO, "transport.globalTransport"),
                                     (kl.BTN_OVERDUB, "transport.globalTransport")])
@pytest.mark.parametrize("velocity", [0, 64])
def test_a_note_off_releases_the_buttons_that_fire_on_release(rig, note, fn, velocity):
    a = rig.midi(0x80, note, velocity)
    assert a.calls_to(fn) and a.handled is True, (note, a.lines)


@pytest.mark.tuned_fix("F-23")
@pytest.mark.parametrize("note", [kl.BTN_PLAY, kl.BTN_STOP, kl.BTN_RECORD, kl.BTN_LOOP, kl.BTN_TAP_TEMPO, kl.BTN_SEQ_TOGGLE,
                                  kl.BTN_MIXER_TOGGLE, kl.BTN_NEXT, kl.BTN_JOG_PUSH, kl.BTN_SNAP[0]])
def test_a_note_off_is_never_a_press(rig, note):
    a = rig.midi(0x80, note, 127)                       # a note-off with a high release velocity
    assert a.effects == [] and a.handled is True


@pytest.mark.tuned_fix("F-23")
def test_a_note_off_is_not_a_bar_offset_press_in_sequencer_mode(rig):
    enter_sequencer(rig)
    a = rig.midi(0x80, kl.BTN_FORWARD, 127)
    assert not a.calls_to("ui.crDisplayRect") and module("KLTProcess").RECT_OFFSET == 0
    b = rig.midi(0x90, kl.BTN_FORWARD, 100)             # any press velocity counts (stock: exactly 127)
    assert b.called("ui.crDisplayRect", 16)


def test_note_off_routing_is_a_switch_and_off_means_stock_behaviour(rig, target):
    tuned_only(target)
    rig.host.set_config(NOTE_OFF_IS_RELEASE=False)
    a = rig.midi(0x80, kl.BTN_MUTE[0], 0)
    assert a.effects == [] and a.handled is False, "stock never routed note-offs"


# ================================================================================================ robustness of ProcessEvent

BATTERY = [(0x90, n, v) for n in (94, 74, 51, 84, 46, 47, 24, 8, 16, 91, 92, 98, 99, 57, 81, 87) for v in (127, 0)] + \
          [(0xB0, n, v) for n in (60, 16, 20, 24, 1, 74) for v in (1, 65)] + [(0xE0 + i, 0, 90) for i in range(9)] + \
          [(0x99, n, 100) for n in (36, 51)] + [(0x89, n, 0) for n in (36, 51)]


@pytest.mark.parametrize("failing", ["ui.getFocused", "ui.setFocused", "channels.channelCount", "channels.selectedChannel",
                                     "mixer.trackCount", "mixer.setTrackVolume", "mixer.getTrackPan", "plugins.getParamValue",
                                     "channels.getGridBit", "transport.getLoopMode", "patterns.patternNumber",
                                     "channels.showEditor", "device.processMIDICC"])
def test_no_exception_escapes_the_processor_when_an_fl_call_fails(rig, target, failing):
    """A raising FL call inside any handler is caught at the top of ProcessEvent (FL would print a traceback and lose
    the callback's work) and lands in klt.log with its traceback. Tuned folder only: stock lets them escape."""
    tuned_only(target)
    focus_plugin(rig, "FPC")
    enter_sequencer(rig)
    rig.host.inject_fault(failing, RuntimeError)
    for status, d1, d2 in BATTERY:
        a = rig.midi(status, d1, d2)
        assert a.errors == [], (failing, hex(status), d1, [(e.callback, str(e.exc)) for e in a.errors])


def test_a_caught_handler_failure_is_logged_with_its_traceback_and_the_control_stays_consumed(rig, target):
    tuned_only(target)
    fresh_second(rig)
    rig.host.inject_fault("transport.start", RuntimeError)
    a = rig.button(kl.BTN_PLAY)
    assert a.errors == [] and a.handled is True
    assert any("EXC in KeyLabMidiProcessor.button" in l for l in log_lines(rig)), log_lines(rig)[-3:]


# ================================================================================================ regression net: seeded sweep

def _sweep(rig, seed, n):
    import random
    from tests.flsim import streams
    r = random.Random(seed)
    for _ in range(n):
        op = streams._midi_entry(r) if r.random() < 0.75 else streams._midi_forward(r)
        if r.random() < 0.15:
            streams.apply_state_op(rig.host.state, *streams._state_op(r)[1:])
        streams.apply_op(rig.scripts, op)


@pytest.mark.tuned_fix("F-01", "F-02", "F-06", "F-09", "F-11", "F-12")
@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("populated", [True, False], ids=["H1", "H2"])
def test_a_random_sweep_of_input_events_never_raises_nor_violates_an_fl_rule(make_rig, seed, populated):
    """Random events on both ports x random FL states. Checks what the fuzz suite cannot see: exceptions that a handler
    caught (klt.log 'EXC in') and every rule violation the strict fakes know (index, param-index, value, event-range)."""
    rig = make_rig(midi_in_populated=populated)
    rig.host.set_config(LOG_MAX_LINES_PER_SEC=100000)
    _sweep(rig, seed, 2500)
    assert rig.host.errors == [], [(e.callback, str(e.exc), e.site) for e in rig.host.errors[:3]]
    assert [l for l in log_lines(rig) if "EXC in" in l] == []
    bad = [(v.kind, v.where) for v in rig.host.violations if v.kind in ("index", "param-index", "value", "event-range")]
    assert bad == [], sorted(set(bad))[:6]


@pytest.mark.parametrize("seed", [4, 5])
def test_the_sweep_with_every_stock_leaning_switch_still_never_raises(make_rig, target, seed):
    tuned_only(target)
    rig = make_rig()
    rig.host.set_config(PASS_UNMAPPED=False, ENCODER_USE_TICKS=False, PADS_REMAP_ONLY_FOR_FPC=False, NOTE_OFF_IS_RELEASE=False,
                        MODE_FOLLOWS_FOCUS=False, FORWARD_USE_PROCESSOR=True, FORWARD_PROCESSOR_KINDS=("note", "cc", "bend"),
                        ANALOG_LAB_CC_TO_PLUGIN_DB=True, GROUP_RELATIVE_CHANNELS=False, LOG_MAX_LINES_PER_SEC=100000)
    _sweep(rig, seed, 2500)
    assert rig.host.errors == [], [(e.callback, str(e.exc), e.site) for e in rig.host.errors[:3]]
    assert [l for l in log_lines(rig) if "EXC in" in l] == []


# ================================================================================================ no output assigned (the tom crash hypothesis)

@pytest.mark.tuned_fix("O-01")
@pytest.mark.parametrize("crash", [True, False], ids=["crash-on-unassigned-output", "noop-on-unassigned-output"])
def test_no_input_event_needs_a_midi_output_or_touches_one_when_none_is_assigned(make_rig, crash):
    """Every control also paints the LCD/LEDs, and midiOutSysex with no output assigned is the leading hypothesis for the
    FL 26.1.6 crash (docs/incidents/2026-09-29): the input side must work with an input-only script assignment."""
    from tests.flsim import FLCrash
    rig = make_rig(boot=False, output_assigned=False, crash_on_unassigned_output=crash)
    focus_plugin(rig, "FPC")
    try:
        rig.scripts.boot(order=("forward", "entry"))
        for status, d1, d2 in BATTERY:
            for role in ("entry", "forward"):
                rig.midi(status, d1, d2, role=role)
        rig.idle(1.0)
    except FLCrash as c:
        pytest.fail("FL would have crashed: %s" % c.reason)
    assert rig.host.errors == [], [(e.callback, str(e.exc)) for e in rig.host.errors[:3]]
    assert rig.host.calls_to("device.midiOutSysex") == [] and rig.host.calls_to("device.midiOutMsg") == []


def test_cc1_is_left_alone_while_a_step_is_being_edited(rig):
    enter_sequencer(rig)                                    # Save closes plugin windows: focus one afterwards
    focus_plugin(rig, "MiniSynth")
    rig.pad_on(36)
    assert not [c for c in fwd(rig, 0xB0, 1, 90).effects if c.qual == "plugins.setParamValue"]
    rig.pad_off(36)
    assert [c for c in fwd(rig, 0xB0, 1, 90).effects if c.qual == "plugins.setParamValue"]
