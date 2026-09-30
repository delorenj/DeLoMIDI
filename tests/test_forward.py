"""The Forward script (keyboard port): keybed, wheels, Analog Lab / V Collection forwarding.

Two hypotheses about OnMidiIn decide what the stock Forward script does (docs/analysis/02 section 3.3):
  H1  midiId/midiChan are populated in OnMidiIn  (Host.midi_in_populated = True)
  H2  they are 0 in OnMidiIn, as the FL manual implies ("only raw data is available here")
Every test that matters runs under both. Hardware/FL behaviour is UNVERIFIED (docs/analysis/02, F-01)."""
from __future__ import annotations

import pytest

from tests import kl

BOTH = pytest.mark.parametrize("populated", [True, False], ids=["H1-midiId-populated", "H2-midiId-zero"])

KEYBED = list(range(21, 109))
EFFECT_PREFIXES = ("ui.", "transport.", "patterns.", "mixer.", "channels.", "plugins.")


def _fwd(rig, status, d1, d2, populated):
    return rig.midi(status, d1, d2, role="forward", populated=populated)


# ================================================================================================ characterization

@BOTH
def test_keybed_notes_are_never_consumed(rig, populated):
    """The keybed must keep sounding: the Forward script leaves every note-on/off unhandled."""
    for note in KEYBED:
        for status, vel in ((0x90, 100), (0x80, 0)):
            a = _fwd(rig, status, note, vel, populated)
            assert a.handled is False, (hex(status), note, populated)
            assert (a.event.status, a.event.data1, a.event.data2) == (status, note, vel)


@BOTH
def test_keybed_note_offs_never_act(rig, populated):
    for note in KEYBED:
        a = _fwd(rig, 0x80, note, 0, populated)
        assert a.effects == [] and a.errors == [], (note, a.lines)


@BOTH
@pytest.mark.parametrize("plugin", kl.V_COL_SAMPLE)
def test_cc_is_forwarded_to_the_arturia_plugin_port_when_a_v_collection_plugin_is_focused(rig, populated, plugin):
    rig.state.select_channel_plugin(plugin)
    rig.state.focus(kl.WID_PLUGIN, plugin)
    for cc, val in ((74, 64), (71, 3), (1, 127), (16, 5)):
        rig.host.forwarded.clear()
        a = _fwd(rig, 0xB0, cc, val, populated)
        assert rig.host.forwarded == [(kl.forward_cc_message(0xB0, cc, val), 2)], (plugin, cc, populated)
        assert a.handled is False and a.errors == []
        assert not [c for c in a.effects if c.qual.startswith(EFFECT_PREFIXES)], a.lines   # not treated as a DAW control


@BOTH
def test_pitch_wheel_is_forwarded_to_the_arturia_plugin_port(rig, populated):
    rig.host.forwarded.clear()
    _fwd(rig, 0xE0, 0, 100, populated)
    assert rig.host.forwarded == [(kl.forward_cc_message(0xE0, 0, 100), 2)]


@BOTH
def test_pitch_wheel_bends_the_selected_channel(rig, populated):
    """Centre = no bend, up = positive, down = negative; the wheel event is consumed."""
    rig.state.selected_channel = 2
    up = _fwd(rig, 0xE0, 0, 127, populated)
    (c_up,) = [c for c in up.effects if c.qual == "channels.setChannelPitch"]
    down = _fwd(rig, 0xE0, 0, 0, populated)
    (c_dn,) = [c for c in down.effects if c.qual == "channels.setChannelPitch"]
    mid = _fwd(rig, 0xE0, 0, 64, populated)
    (c_mid,) = [c for c in mid.effects if c.qual == "channels.setChannelPitch"]
    assert c_up.args[0] == c_dn.args[0] == c_mid.args[0] == 2
    assert c_up.args[1] > 0 > c_dn.args[1] and c_mid.args[1] == 0
    assert up.handled is True and down.handled is True and mid.handled is True


@BOTH
def test_pitch_wheel_does_not_bend_a_v_collection_channel_but_is_still_consumed(rig, populated):
    rig.state.channel_names[0] = "Analog Lab V"
    a = _fwd(rig, 0xE0, 0, 127, populated)
    assert not a.calls_to("channels.setChannelPitch") and a.handled is True


