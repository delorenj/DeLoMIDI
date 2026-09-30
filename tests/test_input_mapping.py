"""Every documented input mapping: what each control of the KeyLab mkII makes the scripts do in FL.

Sources: docs/analysis/02-input-audit.md section 4 (code-derived mapping table, hardware names from the guide) and
01-official-guide.md section 2 (the Arturia guide's control map). The contract the scripts assume (button = note-on
ch1 velocity 127/0, encoders = CC16..24, jog = CC60, faders = pitch bend ch1..9) is UNVERIFIED on the hardware
(F-03); these tests pin what the scripts do *given* that contract.

Characterization tests only: everything here is correct behaviour that the tuned scripts must preserve. The fixed
behaviour of documented bugs lives in test_pads.py / test_banking.py / test_forward.py / test_plugin_db.py."""
from __future__ import annotations

import pytest

from tests import kl

# ---------------------------------------------------------------------------------------------------------------
# guide labels (01-official-guide.md 2.1-2.8): each must have a row below
GUIDE_FUNCTIONS = {
    "Solo", "Mute", "Snap (Record)", "Tap Tempo (Read)", "Cut (Off)", "Drum/Sequencer (Save)", "Browser (In)",
    "Overdub (Out)", "Metro (Marker)", "Undo", "Loop", "Rewind (<<)", "Fast forward (>>)", "Stop", "Play/Pause", "Record",
    "Next", "Previous", "Select 1-8", "Bank/Mixer toggle", "Jog push", "Pattern previous", "Pattern next",
}

# note -> (guide label, when it fires, expectation)
#   press/release = the phase that fires; the other phase must not act.
#   expect = list of (qualified name, *leading args) that must appear among the effects
BUTTON_ROWS = [
    ("Snap (Record)", list(kl.BTN_SNAP), "press", [("ui.snapMode", 1)], {}),
    ("Solo", list(kl.BTN_SOLO), "release", [("channels.soloChannel", 0)], {}),
    ("Solo", list(kl.BTN_SOLO), "release", [("mixer.soloTrack", 1)], {"focus": kl.WID_MIXER}),
    ("Mute", list(kl.BTN_MUTE), "release", [("channels.muteChannel", 0)], {}),
    ("Mute", list(kl.BTN_MUTE), "release", [("mixer.muteTrack", 1)], {"focus": kl.WID_MIXER}),
    ("Tap Tempo (Read)", [kl.BTN_TAP_TEMPO], "press", [("transport.globalTransport", "FPT_TapTempo", 1)], {}),
    ("Cut (Off)", [kl.BTN_CUT], "release", [("ui.cut",)], {}),
    ("Undo", [kl.BTN_UNDO], "release", [("transport.globalTransport", "FPT_Undo")], {}),
    ("Loop", [kl.BTN_LOOP], "press", [("transport.globalTransport", "FPT_LoopRecord", 1)], {}),
    ("Overdub (Out)", [kl.BTN_OVERDUB], "release", [("transport.globalTransport", "FPT_Overdub", 1)], {}),
    ("Metro (Marker)", [kl.BTN_METRO], "release", [("transport.globalTransport", "FPT_Metronome", 1)], {}),
    ("Stop", [kl.BTN_STOP], "press", [("transport.stop",)], {}),
    ("Play/Pause", [kl.BTN_PLAY], "press", [("transport.start",)], {}),
    ("Record", [kl.BTN_RECORD], "press", [("transport.record",)], {}),
    ("Browser (In)", [kl.BTN_BROWSER], "press", [("ui.setFocused", kl.WID_BROWSER)], {}),
    ("Browser (In)", [kl.BTN_BROWSER], "press", [("ui.setFocused", kl.WID_CHANNEL_RACK)], {"focus": kl.WID_BROWSER}),
    ("Bank/Mixer toggle", [kl.BTN_MIXER_TOGGLE], "press", [("ui.setFocused", kl.WID_MIXER)], {}),
    ("Bank/Mixer toggle", [kl.BTN_MIXER_TOGGLE], "press", [("ui.setFocused", kl.WID_CHANNEL_RACK)], {"mixer_mode": True}),
    ("Jog push", [kl.BTN_JOG_PUSH], "press", [("channels.showEditor", 0)], {}),
    ("Jog push", [kl.BTN_JOG_PUSH], "press", [("mixer.armTrack", 1)], {"focus": kl.WID_MIXER}),
    ("Jog push", [kl.BTN_JOG_PUSH], "press", [("transport.globalTransport", "FPT_Enter", 1)],
     {"focus": kl.WID_BROWSER, "node": -100}),
    ("Jog push", [kl.BTN_JOG_PUSH], "press", [("ui.selectBrowserMenuItem",)], {"focus": kl.WID_BROWSER, "node": 0}),
    ("Pattern previous", [kl.BTN_PATTERN_PREV], "press", [("patterns.jumpToPattern", 1)], {"pattern": 2}),
    ("Pattern next", [kl.BTN_PATTERN_NEXT], "press", [("patterns.jumpToPattern", 3)], {"pattern": 2}),
    ("Pattern previous", [kl.BTN_PATTERN_PREV], "press", [("plugins.prevPreset", 0)], {"plugin": "FPC"}),
    ("Pattern next", [kl.BTN_PATTERN_NEXT], "press", [("plugins.nextPreset", 0)], {"plugin": "FPC"}),
]


