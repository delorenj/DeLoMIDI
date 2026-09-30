"""The 16 pads: drum mode (FPC remap) and Sequencer mode (step grid and step editing).

Pads are note-on 0x99 / note-off 0x89 (channel 10), notes 36..51 (docs/analysis/02 section 4.5). Characterization
tests describe behaviour to preserve; @tuned_fix tests assert the fixed behaviour of F-04..F-07 and F-11."""
from __future__ import annotations

import pytest

from tests import kl


def fpc_selected(rig, focus_window=False):
    rig.state.select_channel_plugin("FPC")
    if focus_window:
        rig.state.focus(kl.WID_PLUGIN, "FPC")


def sampler_selected(rig, focus_window=False):
    rig.state.select_channel_plugin("Sampler")
    if focus_window:
        rig.state.focus(kl.WID_PLUGIN, "Sampler")


def enter_sequencer(rig):
    rig.tap(kl.BTN_SEQ_TOGGLE)


# ================================================================================================ drum mode

@pytest.mark.parametrize("focus_window", [False, True], ids=["rack-focused", "fpc-window-focused"])
def test_drum_pads_are_remapped_to_the_fpc_layout_when_fpc_is_selected(rig, focus_window):
    """Pad n sounds FPC pad FPC_MAP[n] (guide p.14 Fig.27); the event still goes on to FL so the note plays."""
    fpc_selected(rig, focus_window)
    for pad, fpc_note in kl.FPC_MAP.items():
        on = rig.pad_on(pad, 100)
        assert on.event.data1 == fpc_note and on.handled is False and on.errors == [], (pad, on.event)
        off = rig.pad_off(pad, 0)
        assert off.event.data1 == fpc_note and off.handled is False and off.errors == [], (pad, off.event)
        assert (on.event.status, off.event.status) == (0x99, 0x89)


def test_drum_pads_do_not_call_fl_and_are_not_consumed(rig):
    a = rig.pad_on(36, 100)
    assert a.handled is False and a.effects == []


def test_fpc_pad_map_is_the_documented_one():
    assert kl.FPC_MAP[36] == 49 and kl.FPC_MAP[49] == 36 and kl.FPC_MAP[51] == 54 and len(set(kl.FPC_MAP.values())) == 16


# ================================================================================================ sequencer mode

def test_sequencer_mode_pad_tap_toggles_the_step_of_the_selected_channel(rig):
    enter_sequencer(rig)
    press = rig.pad_on(36)
    assert press.handled is True and press.errors == [] and not press.calls_to("channels.setGridBit")
    release = rig.pad_off(36)
    assert release.handled is True and release.called("channels.setGridBit", 0, 0, 1)
    rig.pad_on(36)
    again = rig.pad_off(36)
    assert again.called("channels.setGridBit", 0, 0, 0)                        # second tap clears the step
    rig.pad_on(51)
    assert rig.pad_off(51).called("channels.setGridBit", 0, 15, 1)


def test_sequencer_pads_act_on_the_selected_channel(rig):
    enter_sequencer(rig)
    rig.state.selected_channel = 3
    rig.pad_on(40)
    assert rig.pad_off(40).called("channels.setGridBit", 3, 4, 1)


def test_sequencer_step_window_moves_with_forward_and_rewind(rig):
    enter_sequencer(rig)
    rig.button(kl.BTN_FORWARD, True)                                           # second bar: steps 16..31
    rig.pad_on(38)
    assert rig.pad_off(38).called("channels.setGridBit", 0, 16 + 2, 1)
    rig.button(kl.BTN_REWIND, True)
    rig.pad_on(38)
    assert rig.pad_off(38).called("channels.setGridBit", 0, 2, 1)


