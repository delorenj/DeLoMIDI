"""The Forward (keyboard-port) script after the input-side fixes: F-01, F-02, F-05..F-07, F-10, F-15, F-17.

Default path = raw status/data1/data2 filtering and forwarding in OnMidiIn; the DAW command processor on this port is
opt-in (KLTConfig.FORWARD_USE_PROCESSOR) and runs from OnMidiMsg. Every scenario runs under H1 (midiId populated in
OnMidiIn) and H2 (it reads 0), because that is exactly what is unverified (docs/analysis/02 3.3).

test_forward.py holds the original characterization of the keybed/wheel/Analog-Lab behaviour; this file adds the new
paths and the switches."""
from __future__ import annotations

import pytest

from tests import kl
from tests.test_input_helpers import focus_plugin, fresh_second, fwd, log_lines, module, set_params, tuned_only

BOTH = pytest.mark.parametrize("populated", [True, False], ids=["H1-midiId-populated", "H2-midiId-zero"])
H2 = [False]

ANALOG_LAB_CCS = (74, 71, 76, 77, 93, 18, 19, 16, 73, 75, 79, 72, 80, 81, 82, 83, 17)


# ================================================================================================ keybed traffic

@pytest.mark.tuned_fix("F-15")
@BOTH
def test_keybed_traffic_makes_no_fl_call_at_all(rig, populated):
    """Stock asked FL for the focused plugin's name and scanned 32 names on every note/aftertouch event."""
    for status, d1, d2 in ((0x90, 60, 100), (0x80, 60, 0), (0xA0, 60, 30), (0xD0, 40, 0), (0xC0, 3, 0), (0xF8, 0, 0)):
        a = fwd(rig, status, d1, d2, populated)
        assert a.calls == [], (hex(status), populated, [c.short() for c in a.calls])
        assert a.handled is False and (a.event.status, a.event.data1, a.event.data2) == (status, d1, d2)


@pytest.mark.parametrize("populated", [
    pytest.param(True, marks=pytest.mark.tuned_fix("F-01"), id="H1-midiId-populated"),
    pytest.param(False, id="H2-midiId-zero")])
def test_a_keybed_note_shared_with_a_button_id_never_acts(rig, populated):
    for note in (46, 47, 51, 56, 74, 84, 86, 87, 91, 92, 93, 94, 95, 98, 99):
        a = fwd(rig, 0x90, note, 100, populated)
        assert a.effects == [] and a.handled is False, (note, populated)


# ================================================================================================ F-17 lifecycle

def test_loading_and_initialising_the_forward_script_makes_no_fl_call(make_rig):
    rig = make_rig(boot=False)
    assert rig.host.calls == [], "import time: %s" % [c.short() for c in rig.host.calls[:3]]
    a = rig.capture(lambda: rig.forward.call("OnInit"))
    assert a.calls == [] and a.errors == []


@pytest.mark.tuned_fix("F-17")
def test_the_forward_oninit_does_not_replace_the_daw_scripts_objects(make_rig):
    rig = make_rig(boot=False)
    rig.entry.call("OnInit")
    mk2, proc = rig.entry.module._mk2, rig.entry.module._processor
    rig.forward.call("OnInit")
    assert rig.entry.module._mk2 is mk2 and rig.entry.module._processor is proc


# ================================================================================================ pads on the keyboard port

@pytest.mark.tuned_fix("F-05")
@BOTH
def test_pads_on_the_keyboard_port_keep_their_velocity_and_get_the_fpc_layout_for_fpc(rig, populated):
    rig.state.select_channel_plugin("FPC")
    for pad, fpc_note in ((36, 49), (37, 55), (51, 54)):
        on = fwd(rig, 0x99, pad, 100, populated)
        off = fwd(rig, 0x89, pad, 64, populated)
        assert (on.event.data1, on.event.data2, on.handled) == (fpc_note, 100, False), (pad, populated)
        assert (off.event.data1, off.event.data2, off.handled) == (fpc_note, 64, False)
        assert on.errors == [] and off.errors == []