def _setup(rig, opts):
    st = rig.state
    if "focus" in opts:
        st.focus(opts["focus"])
    if "node" in opts:
        st.node_file_type = opts["node"]
    if "pattern" in opts:
        st.pattern = opts["pattern"]
    if "plugin" in opts:
        st.select_channel_plugin(opts["plugin"])
        st.focus(kl.WID_PLUGIN, opts["plugin"])
    if opts.get("mixer_mode"):
        rig.button(kl.BTN_MIXER_TOGGLE)
        rig.button(kl.BTN_MIXER_TOGGLE, False)


def _resolve(rig, expect):
    """Turn ('transport.globalTransport', 'FPT_Metronome', 1) into real args using the real midi.py."""
    midi = rig.host.modules["midi"]
    return [(e[0],) + tuple(getattr(midi, a) if isinstance(a, str) else a for a in e[1:]) for e in expect]


def _id(row):
    label, notes, when, expect, opts = row
    return "%s-%s-%s" % (label.split(" ")[0].lower(), when, ",".join("%s=%s" % kv for kv in opts.items()) or "default")


@pytest.mark.parametrize("row", BUTTON_ROWS, ids=_id)
def test_button_fires_on_its_documented_phase_only(rig, row):
    label, notes, when, expect, opts = row
    for note in notes:
        rig.host.clear_trace()
        _setup(rig, opts)
        rig.host.clear_trace()
        first = rig.button(note, pressed=(when == "press"))
        for q, *args in _resolve(rig, expect):
            assert first.called(q, *args), "%s (note %d) %s: expected %s%s, got %s" % (label, note, when, q, tuple(args), first.lines)
        assert first.handled is True and first.errors == [], (label, note)
        if when == "press":                          # release is ignored (or only stops what press started)
            second = rig.button(note, pressed=False)
            assert second.effects == [], "%s (note %d): release must not act, got %s" % (label, note, second.lines)
        else:                                        # a bare press does nothing for release-driven buttons
            rig.host.clear_trace()
            _setup(rig, opts)
            pre = rig.button(note, pressed=True)
            assert pre.effects == [], "%s (note %d): press must not act, got %s" % (label, note, pre.lines)


def test_every_guide_function_has_a_mapping_row():
    covered = {r[0] for r in BUTTON_ROWS} | {"Rewind (<<)", "Fast forward (>>)", "Next", "Previous", "Select 1-8",
                                             "Drum/Sequencer (Save)"}
    assert GUIDE_FUNCTIONS <= covered, sorted(GUIDE_FUNCTIONS - covered)


@pytest.mark.parametrize("note,cm,speed", [(kl.BTN_REWIND, "rewind", -1), (kl.BTN_FORWARD, "fast-forward", 1)])
def test_rewind_and_fast_forward_scrub_while_held(rig, note, cm, speed):
    down = rig.button(note, True)
    up = rig.button(note, False)
    assert down.called("transport.continuousMove", speed, 2)                  # SS_START
    assert up.called("transport.continuousMove", speed, 0)                    # SS_STOP
    assert down.handled is True and up.handled is True


def test_sequencer_mode_repurposes_rewind_and_forward_as_step_window_offset(rig):
    rig.tap(kl.BTN_SEQ_TOGGLE)
    a = rig.button(kl.BTN_FORWARD, True)
    assert a.called("ui.crDisplayRect", 16) and not a.calls_to("transport.continuousMove")
    b = rig.button(kl.BTN_REWIND, True)
    assert b.called("ui.crDisplayRect", 0) and not b.calls_to("transport.continuousMove")
    c = rig.button(kl.BTN_REWIND, True)                                        # never below the first bar
    assert c.called("ui.crDisplayRect", 0)


