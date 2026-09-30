"""Seeded fuzz of the output side under non-default KLTConfig switches (the default configuration is covered by
test_fuzz.py): random events on both ports x random FL states x every callback, with a switch set that stresses the gate,
the budgets, the init animation and the splash. No exception may escape, FL must never crash, every frame is well framed
and the hard per-second budget holds throughout."""
from __future__ import annotations

import math

import pytest

from tests.conftest import BOOT_ORDER
from tests.flsim import streams
from tests.flsim.host import FLCrash, Host
from tests.flsim.state import FLState
from tests.test_output_support import tuned_only  # noqa: F401

EVENTS = 6000
SEED = 20260930
# exceptions from the callbacks the output side owns; the input callbacks (OnMidiIn/OnMidiMsg/OnPitchBend...) have their own
# fuzz in test_fuzz.py and must not make this file's verdict depend on the input side
OUTPUT_CALLBACKS = {"OnInit", "OnDeInit", "OnIdle", "OnRefresh", "OnUpdateBeatIndicator", "OnSysEx", "OnDoFullRefresh",
                    "OnProjectLoad"}

CONFIGS = {
    "tight-budgets": dict(OUT_MAX_SYSEX_PER_SEC=12, OUT_MAX_SYSEX_PER_TICK=1, OUT_LCD_MIN_GAP_S=0.25),
    "stock-animation-and-flip": dict(INIT_ANIMATION=2, PAD_LED_FLIP_ROWS=True, SAVE_LED_FOLLOWS_MODE=True, INIT_FRAMES_PER_TICK=2),
    "no-keepalive-noisy-refresh": dict(OUT_TRICKLE_S=0, OUT_LCD_KEEPALIVE_S=0, REFRESH_IGNORE_NOISY_FLAGS=True,
                                       OUT_LED_PASS_S=0.0, SPLASH_MS=0, SPLASH_TAG_MS=0),
    "global-index-no-reset": dict(GROUP_RELATIVE_CHANNELS=False, RESET_HELPER_STATE_ON_INIT=False, LCD_SCROLL_MS=50,
                                  SEND_DEINIT_FRAME=False, CLEAR_LEDS_ON_DEINIT=True),
    "broken-values": dict(OUT_MAX_SYSEX_PER_SEC="many", OUT_TICK_S=None, INIT_FRAMES_PER_TICK="x", LCD_SCROLL_MS=-5,
                          OUT_LED_PASS_S="soon", INIT_ANIMATION="2"),
}


def _fuzz(folder, cfg, assigned, events=EVENTS, seed=SEED):
    """Returns (exceptions in output callbacks, FL crashes, framing violations, worst SysEx in any sliding second, total)."""
    exceptions, crashes, framing, worst = [], [], 0, 0
    sent = 0
    with Host(output_assigned=assigned, record_calls=False) as host:
        for ep in streams.episodes(seed, events, 250):
            host.state = FLState()
            host.clear_trace()
            host.midi_in_populated = ep.midi_in_populated
            scripts = host.load(folder)
            host.set_config(**cfg)
            try:
                scripts.boot(order=BOOT_ORDER)
                for op in ep.ops:
                    streams.apply_op(scripts, op)
                for _ in range(400):
                    streams.apply_op(scripts, ("idle",))
                scripts.deinit()
            except FLCrash as c:
                crashes.append(c.reason)
            exceptions += [(e.callback, type(e.exc).__name__, e.site) for e in host.errors if e.callback in OUTPUT_CALLBACKS]
            framing += sum(1 for v in host.violations if v.kind == "sysex-framing")
            times = [m.t for m in host.sysex]
            sent += len(times)
            j = 0
            for i, t in enumerate(times):                     # worst sliding second (two pointers)
                while times[i] - times[j] >= 1.0 - 1e-6:
                    j += 1
                worst = max(worst, i - j + 1)
    return exceptions, crashes, framing, worst, sent


@pytest.mark.fuzz
@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_output_switches_never_make_a_callback_raise_or_flood(target, name):
    cfg = CONFIGS[name]
    exceptions, crashes, framing, worst, sent = _fuzz(target.path, cfg, assigned=True)
    assert crashes == [] and framing == 0
    assert exceptions == [], "%d exceptions in output callbacks, e.g. %s" % (len(exceptions), exceptions[:2])
    assert sent > 0
    cap = cfg.get("OUT_MAX_SYSEX_PER_SEC")
    if isinstance(cap, int):
        assert worst <= cap, "%d frames in one second (cap %d)" % (worst, cap)
    else:
        assert worst <= 100                                    # a broken value falls back to the default cap


@pytest.mark.fuzz
@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_output_switches_are_safe_without_an_output(target, name):
    exceptions, crashes, framing, worst, sent = _fuzz(target.path, CONFIGS[name], assigned=False, events=2500)
    assert crashes == [], crashes[:2]
    assert exceptions == [], exceptions[:2]
    assert sent == 0