def test_holding_a_pad_and_turning_an_encoder_edits_that_steps_parameter(rig):
    """Guide p.15 Fig.31: encoder 1..7 = pitch, velocity, release velocity, fine pitch, pan, mod X, mod Y."""
    enter_sequencer(rig)
    for enc, param in zip(range(16, 23), range(7)):
        rig.pad_on(38)
        a = rig.cc(enc, 1)
        sets = [c for c in a.effects if c.qual == "channels.setStepParameterByIndex"]
        assert sets and all(c.args[2] == 2 and c.args[3] == param for c in sets), (enc, a.lines)
        rig.pad_off(38)


def test_pads_held_together_are_edited_together(rig):
    enter_sequencer(rig)
    rig.pad_on(36)
    rig.pad_on(37)
    a = rig.cc(17, 1)
    assert sorted({c.args[2] for c in a.effects if c.qual == "channels.setStepParameterByIndex"}) == [0, 1]


def test_a_step_that_was_edited_is_not_toggled_by_releasing_the_pad(rig):
    enter_sequencer(rig)
    rig.pad_on(36)
    rig.cc(17, 1)
    a = rig.pad_off(36)
    assert not a.calls_to("channels.setGridBit")


def test_releasing_the_last_pad_closes_the_graph_editor_and_ends_edit_mode(rig):
    enter_sequencer(rig)
    rig.pad_on(36)
    rig.cc(17, 1)
    assert rig.state.graph_editor_visible
    rig.pad_off(36)
    assert not rig.state.graph_editor_visible
    a = rig.cc(24, 1)                                                          # encoder 9 pans the track again
    assert a.called("mixer.setTrackPan")


def test_toggling_sequencer_mode_back_restores_drum_pads(rig):
    fpc_selected(rig)
    enter_sequencer(rig)
    enter_sequencer(rig)
    a = rig.pad_on(36, 100)
    assert a.event.data1 == 49 and a.handled is False


# ================================================================================================ tuned fixes

@pytest.mark.tuned_fix("F-05")
def test_drum_pad_velocity_is_preserved(rig):
    """Process.py:268,277 overwrote data2 with MIDI_NOTEON (144) / MIDI_NOTEOFF (128): the velocity is destroyed and
    out of the 7-bit range, so every pad plays at an undefined level (or raises where the event is range-checked)."""
    fpc_selected(rig)
    for vel in (1, 37, 100, 127):
        on = rig.pad_on(38, vel)
        assert on.event.data2 == vel, "pad velocity %d became %d" % (vel, on.event.data2)
        assert on.errors == []
    off = rig.pad_off(38, 64)
    assert off.event.data2 == 64
    assert rig.host.violations == [] or all(v.kind != "event-range" for v in rig.host.violations)


@pytest.mark.tuned_fix("F-05")
def test_a_range_checked_event_does_not_raise_on_pads(make_rig):
    rig = make_rig(on_violation="raise")
    fpc_selected(rig)
    a = rig.pad_on(36, 100)
    assert a.errors == [], [(e.callback, e.exc) for e in a.errors]


@pytest.mark.tuned_fix("F-06")
@pytest.mark.parametrize("note", [0, 20, 35, 52, 60, 127])
def test_drum_pads_outside_36_51_are_left_alone(rig, note):
    """FPC_MAP.get() is None for notes outside 36..51; event.data1 = None raised TypeError."""
    for fn in (rig.pad_on, rig.pad_off):
        a = fn(note, 90)
        assert a.errors == [], (note, [(e.callback, str(e.exc)) for e in a.errors])
        assert isinstance(a.event.data1, int)


@pytest.mark.tuned_fix("F-06")
@pytest.mark.parametrize("note", [0, 20, 35, 52, 60, 127])
def test_sequencer_pad_release_outside_36_51_does_not_raise(rig, note):
    enter_sequencer(rig)
    for fn in (rig.pad_on, rig.pad_off):
        a = fn(note, 90)
        assert a.errors == [], (note, [(e.callback, str(e.exc)) for e in a.errors])


