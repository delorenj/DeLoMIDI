"""SysEx economy of the output layer: shadow state, the hard budgets, the trailing flush, the keep-alive (O-02, O-05, O-06).

Stock: 22-24 frames per OnIdle tick (~1,200 SysEx/s at FL's documented 50 Hz), no rate limit on the LCD, an LCD cache that
was never invalidated. The tuned output layer sends only changes, never more than OUT_MAX_SYSEX_PER_SEC frames in any
sliding second nor OUT_MAX_SYSEX_PER_TICK in one tick, and the budgets never change the settled result, only when it arrives."""
from __future__ import annotations

from collections import Counter

import pytest

from tests import kl
from tests.conftest import BOOT_ORDER
from tests.flsim.rig import Rig
from tests.flsim.sysex import decode, led_mono_frame, led_rgb_frame
from tests.test_output_support import boot, per_second, sent, tuned_only  # noqa: F401


def _busy_schedule(seconds):
    """FL state changing a lot: a change every 100 ms, each followed by the OnRefresh FL sends."""
    def sel(st): st.selected_channel = (st.selected_channel + 1) % st.channel_count()
    def mute(st): st.muted_channels ^= {st.selected_channel}
    def solo(st): st.solo_channels ^= {(st.selected_channel + 3) % st.channel_count()}
    def metro(st): st.metronome = not st.metronome
    def focus(st): st.focus(kl.WID_MIXER if st.focused == kl.WID_CHANNEL_RACK else kl.WID_CHANNEL_RACK)
    fs = [sel, mute, solo, metro, focus]
    return [(0.1 * i, fs[i % len(fs)]) for i in range(int(seconds * 10))]


# ================================================================================================ hard budgets

@pytest.mark.parametrize("cap", [20, 60, 100])
def test_the_per_second_cap_holds_in_every_sliding_second(make_rig, cap):
    rig = boot(make_rig, cfg={"OUT_MAX_SYSEX_PER_SEC": cap})
    rig.settle(5.0)
    h = rig.host
    t0 = h.clock.now
    rig.driver.run(20, schedule=_busy_schedule(20), playback=False)
    times = [m.t for m in h.sysex if m.t >= t0]
    assert times, "the busy session sent nothing"
    worst = max(sum(1 for u in times if t <= u < t + 1.0 - 1e-6) for t in times)
    assert worst <= cap, "%d frames inside one second (cap %d)" % (worst, cap)
    assert h.errors == [] and h.violations == []


@pytest.mark.parametrize("per_tick", [1, 4, 8])
def test_the_per_tick_cap_holds_in_every_tick(make_rig, per_tick):
    rig = boot(make_rig, cfg={"OUT_MAX_SYSEX_PER_TICK": per_tick, "OUT_MAX_SYSEX_PER_SEC": 1000})
    rig.settle(2.0)
    h = rig.host
    t0 = h.clock.now
    rig.driver.run(10, schedule=_busy_schedule(10), playback=False)
    ticks = Counter(round((m.t - t0) / 0.02) for m in h.sysex if m.t >= t0)
    assert ticks and max(ticks.values()) <= per_tick, "a tick carried %d frames (cap %d)" % (max(ticks.values()), per_tick)


def test_the_default_per_tick_cap_also_covers_the_frames_a_callback_asks_for(rig):
    """Switching to Sequencer mode repaints the 16 pads inside one OnMidiMsg; only OUT_MAX_SYSEX_PER_TICK leave at once."""
    rig.settle(2.0)
    a = rig.tap(kl.BTN_SEQ_TOGGLE)
    first = [m for act in a for m in act.sysex]
    assert len(first) <= 8
    rig.settle(1.0)
    m = rig.host.device_model()
    assert all(m.rgb[p] == kl.WHITE for p in kl.PAD_LEDS)              # every pad arrived, just not in one burst


