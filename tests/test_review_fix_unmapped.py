"""Review round 1, guide acceptance (RA-01, RA-04): what happens to an event no handler claims, per PORT.

DAW port (the DAW script's OnMidiMsg): a button the script does not know is a panel button, not a key. Left to FL it is a note
on the selected channel (Next/Previous with Bank off, Category/Preset, the 9th Select button ...): audible, and recorded when
record is armed. Arturia's script swallowed all of them; so does the tuned default now (PASS_UNMAPPED = False), still logging every
id. Keyboard port (the Forward script): keybed, pedals and wheels live there; the Forward script NEVER swallows an unmapped event,
whatever PASS_UNMAPPED says and whichever path (raw OnMidiIn or the opt-in processor) sees it."""
from __future__ import annotations

import pytest

from tests.test_input_helpers import fresh_second, log_lines, tuned_only

POPS = [pytest.param(True, id="H1"), pytest.param(False, id="H2")]
STRAY_NOTES = [32, 39, 48, 49, 55, 96, 97, 100, 104, 112]
STRAY_CCS = [1, 7, 11, 28, 29, 64, 71, 74, 93]
KEYBOARD_TRAFFIC = [(0x90, 60, 100), (0x80, 60, 0), (0xB0, 64, 127), (0xB0, 11, 90), (0xB0, 7, 90), (0xB0, 1, 50),
                    (0xD0, 40, 0), (0xA0, 60, 30)]


def test_pass_unmapped_is_off_by_default(make_rig, target):
    tuned_only(target)
    rig = make_rig()
    import KLTConfig
    assert KLTConfig.PASS_UNMAPPED is False


@pytest.mark.parametrize("populated", POPS)
@pytest.mark.parametrize("note", STRAY_NOTES)
def test_an_unclaimed_panel_button_on_the_daw_port_is_not_played_by_fl(make_rig, target, populated, note):
    tuned_only(target)
    rig = make_rig(midi_in_populated=populated)
    assert rig.button(note, True, role="entry").handled is True
    assert rig.button(note, False, role="entry").handled is True       # note-on velocity 0 = the release


@pytest.mark.parametrize("populated", POPS)
def test_a_note_off_is_never_swallowed_on_the_daw_port(make_rig, target, populated):
    """Swallowing a note-off could hang a note; stock never routed them either."""
    tuned_only(target)
    rig = make_rig(midi_in_populated=populated)
    for note in STRAY_NOTES:
        assert rig.midi(0x80, note, 64, role="entry").handled is False, note


@pytest.mark.parametrize("cc", STRAY_CCS)
def test_unmapped_ccs_on_the_daw_port_are_swallowed_like_stock(make_rig, target, cc):
    tuned_only(target)
    rig = make_rig()
    a = rig.cc(cc, 64)
    assert a.handled is True and a.effects == []


@pytest.mark.parametrize("status", [0xE9, 0xEA, 0xEF])
def test_pitch_bend_beyond_the_nine_faders_is_swallowed_on_the_daw_port(make_rig, target, status):
    tuned_only(target)
    assert make_rig().midi(status, 5, 100, role="entry").handled is True


def test_every_note_id_of_channel_1_on_the_daw_port_is_now_either_mapped_or_swallowed(make_rig, target):
    tuned_only(target)
    rig = make_rig()
    leaked = [n for n in range(128) if rig.midi(0x90, n, 127, role="entry").handled is False]
    assert leaked == []


@pytest.mark.parametrize("note", STRAY_NOTES)
def test_pass_unmapped_true_still_hands_the_button_to_fl(make_rig, target, note):
    tuned_only(target)
    rig = make_rig()
    rig.host.set_config(PASS_UNMAPPED=True)
    assert rig.button(note, True, role="entry").handled is False
    assert rig.button(note, False, role="entry").handled is False


def test_the_unmapped_ids_are_still_logged_once_with_the_true_disposition(make_rig, target):
    tuned_only(target)
    rig = make_rig()
    fresh_second(rig)
    rig.button(104, True, role="entry")
    rig.button(104, True, role="entry")
    lines = [l for l in log_lines(rig, "UNMAPPED ") if "d1=104" in l]
    assert len(lines) == 1 and "st=0x90 d1=104" in lines[0] and "swallowed" in lines[0] and "port=0" in lines[0]
    rig.host.set_config(PASS_UNMAPPED=True)
    rig.button(105, True, role="entry")
    assert "passed to FL" in [l for l in log_lines(rig, "UNMAPPED ") if "d1=105" in l][0]


# ================================================================================================ the keyboard port

@pytest.mark.parametrize("populated", POPS)
@pytest.mark.parametrize("processor", [False, True], ids=["raw-path", "processor-path"])
@pytest.mark.parametrize("pass_unmapped", [True, False], ids=["pass", "swallow"])
def test_the_keyboard_port_never_swallows_an_unmapped_event(make_rig, target, populated, processor, pass_unmapped):
    """RA-04: PASS_UNMAPPED=False (advised for the DAW port) must not cost the instrument its pedals and mod wheel, on either
    path. Only the wheel (OnPitchBend) is consumed on this port, as before."""
    tuned_only(target)
    rig = make_rig(midi_in_populated=populated)
    rig.host.set_config(PASS_UNMAPPED=pass_unmapped, FORWARD_USE_PROCESSOR=processor,
                        FORWARD_PROCESSOR_KINDS=("note", "cc", "bend") if processor else ("cc",))
    for status, d1, d2 in KEYBOARD_TRAFFIC:
        a = rig.midi(status, d1, d2, role="forward", populated=populated)
        if processor and status == 0x90 and d1 in (46, 47, 51, 56, 74, 84, 86, 87, 91, 92, 93, 94, 95, 98, 99):
            continue                                                       # a documented button id: mapped on purpose
        assert a.handled is False, (hex(status), d1, pass_unmapped, processor)


@pytest.mark.parametrize("populated", POPS)
def test_a_mapped_control_on_the_keyboard_port_is_still_consumed_on_the_processor_path(make_rig, target, populated):
    tuned_only(target)
    rig = make_rig(midi_in_populated=populated)
    rig.host.set_config(FORWARD_USE_PROCESSOR=True, PASS_UNMAPPED=False)
    assert rig.midi(0xB0, 60, 1, role="forward", populated=populated).handled is True       # the jog: mapped


def test_the_keyboard_port_unmapped_line_says_passed_to_fl_whatever_the_switch_says(make_rig, target):
    tuned_only(target)
    rig = make_rig(midi_in_populated=False)
    fresh_second(rig)
    rig.host.set_config(PASS_UNMAPPED=False)
    assert rig.midi(0xB0, 64, 127, role="forward").handled is False
    (line,) = [l for l in log_lines(rig, "UNMAPPED") if "forward-cc" in l]
    assert "passed to FL" in line and "swallowed" not in line
    rig.host.set_config(FORWARD_USE_PROCESSOR=True)
    rig.midi(0xB0, 65, 127, role="forward")
    (line2,) = [l for l in log_lines(rig, "UNMAPPED") if "d1=65" in l]
    assert "passed to FL" in line2 and "swallowed" not in line2


def test_the_wheel_is_consumed_on_the_keyboard_port_as_before(make_rig, target):
    tuned_only(target)
    rig = make_rig(midi_in_populated=False)
    assert rig.midi(0xE0, 0, 100, role="forward").handled is True