@BOTH
def test_forward_events_do_not_raise_for_ordinary_input(rig, populated):
    for st, d1, d2 in ((0xD0, 50, 0), (0xA0, 60, 30), (0xC0, 3, 0), (0xF8, 0, 0), (0xB0, 7, 100), (0xB0, 64, 127)):
        a = _fwd(rig, st, d1, d2, populated)
        assert a.errors == [], (hex(st), d1, populated, [(e.callback, str(e.exc)) for e in a.errors])


# ================================================================================================ tuned fixes

H1_IS_THE_BUG = pytest.mark.parametrize("populated", [
    pytest.param(True, marks=pytest.mark.tuned_fix("F-01"), id="H1-midiId-populated"),
    pytest.param(False, id="H2-midiId-zero")])           # H2: the stock script does not act on any key either


@H1_IS_THE_BUG
def test_keybed_notes_never_trigger_transport_window_or_pattern_actions(rig, populated):
    """H1: 15 of the 88 keys (46, 47, 51, 56, 74, 84, 86, 87, 91-95, 98, 99) ran the DAW command table through
    Forward.OnMidiIn (play, record, pattern jump, ...) because keybed notes share their numbers with button ids."""
    acting = {}
    for note in KEYBED:
        a = _fwd(rig, 0x90, note, 100, populated)
        if [c for c in a.effects if c.qual.startswith(EFFECT_PREFIXES)]:
            acting[note] = a.lines[:2]
    assert acting == {}, "keys that act on FL: %s" % acting


@pytest.mark.tuned_fix("F-01")
def test_held_keybed_keys_never_leave_the_transport_scrubbing(rig):
    """Keys 91/92 started transport.continuousMove(+-1, start) and their release (a note-off) was never routed."""
    for note in (91, 92):
        rig.midi(0x90, note, 100, role="forward", populated=True)
        rig.midi(0x80, note, 0, role="forward", populated=True)
    started = [c for c in rig.host.calls if c.qual == "transport.continuousMove" and c.args[1] == 2]
    stopped = [c for c in rig.host.calls if c.qual == "transport.continuousMove" and c.args[1] == 0]
    assert len(started) == len(stopped)


@pytest.mark.parametrize("plugin", [
    pytest.param("", marks=pytest.mark.tuned_fix("F-02")), pytest.param("FLEX", marks=pytest.mark.tuned_fix("F-02")),
    pytest.param("FPC", marks=pytest.mark.tuned_fix("F-02")), pytest.param("Sampler", marks=pytest.mark.tuned_fix("F-02")),
    "Analog Lab V"])                                      # a V Collection plugin: CCs are forwarded, never dispatched
def test_analog_lab_ccs_never_raise_on_the_keyboard_port(rig, plugin):
    """The 17 Analog Lab CCs were registered with a handler taking (event, clef) but dispatched with (event):
    TypeError, and the CC was left consumed. Reachable through the keyboard port under H2."""
    if plugin:
        rig.state.select_channel_plugin(plugin)
        rig.state.focus(kl.WID_PLUGIN, plugin)
    for cc in (74, 71, 76, 77, 93, 18, 19, 16, 73, 75, 79, 72, 80, 81, 82, 83, 17, 1, 28, 29):
        for val in (1, 64, 65, 127):
            for populated in (True, False):
                a = _fwd(rig, 0xB0, cc, val, populated)
                assert a.errors == [], (plugin, cc, val, populated, [(e.callback, str(e.exc)) for e in a.errors])


@pytest.mark.tuned_fix("F-02")
def test_mod_wheel_never_reaches_a_mixer_track_pan_with_a_negative_index(rig):
    """H2 + mixer mode: CC1 -> SetPanTrack -> track = (1 - 15) + 8*offset = -14 -> mixer.getTrackPan(-14)."""
    rig.tap(kl.BTN_MIXER_TOGGLE)
    rig.host.violations.clear()
    for populated in (True, False):
        _fwd(rig, 0xB0, 1, 64, populated)
    assert [v for v in rig.host.violations if v.kind == "index"] == []
