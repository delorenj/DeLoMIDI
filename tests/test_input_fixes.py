"""Fixes for documented input-side stock bugs that are not about pads/banking/the Forward script.

Each @tuned_fix test asserts the behaviour the finding asks for (docs/analysis/02-input-audit.md section 5)."""
from __future__ import annotations

import pytest

from tests import kl


def focused_plugin(rig, name):
    rig.state.select_channel_plugin(name)
    rig.state.focus(kl.WID_PLUGIN, name)


# ================================================================================================ characterization

def test_consumed_controls_stay_consumed_in_channel_rack_mode(rig):
    """Buttons, the jog, encoder 9 and fader 9 are handled by the script: FL must not also process them."""
    assert rig.button(kl.BTN_PLAY).handled is True
    assert rig.cc(60, 1).handled is True
    assert rig.cc(24, 1).handled is True
    assert rig.fader(8, 100).handled is True


# ================================================================================================ tuned fixes

@pytest.mark.tuned_fix("F-08")
@pytest.mark.parametrize("control", ["fader1", "fader5", "fader8", "master-fader", "enc1", "enc8", "master-enc"])
def test_mixer_mode_controls_are_consumed_after_they_are_applied(rig, control):
    """AKLmk2.SetVolumeTrack/SetPanTrack set event.handled = False after applying the change (and mutated the event
    into a CC-shaped body), so the same movement also went on to FL's default routing."""
    rig.tap(kl.BTN_MIXER_TOGGLE)
    kind, n = ("fader", int(control[5:]) - 1) if control.startswith("fader") else \
              ("fader", 8) if control == "master-fader" else \
              ("enc", int(control[3:]) - 1) if control.startswith("enc") else ("enc", 8)
    a = rig.fader(n, 90) if kind == "fader" else rig.cc(16 + n, 1)
    assert a.effects and a.handled is True


@pytest.mark.tuned_fix("F-08")
@pytest.mark.parametrize("plugin", ["FPC", "FLEX", "Sytrus"])
def test_mapped_plugin_controls_are_consumed_after_they_are_applied(rig, plugin):
    """Plugin() set handled = False after setting the parameter: a fader moved with FPC focused was applied to the
    plugin and continued as a pitch bend to the selected channel."""
    focused_plugin(rig, plugin)
    k = rig.cc(16, 1)
    f = rig.fader(0, 100)
    assert k.calls_to("plugins.setParamValue") and f.calls_to("plugins.setParamValue")
    assert k.handled is True and f.handled is True


@pytest.mark.tuned_fix("F-14")
def test_a_jog_tick_does_not_touch_every_channel_editor(make_rig):
    """_hideAll looped channels.showEditor(i, 0) over every channel on every jog tick (300 API calls at 300 channels)."""
    rig = make_rig()
    rig.state.resize_channels(300)
    a = rig.cc(60, 1)
    n = len(a.calls_to("channels.showEditor"))
    assert n <= 5, "%d channels.showEditor calls for one jog tick at 300 channels" % n


@pytest.mark.tuned_fix("F-16")
def test_unmapped_plugin_slots_are_not_queried_with_parameter_index_minus_one(rig):
    """Plugin() called plugins.getParamValue(-1, ...) for an unmapped slot before checking for -1."""
    focused_plugin(rig, "Fruit kick")
    for i in range(8):
        rig.cc(16 + i, 1)
        rig.fader(i, 100)
    bad = [v for v in rig.host.violations if v.kind == "param-index"]
    assert bad == [], bad[:2]


@pytest.mark.tuned_fix("F-21")
def test_previous_pattern_at_pattern_1_does_not_jump_to_pattern_0(rig):
    rig.state.pattern = 1
    a = rig.button(kl.BTN_PATTERN_PREV)
    assert all(c.args[0] >= 1 for c in a.calls_to("patterns.jumpToPattern")), a.lines
    assert [v for v in rig.host.violations if v.kind == "index"] == []
    assert rig.state.pattern >= 1


@pytest.mark.tuned_fix("F-23")
@pytest.mark.parametrize("note,speed", [(kl.BTN_REWIND, -1), (kl.BTN_FORWARD, 1)])
def test_scrubbing_stops_when_the_hardware_releases_with_a_note_off(rig, note, speed):
    """Release-driven handlers only understood note-on velocity 0; a note-off (0x80) release never stopped the
    scrub. The hardware's release message is UNVERIFIED (F-23), so both forms must work."""
    down = rig.midi(0x90, note, 127)
    assert down.called("transport.continuousMove", speed, 2)
    up = rig.midi(0x80, note, 0)
    assert up.called("transport.continuousMove", speed, 0), "note-off release did not stop the scrub"


@pytest.mark.tuned_fix("F-23")
@pytest.mark.parametrize("note,speed", [(kl.BTN_REWIND, -1), (kl.BTN_FORWARD, 1)])
def test_scrubbing_stops_even_if_the_sequencer_mode_was_toggled_while_the_button_was_held(rig, note, speed):
    """Press << in drum mode (scrub starts), toggle Save, release <<: the release was interpreted as a Sequencer-mode
    bar offset and the scrub was never stopped, so FL kept scrubbing until << was pressed again."""
    rig.button(note, True)
    rig.tap(kl.BTN_SEQ_TOGGLE)
    up = rig.button(note, False)
    assert up.called("transport.continuousMove", speed, 0), "scrub left running: %s" % up.lines


@pytest.mark.tuned_fix("F-12")
def test_mixer_mode_follows_the_window_the_user_focused_with_the_mouse(rig):
    """MIXER_MODE was tied to the Bank button, not to the focused window: after clicking the Channel Rack the faders
    still drove mixer tracks (Solo/Mute and the jog already followed the real focus)."""
    rig.tap(kl.BTN_MIXER_TOGGLE)
    assert rig.state.focused == kl.WID_MIXER
    rig.state.focus(kl.WID_CHANNEL_RACK)                                        # the user clicks the Channel Rack
    rig.refresh(32)                                                             # HW_Dirty_FocusedWindow
    a = rig.fader(8, 100)
    (c,) = [x for x in a.effects if x.qual == "mixer.setTrackVolume"]
    assert c.args[0] == rig.state.current_track, "fader 9 still drives the master track"
    b = rig.cc(24, 1)
    assert [x.args[0] for x in b.effects if x.qual == "mixer.setTrackPan"] == [rig.state.current_track]
