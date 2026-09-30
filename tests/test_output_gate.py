"""The output gate (O-01) and the diagnostics around it (O-15): nothing is sent to the keyboard unless FL says the script
has a MIDI output, whatever FL does when it has not (crash or no-op), and the log says what happened.

Leading hypothesis for the FL 26.1.6 crash (docs/incidents/2026-09-29-fl-crash-kl-probe.crash.txt): a native null read
from a device.* call while the script's MIDI output is not assigned. The stock scripts call device.midiOutSysex without
ever asking. The simulator models both possibilities (Host.crash_on_unassigned_output)."""
from __future__ import annotations

import pytest

from tests import kl
from tests.flsim import FLCrash
from tests.flsim.sysex import HEADER, DEINIT_PAYLOAD
from tests.test_output_support import boot, entry_module, log_lines, printed, sent, tuned_only  # noqa: F401

MEMORY_SWITCH = kl.SYSEX_MEMORY_SWITCH


def _exercise(rig, seconds=3.0):
    """Every callback and a few controls, the way a session would."""
    rig.idle(seconds)
    rig.refresh()
    rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 1))
    rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 0))
    rig.entry.deliver_sysex(MEMORY_SWITCH)
    rig.tap(kl.BTN_PLAY)
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.fader(1, 100)
    rig.idle(1.0)


# ================================================================================================ never without an output

@pytest.mark.parametrize("crash", [True, False], ids=["fl-crashes", "fl-ignores"])
def test_no_frame_and_no_crash_when_no_output_is_assigned(make_rig, crash):
    rig = boot(make_rig, output_assigned=False, crash_on_unassigned_output=crash)
    try:
        _exercise(rig)
        rig.scripts.deinit()
    except FLCrash as c:
        pytest.fail("FL would have crashed: %s" % c.reason)
    h = rig.host
    assert h.calls_to("device.midiOutSysex") == [] and h.dropped_sysex == []
    assert h.errors == []


def test_the_only_device_call_made_without_an_output_is_isassigned(make_rig):
    """The stub documents isAssigned() as the guard; getName/getPortNumber/isMidiOutAssigned/getDeviceID are not asked
    while the script has no output (one of them is the likeliest culprit of the tom crash if isAssigned is not)."""
    rig = boot(make_rig, output_assigned=False)
    _exercise(rig)
    rig.scripts.deinit()
    used = {c.qual for c in rig.host.calls if c.qual.startswith("device.")}
    assert used == {"device.isAssigned"}, used


def test_no_device_call_at_import_time(make_rig):
    rig = make_rig(boot=False)
    assert rig.host.calls == []


def test_unassigned_output_is_reported_once_in_the_log_and_once_on_screen(make_rig):
    rig = boot(make_rig, output_assigned=False)
    _exercise(rig, 5.0)
    h = rig.host
    msgs = log_lines(h, "no MIDI output for this script")
    assert len(msgs) == 1 and "Options > MIDI settings" in msgs[0] and "isAssigned() is False" in msgs[0]
    assert len(printed(h, "no MIDI output for this script")) == 1


def test_asking_fl_again_while_unassigned_is_rate_limited(make_rig):
    rig = boot(make_rig, output_assigned=False, cfg={"OUT_UNASSIGNED_RECHECK_S": 0.5})
    n0 = len(rig.host.calls_to("device.isAssigned"))
    rig.idle(10.0)
    asked = len(rig.host.calls_to("device.isAssigned")) - n0
    assert 15 <= asked <= 25, "asked FL %d times in 10 s (expected about every 0.5 s)" % asked


def test_assigned_output_is_asked_before_every_frame_that_leaves_in_one_burst_of_callbacks(make_rig):
    rig = boot(make_rig)
    rig.idle(2.0)
    calls = rig.host.api_calls()
    asked_before_send = []
    asked = 0
    for c in calls:
        if c.qual == "device.isAssigned":
            asked += 1
        elif c.qual == "device.midiOutSysex":
            asked_before_send.append(asked)
    assert asked_before_send and asked_before_send[0] >= 1
    # never one query per frame: a flush of pending frames asks once
    assert len(rig.host.calls_to("device.isAssigned")) < len(asked_before_send)


# ================================================================================================ isMidiOutAssigned

def _patch_ismidioutassigned(value=None, exc=None):
    import device

    def fn():
        if exc is not None:
            raise exc
        return value
    device.isMidiOutAssigned = fn