def test_next_and_previous_page_the_select_buttons_by_eight_channels(rig):
    rig.state.resize_channels(20)
    assert rig.button(kl.BTN_SELECT[0], False).called("channels.selectOneChannel", 0)
    rig.button(kl.BTN_NEXT)
    rig.button(kl.BTN_NEXT, False)
    assert rig.button(kl.BTN_SELECT[0], False).called("channels.selectOneChannel", 8)
    assert rig.button(kl.BTN_SELECT[3], False).called("channels.selectOneChannel", 11)
    rig.button(kl.BTN_NEXT)
    rig.button(kl.BTN_NEXT)                                                    # already on the last page (16..19)
    assert rig.button(kl.BTN_SELECT[0], False).called("channels.selectOneChannel", 16)
    assert not rig.button(kl.BTN_SELECT[5], False).calls_to("channels.selectOneChannel")    # 21st channel: none
    for _ in range(5):
        rig.button(kl.BTN_PREV)
    assert rig.button(kl.BTN_SELECT[0], False).called("channels.selectOneChannel", 0)       # clamps at the first page


def test_select_buttons_pick_the_channel_and_follow_its_mixer_track(rig):
    a = rig.button(kl.BTN_SELECT[2], False)
    assert a.called("channels.selectOneChannel", 2) and a.called("mixer.setTrackNumber", 3, 3)
    assert a.called("ui.setFocused", kl.WID_CHANNEL_RACK)
    assert rig.state.selected_channel == 2 and rig.state.current_track == 3
    assert rig.button(kl.BTN_SELECT[2], True).effects == []                    # fires on release only


def test_select_buttons_beyond_the_channel_count_do_nothing(rig):
    rig.state.resize_channels(5)
    assert rig.button(kl.BTN_SELECT[6], False).calls_to("channels.selectOneChannel") == []


