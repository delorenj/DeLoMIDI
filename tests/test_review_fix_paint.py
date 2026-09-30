"""Review round 1, hardware fidelity (R-HS-04, OUT-2, OUT-1): what the keyboard is showing must not depend on FL sending an
OnRefresh after OnInit (unverified for FL 26.1.6), and a keyboard that loses its LEDs without telling FL must heal in seconds,
not in up to 43 s.

The simulator's boot() sends a full OnRefresh right after OnInit (an assumption); these tests boot WITHOUT it."""
from __future__ import annotations

import pytest

from tests import kl
from tests.conftest import BOOT_ORDER
from tests.flsim.sysex import decode
from tests.test_output_support import boot, log_lines, sent, tuned_only  # noqa: F401


def _boot_without_refresh(make_rig, cfg=None, **host_kw):
    rig = make_rig(boot=False, **host_kw)
    if cfg:
        rig.host.set_config(**cfg)
    rig.scripts.boot(order=BOOT_ORDER, refresh_flags=None)
    return rig


def _led_keys(frames):
    return {(f.kind, f.fields["id"]) for f in frames if f.kind in ("led_mono", "led_rgb")}


# ================================================================================================ R-HS-04 / OUT-2

def test_pads_and_transport_leds_are_painted_when_fl_never_sends_an_onrefresh(make_rig):
    rig = _boot_without_refresh(make_rig)
    rig.idle(3.0)
    m = rig.host.device_model()
    assert all(m.rgb.get(p) == kl.RED for p in kl.PAD_LEDS), {hex(p): m.rgb.get(p) for p in kl.PAD_LEDS}
    assert m.mono.get(kl.LED_STOP) == kl.LED_ON and m.mono.get(kl.LED_PLAY) == kl.LED_OFF
    assert m.mono.get(kl.LED_RECORD) == kl.LED_OFF
    assert m.lcd == ("1 - Kick", "Pattern 1")
    assert rig.host.errors == []


def test_the_paint_after_init_costs_nothing_when_fl_does_send_the_refresh(host_factory, target):
    """The frames are the same ones the OnRefresh queued: the shadow/pending state de-duplicates them."""
    from tests.flsim.rig import Rig

    def run(refresh):
        h = host_factory()
        s = h.load(target.path)
        s.boot(order=BOOT_ORDER, **({} if refresh else {"refresh_flags": None}))
        rig = Rig(h, s)
        rig.settle(3.0)
        out = (len(h.sysex), h.device_model().state())
        host_factory.close(h)
        return out
    with_refresh, without = run(True), run(False)
    assert with_refresh == without


def test_the_paint_after_init_waits_for_a_late_output_and_needs_no_refresh(make_rig):
    rig = _boot_without_refresh(make_rig, output_assigned=False)
    rig.idle(2.0)
    assert rig.host.sysex == []
    rig.host.set_output_assigned("entry", True)
    rig.idle(2.0)
    m = rig.host.device_model()
    assert all(m.rgb.get(p) == kl.RED for p in kl.PAD_LEDS)
    assert m.mono.get(kl.LED_STOP) == kl.LED_ON


def test_the_paint_after_init_happens_once(make_rig):
    rig = _boot_without_refresh(make_rig)
    rig.idle(0.15)                                   # before the keep-alive starts re-sending known frames
    n = sum(1 for m in rig.host.sysex if decode(m.data).kind == "led_rgb"
            and decode(m.data).fields["id"] in kl.PAD_LEDS)
    assert n == len(kl.PAD_LEDS), "each pad LED is written once at init, not once per repaint (%d)" % n


def test_the_init_paint_does_not_call_the_selected_channel_from_onidle_with_the_global_index_switch(make_rig):
    """The LCD label (Sync) is not part of the init paint: it was set in OnInit."""
    rig = _boot_without_refresh(make_rig, cfg={"GROUP_RELATIVE_CHANNELS": False})
    rig.idle(2.0)
    assert [c for c in rig.host.calls if c.qual == "channels.selectedChannel" and c.cb == "OnIdle"] == []


# ================================================================================================ OUT-1: keep-alive cycle