def test_a_false_ismidioutassigned_blocks_sending_even_when_isassigned_is_true(make_rig):
    rig = make_rig(boot=False)
    _patch_ismidioutassigned(False)
    rig.scripts.boot(order=("forward", "entry"))
    rig.idle(3.0)
    rig.refresh()
    assert rig.host.calls_to("device.midiOutSysex") == []
    assert any("isMidiOutAssigned() is False" in l for l in log_lines(rig.host))


def test_the_ismidioutassigned_requirement_can_be_switched_off(make_rig):
    rig = make_rig(boot=False)
    _patch_ismidioutassigned(False)
    rig.host.set_config(OUT_REQUIRE_MIDIOUT_ASSIGNED=False)
    rig.scripts.boot(order=("forward", "entry"))
    rig.settle(3.0)
    assert rig.host.device_model().lcd == ("1 - Kick", "Pattern 1")


def test_ismidioutassigned_is_not_asked_when_isassigned_is_false(make_rig):
    rig = boot(make_rig, output_assigned=False)
    rig.idle(3.0)
    assert rig.host.calls_to("device.isMidiOutAssigned") == []


def test_a_missing_ismidioutassigned_falls_back_to_isassigned(make_rig):
    """Some FL build without the undocumented function: isAssigned() alone decides."""
    rig = make_rig(boot=False)
    import device
    del device.isMidiOutAssigned          # module attribute of the fake
    rig.scripts.boot(order=("forward", "entry"))
    rig.settle(3.0)
    assert rig.host.device_model().lcd == ("1 - Kick", "Pattern 1")
    assert rig.host.errors == []


# ================================================================================================ unanswerable queries fail safe

@pytest.mark.parametrize("query", ["device.isAssigned", "device.isMidiOutAssigned"])
def test_a_query_that_raises_means_not_assigned(make_rig, query):
    rig = make_rig(boot=False)
    rig.host.inject_fault(query, RuntimeError)
    rig.scripts.boot(order=("forward", "entry"))
    rig.idle(3.0)
    rig.refresh()
    assert rig.host.calls_to("device.midiOutSysex") == []
    assert rig.host.errors == []
    assert any(query + "() raised" in l for l in log_lines(rig.host))


def test_output_resumes_and_repaints_once_the_query_answers_again(make_rig):
    rig = make_rig(boot=False)
    rig.host.inject_fault("device.isAssigned", RuntimeError)
    rig.scripts.boot(order=("forward", "entry"))
    rig.idle(2.0)
    assert rig.host.sysex == []
    rig.host.clear_faults()
    rig.settle(3.0)
    m = rig.host.device_model()
    assert m.lcd == ("1 - Kick", "Pattern 1")
    assert all(m.rgb[p] == kl.RED for p in kl.PAD_LEDS) and m.rgb[kl.SELECT_LEDS[0]] == kl.YELLOW


# ================================================================================================ assignment changes at run time

def test_assigning_the_output_later_repaints_everything(make_rig):
    rig = boot(make_rig, output_assigned=False)
    rig.state.muted_channels.add(3)
    rig.idle(2.0)
    assert rig.host.sysex == []
    rig.host.set_output_assigned("entry", True)
    rig.settle(3.0)
    m = rig.host.device_model()
    assert m.lcd == ("1 - Kick", "Pattern 1")
    assert all(m.rgb[p] == kl.RED for p in kl.PAD_LEDS)
    assert m.rgb[kl.SELECT_LEDS[3]] == kl.RED and m.rgb[kl.SELECT_LEDS[0]] == kl.YELLOW
    assert m.mono[kl.LED_STOP] == kl.LED_ON and all(m.mono[i] == kl.LED_ON for i in kl.LED_STEADY)
    assert any("output is now assigned" in l for l in log_lines(rig.host))


def test_unassigning_the_output_at_run_time_stops_all_traffic_without_a_crash(make_rig):
    rig = boot(make_rig)
    rig.settle(3.0)
    rig.host.set_output_assigned("entry", False)
    m0 = rig.host.mark()
    try:
        _exercise(rig)
    except FLCrash as c:
        pytest.fail("FL would have crashed: %s" % c.reason)
    assert rig.host.since(m0).sysex == [] and rig.host.errors == []