@pytest.mark.tuned_fix("F-07")
@BOTH
def test_pads_on_the_keyboard_port_are_not_remapped_for_other_instruments(rig, populated):
    rig.state.select_channel_plugin("Sampler")
    assert fwd(rig, 0x99, 36, 100, populated).event.data1 == 36
    assert fwd(rig, 0x89, 36, 0, populated).event.data1 == 36


@pytest.mark.tuned_fix("F-01")
@BOTH
def test_a_pad_on_the_keyboard_port_in_sequencer_mode_is_a_step_button_and_never_plays_a_note(rig, populated):
    """Stock's Forward script reset handled to False after the pad logic had consumed the pad: the pad toggled a step
    AND played the selected channel's instrument."""
    rig.tap(kl.BTN_SEQ_TOGGLE)                                                  # Save, on the DAW port
    press = fwd(rig, 0x99, 36, 100, populated)
    release = fwd(rig, 0x89, 36, 0, populated)
    assert press.handled is True and release.handled is True
    assert release.called("channels.setGridBit", 0, 0, 1), release.lines


def test_pads_on_the_keyboard_port_can_be_left_alone(rig, target):
    tuned_only(target)
    rig.host.set_config(FORWARD_PADS=False)
    rig.state.select_channel_plugin("FPC")
    a = fwd(rig, 0x99, 36, 100)
    assert a.calls == [] and a.event.data1 == 36 and a.handled is False


# ================================================================================================ CC28/29, mod wheel, Analog Lab CCs

H1_IS_THE_BUG = pytest.mark.parametrize("populated", [
    pytest.param(True, marks=pytest.mark.tuned_fix("F-01"), id="H1-midiId-populated"),
    pytest.param(False, id="H2-midiId-zero")])


@H1_IS_THE_BUG
@pytest.mark.parametrize("cc,expected", [(28, "plugins.prevPreset"), (29, "plugins.nextPreset")])
def test_the_preset_buttons_step_the_focused_plugins_preset_on_press_only(rig, populated, cc, expected):
    focus_plugin(rig, "FPC")
    a = fwd(rig, 0xB0, cc, 127, populated)
    assert a.called(expected, 0) and a.errors == [] and a.handled is False
    assert fwd(rig, 0xB0, cc, 0, populated).effects == []                        # release
    rig.state.focus(kl.WID_CHANNEL_RACK)
    assert fwd(rig, 0xB0, cc, 127, populated).effects == []                      # no plugin window focused


@pytest.mark.tuned_fix("F-10")
@pytest.mark.parametrize("populated", H2)
def test_the_mod_wheel_drives_its_database_parameter_absolutely(rig, populated):
    """Stock treated the mod wheel's value as a relative tick count (added 2*data2 to the live value)."""
    focus_plugin(rig, "MiniSynth")                                              # database: CC1 -> parameter 1
    rig.state.param_values[(0, 1)] = 0.2
    for value in (0, 40, 100, 127):
        a = fwd(rig, 0xB0, 1, value, populated)
        assert set_params(a) == [(1, round(value / 127, 4))], (value, a.lines)
        assert a.handled is False, "the mod wheel must still reach the instrument"


@pytest.mark.parametrize("plugin", ["FPC", "FLEX", "Sampler"])
def test_the_mod_wheel_does_nothing_without_a_database_row(rig, plugin):
    focus_plugin(rig, plugin)
    a = fwd(rig, 0xB0, 1, 90)
    assert a.effects == [] and a.errors == []


def test_the_mod_wheel_is_left_alone_in_mixer_mode_and_while_editing_a_step(rig):
    focus_plugin(rig, "MiniSynth")
    rig.tap(kl.BTN_MIXER_TOGGLE)
    assert fwd(rig, 0xB0, 1, 90).effects == []
    rig.tap(kl.BTN_MIXER_TOGGLE)
    focus_plugin(rig, "MiniSynth")
    assert fwd(rig, 0xB0, 1, 90).effects != []


