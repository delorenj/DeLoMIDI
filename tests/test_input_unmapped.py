"""F-03: events no handler claims (unmapped button ids, other CCs, pitch bend on other channels).

Stock set event.handled = True before it looked at the table, so every unmapped note / CC / fader event on channel 1
was swallowed without a trace. The tuned scripts log it (KLTLog, KLTConfig.LOG_UNMAPPED) and, per
KLTConfig.PASS_UNMAPPED, hand it back to FL. The hardware's real DAW preset is unverified (docs/analysis/02, F-03):
these logs are how the first run on the keyboard finds out what it sends.

Review round 1 (RA-01): the DEFAULT of PASS_UNMAPPED is now False on the DAW port (a panel button nobody claims is not a
note for the selected channel), so the tests that pin "passed on to FL" switch it on explicitly; the new default is pinned in
tests/test_review_fix_unmapped.py."""
from __future__ import annotations

import pytest

from tests import kl
from tests.test_input_helpers import fresh_second, log_lines, tuned_only

UNMAPPED_NOTES = [32, 39, 55, 100, 104, 112]
UNMAPPED_CCS = [1, 7, 11, 28, 29, 64, 71, 74, 93]


# ================================================================================================ characterization

@pytest.mark.parametrize("note", [kl.BTN_PLAY, kl.BTN_MUTE[0], kl.BTN_SNAP[0], kl.BTN_SELECT[3], kl.BTN_UNDO, kl.BTN_METRO])
def test_mapped_buttons_stay_consumed_in_both_phases(rig, note):
    """Including the phase the handler ignores (a press of a release-driven button): FL must never see a mapped button."""
    for pressed in (True, False):
        assert rig.button(note, pressed).handled is True, (note, pressed)


@pytest.mark.parametrize("cc", [16, 20, 24, 60])
def test_mapped_encoders_and_the_jog_stay_consumed(rig, cc):
    for value in (1, 65, 64, 0):
        assert rig.cc(cc, value).handled is True, (cc, value)


def test_unmapped_events_never_reach_a_handler(rig):
    """No FL call at all for an id nobody maps (the fix only changes what happens to the event afterwards)."""
    for note in UNMAPPED_NOTES:
        for a in (rig.button(note, True), rig.button(note, False)):
            assert a.effects == [] and a.errors == [], (note, a.lines)
    for cc in UNMAPPED_CCS:
        a = rig.cc(cc, 64)
        assert a.effects == [] and a.errors == [], (cc, a.lines)


# ================================================================================================ tuned fixes

@pytest.mark.tuned_fix("F-03")
@pytest.mark.parametrize("note", UNMAPPED_NOTES)
def test_unmapped_button_ids_are_passed_on_to_fl(rig, note):
    rig.host.set_config(PASS_UNMAPPED=True)              # RA-01: no longer the default
    for status, vel in ((0x90, 127), (0x90, 0), (0x80, 64)):
        a = rig.midi(status, note, vel)
        assert a.handled is False, (hex(status), note)
        assert (a.event.status, a.event.data1, a.event.data2) == (status, note, vel)


@pytest.mark.tuned_fix("F-03")
@pytest.mark.parametrize("cc", UNMAPPED_CCS)
def test_unmapped_ccs_are_passed_on_to_fl(rig, cc):
    rig.host.set_config(PASS_UNMAPPED=True)              # RA-01: no longer the default
    a = rig.cc(cc, 64)
    assert a.handled is False and a.event.data1 == cc and a.event.data2 == 64


@pytest.mark.tuned_fix("F-03")
@pytest.mark.parametrize("status", [0xE9, 0xEA, 0xEF])
def test_pitch_bend_beyond_the_nine_faders_is_passed_on(rig, status):
    rig.host.set_config(PASS_UNMAPPED=True)              # RA-01: no longer the default
    assert rig.midi(status, 5, 100).handled is False


@pytest.mark.tuned_fix("F-03")
def test_unmapped_events_are_logged_once_per_distinct_id(rig, target):
    tuned_only(target)
    fresh_second(rig)
    rig.host.set_config(PASS_UNMAPPED=True)              # RA-01: the line says what really happens; this test pins "passed to FL"
    for _ in range(5):
        rig.button(104, True)
    rig.button(112, True)
    rig.cc(74, 64)
    lines = log_lines(rig, "UNMAPPED")
    assert len([l for l in lines if "st=0x90 d1=104" in l]) == 1, lines
    assert len([l for l in lines if "st=0x90 d1=112" in l]) == 1
    assert len([l for l in lines if "st=0xB0 d1=74" in l]) == 1
    assert "port=0" in lines[0] and "passed to FL" in lines[0] and "note-on" in lines[0], lines[0]


@pytest.mark.tuned_fix("F-03")
def test_the_unmapped_log_line_repeats_at_ten_and_one_hundred(rig, target):
    tuned_only(target)
    fresh_second(rig)
    for _ in range(120):
        rig.button(104, True)
    counts = [int(l.split("seen ")[1].split(" ")[0]) for l in log_lines(rig, "UNMAPPED")]
    assert counts == [1, 10, 100]


def test_log_unmapped_off_writes_no_line(rig, target):
    tuned_only(target)
    fresh_second(rig)
    rig.host.set_config(LOG_UNMAPPED=False)
    rig.button(104, True)
    rig.cc(74, 64)
    assert log_lines(rig, "UNMAPPED") == []


def test_the_unmapped_log_remembers_a_bounded_number_of_ids(rig, target):
    tuned_only(target)
    fresh_second(rig)
    rig.host.set_config(LOG_UNMAPPED_MAX_KEYS=5)
    for note in range(100, 120):
        rig.button(note, True)
    assert len(log_lines(rig, "UNMAPPED")) == 5


def test_realtime_and_system_bytes_are_never_logged_as_unmapped(rig, target):
    tuned_only(target)
    fresh_second(rig)
    for status in (0xF8, 0xFE, 0xFA):
        rig.midi(status, 0, 0)
    assert log_lines(rig, "UNMAPPED") == []


def test_pass_unmapped_off_swallows_like_stock_but_never_a_note_off(rig, target):
    tuned_only(target)
    fresh_second(rig)
    rig.host.set_config(PASS_UNMAPPED=False)
    assert rig.midi(0x90, 104, 127).handled is True
    assert rig.midi(0x90, 104, 0).handled is True
    assert rig.midi(0x80, 104, 64).handled is False, "stock never routed note-offs; swallowing them would hang notes"
    assert rig.cc(74, 64).handled is True
    assert rig.midi(0xE9, 0, 64).handled is True
    assert rig.midi(0xA0, 60, 50).handled is False, "events with no table entry were never swallowed"
    a = rig.midi(0x90, 104, 127)
    assert a.effects == []
    assert "swallowed" in log_lines(rig, "UNMAPPED")[0]