def test_output_that_comes_back_after_being_unassigned_is_repainted(make_rig):
    rig = boot(make_rig)
    rig.settle(3.0)
    rig.host.set_output_assigned("entry", False)
    rig.idle(2.0)
    rig.state.muted_channels.add(2)
    rig.idle(1.0)
    rig.host.set_output_assigned("entry", True)
    rig.settle(3.0)
    m = rig.host.device_model()
    assert m.rgb[kl.SELECT_LEDS[2]] == kl.RED
    assert m.lcd == ("1 - Kick", "Pattern 1")


# ================================================================================================ kill switch and failing sends

def test_the_master_kill_switch_sends_nothing(make_rig):
    rig = boot(make_rig, cfg={"OUT_ENABLED": False})
    _exercise(rig)
    rig.scripts.deinit()
    assert rig.host.calls_to("device.midiOutSysex") == [] and rig.host.errors == []
    assert any("DISABLED" in l for l in log_lines(rig.host)) or any("OUT_ENABLED" in l for l in log_lines(rig.host))


def test_a_failing_midioutsysex_backs_off_and_recovers(make_rig):
    rig = make_rig(boot=False)
    rig.host.set_config(OUT_FAIL_BACKOFF_S=2.0)
    rig.host.inject_fault("device.midiOutSysex", RuntimeError)
    rig.scripts.boot(order=("forward", "entry"))
    rig.idle(1.5)
    tried = len(rig.host.calls_to("device.midiOutSysex"))
    assert 5 <= tried <= 8, "5 failures then a pause, not a hammering port: %d attempts in 1.5 s" % tried
    assert rig.host.errors == [] and rig.host.sysex == []
    assert len(log_lines(rig.host, "midiOutSysex raised")) == 1
    assert any("pausing output for 2.0 s" in l for l in log_lines(rig.host))
    rig.host.clear_faults()
    rig.settle(4.0)                                # the back-off ends, everything is repainted
    assert rig.host.device_model().lcd == ("1 - Kick", "Pattern 1")


# ================================================================================================ after OnDeInit

def test_nothing_is_sent_after_ondeinit_until_the_next_oninit(make_rig):
    rig = boot(make_rig)
    rig.settle(3.0)
    rig.entry.call("OnDeInit")
    m0 = rig.host.mark()
    rig.idle(2.0)
    rig.refresh()
    rig.capture(lambda: rig.entry.call("OnUpdateBeatIndicator", 1))
    rig.entry.deliver_sysex(MEMORY_SWITCH)
    rig.tap(kl.BTN_PLAY)
    rig.fader(1, 90)
    rig.entry.call("OnDeInit")                     # a second deinit is harmless
    assert rig.host.since(m0).sysex == [] and rig.host.errors == []
    rig.entry.call("OnInit")
    rig.entry.call("OnRefresh", 0x1FFFF)
    rig.settle(3.0)
    assert rig.host.device_model(since=m0).lcd == ("1 - Kick", "Pattern 1")


def test_deinit_frames_are_byte_identical_to_stock(make_rig):
    rig = boot(make_rig)
    rig.settle(3.0)
    m0 = rig.host.mark()
    rig.entry.call("OnDeInit")
    v = rig.host.since(m0)
    assert any(x.data == HEADER + DEINIT_PAYLOAD + b"\xf7" for x in v.sysex)
    assert rig.host.device_model(since=m0).lcd == ("KeyLab mkII", "Disconnected")


def test_deinit_frame_and_led_clearing_are_switches(make_rig):
    rig = boot(make_rig, cfg={"SEND_DEINIT_FRAME": False, "CLEAR_LEDS_ON_DEINIT": True})
    rig.settle(3.0)
    m0 = rig.host.mark()
    rig.entry.call("OnDeInit")
    m = rig.host.device_model(since=m0)
    assert m.deinit_times == [] and m.lcd == ("KeyLab mkII", "Disconnected")
    assert all(m.rgb[p] == kl.OFF for p in kl.PAD_LEDS + kl.SELECT_LEDS + [kl.LED_MULTI])


def test_deinit_with_the_output_unassigned_sends_nothing(make_rig):
    rig = boot(make_rig, output_assigned=False)
    rig.idle(1.0)
    rig.scripts.deinit()
    assert rig.host.calls_to("device.midiOutSysex") == [] and rig.host.errors == []


# ================================================================================================ the init banner (O-15)