def test_the_plugin_ccs_can_be_switched_off(rig, target):
    tuned_only(target)
    rig.host.set_config(FORWARD_PLUGIN_CCS=False)
    focus_plugin(rig, "MiniSynth")
    for cc in (1, 28, 29):
        assert fwd(rig, 0xB0, cc, 100).effects == []


@pytest.mark.tuned_fix("F-02")
@pytest.mark.parametrize("plugin", ["FLEX", "FPC", "Sytrus"])
@pytest.mark.parametrize("cc", ANALOG_LAB_CCS)
def test_analog_lab_ccs_reach_fl_unchanged_while_a_native_plugin_is_focused(rig, plugin, cc):
    """Stock: TypeError (handler called without its `clef`), the CC left consumed. Default now: unmapped = passed on."""
    focus_plugin(rig, plugin)
    for populated in (True, False):
        a = fwd(rig, 0xB0, cc, 64, populated)
        assert a.errors == [] and a.handled is False and a.effects == [], (plugin, cc, populated, a.lines)


def test_analog_lab_ccs_are_logged_as_unmapped_on_the_keyboard_port(rig, target):
    tuned_only(target)
    fresh_second(rig)
    focus_plugin(rig, "FLEX")
    fwd(rig, 0xB0, 74, 64)
    assert any("UNMAPPED forward-cc port=1 cc st=0xB0 d1=74" in l for l in log_lines(rig, "UNMAPPED"))


@pytest.mark.parametrize("cc,param", [(74, 21), (71, 22), (76, 25), (77, 30), (93, 0), (18, 2), (19, 3), (16, 4),
                                      (73, 10), (75, 11), (79, 12), (72, 13), (80, 14), (81, 15), (82, 16), (83, 17)])
def test_analog_lab_ccs_can_drive_the_plugin_database_absolutely(rig, target, cc, param):
    """Opt-in guess (KLTConfig.ANALOG_LAB_CC_TO_PLUGIN_DB): knob i -> encoder i, fader j -> fader j. FLEX rows."""
    tuned_only(target)
    rig.host.set_config(ANALOG_LAB_CC_TO_PLUGIN_DB=True)
    focus_plugin(rig, "FLEX")
    rig.state.param_values[(0, param)] = 0.9
    a = fwd(rig, 0xB0, cc, 32)
    assert set_params(a) == [(param, round(32 / 127, 4))], a.lines            # absolute, not a tick count
    assert a.handled is False and a.errors == []


def test_the_ninth_analog_lab_fader_and_unknown_ccs_map_to_nothing_even_when_translating(rig, target):
    tuned_only(target)
    rig.host.set_config(ANALOG_LAB_CC_TO_PLUGIN_DB=True)
    focus_plugin(rig, "FLEX")
    for cc in (17, 7, 64, 2):
        assert fwd(rig, 0xB0, cc, 50).effects == []


@BOTH
@pytest.mark.parametrize("plugin", kl.V_COL_SAMPLE)
def test_an_arturia_plugin_gets_the_ccs_forwarded_and_never_the_database(rig, target, populated, plugin):
    focus_plugin(rig, plugin)
    if not target.is_stock:
        rig.host.set_config(ANALOG_LAB_CC_TO_PLUGIN_DB=True)
    for cc in (1, 28, 74):
        rig.host.forwarded.clear()
        a = fwd(rig, 0xB0, cc, 77, populated)
        assert rig.host.forwarded == [(kl.forward_cc_message(0xB0, cc, 77), 2)]
        assert [c.qual for c in a.effects] == ["device.forwardMIDICC"], a.lines


def test_the_forward_target_port_and_mode_are_switches(rig, target):
    tuned_only(target)
    rig.host.set_config(FORWARD_TARGET_PORT=11, FORWARD_MODE=1)
    focus_plugin(rig, "Analog Lab V")
    rig.host.forwarded.clear()
    fwd(rig, 0xB0, 74, 5)
    assert rig.host.forwarded == [(0xB0 + (74 << 8) + (5 << 16) + (11 << 24), 1)]


