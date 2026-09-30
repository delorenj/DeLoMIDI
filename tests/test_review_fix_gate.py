"""Review round 1, host safety (R-HS-02, RA-10, R-HS-05): what the tuned DEFAULT asks FL for, and when.

The FL 26.1.6 crash on tom is a native null read reached from a device.* / general.* call; which call is unproven. The
default config therefore makes the fewest native calls that still work (device.isAssigned() is the only query, as in
Image-Line's MackieCU), makes none of them from inside OnInit except that one, and sends no SysEx from inside OnInit. The
richer diagnostics are a documented "probe profile" (LOG_DEVICE_DETAILS, OUT_REQUIRE_MIDIOUT_ASSIGNED), opt-in.

Nothing here says anything about real FL: it pins what the SCRIPTS do, against the strict simulator."""
from __future__ import annotations

import pytest

from tests import kl
from tests.flsim import FLCrash
from tests.test_output_support import boot, entry_module, log_lines, printed, sent, tuned_only  # noqa: F401

PROBE_PROFILE = {"LOG_DEVICE_DETAILS": True, "OUT_REQUIRE_MIDIOUT_ASSIGNED": True}


def _session(rig):
    """Every callback the way a session runs them."""
    rig.idle(3.0)
    rig.refresh()
    rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 1))
    rig.entry.deliver_sysex(kl.SYSEX_MEMORY_SWITCH)
    rig.tap(kl.BTN_PLAY)
    rig.fader(1, 100)
    rig.idle(1.0)
    rig.scripts.deinit()


def _device_quals(host, calls=None):
    return {c.qual for c in (host.calls if calls is None else calls) if c.qual.startswith(("device.", "general."))}


# ================================================================================================ the default's native calls

def test_the_default_asks_fl_only_for_isassigned_and_sends(make_rig):
    """R-HS-02 / RA-10: isMidiOutAssigned (crash-warned, undocumented), getPortNumber, getName, getDeviceID and
    general.getVersion are not part of the default attach path."""
    rig = boot(make_rig)
    _session(rig)
    assert _device_quals(rig.host) == {"device.isAssigned", "device.midiOutSysex"}, sorted(_device_quals(rig.host))


def test_the_shipped_switches_are_the_minimal_profile(make_rig):
    rig = make_rig(boot=False)
    import KLTConfig
    assert KLTConfig.OUT_REQUIRE_MIDIOUT_ASSIGNED is False
    assert KLTConfig.LOG_DEVICE_DETAILS is False
    assert KLTConfig.LOG_DEVICE_ID is False
    assert rig.host.calls == []


def test_oninit_makes_exactly_one_device_call_isassigned(make_rig):
    """RA-10: inside OnInit the only device.* / general.* call is the documented isAssigned() of the banner."""
    rig = make_rig(boot=False)
    m = rig.host.mark()
    rig.scripts.boot(order=("forward", "entry"))
    in_init = [c for c in rig.host.since(m).calls if c.cb == "OnInit" and c.qual.startswith(("device.", "general."))]
    assert [c.qual for c in in_init] == ["device.isAssigned"], [c.qual for c in in_init]


def test_no_sysex_leaves_from_inside_oninit_or_onrefresh(make_rig):
    """RA-10b: the tom probe died inside OnInit. Frames asked for there wait for the first OnIdle tick."""
    rig = make_rig(boot=False)
    m = rig.host.mark()
    rig.scripts.boot(order=("forward", "entry"))
    assert [c for c in rig.host.since(m).calls if c.qual == "device.midiOutSysex"] == []
    assert not any(c.qual == "device.isAssigned" and c.cb != "OnInit" for c in rig.host.since(m).calls), \
        "the gate must not be asked before the first OnIdle tick"
    rig.idle(ticks=1)
    first = [c for c in rig.host.since(m).calls if c.qual == "device.midiOutSysex"]
    assert first and {c.cb for c in first} == {"OnIdle"}


def test_the_welcome_lcd_frame_is_the_first_frame_and_arrives_with_the_first_idle_tick(make_rig):
    rig = make_rig(boot=False)
    rig.scripts.boot(order=("forward", "entry"))
    rig.idle(ticks=1)
    frames = sent(rig.host)
    assert frames and frames[0].kind == "lcd", [f.kind for f in frames[:3]]
    assert frames[0].fields["line1"].startswith("KeyLab mkII")