@pytest.mark.parametrize("cfg", [
    {"OUT_MAX_SYSEX_PER_SEC": 15, "OUT_MAX_SYSEX_PER_TICK": 1},
    {"OUT_MAX_SYSEX_PER_SEC": 40, "OUT_LED_PASS_S": 0.5},
    {"OUT_LCD_MIN_GAP_S": 0.3, "OUT_TRICKLE_S": 0, "OUT_LCD_KEEPALIVE_S": 0},
], ids=["1-per-tick-15-per-second", "40-per-second-slow-poll", "slow-lcd-no-keepalive"])
def test_budgets_change_when_the_keyboard_is_told_never_what_it_ends_up_showing(host_factory, target, cfg):
    """The same busy session under default and under tight budgets must leave the keyboard in the same state."""
    def run(cfg):
        h = host_factory()
        s = h.load(target.path)
        h.set_config(**cfg)
        s.boot(order=BOOT_ORDER)
        rig = Rig(h, s)
        rig.settle(3.0)
        rig.driver.run(8, schedule=_busy_schedule(8), playback=False)
        rig.settle(12.0)
        assert h.errors == []
        state = h.device_model().state()
        host_factory.close(h)
        return state
    assert run({}) == run(cfg)


# ================================================================================================ shadow state

def test_a_quiet_idle_loop_only_sends_the_keep_alive(rig):
    rig.settle(3.0)
    h = rig.host
    t0 = h.clock.now
    rig.driver.run(30, playback=False)
    per = per_second(h, t0, 30)
    assert sum(per) <= 40, "quiet idle sent %d frames in 30 s" % sum(per)
    assert max(per) <= 2


def test_without_keep_alive_a_quiet_idle_loop_sends_nothing_at_all(make_rig):
    rig = boot(make_rig, cfg={"OUT_TRICKLE_S": 0, "OUT_LCD_KEEPALIVE_S": 0})
    rig.settle(4.0)
    h = rig.host
    m0 = h.mark()
    rig.driver.run(30, playback=False)
    assert h.since(m0).sysex == []


def test_the_keep_alive_re_sends_one_known_frame_at_a_time_and_covers_them_all(make_rig):
    rig = boot(make_rig, cfg={"OUT_TRICKLE_S": 0.25, "OUT_LCD_KEEPALIVE_S": 5.0})
    rig.settle(4.0)
    h = rig.host
    keys_known = {(f.kind, f.fields["id"]) for f in sent(h) if f.kind in ("led_mono", "led_rgb")}
    m0 = h.mark()
    rig.driver.run(60, playback=False)
    again = sent(h, m0)
    assert {(f.kind, f.fields["id"]) for f in again if f.kind in ("led_mono", "led_rgb")} == keys_known
    assert any(f.kind == "lcd" for f in again)
    per = per_second(h, h.clock.now - 60, 60)
    assert max(per) <= 5                                              # 4/s trickle + the odd LCD frame


def test_only_changed_leds_are_sent(rig):
    rig.settle(3.0)
    rig.state.muted_channels.add(2)
    rig.refresh()
    rig.settle(0.5)
    m0 = rig.host.mark()
    rig.state.muted_channels.discard(2)
    rig.refresh()
    rig.idle(0.5)
    frames = [f for f in sent(rig.host, m0) if f.kind in ("led_mono", "led_rgb")]
    # channel 3 goes from muted (red) back to available (purple); nothing else changes
    assert [(f.fields["id"], f.fields["rgb"]) for f in frames if f.kind == "led_rgb"] == [(kl.SELECT_LEDS[2], kl.PURPLE)]
    assert [f for f in frames if f.kind == "led_mono"] == []


def test_a_change_that_reverts_before_it_is_sent_sends_nothing(make_rig):
    """Latest wins: with the tick budget exhausted the pending frame for an LED is replaced, and when the wanted value
    equals what the keyboard already shows it is dropped."""
    rig = boot(make_rig, cfg={"OUT_MAX_SYSEX_PER_TICK": 1, "OUT_TRICKLE_S": 0, "OUT_LCD_KEEPALIVE_S": 0})
    rig.settle(3.0)
    m0 = rig.host.mark()
    for _ in range(3):
        rig.state.muted_channels ^= {1}
        rig.state.muted_channels ^= {1}
    rig.refresh()
    rig.settle(1.0)
    assert [f for f in sent(rig.host, m0) if f.kind in ("led_mono", "led_rgb")] == []


