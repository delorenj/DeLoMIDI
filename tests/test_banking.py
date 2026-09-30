"""Mixer and channel banking (Next/Previous shift the 8 faders/encoders/Select buttons by 8) and its limits.

FL's mixer always has 127 tracks: master (0), inserts 1..125 and the "current track" pseudo track 126
(mixer.trackCount() == 127, valid indices 0..126). The stock bank limit assumes 125 tracks, so at the last bank
(offset 15: tracks 121..128) pan/select/LED code touches tracks that do not exist (F-09)."""
from __future__ import annotations

import pytest

from tests import kl

LAST_BANK_FIRST_TRACK = 121


def go_to_last_mixer_bank(rig, presses=30):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    for _ in range(presses):
        rig.tap(kl.BTN_NEXT)


def mixer_index_violations(rig):
    return [v for v in rig.host.violations if v.kind == "index" and v.where.startswith("mixer.")]


# ================================================================================================ characterization

def test_next_stops_at_the_last_mixer_bank(rig):
    go_to_last_mixer_bank(rig, 40)
    a = rig.fader(0, 100)
    assert [c.args[0] for c in a.effects if c.qual == "mixer.setTrackVolume"] == [LAST_BANK_FIRST_TRACK]
    a = rig.cc(16, 1)
    assert [c.args[0] for c in a.effects if c.qual == "mixer.setTrackPan"] == [LAST_BANK_FIRST_TRACK]


def test_previous_stops_at_the_first_mixer_bank(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    for _ in range(3):
        rig.tap(kl.BTN_PREV)
    a = rig.fader(0, 100)
    assert [c.args[0] for c in a.effects if c.qual == "mixer.setTrackVolume"] == [1]


def test_volume_at_the_last_bank_never_addresses_a_missing_track(rig):
    go_to_last_mixer_bank(rig)
    for i in range(9):
        rig.fader(i, 100)
    assert mixer_index_violations(rig) == []
    touched = {c.args[0] for c in rig.host.calls if c.qual == "mixer.setTrackVolume"}
    assert touched <= set(range(0, 126)) and LAST_BANK_FIRST_TRACK in touched and 0 in touched


def test_channel_banking_is_bounded_by_the_channel_count(rig):
    rig.state.resize_channels(19)
    for _ in range(10):
        rig.tap(kl.BTN_NEXT)
    assert rig.button(kl.BTN_SELECT[0], False).called("channels.selectOneChannel", 16)
    assert rig.button(kl.BTN_SELECT[2], False).called("channels.selectOneChannel", 18)
    assert not rig.button(kl.BTN_SELECT[3], False).calls_to("channels.selectOneChannel")      # channel 19 does not exist
    assert rig.host.violations == []


def test_channel_bank_with_exactly_eight_channels_has_a_single_page(rig):
    rig.state.resize_channels(8)
    for _ in range(3):
        rig.tap(kl.BTN_NEXT)
    assert rig.button(kl.BTN_SELECT[0], False).called("channels.selectOneChannel", 0)


# ================================================================================================ tuned fixes

@pytest.mark.tuned_fix("F-09")
def test_last_mixer_bank_never_addresses_tracks_beyond_trackcount(rig):
    """Bank offset 15 covers tracks 121..128: pan and Select addressed 127 and 128 (trackCount() is 127)."""
    go_to_last_mixer_bank(rig)
    for i in range(9):
        rig.cc(16 + i, 1)
        rig.cc(16 + i, 65)
    for b in kl.BTN_SELECT:
        rig.button(b, False)
    rig.idle(1.0)
    v = mixer_index_violations(rig)
    assert v == [], "%d out-of-range mixer accesses, e.g. %s" % (len(v), v[0].message if v else "")


def test_last_mixer_bank_leds_only_light_slots_for_existing_tracks(rig):
    go_to_last_mixer_bank(rig)
    rig.refresh()
    rig.idle(1.0)
    assert mixer_index_violations(rig) == []
    m = rig.host.device_model()
    assert m.rgb[kl.SELECT_LEDS[5]] == kl.OFF and m.rgb[kl.SELECT_LEDS[7]] == kl.OFF         # tracks 126..128: no slot


@pytest.mark.tuned_fix("F-09")
def test_mod_wheel_or_stray_cc_never_produces_a_negative_track(rig):
    rig.tap(kl.BTN_MIXER_TOGGLE)
    for cc in (1, 7, 74):
        rig.cc(cc, 64)
        rig.midi(0xB0, cc, 64, role="forward", populated=False)
    assert mixer_index_violations(rig) == []