def test_the_deferral_is_a_switch(make_rig):
    """OUT_DEFER_TO_IDLE=False restores the sends from inside OnInit (stock timing)."""
    rig = make_rig(boot=False)
    rig.host.set_config(OUT_DEFER_TO_IDLE=False)
    m = rig.host.mark()
    rig.scripts.boot(order=("forward", "entry"))
    inside = [c for c in rig.host.since(m).calls if c.qual == "device.midiOutSysex" and c.cb == "OnInit"]
    assert inside, "with the deferral off the welcome frame leaves from OnInit"


def test_a_script_that_never_gets_an_idle_tick_still_sends_after_the_defer_timeout(make_rig):
    """The deferral is bounded by OUT_DEFER_TIMEOUT_S: if OnIdle never runs, the other callbacks send as they always did."""
    rig = boot(make_rig)                             # OnInit + OnRefresh, no OnIdle
    rig.host.advance(2.0)
    rig.refresh()
    assert rig.host.sysex == [], "still inside the default 3 s deferral"
    rig.host.advance(1.5)
    rig.refresh()
    assert rig.host.sysex and {m.callback for m in rig.host.sysex} == {"OnRefresh"}


def test_the_defer_timeout_is_a_switch(make_rig):
    rig = boot(make_rig, cfg={"OUT_DEFER_TIMEOUT_S": 1.0})
    rig.host.advance(1.2)
    rig.refresh()
    assert rig.host.sysex, "with a 1 s timeout the refresh after 1.2 s sends"


def test_deferral_and_immediate_send_end_on_the_same_keyboard_state(host_factory, target):
    from tests.conftest import BOOT_ORDER
    from tests.flsim.rig import Rig

    def run(cfg):
        h = host_factory()
        s = h.load(target.path)
        h.set_config(**cfg)
        s.boot(order=BOOT_ORDER)
        rig = Rig(h, s)
        rig.settle(4.0)
        st = h.device_model().state()
        host_factory.close(h)
        return st
    assert run({}) == run({"OUT_DEFER_TO_IDLE": False})


def test_a_deinit_before_the_first_idle_sends_only_the_deinit_frame(make_rig):
    """Nothing was ever shown on the keyboard (the welcome frame was still queued), so there is nothing to say goodbye to;
    stock's deinit frame is unchanged and nothing raises."""
    rig = make_rig(boot=False)
    rig.scripts.boot(order=("forward", "entry"))
    rig.scripts.deinit()
    m = rig.host.device_model()
    assert m.lcd is None and len(m.deinit_times) == 1 and rig.host.errors == []
    rig.idle(1.0)
    assert len(rig.host.device_model().deinit_times) == 1, "nothing more leaves after OnDeInit"


def test_a_deinit_after_the_first_idle_still_says_goodbye(make_rig):
    rig = boot(make_rig)
    rig.settle(4.0)
    rig.scripts.deinit()
    m = rig.host.device_model()
    assert m.lcd == ("KeyLab mkII", "Disconnected") and len(m.deinit_times) == 1


def test_an_unassigned_output_is_still_never_written_to_with_the_deferral(make_rig):
    rig = boot(make_rig, output_assigned=False, crash_on_unassigned_output=True)
    try:
        _session(rig)
    except FLCrash as c:
        pytest.fail("FL would have crashed: %s" % c.reason)
    assert rig.host.calls_to("device.midiOutSysex") == []
    assert _device_quals(rig.host) == {"device.isAssigned"}


# ================================================================================================ isMidiOutAssigned (opt-in)

def _patch_ismidioutassigned(value=None, exc=None):
    """Replace the fake's device.isMidiOutAssigned; the returned list counts the calls made to it."""
    import device
    asked = []

    def fn():
        asked.append(1)
        if exc is not None:
            raise exc
        return value
    device.isMidiOutAssigned = fn
    return asked


@pytest.mark.parametrize("answer", [0, None, False, ""], ids=["0", "None", "False", "empty"])
def test_whatever_fl_answers_to_ismidioutassigned_the_default_keyboard_is_not_darkened(make_rig, answer):
    """R-HS-02: the false-negative exposure. With the default the undocumented query is never asked at all."""
    rig = make_rig(boot=False)
    asked = _patch_ismidioutassigned(answer)
    rig.scripts.boot(order=("forward", "entry"))
    rig.idle(3.0)
    assert rig.host.device_model().lcd == ("1 - Kick", "Pattern 1")
    assert asked == [], "the undocumented query is not asked in the default profile"


@pytest.mark.parametrize("answer,sends", [(True, True), (None, True), (0, True), (False, False)],
                         ids=["True", "None", "0", "False"])