def test_frames_of_one_callback_are_coalesced_to_the_final_state(rig):
    """OnUpdateBeatIndicator in Sequencer mode repaints all pads and then the playhead pad: the pad that ends up the
    playhead is sent once, not as 'normal' and then 'highlight'."""
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.state.tempo = 120.0
    rig.state.song_tick_pos = 1
    rig.state.song_step_pos = 3
    rig.settle(2.0)
    a = rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 1))
    pad = [decode(m.data) for m in a.sysex if decode(m.data).kind == "led_rgb"]
    ids = [f.fields["id"] for f in pad]
    assert len(ids) == len(set(ids)), "a pad was sent twice in one callback: %s" % ids


def test_the_polled_leds_are_evaluated_at_the_pass_interval(make_rig):
    rig = boot(make_rig, cfg={"OUT_LED_PASS_S": 0.5})
    rig.settle(2.0)
    h = rig.host
    n0 = len(h.calls_to("ui.isMetronomeEnabled"))
    rig.driver.run(10, playback=False)
    polls = len(h.calls_to("ui.isMetronomeEnabled")) - n0
    assert 18 <= polls <= 22, "%d passes in 10 s at 0.5 s" % polls


def test_a_polled_led_follows_fl_within_one_pass_interval(rig):
    rig.settle(3.0)
    rig.state.metronome = True                       # no OnRefresh for this one: the poll finds it
    rig.idle(0.3)
    assert rig.host.device_model().mono[kl.LED_METRO] == kl.LED_ON


# ================================================================================================ LCD

def test_lcd_frames_keep_the_configured_gap_and_the_last_text_arrives(make_rig):
    rig = boot(make_rig, cfg={"OUT_LCD_MIN_GAP_S": 0.2})
    rig.tap(kl.BTN_MIXER_TOGGLE)
    rig.settle(4.0)
    m0 = rig.host.mark()
    for v in range(0, 128, 2):
        rig.fader(2, v)
        rig.driver.tick(1, playback=False)
    rig.settle(0.3)
    frames = rig.host.device_model(since=m0).lcd_frames
    gaps = [b[0] - a[0] for a, b in zip(frames, frames[1:])]
    assert gaps and min(gaps) >= 0.2 - 1e-6
    assert frames[-1][1] == "Volume - 3" and frames[-1][2] in ("79%", "80%"), frames[-1]      # the last fader value


def test_an_unchanged_lcd_text_is_not_sent_again_except_by_the_keep_alive(make_rig):
    rig = boot(make_rig, cfg={"OUT_TRICKLE_S": 0, "OUT_LCD_KEEPALIVE_S": 0})
    rig.settle(4.0)
    m0 = rig.host.mark()
    for _ in range(50):
        rig.refresh()
        rig.driver.tick(1, playback=False)
    assert rig.host.device_model(since=m0).lcd_frames == []


# ================================================================================================ resync (O-05)

def test_a_memory_switch_re_sends_every_led_and_the_lcd(rig):
    rig.settle(3.0)
    before = rig.host.device_model().state()
    m0 = rig.host.mark()
    rig.capture(lambda: rig.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH))
    rig.settle(2.0)
    m = rig.host.device_model(since=m0)
    assert m.lcd_frames and set(m.rgb) >= set(kl.PAD_LEDS + kl.SELECT_LEDS + [kl.LED_MULTI])
    assert set(m.mono) >= set(kl.LED_STEADY + [kl.LED_METRO, kl.LED_LOOP, kl.LED_MUTE, kl.LED_SOLO, kl.LED_PLAY, kl.LED_STOP, kl.LED_RECORD])
    assert rig.host.device_model().state() == before                    # and the keyboard shows what it showed