@pytest.mark.tuned_fix("F-07")
@pytest.mark.parametrize("focus_window", [False, True], ids=["rack-focused", "plugin-window-focused"])
def test_pads_are_not_remapped_for_instruments_other_than_fpc(rig, focus_window):
    """The FPC layout remap was applied to every instrument, scrambling Sampler/Slicex/piano pads (mk3 gates it on
    the plugin name)."""
    sampler_selected(rig, focus_window)
    for pad in kl.PAD_NOTES:
        on = rig.pad_on(pad, 100)
        off = rig.pad_off(pad, 0)
        assert on.event.data1 == pad and off.event.data1 == pad, "pad %d became %d" % (pad, on.event.data1)


@pytest.mark.tuned_fix("F-04")
def test_a_pad_press_in_song_mode_does_not_leave_the_encoders_stuck_in_edit_mode(rig):
    """In song mode (getLoopMode() == 1) the pad release was ignored, so the held-pad state stayed set forever and
    every encoder kept editing step 0's pitch: encoder 9 no longer panned."""
    enter_sequencer(rig)
    rig.state.loop_mode = 1
    rig.pad_on(36)
    rig.pad_off(36)
    rig.state.loop_mode = 0
    a = rig.cc(24, 1)
    b = rig.cc(16, 1)
    assert a.called("mixer.setTrackPan"), "encoder 9 stuck: %s" % a.lines
    assert not a.calls_to("channels.setStepParameterByIndex") and not b.calls_to("channels.setStepParameterByIndex"), b.lines


@pytest.mark.tuned_fix("F-04")
def test_leaving_sequencer_mode_clears_held_pads(rig):
    enter_sequencer(rig)
    rig.pad_on(36)                                                             # released never arrives
    enter_sequencer(rig)                                                       # back to drum mode
    a = rig.cc(24, 1)
    assert a.called("mixer.setTrackPan") and not a.calls_to("channels.setStepParameterByIndex")


@pytest.mark.tuned_fix("F-11")
def test_step_pitch_encoder_turns_clockwise_to_raise_the_pitch(rig):
    """SeqParam.py:38 decremented the pitch for clockwise ticks (the other parameters increase)."""
    enter_sequencer(rig)
    base = rig.state.step_param(0, 1, 0, 0)
    rig.pad_on(36)
    up = rig.cc(16, 1)
    (c,) = [x for x in up.effects if x.qual == "channels.setStepParameterByIndex"]
    assert c.args[4] > base, "clockwise moved pitch %d -> %d" % (base, c.args[4])
    rig.state.step_params[(0, 1, 0, 0)] = base
    down = rig.cc(16, 65)
    (c,) = [x for x in down.effects if x.qual == "channels.setStepParameterByIndex"]
    assert c.args[4] < base


@pytest.mark.tuned_fix("F-11")
def test_step_parameters_stay_inside_their_documented_ranges(rig):
    """MOD Y was written as 2 * value (up to 254; documented range 0..127); pitch had no bounds."""
    enter_sequencer(rig)
    rig.pad_on(36)
    for enc in range(16, 23):
        for _ in range(70):
            rig.cc(enc, 1)
        for _ in range(140):
            rig.cc(enc, 65)
    bad = [v for v in rig.host.violations if v.kind == "value"]
    assert bad == [], bad[:2]


@pytest.mark.tuned_fix("F-11")
def test_step_parameter_edit_starts_from_the_steps_current_value(rig):
    """One global accumulator seeded at 64: the first velocity tick jumped a velocity-100 step to 67."""
    enter_sequencer(rig)
    rig.state.step_params[(0, 1, 0, 1)] = 100
    rig.pad_on(36)
    a = rig.cc(17, 1)
    (c,) = [x for x in a.effects if x.qual == "channels.setStepParameterByIndex"]
    assert abs(c.args[4] - 100) <= 10, "velocity 100 -> %d after one tick" % c.args[4]