def test_mixer_mode_select_buttons_pick_tracks_and_banks_shift_by_eight(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    a = rig.button(kl.BTN_SELECT[0], False)
    assert a.called("mixer.setTrackNumber", 1, 3)                              # slot 1 of bank 0 = track 1
    rig.tap(kl.BTN_NEXT)
    assert rig.button(kl.BTN_SELECT[2], False).called("mixer.setTrackNumber", 11, 3)
    rig.tap(kl.BTN_PREV)
    assert rig.button(kl.BTN_SELECT[2], False).called("mixer.setTrackNumber", 3, 3)


UNMAPPED_NOTES = [n for n in (32, 33, 34, 35, 36, 40, 55, 60, 75, 76, 80, 82, 83, 85, 96, 97, 100, 101, 104, 108, 112, 127)]


@pytest.mark.parametrize("note", UNMAPPED_NOTES)
def test_unmapped_button_ids_make_no_fl_call(rig, note):
    for pressed in (True, False):
        a = rig.button(note, pressed)
        assert a.effects == [] and a.errors == [], (note, pressed, a.lines)


# ---------------------------------------------------------------------------------------------------------------
# jog wheel (CC60): +1 = clockwise, 65 = counter-clockwise (only exactly these values are acted upon)

JOG_ROWS = [
    # (id, setup, cw expectation, ccw expectation)
    ("channel-rack", {}, ("ui.next", ), ("ui.previous", )),
    ("mixer", {"focus": kl.WID_MIXER}, ("ui.next", ), ("ui.previous", )),
    ("browser", {"focus": kl.WID_BROWSER}, ("ui.next", ), ("ui.previous", )),
    ("browser-popup", {"focus": kl.WID_BROWSER, "popup": True}, ("ui.down", ), ("ui.up", )),
]


@pytest.mark.parametrize("row", JOG_ROWS, ids=[r[0] for r in JOG_ROWS])
def test_jog_wheel_navigates_the_focused_window(rig, row):
    _, opts, cw, ccw = row
    if "focus" in opts:
        rig.state.focus(opts["focus"])
    rig.state.in_popup_menu = opts.get("popup", False)
    a = rig.cc(60, 1)
    b = rig.cc(60, 65)
    assert a.called(*cw), a.lines
    assert b.called(*ccw), b.lines
    assert a.handled is True and b.handled is True


def test_jog_wheel_in_the_channel_rack_selects_channels_and_their_mixer_track(rig):
    a = rig.cc(60, 1)
    assert rig.state.selected_channel == 1 and a.called("mixer.setTrackNumber", 2, 3)
    rig.cc(60, 65)
    assert rig.state.selected_channel == 0


def test_jog_wheel_over_a_plugin_window_returns_to_the_channel_rack(rig):
    rig.state.select_channel_plugin("Sytrus")
    rig.state.focus(kl.WID_PLUGIN, "Sytrus")
    rig.cc(60, 1)
    assert rig.state.focused == kl.WID_CHANNEL_RACK and not rig.state.open_editors


# ---------------------------------------------------------------------------------------------------------------
# encoders (CC16..24, relative: 1..63 clockwise, 65..127 counter-clockwise) and faders (pitch bend ch1..9)

def _approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_encoder_9_pans_the_selected_mixer_track_in_channel_rack_mode(rig):
    rig.state.current_track = 4
    cw = rig.cc(24, 1)
    (c,) = [x for x in cw.effects if x.qual == "mixer.setTrackPan"]
    assert c.args[0] == 4 and c.args[1] > 0
    ccw = rig.cc(24, 65)
    (c,) = [x for x in ccw.effects if x.qual == "mixer.setTrackPan"]
    assert c.args[0] == 4 and c.args[1] < 0.06                                 # moved back towards the centre
    assert rig.state.track_pan[4] == pytest.approx(0.0)


def test_fader_9_sets_the_selected_track_volume_in_channel_rack_mode(rig):
    rig.state.current_track = 6
    a = rig.fader(8, 127)
    (c,) = [x for x in a.effects if x.qual == "mixer.setTrackVolume"]
    assert c.args[0] == 6 and _approx(c.args[1], 0.8)                          # full fader = 0 dB = 0.8
    b = rig.fader(8, 0)
    assert rig.state.track_volume[6] == 0.0 and b.errors == []
    rig.fader(8, 64)
    assert rig.state.track_volume[6] == pytest.approx(0.8 * 64 / 127)


def test_faders_and_encoders_1_to_8_need_a_focused_plugin_in_channel_rack_mode(rig):
    for i in range(8):
        for a in (rig.fader(i, 90), rig.cc(16 + i, 1)):
            assert not [c for c in a.effects if c.qual.startswith(("mixer.", "plugins."))], a.lines
    rig.idle(0.1)
    assert rig.host.device_model().lcd == ("No Plugin", "Focused")


def test_mixer_mode_faders_set_the_volume_of_the_banked_tracks(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    for i in range(8):
        a = rig.fader(i, 100)
        (c,) = [x for x in a.effects if x.qual == "mixer.setTrackVolume"]
        assert c.args[0] == 1 + i and _approx(c.args[1], 0.8 * 100 / 127), (i, a.lines)
    a = rig.fader(8, 100)
    assert [c.args[0] for c in a.effects if c.qual == "mixer.setTrackVolume"] == [0]          # master
    rig.tap(kl.BTN_NEXT)
    a = rig.fader(0, 100)
    assert [c.args[0] for c in a.effects if c.qual == "mixer.setTrackVolume"] == [9]          # second bank


def test_mixer_mode_encoders_pan_the_banked_tracks_and_encoder_9_the_master(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    for i in range(8):
        a = rig.cc(16 + i, 1)
        (c,) = [x for x in a.effects if x.qual == "mixer.setTrackPan"]
        assert c.args[0] == 1 + i and c.args[1] > 0, (i, a.lines)
        b = rig.cc(16 + i, 65)
        (c,) = [x for x in b.effects if x.qual == "mixer.setTrackPan"]
        assert c.args[0] == 1 + i and c.args[1] < 0.06
    a = rig.cc(24, 1)
    assert [c.args[0] for c in a.effects if c.qual == "mixer.setTrackPan"] == [0]


def test_mixer_mode_lcd_shows_the_track_and_the_level(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    rig.fader(2, 127)
    rig.idle(0.1)
    assert rig.host.device_model().lcd == ("Volume - 3", "80%")
    rig.cc(19, 1)
    rig.idle(0.1)
    assert rig.host.device_model().lcd[0] == "Pan - 4"


def test_transport_buttons_show_feedback_on_the_lcd_and_the_main_page_returns(rig):
    rig.settle(3.0)
    rig.tap(kl.BTN_STOP)
    rig.idle(0.1)
    assert rig.host.device_model().lcd == ("Stop", "")
    rig.settle(3.0)
    assert rig.host.device_model().lcd == ("1 - Kick", "Pattern 1")          # the ephemeral page expires after 1 s


# ---------------------------------------------------------------------------------------------------------------
# events the scripts must leave alone

@pytest.mark.parametrize("status,d1,d2", [(0xF8, 0, 0), (0xFE, 0, 0), (0xC0, 5, 0), (0xD0, 50, 0), (0xA0, 60, 50)])
def test_channel_and_system_messages_pass_through_untouched(rig, status, d1, d2):
    a = rig.midi(status, d1, d2)
    assert a.effects == [] and a.errors == [] and a.handled is False
    assert (a.event.status, a.event.data1, a.event.data2) == (status, d1, d2)


def test_non_note_on_status_bytes_on_other_channels_are_ignored(rig):
    for st in (0x91, 0x9F, 0xB1, 0xBF):
        a = rig.midi(st, 94, 127)
        assert a.effects == [] and a.errors == [], hex(st)
