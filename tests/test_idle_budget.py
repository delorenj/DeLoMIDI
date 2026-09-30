"""SysEx budget of the idle loop.

The stock OnIdle re-sends 22-24 SysEx on every tick with no shadow state: 1,200 messages/s (315-byte bursts) at FL's
documented 50 Hz idle rate, 1,340/s in Sequencer mode while playing (docs/analysis/03-output-audit.md 3.3, O-02).
The community project the stock display code descends from limits each LED to one send per 33 ms and the LCD to one
frame per 35 ms because flooding "can cause the keyboard to get into a bad state where display changes are rejected
until keyboard is powered off" (O-06). The audit's tested patch reaches 12 msg/s steady and 39 msg/s while playing.

The budgets below are deliberately loose (an order of magnitude under the stock storm) so that any reasonable
de-duplication + keep-alive design passes; tighten them once the hardware's tolerance is measured on tom."""
from __future__ import annotations

import pytest

from tests import kl
from tests.flsim.driver import sysex_per_second

IDLE_HZ = 50                 # FL documents OnIdle as "roughly once every 20 ms"
SESSION_SECONDS = 60
QUIET_SECONDS = 10
QUIET_MAX_PER_SECOND = 30    # nothing changes: keep-alives only
WORST_SECOND_MAX = 150       # any single second, with FL state changing every 2 s
AVERAGE_MAX_PER_SECOND = 60
LCD_MIN_GAP_S = 0.035        # community-tested safe LCD frame spacing


def _changes():
    """FL state changing every 2 s for a minute (each followed by the OnRefresh FL would send)."""
    def select(st): st.selected_channel = (st.selected_channel + 1) % st.channel_count()
    def mute(st): st.muted_channels ^= {st.selected_channel}
    def focus_mixer(st): st.focus(kl.WID_MIXER)
    def track(st): st.current_track = (st.current_track % 20) + 1
    def solo(st): st.solo_tracks ^= {st.current_track}
    def focus_rack(st): st.focus(kl.WID_CHANNEL_RACK)
    def tempo(st): st.tempo = 100 + (st.tempo % 40)
    def pattern(st): st.pattern = st.pattern % st.pattern_count + 1
    fs = [select, mute, focus_mixer, track, solo, focus_rack, tempo, pattern]
    return [(2.0 * i + 1.0, fs[i % len(fs)]) for i in range(SESSION_SECONDS // 2 - 1)]


def _prepare(rig, scenario):
    if scenario == "mixer":
        rig.tap(kl.BTN_MIXER_TOGGLE)
    elif scenario == "sequencer-playing":
        rig.tap(kl.BTN_SEQ_TOGGLE)
        rig.state.grid.update({(0, 0): 1, (0, 4): 1, (0, 8): 1})
        rig.state.playing = True
        rig.state.tempo = 120.0
    rig.settle(3.0)


SCENARIOS = ["drum", "mixer", "sequencer-playing"]


@pytest.mark.tuned_fix("O-02")
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_sysex_per_second_stays_within_budget_while_fl_state_changes(rig, scenario):
    """OnIdle at 50 Hz for 60 virtual seconds; FL state (selection, mute, solo, focus, tempo, pattern) changes every
    2 s; in Sequencer mode the transport plays and the beat indicator fires."""
    _prepare(rig, scenario)
    h = rig.host
    t0 = h.clock.now
    rig.driver.run(SESSION_SECONDS, schedule=_changes(), playback=(scenario == "sequencer-playing"))
    per = sysex_per_second(h, t0, t0 + SESSION_SECONDS)
    assert h.errors == [] and h.violations == []
    assert max(per) <= WORST_SECOND_MAX, "worst second: %d SysEx (budget %d); per second: %s..." % (
        max(per), WORST_SECOND_MAX, per[:8])
    assert sum(per) / SESSION_SECONDS <= AVERAGE_MAX_PER_SECOND, "average %.0f SysEx/s (budget %d)" % (
        sum(per) / SESSION_SECONDS, AVERAGE_MAX_PER_SECOND)


@pytest.mark.tuned_fix("O-02")
def test_a_quiet_idle_loop_sends_almost_nothing(rig):
    rig.settle(3.0)
    h = rig.host
    t0 = h.clock.now
    rig.driver.run(QUIET_SECONDS, playback=False)
    per = sysex_per_second(h, t0, t0 + QUIET_SECONDS)
    assert max(per) <= QUIET_MAX_PER_SECOND, "steady state: %s SysEx per second (budget %d)" % (per, QUIET_MAX_PER_SECOND)


@pytest.mark.tuned_fix("O-06")
def test_lcd_frames_are_spaced_and_the_last_value_still_arrives(rig):
    """A fader sweep changes the text on every event (100 frames/s in the stock script); the display must be
    rate-limited but still end on the final value."""
    rig.tap(kl.BTN_MIXER_TOGGLE)
    rig.settle(3.0)
    m0 = rig.host.mark()
    for v in range(0, 128):                                      # 128 events over ~1.3 s
        rig.fader(2, v)
        rig.driver.tick(1, playback=False)
        rig.host.advance(0.0)
    rig.settle(0.5)
    frames = rig.host.device_model(since=m0).lcd_frames
    times = [t for t, _, _ in frames]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert min(gaps) >= LCD_MIN_GAP_S - 1e-6, "LCD frames %.0f ms apart (minimum %.0f ms)" % (min(gaps) * 1000, LCD_MIN_GAP_S * 1000)
    assert frames[-1][1:] == ("Volume - 3", "80%"), frames[-1]


def test_idle_never_raises_and_every_message_is_well_framed(rig):
    for scenario_setup in (None, kl.BTN_MIXER_TOGGLE, kl.BTN_SEQ_TOGGLE):
        if scenario_setup:
            rig.tap(scenario_setup)
        rig.driver.run(5.0, schedule=_changes()[:2], playback=False)
    assert rig.host.errors == []
    assert all(m.valid for m in rig.host.sysex)