def test_the_init_banner_says_what_fl_did(make_rig):
    rig = boot(make_rig)
    lines = log_lines(rig.host, "KeyLab mkII (tuned) v")
    assert len(lines) == 1
    line = lines[0]
    mod = entry_module()
    assert ("v" + mod.KLT_VERSION) in line and "python 3.12" in line
    assert "FL api 45" in line and "device.isAssigned=True" in line and "isMidiOutAssigned=True" in line
    assert "port=0" in line and "name='MIDIIN2 (KeyLab mkII 88)'" in line and "output=on" in line
    assert printed(rig.host, "OnInit start") and printed(rig.host, "OnInit done")
    assert printed(rig.host, "device.isAssigned=True")


def test_the_banner_without_an_output_says_so_and_asks_nothing_else(make_rig):
    rig = boot(make_rig, output_assigned=False)
    (line,) = log_lines(rig.host, "KeyLab mkII (tuned) v")
    assert "device.isAssigned=False" in line and "not queried" in line
    assert "port=" not in line and "name=" not in line


def test_the_banner_warns_about_port_10(make_rig):
    rig = make_rig(boot=False)
    rig.host.port_numbers["entry"] = 10
    rig.scripts.boot(order=("forward", "entry"))
    assert any("port 10" in l and "Analog Lab" in l for l in log_lines(rig.host, "WARNING"))


def test_the_device_id_is_not_asked_by_default(make_rig):
    rig = boot(make_rig)
    assert rig.host.calls_to("device.getDeviceID") == []


def test_the_device_id_is_logged_on_request(make_rig):
    rig = boot(make_rig, cfg={"LOG_DEVICE_ID": True})
    assert rig.host.calls_to("device.getDeviceID") != [] and any("deviceID=" in l for l in log_lines(rig.host))


def test_every_oninit_writes_its_own_banner(make_rig):
    rig = boot(make_rig)
    rig.entry.call("OnDeInit")
    rig.entry.call("OnInit")
    assert len(log_lines(rig.host, "KeyLab mkII (tuned) v")) == 2


# ================================================================================================ crash post-mortem (O-15)

@pytest.mark.parametrize("call,needle", [
    ("general.getVersion", "general.getVersion()"),
    ("device.isAssigned", "device.isAssigned()"),
    ("device.isMidiOutAssigned", "device.isMidiOutAssigned()"),
    ("device.getPortNumber", "device.getPortNumber()"),
    ("device.getName", "device.getName()"),
    ("device.midiOutSysex", "device.midiOutSysex() for the first time"),
])
def test_if_fl_dies_inside_a_native_call_the_last_line_of_the_log_names_it(make_rig, call, needle):
    """The FL 26.1.6 crash was a native null read: nothing can be caught. Every native call of the attach path is announced
    in klt.log first (append + close per line), so a crash leaves the culprit as the last line on disk."""
    from tests.flsim.host import FLCrash
    rig = make_rig(boot=False)
    rig.host.inject_fault(call, FLCrash("boom", call))
    with pytest.raises(FLCrash):
        rig.scripts.boot(order=("forward", "entry"))
    assert needle in log_lines(rig.host)[-1], log_lines(rig.host)[-3:]


def test_with_details_off_and_no_midiout_requirement_isassigned_is_the_only_query(make_rig):
    rig = boot(make_rig, cfg={"LOG_DEVICE_DETAILS": False, "OUT_REQUIRE_MIDIOUT_ASSIGNED": False})
    _exercise(rig)
    rig.scripts.deinit()
    used = {c.qual for c in rig.host.calls if c.qual.startswith("device.")}
    assert used == {"device.isAssigned", "device.midiOutSysex"}, used
    assert any("LOG_DEVICE_DETAILS is off" in l for l in log_lines(rig.host, "KeyLab mkII (tuned) v"))


def test_the_gate_announces_each_native_query_once_per_oninit(make_rig):
    rig = boot(make_rig)
    rig.settle(2.0)
    assert len(log_lines(rig.host, "gate: about to call device.isAssigned()")) == 1
    assert len(log_lines(rig.host, "gate: about to call device.isMidiOutAssigned()")) == 1
    assert len(log_lines(rig.host, "gate: about to call device.midiOutSysex()")) == 1


def test_the_message_names_the_switch_when_isMidiOutAssigned_is_what_says_no(make_rig):
    rig = make_rig(boot=False)
    _patch_ismidioutassigned(False)
    rig.scripts.boot(order=("forward", "entry"))
    (msg,) = log_lines(rig.host, "no MIDI output for this script")
    assert "OUT_REQUIRE_MIDIOUT_ASSIGNED = False" in msg
    assert "OUT_REQUIRE_MIDIOUT_ASSIGNED" not in "".join(log_lines(rig.host, "isAssigned() is False"))