# ================================================================================================ the processor path (opt-in)

def test_the_processor_path_is_off_by_default(rig, target):
    tuned_only(target)
    import KLTConfig
    assert KLTConfig.FORWARD_USE_PROCESSOR is False
    a = fwd(rig, 0xB0, 60, 1)
    assert a.effects == [] and a.handled is False, "the jog on the keyboard port is not ours unless asked for"


def test_the_processor_path_runs_channel_one_ccs_from_onmidimsg_and_consumes_them(rig, target):
    tuned_only(target)
    rig.host.set_config(FORWARD_USE_PROCESSOR=True)
    for populated in (True, False):
        a = fwd(rig, 0xB0, 60, 1, populated)
        assert a.called("ui.next") and a.handled is True, (populated, a.lines)
        assert [s for s, _ in a.delivery.stages] == ["OnMidiIn", "OnMidiMsg"]


def test_the_processor_path_never_turns_keybed_notes_into_buttons_by_default(rig, target):
    tuned_only(target)
    rig.host.set_config(FORWARD_USE_PROCESSOR=True)
    for note in (46, 47, 51, 74, 91, 93, 94, 95, 98, 99):
        for populated in (True, False):
            a = fwd(rig, 0x90, note, 100, populated)
            assert a.effects == [] and a.handled is False, (note, populated)


def test_the_processor_path_can_be_told_to_take_notes_too_which_is_the_h1_footgun(rig, target):
    tuned_only(target)
    rig.host.set_config(FORWARD_USE_PROCESSOR=True, FORWARD_PROCESSOR_KINDS=("cc", "note"))
    a = fwd(rig, 0x90, 94, 127)
    assert a.called("transport.start") and a.handled is True
    fwd(rig, 0x90, 91, 127)
    up = fwd(rig, 0x80, 91, 0)
    assert up.called("transport.continuousMove", -1, 0), "a note-off releases the scrub it started"


def test_a_pad_is_processed_once_when_the_processor_path_is_on(rig, target):
    """FPC layout twice would undo itself (36 -> 49 -> 36)."""
    tuned_only(target)
    rig.host.set_config(FORWARD_USE_PROCESSOR=True, FORWARD_PROCESSOR_KINDS=("cc", "note", "bend"))
    rig.state.select_channel_plugin("FPC")
    assert fwd(rig, 0x99, 36, 100).event.data1 == 49


def test_the_processor_path_before_the_daw_script_is_initialised_skips_and_logs_once(make_rig, target):
    tuned_only(target)
    rig = make_rig(boot=False)
    fresh_second(rig)
    rig.host.set_config(FORWARD_USE_PROCESSOR=True)
    for _ in range(3):
        a = rig.midi(0xB0, 60, 1, role="forward")
        assert a.errors == [] and a.effects == [] and a.handled is False
    assert len(log_lines(rig, "has not created its processor yet")) == 1


# ================================================================================================ pitch wheel (F-15)

def bend(rig, lsb, msb, populated=False):
    a = fwd(rig, 0xE0, lsb, msb, populated)
    (c,) = [c for c in a.effects if c.qual == "channels.setChannelPitch"]
    return a, c


@pytest.mark.tuned_fix("F-15")
@BOTH
def test_the_pitch_wheel_uses_all_fourteen_bits_as_a_fraction_of_the_channels_range(rig, populated):
    rig.state.selected_channel = 2
    _, centre = bend(rig, 0, 64, populated)
    _, one_lsb_up = bend(rig, 1, 64, populated)
    _, top = bend(rig, 127, 127, populated)
    _, bottom = bend(rig, 0, 0, populated)
    assert centre.args[:3] == (2, 0.0, 0)
    assert one_lsb_up.args[1] == pytest.approx(1 / 8192) and one_lsb_up.args[1] > centre.args[1], "the LSB counts"
    assert top.args[1] == pytest.approx(8191 / 8192) and bottom.args[1] == -1.0
    assert top.args[2] == 0, "mode 0: a factor of the channel's own pitch range (stock: fixed +-200 cents)"