def test_when_required_only_a_literal_false_refuses(make_rig, answer, sends):
    """The opt-in probe profile: `not out` used to close the gate for good on 0/None; now only a literal False (FL's
    documented bool answer for 'no') or an exception refuses, because isAssigned() already said yes."""
    rig = make_rig(boot=False)
    rig.host.set_config(OUT_REQUIRE_MIDIOUT_ASSIGNED=True)
    asked = _patch_ismidioutassigned(answer)
    rig.scripts.boot(order=("forward", "entry"))
    rig.idle(3.0)
    assert bool(rig.host.calls_to("device.midiOutSysex")) is sends
    assert asked != []


def test_when_required_an_exception_from_ismidioutassigned_refuses(make_rig):
    rig = make_rig(boot=False)
    rig.host.set_config(OUT_REQUIRE_MIDIOUT_ASSIGNED=True)
    _patch_ismidioutassigned(exc=RuntimeError("boom"))
    rig.scripts.boot(order=("forward", "entry"))
    rig.idle(3.0)
    assert rig.host.calls_to("device.midiOutSysex") == []
    assert any("isMidiOutAssigned() raised" in l for l in log_lines(rig.host))


def test_the_probe_profile_restores_every_diagnostic_call_and_the_banner(make_rig):
    rig = boot(make_rig, cfg=PROBE_PROFILE)
    rig.idle(2.0)
    assert {"device.isAssigned", "device.isMidiOutAssigned", "device.getPortNumber", "device.getName",
            "general.getVersion", "device.midiOutSysex"} <= _device_quals(rig.host)
    (line,) = log_lines(rig.host, "KeyLab mkII (tuned) v")
    assert "FL api 45" in line and "isMidiOutAssigned=True" in line and "port=0" in line


def test_the_default_banner_says_which_queries_were_skipped(make_rig):
    rig = boot(make_rig)
    (line,) = log_lines(rig.host, "KeyLab mkII (tuned) v")
    assert "device.isAssigned=True" in line and "LOG_DEVICE_DETAILS is off" in line
    assert "FL api" not in line or "not queried" in line


# ================================================================================================ R-HS-05: the wiring is loud

def test_the_log_states_the_port_rule_at_every_init(make_rig):
    rig = boot(make_rig)
    lines = log_lines(rig.host, "wiring:")
    assert len(lines) == 1
    text = lines[0]
    assert "no other MIDI output" in text and "same port number" in text
    assert "greeting" in text and "tuned v" in text, "the LCD greeting is the acceptance test"
    assert "port 0" not in text, "the default profile does not query the port number"


def test_with_details_on_the_wiring_line_names_the_numeric_port(make_rig):
    rig = boot(make_rig, cfg={"LOG_DEVICE_DETAILS": True})
    (text,) = log_lines(rig.host, "wiring:")
    assert "port 0" in text and "no other MIDI output may use port 0" in text


def test_the_first_event_names_the_numeric_port_without_a_native_call(make_rig):
    """R-HS-05 without getPortNumber: FlMidiMsg.port carries the number, once per OnInit."""
    rig = boot(make_rig)
    rig.host.port_numbers["entry"] = 3
    m = rig.host.mark()
    rig.tap(kl.BTN_PLAY)
    rig.tap(kl.BTN_PLAY)
    lines = [l for l in log_lines(rig.host, "wiring:") if "first event" in l]
    assert len(lines) == 1 and "port 3" in lines[0] and "no other MIDI output may use port 3" in lines[0]
    assert "device.getPortNumber" not in {c.qual for c in rig.host.since(m).calls}
    rig.entry.call("OnInit")
    rig.tap(kl.BTN_PLAY)
    assert len([l for l in log_lines(rig.host, "wiring:") if "first event" in l]) == 2, "once per OnInit"


def test_the_unassigned_message_states_the_port_rule(make_rig):
    rig = boot(make_rig, output_assigned=False)
    rig.idle(1.0)
    (msg,) = log_lines(rig.host, "no MIDI output for this script")
    assert "same port number" in msg and "no other MIDI output" in msg
    assert len(printed(rig.host, "no other MIDI output")) == 1


def test_a_true_gate_is_not_described_as_the_output_working(make_rig):
    rig = boot(make_rig)
    rig.idle(2.0)
    text = "\n".join(log_lines(rig.host))
    assert "first frame delivered" not in text and "output OK" not in text
    (line,) = log_lines(rig.host, "first frame handed to FL")
    assert "does not confirm" in line and "greeting" in line
