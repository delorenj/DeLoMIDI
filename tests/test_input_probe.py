"""F-01 / F-17 diagnostics: klt.log records what FL fills in per callback and per port, so ONE run on the hardware settles
which hypothesis is true (docs/analysis/02-input-audit.md 3.3):

  H1  midiId / midiChan are populated in OnMidiIn        H2  they are 0 there ("only raw data is available here")

plus whether the two device scripts share one Python interpreter (F-17). The scripts themselves never read those fields:
they derive everything from status/data1/data2, so the answer is diagnostic only. Tuned folder only."""
from __future__ import annotations

import os

import pytest

from tests.test_input_helpers import fresh_second, fwd, log_lines, tuned_only


@pytest.fixture
def probing(rig, target):
    tuned_only(target)
    fresh_second(rig)
    return rig


def verdicts(rig):
    return {l.split("PROBE-VERDICT ")[1].split(":")[0]: l for l in log_lines(rig, "PROBE-VERDICT")}


def test_a_keyboard_note_records_midiid_per_callback_and_port_under_h2(probing):
    fwd(probing, 0x90, 60, 100, populated=False)
    v = verdicts(probing)
    assert "NOT populated, reads 0x00 (H2)" in v["Forward.OnMidiIn port=1"]
    assert "POPULATED (H1)" in v["Forward.OnMidiMsg port=1"], "FL fills midiId before OnMidiMsg (MackieCU relies on it)"
    lines = log_lines(probing, "PROBE Forward.OnMidiIn port=1 note-on")
    assert lines and "st=0x90 d1=60 d2=100 midiId=0x00 (want 0x90)" in lines[0] and "controlNum=" in lines[0]


def test_a_keyboard_note_records_midiid_per_callback_and_port_under_h1(probing):
    fwd(probing, 0x90, 60, 100, populated=True)
    v = verdicts(probing)
    assert "POPULATED (H1)" in v["Forward.OnMidiIn port=1"] and "POPULATED (H1)" in v["Forward.OnMidiMsg port=1"]


def test_the_daw_port_is_probed_in_its_own_callback(probing):
    probing.button(94, True)
    v = verdicts(probing)
    assert "POPULATED (H1)" in v["DAW.OnMidiMsg port=0"]
    assert "Forward.OnMidiIn port=1" not in v


def test_midichan_is_decisive_on_channels_other_than_one(probing):
    probing.button(94, True)                    # channel 1: midiChan 0 either way, so the line says it cannot tell
    probing.pad_on(36, 100)                     # channel 10
    probing.fader(3, 50)                        # channel 4
    lines = log_lines(probing, "PROBE DAW.OnMidiMsg")
    button = [l for l in lines if "note-on" in l and "st=0x90" in l][0]
    pad = [l for l in lines if "note-on" in l and "st=0x99" in l][0]
    bend = [l for l in lines if "pitch-bend" in l][0]
    assert "midiChan=9 (want 9)" in pad and "midiChan=3 (want 3)" in bend
    assert "ambiguous on channel 1" in button and "ambiguous" not in pad


def test_probe_lines_are_capped_per_callback_port_and_kind(probing):
    probing.host.set_config(PROBE_SAMPLES_PER_KIND=2)
    for note in range(40, 60):
        fwd(probing, 0x90, note, 100)
        fwd(probing, 0xB0, 74, note)
    assert len(log_lines(probing, "PROBE Forward.OnMidiIn port=1 note-on")) == 2
    assert len(log_lines(probing, "PROBE Forward.OnMidiIn port=1 cc")) == 2
    assert len(log_lines(probing, "PROBE Forward.OnMidiMsg port=1 note-on")) == 2


def test_the_probe_can_be_switched_off(probing):
    probing.host.set_config(PROBE_MIDI_FIELDS=False)
    fwd(probing, 0x90, 60, 100)
    probing.button(94, True)
    assert log_lines(probing, "PROBE") == []


def test_the_verdict_lines_name_the_interpreter_so_a_shared_one_is_visible(probing):
    fwd(probing, 0x90, 60, 100)
    probing.button(94, True)
    ids = {l.split("[interpreter ")[1].split(",")[0] for l in log_lines(probing, "PROBE-VERDICT")}
    assert len(ids) == 1, "the simulator runs both device scripts in one interpreter: one id in every verdict line"


def test_probing_makes_no_fl_call_for_a_keybed_note(probing):
    for populated in (True, False):
        a = fwd(probing, 0x90, 60, 100, populated=populated)
        assert a.calls == [] and a.handled is False


def test_raw_event_logging_captures_both_ports(probing):
    probing.host.set_config(LOG_RAW_EVENTS=True)
    probing.button(94, True)
    fwd(probing, 0x90, 60, 100)
    fwd(probing, 0xB0, 74, 12)
    raw = log_lines(probing, "RAW ")
    assert any("RAW DAW.OnMidiMsg port=0 st=0x90 d1=94 d2=127" in l for l in raw)
    assert any("RAW Forward.OnMidiIn port=1 st=0x90 d1=60 d2=100" in l for l in raw)
    assert any("RAW Forward.OnMidiIn port=1 st=0xB0 d1=74 d2=12" in l for l in raw)


def test_raw_event_logging_is_off_by_default(probing):
    probing.button(94, True)
    assert log_lines(probing, "RAW ") == []


def test_a_broken_log_path_never_breaks_an_event(probing):
    """KLTLog swallows its own I/O errors: an unwritable klt.log must not cost a single control."""
    blocker = os.path.join(probing.host.tmpdir, "blocker")          # a regular file: the log's folder can never be created
    with open(blocker, "w") as f:
        f.write("x")
    probing.host.set_config(LOG_PATH=os.path.join(blocker, "none", "klt.log"), PROBE_MIDI_FIELDS=True, LOG_RAW_EVENTS=True)
    a = probing.button(94, True)
    b = fwd(probing, 0xB0, 74, 12)
    assert a.errors == [] and a.called("transport.start") and b.errors == []