def _blank_and_watch(rig, seconds):
    """The keyboard forgets everything without telling FL; which of the objects it was showing are re-asserted, and when."""
    h = rig.host
    known = _led_keys(sent(h)) | ({("lcd", 0)} if h.device_model().lcd else set())
    t0 = h.clock.now
    m0 = h.mark()
    rig.idle(seconds)
    first = {}
    for msg in h.sysex[m0.sysex:]:
        f = decode(msg.data)
        k = ("lcd", 0) if f.kind == "lcd" else (f.kind, f.fields.get("id"))
        first.setdefault(k, msg.t - t0)
    return known, first


def test_every_led_is_re_asserted_within_the_keep_alive_cycle(make_rig):
    rig = boot(make_rig)
    rig.settle(5.0)
    known, first = _blank_and_watch(rig, 6.0)
    leds = {k for k in known if k[0] != "lcd"}
    assert leds and leds <= set(first), sorted(leds - set(first))
    assert max(first[k] for k in leds) <= 3.0 + 0.2, max(first[k] for k in leds)


def test_the_keep_alive_rate_is_bounded_and_far_below_the_stock_storm(make_rig):
    rig = boot(make_rig)
    rig.settle(5.0)
    h = rig.host
    t0 = h.clock.now
    m0 = h.mark()
    rig.idle(20.0)
    frames = h.since(m0).sysex
    per = [0] * 20
    for msg in frames:
        per[min(19, int(msg.t - t0))] += 1
    assert max(per) <= 20, per                       # OUT_KEEPALIVE_MIN_GAP_S = 0.05 s
    assert sum(per) / 20.0 >= 5, "about one frame per 68 ms is the cost of a 3 s cycle: %s" % per


def test_the_keep_alive_frames_change_nothing_on_the_keyboard(make_rig):
    rig = boot(make_rig)
    rig.settle(5.0)
    before = rig.host.device_model().state()
    rig.idle(10.0)
    assert rig.host.device_model().state() == before


def test_the_keep_alive_cycle_is_a_switch_and_zero_restores_the_legacy_trickle(make_rig):
    rig = boot(make_rig, cfg={"OUT_KEEPALIVE_CYCLE_S": 0})
    rig.settle(5.0)
    h = rig.host
    t0 = h.clock.now
    m0 = h.mark()
    rig.idle(20.0)
    per = [0] * 20
    for msg in h.since(m0).sysex:
        per[min(19, int(msg.t - t0))] += 1
    assert max(per) <= 2, per                        # one frame per OUT_TRICKLE_S plus the odd LCD frame


def test_a_larger_cycle_spreads_the_re_assertion(make_rig):
    rig = boot(make_rig, cfg={"OUT_KEEPALIVE_CYCLE_S": 10.0})
    rig.settle(5.0)
    known, first = _blank_and_watch(rig, 12.0)
    leds = {k for k in known if k[0] != "lcd"}
    assert leds <= set(first) and 3.5 < max(first[k] for k in leds) <= 10.5


def test_the_keep_alive_never_runs_while_the_trickle_is_off(make_rig):
    rig = boot(make_rig, cfg={"OUT_TRICKLE_S": 0, "OUT_LCD_KEEPALIVE_S": 0})
    rig.settle(5.0)
    m0 = rig.host.mark()
    rig.idle(20.0)
    assert rig.host.since(m0).sysex == []


def test_the_keep_alive_min_gap_caps_the_rate(make_rig):
    rig = boot(make_rig, cfg={"OUT_KEEPALIVE_CYCLE_S": 0.5, "OUT_KEEPALIVE_MIN_GAP_S": 0.2})
    rig.settle(5.0)
    h = rig.host
    t0 = h.clock.now
    m0 = h.mark()
    rig.idle(10.0)
    per = [0] * 10
    for msg in h.since(m0).sysex:
        per[min(9, int(msg.t - t0))] += 1
    assert max(per) <= 6, per                        # 5/s keep-alive + the odd LCD frame


# ================================================================================================ OUT-1: settle repaints

def _reasserted_between(rig, t_from, t_to):
    h = rig.host
    return _led_keys([decode(m.data) for m in h.sysex if t_from <= m.t < t_to])