def test_a_full_refresh_request_repaints_everything(rig):
    rig.settle(3.0)
    m0 = rig.host.mark()
    rig.capture(lambda: rig.entry.call("OnDoFullRefresh"))
    rig.settle(2.0)
    m = rig.host.device_model(since=m0)
    assert m.lcd_frames and set(m.rgb) >= set(kl.PAD_LEDS + kl.SELECT_LEDS)


def test_a_loaded_project_repaints_but_a_loading_one_does_not(rig):
    rig.settle(3.0)
    m0 = rig.host.mark()
    rig.capture(lambda: rig.entry.call("OnProjectLoad", 0))               # midi.PL_Start
    rig.settle(0.5)
    assert rig.host.device_model(since=m0).lcd_frames == [] and rig.host.errors == []
    rig.state.set_channels(["A", "B", "C"])
    rig.capture(lambda: rig.entry.call("OnProjectLoad", 100))             # midi.PL_LoadOk
    rig.settle(1.0)
    m = rig.host.device_model()
    assert m.lcd == ("1 - A", "Pattern 1") and [m.rgb[s] for s in kl.SELECT_LEDS][:3] == [kl.YELLOW, kl.PURPLE, kl.PURPLE]
    assert [m.rgb[s] for s in kl.SELECT_LEDS][3:] == [kl.OFF] * 5


def test_noisy_refresh_flags_are_processed_by_default_and_skipped_on_request(make_rig):
    """O-07: HW_Dirty_Mixer_Controls (4) / HW_Dirty_ControlValues (4096) fire while faders move. Their meaning for the
    Arturia LEDs is unverified, so the default processes them like stock; the switch skips them (0 and mixed flags never)."""
    rig = boot(make_rig)
    rig.settle(2.0)
    h = rig.host
    for flags, expect_default in ((4, True), (4096, True), (4 | 4096, True), (256, True), (0, True), (4 | 256, True)):
        n0 = len(h.calls_to("patterns.patternNumber"))
        rig.refresh(flags)
        assert (len(h.calls_to("patterns.patternNumber")) > n0) is expect_default, flags


def test_noisy_refresh_flags_can_be_skipped(make_rig):
    rig = boot(make_rig, cfg={"REFRESH_IGNORE_NOISY_FLAGS": True})
    rig.settle(2.0)
    h = rig.host
    for flags, works in ((4, False), (4096, False), (4 | 4096, False), (256, True), (0, True), (4 | 256, True), (32, True)):
        n0 = len(h.calls_to("patterns.patternNumber"))
        rig.refresh(flags)
        assert (len(h.calls_to("patterns.patternNumber")) > n0) is works, flags


# ================================================================================================ statistics line

def test_the_output_counters_are_logged_once_a_minute_when_frames_were_sent(make_rig):
    rig = boot(make_rig, cfg={"OUT_STATS_LOG_S": 5.0})
    rig.idle(16.0)
    lines = [l for l in rig.host.read_log().splitlines() if "output stats:" in l]
    assert 2 <= len(lines) <= 4
    assert "sent=" in lines[0] and "deduped=" in lines[0] and "defer_sec=0" in lines[0]


def test_the_output_counters_can_be_switched_off(make_rig):
    rig = boot(make_rig, cfg={"OUT_STATS_LOG_S": 0})
    rig.idle(70.0)
    assert "output stats:" not in rig.host.read_log()


def test_a_flood_of_full_refresh_requests_cannot_become_a_flood_of_sysex(rig):
    rig.settle(3.0)
    h = rig.host
    t0 = h.clock.now
    for _ in range(200):                                     # FL asking for everything at 50 Hz for 4 s
        rig.capture(lambda: rig.entry.call("OnDoFullRefresh"))
        rig.driver.tick(1, playback=False)
    per = per_second(h, t0, 4)
    assert max(per) <= 100 and h.errors == []
    assert sum(per) <= 4 * 60                                # about one full repaint (44 frames) per second, not 200