@BOTH
def test_the_pitch_wheel_is_still_forwarded_and_consumed(rig, populated):
    rig.host.forwarded.clear()
    a, _ = bend(rig, 5, 100, populated)
    assert rig.host.forwarded == [(kl.forward_cc_message(0xE0, 5, 100), 2)] and a.handled is True


@pytest.mark.tuned_fix("F-15")
def test_an_arturia_plugin_hosted_by_a_renamed_channel_is_not_bent(rig):
    """Stock looked at the channel's NAME only (user-renamable); the plugin it hosts counts too."""
    rig.state.channel_names[0] = "Lead"
    rig.state.select_channel_plugin("Mini V3")
    a = fwd(rig, 0xE0, 0, 127)
    assert not a.calls_to("channels.setChannelPitch") and a.handled is True


@pytest.mark.tuned_fix("F-13")
def test_the_pitch_wheel_is_consumed_without_a_call_in_an_empty_rack(make_rig):
    rig = make_rig(boot=False)
    rig.state.set_channels([])
    rig.scripts.boot(order=("forward", "entry"))
    a = fwd(rig, 0xE0, 0, 127)
    assert a.errors == [] and a.handled is True and not a.calls_to("channels.setChannelPitch")
    assert [v for v in rig.host.violations if v.kind == "index"] == []


# ================================================================================================ robustness (FL API misbehaves)

@pytest.mark.tuned_fix("F-01")
@pytest.mark.parametrize("failing", ["ui.getFocusedPluginName", "device.forwardMIDICC", "channels.setChannelPitch",
                                     "plugins.getPluginName", "plugins.setParamValue", "plugins.getParamCount",
                                     "channels.getChannelName", "device.processMIDICC"])
def test_no_forward_callback_raises_when_an_fl_call_fails(rig, failing):
    rig.host.inject_fault(failing, RuntimeError)
    focus_plugin(rig, "MiniSynth")
    for status, d1, d2 in ((0xB0, 1, 90), (0xB0, 74, 5), (0xB0, 28, 127), (0xE0, 3, 100), (0x90, 60, 100), (0x99, 36, 100),
                           (0x89, 36, 0)):
        for populated in (True, False):
            a = fwd(rig, status, d1, d2, populated)
            assert a.errors == [], (failing, hex(status), d1, [(e.callback, str(e.exc)) for e in a.errors])


def test_a_failing_forward_call_is_logged_once_and_the_event_still_reaches_fl(rig, target):
    tuned_only(target)
    fresh_second(rig)
    focus_plugin(rig, "Analog Lab V")
    rig.host.inject_fault("device.forwardMIDICC", RuntimeError)
    for _ in range(3):
        a = fwd(rig, 0xB0, 74, 5)
        assert a.handled is False and a.errors == []
    assert len(log_lines(rig, "forwardMIDICC raised")) == 1


def test_the_forward_script_survives_the_processor_module_failing_to_import(rig, target):
    tuned_only(target)
    fresh_second(rig)
    fwd_mod = rig.forward.module
    fwd_mod._process_module = None
    fwd_mod._process_import_failed = False
    import sys
    saved = sys.modules.pop("KLTProcess")
    sys.modules["KLTProcess"] = None                                            # `import KLTProcess` now raises ImportError
    try:
        a = fwd(rig, 0x99, 36, 100)
        b = fwd(rig, 0xB0, 1, 50)
        focus_plugin(rig, "Analog Lab V")
        rig.host.forwarded.clear()
        c = fwd(rig, 0xB0, 74, 5)
        w = fwd(rig, 0xE0, 0, 100)
    finally:
        sys.modules["KLTProcess"] = saved
    assert a.errors == [] and b.errors == [] and c.errors == [] and w.errors == []
    assert rig.host.forwarded[0][0] == kl.forward_cc_message(0xB0, 74, 5), "Analog Lab forwarding must not depend on KLTProcess"
    assert log_lines(rig, "EXC in Forward: import KLTProcess")