def test_a_memory_switch_is_repainted_again_after_the_keyboard_has_finished_its_own_reset(make_rig):
    """The keyboard may still be blanking its LEDs when the immediate repaint lands: everything is written again at +0.5 s
    (and +2 s), long before the round-robin keep-alive would come back to each LED."""
    rig = boot(make_rig)
    rig.settle(6.0)
    known = _led_keys(sent(rig.host))
    t_switch = rig.host.clock.now
    rig.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH)
    rig.idle(2.0)
    late = _reasserted_between(rig, t_switch + 0.3, t_switch + 1.4)
    assert known <= late, sorted(known - late)


def test_the_settle_repaints_are_a_switch(make_rig):
    rig = boot(make_rig, cfg={"OUT_SETTLE_REPAINT_S": ()})
    rig.settle(6.0)
    known = _led_keys(sent(rig.host))
    t_switch = rig.host.clock.now
    rig.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH)
    rig.idle(2.0)
    late = _reasserted_between(rig, t_switch + 0.3, t_switch + 1.4)
    assert not known <= late, "without the settle repaints only the keep-alive is left to re-assert them"


def test_a_full_refresh_request_is_repainted_again_too(make_rig):
    rig = boot(make_rig)
    rig.settle(6.0)
    known = _led_keys(sent(rig.host))
    t0 = rig.host.clock.now
    rig.capture(lambda: rig.entry.call("OnDoFullRefresh"))
    rig.idle(2.0)
    assert known <= _reasserted_between(rig, t0 + 0.3, t0 + 1.4)


def test_the_settle_repaints_do_not_repeat_forever(make_rig):
    rig = boot(make_rig)
    rig.settle(6.0)
    rig.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH)
    rig.idle(5.0)                                    # both settle repaints are done
    h = rig.host
    t0 = h.clock.now
    m0 = h.mark()
    rig.idle(10.0)
    assert len(h.since(m0).sysex) <= 10 * 20         # only the bounded keep-alive


def test_a_new_event_restarts_the_settle_schedule_instead_of_stacking(make_rig):
    rig = boot(make_rig)
    rig.settle(6.0)
    for _ in range(5):
        rig.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH)
        rig.idle(0.1)
    rig.idle(4.0)
    assert rig.host.errors == [] and len([1 for m in rig.host.sysex if m.t > rig.host.clock.now - 4.0]) < 400


def test_settle_repaints_stay_inside_the_hard_frame_cap(make_rig):
    rig = boot(make_rig)
    rig.settle(6.0)
    t0 = rig.host.clock.now
    rig.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH)
    rig.idle(4.0)
    times = [m.t for m in rig.host.sysex if m.t >= t0]
    worst = max(sum(1 for u in times if t <= u < t + 0.999) for t in times)
    assert worst <= 100, worst                       # OUT_MAX_SYSEX_PER_SEC, over any sliding second


# ================================================================================================ malformed values

NEW_SWITCHES = ["OUT_DEFER_TO_IDLE", "OUT_DEFER_TIMEOUT_S", "OUT_KEEPALIVE_CYCLE_S", "OUT_KEEPALIVE_MIN_GAP_S",
                "OUT_SETTLE_REPAINT_S", "OUT_REQUIRE_MIDIOUT_ASSIGNED", "LOG_DEVICE_DETAILS", "LOG_RETRY_S"]


@pytest.mark.parametrize("name", NEW_SWITCHES)
def test_a_malformed_value_of_a_review_round_1_switch_never_raises_or_crashes(make_rig, name):
    """A string, None, a negative number, an empty container: the layer falls back to the default (or switches the feature off),
    and the session still ends with a keyboard that shows the LCD greeting. Same convention as test_output_fuzz.py."""
    rig = make_rig(boot=False)
    rig.host.set_config(LOG_MAX_LINES_PER_SEC=100000)
    for junk in ("x", None, -5, 0, [], {}, 1e12):
        rig.host.set_config(**{name: junk})
        rig.scripts.boot(order=BOOT_ORDER)
        rig.idle(3.0)
        rig.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH)
        rig.capture(lambda: rig.entry.call("OnDoFullRefresh"))
        rig.idle(3.0)
        rig.tap(kl.BTN_PLAY)
        rig.scripts.deinit()
        assert rig.host.errors == [] and rig.host.violations == [], (name, junk, rig.host.errors[:1])
        swallowed = [l for l in log_lines(rig.host) if "EXC in" in l or " failed: " in l]      # the layers catch their own errors
        assert swallowed == [], (name, junk, swallowed[:2])
