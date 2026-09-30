"""Tests of the flsim simulator itself: strictness, crash emulation, virtual clock, loader, event model, decoders.

They do not depend on the script folder under test (they build tiny throwaway script folders)."""
from __future__ import annotations

import inspect
import os
import sys
import textwrap
import time

import pytest

from tests.flsim import (DeviceModel, FLCrash, FlEvent, FLState, Host, RuleViolation, SessionDriver, decode)
from tests.flsim import streams, surface
from tests.flsim.fakes import IMPLS
from tests.flsim.fakes.pylib import DEFAULT_MIDI_PY
from tests.flsim.loader import detect_scripts, header_value
from tests.flsim.sysex import HEADER, lcd_frame, led_mono_frame, led_rgb_frame

pytestmark = pytest.mark.harness

_REAL_MONOTONIC = time.monotonic
_REAL_SLEEP = time.sleep
_REAL_TIME = time.time


def write_scripts(folder, entry, forward=None, helpers=None):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "device_Fake.py").write_text("# name=Fake entry\n" + textwrap.dedent(entry))
    if forward is not None:
        (folder / "device_FakeForward.py").write_text("# name=Fake forward\n# receiveFrom=Fake forward\n" + textwrap.dedent(forward))
    for name, src in (helpers or {}).items():
        (folder / name).write_text(textwrap.dedent(src))
    return folder


# ================================================================================================ the surface / fakes

def test_surface_has_every_native_module_and_the_python_lib_modules():
    data = surface.load_surface()
    for m in surface.API_MODULES:
        assert data[m], m
    assert "OnMidiIn" in surface.callback_names() and "OnIdle" in surface.callback_names()


def test_fake_modules_expose_exactly_the_surface(host):
    for name in surface.NATIVE_MODULES:
        mod = host.modules[name]
        exposed = sorted(k for k, v in vars(mod).items() if callable(v))
        assert exposed == surface.function_names(name), name


def test_modelled_functions_match_the_surface_signature():
    """A fake with a different parameter list than the official stub would accept calls FL rejects (or vice versa)."""
    problems = []
    for mod, cls in IMPLS.items():
        if cls is None:
            continue
        for fname in surface.function_names(mod):
            fn = getattr(cls, fname, None)
            if fn is None:
                continue
            sp = surface.spec(mod, fname)
            sig = [p for p in inspect.signature(fn).parameters.values() if p.name != "self"]
            names = [p.name for p in sig]
            required = len([p for p in sig if p.default is inspect.Parameter.empty])
            if names != sp.params or required != sp.required:
                problems.append("%s.%s: fake(%s) req=%d vs surface(%s) req=%d" % (mod, fname, names, required, sp.params, sp.required))
    assert not problems, "\n".join(problems)


def test_impl_with_a_function_not_in_the_surface_is_rejected(host):
    from tests.flsim.fakes.base import Impl, build_native_module

    class Bad(Impl):
        def notARealFunction(self):
            pass
    with pytest.raises(AssertionError, match="notARealFunction"):
        build_native_module(host, "ui", Bad(host))


def test_wrong_arity_raises_typeerror(host):
    ui, channels = host.modules["ui"], host.modules["channels"]
    with pytest.raises(TypeError):
        ui.getFocused()
    with pytest.raises(TypeError):
        ui.getFocused(1, 2)
    with pytest.raises(TypeError):
        ui.getProgTitle(1)
    with pytest.raises(TypeError):
        channels.setGridBit(0, 1)              # value is required
    with pytest.raises(TypeError):
        channels.getChannelName(0, False, 3)   # too many


def test_keyword_arguments_follow_the_surface(host):
    ch = host.modules["channels"]
    assert ch.getChannelName(index=0) == "Kick"
    assert ch.getChannelName(0, useGlobalIndex=True) == "Kick"
    with pytest.raises(TypeError):
        ch.getChannelName(0, noSuchKeyword=1)
    with pytest.raises(TypeError):
        ch.closeGraphEditor(index=1)           # positional-only in the stub


def test_argument_types_are_checked(host):
    ui, mixer, plugins, device = (host.modules[n] for n in ("ui", "mixer", "plugins", "device"))
    with pytest.raises(TypeError):
        ui.getFocused("1")
    with pytest.raises(TypeError):
        mixer.setTrackVolume(1.5, 0.5)         # float where an int track index is required
    with pytest.raises(TypeError):
        plugins.getParamValue(None, 0)         # the F-06 shape: an int parameter given None
    host.current = _FakeScript("entry")
    with pytest.raises(TypeError):
        device.midiOutSysex("F0 F7")           # str is not bytes
    with pytest.raises(TypeError):
        device.midiOutSysex(None)


def test_types_can_be_relaxed(host_factory):
    h = host_factory(strict_types=False)
    h.modules["ui"].getFocused("1")            # arity still checked, types are not


def test_unknown_name_is_attributeerror(host):
    with pytest.raises(AttributeError, match="noSuchFunction"):
        host.modules["device"].noSuchFunction
    with pytest.raises(AttributeError):
        host.modules["ui"].NotAThing()
    assert hasattr(host.modules["ui"], "getFocused")
    assert not hasattr(host.modules["ui"], "nope")


def test_known_but_unmodelled_function_raises_notimplemented_naming_it(host):
    arrangement = host.modules["arrangement"]
    with pytest.raises(NotImplementedError, match=r"arrangement\.currentTime"):
        arrangement.currentTime(1)
    with pytest.raises(TypeError):
        arrangement.currentTime()              # arity is still checked first
    # the attempt is on record so a test can see which new API a script tried
    assert [c.qual for c in host.calls][-2:] == ["arrangement.currentTime", "arrangement.currentTime"]
    assert isinstance(host.calls[-2].exc, NotImplementedError)
    with pytest.raises(NotImplementedError, match=r"screen\.blank"):
        host.modules["screen"].blank()


def test_calls_are_recorded_with_args_result_and_context(host):
    host.current = _FakeScript("entry")
    host.phase = host.cb = "OnIdle"
    host.modules["ui"].setFocused(4)
    assert host.modules["ui"].getFocused(4) is True
    a, b = host.calls
    assert (a.qual, a.args, a.script, a.cb) == ("ui.setFocused", (4,), "entry", "OnIdle")
    assert (b.qual, b.result) == ("ui.getFocused", True)
    assert [c.qual for c in host.effects()] == ["ui.setFocused"]      # getFocused is a query
    assert host.calls_to("ui.") == host.calls


def test_fault_injection(host):
    ui = host.modules["ui"]
    host.inject_fault("ui.getProgTitle", ValueError, times=2)
    for _ in range(2):
        with pytest.raises(ValueError, match="injected fault"):
            ui.getProgTitle()
    assert ui.getProgTitle() == "FL Studio 2026"                       # the fault ran out
    host.inject_fault("ui.getSnapMode", KeyError("x"))
    with pytest.raises(KeyError):
        ui.getSnapMode()
    host.clear_faults()
    assert ui.getSnapMode() == 1
    assert isinstance(host.calls[0].exc, ValueError)


def test_record_calls_off_still_counts(host_factory):
    h = host_factory(record_calls=False)
    h.modules["ui"].getFocused(1)
    assert h.calls == [] and h.call_count == 1


def test_query_classification():
    q = surface.is_query
    for name in ("ui.getFocused", "mixer.isTrackMuted", "channels.channelCount", "channels.selectedChannel",
                 "mixer.trackNumber", "patterns.patternNumber", "mixer.trackCount", "device.isAssigned"):
        assert q(name), name
    for name in ("ui.setFocused", "mixer.setTrackVolume", "transport.start", "device.midiOutSysex", "channels.showEditor"):
        assert not q(name), name


# ================================================================================================ state-backed behaviour

def test_fakes_read_and_write_the_fl_state(host):
    m, ch, ui = host.modules["mixer"], host.modules["channels"], host.modules["ui"]
    m.setTrackVolume(3, 0.5)
    assert host.state.track_volume[3] == 0.5 and m.getTrackVolume(3) == 0.5 and m.getTrackVolume(4) == 0.8
    host.state.select_channel_plugin("FPC", 2)
    ch.selectOneChannel(2)
    assert host.state.selected_channel == 2 and ch.channelNumber() == 2 and ch.isChannelSelected(2)
    ui.setFocused(0)
    ui.next()
    assert host.state.current_track == 2                       # mixer focused: next track
    ui.setFocused(1)
    ui.next()
    assert host.state.selected_channel == 3                    # channel rack focused: next channel
    ch.showEditor(3)
    assert ui.getFocused(5) and ui.getFocusedPluginName() == "Sampler"
    ch.showEditor(3)
    assert not ui.getFocused(5) and ui.getFocused(1) and ui.getFocusedPluginName() == ""
    assert host.modules["patterns"].patternNumber() == 1
    host.modules["patterns"].jumpToPattern(5)
    assert host.state.pattern == 5 and host.state.pattern_count == 5          # jumping past the last creates it


def test_globaltransport_toggles_metronome_and_loop_record(host):
    tr, ui, midi = host.modules["transport"], host.modules["ui"], host.modules["midi"]
    assert midi.FPT_Metronome == 110 and midi.FPT_LoopRecord == 113            # the ids transport.py hard-codes
    assert not ui.isMetronomeEnabled()
    tr.globalTransport(midi.FPT_Metronome, 1)
    assert ui.isMetronomeEnabled()
    tr.globalTransport(midi.FPT_LoopRecord, 1)
    assert ui.isLoopRecEnabled()
    tr.start()
    assert tr.isPlaying()
    tr.stop()
    assert not tr.isPlaying()


def test_automation_calls_are_modelled_for_fader_fixes(host):
    m, midi = host.modules["mixer"], host.modules["midi"]
    ev = m.getTrackPluginId(3, 0) + midi.REC_Mixer_Vol
    assert isinstance(ev, int) and m.automateEvent(ev, 30000, midi.REC_MIDIController, 5) == 30000
    assert [c.qual for c in host.calls] == ["mixer.getTrackPluginId", "mixer.automateEvent"]


def test_out_of_range_indices_are_violations_not_silent(host):
    m = host.modules["mixer"]
    assert m.getTrackPan(127) == 0.0
    m.setTrackNumber(-3)
    v = host.violations
    assert [x.kind for x in v] == ["index", "index"] and "127" in v[0].message
    host.modules["plugins"].getParamValue(-1, 0)
    assert host.violations[-1].kind == "param-index"
    host.modules["mixer"].setTrackVolume(1, 1.4)
    assert host.violations[-1].kind == "value"


def test_violations_can_raise_instead(host_factory):
    h = host_factory(on_violation="raise")
    with pytest.raises(RuleViolation):
        h.modules["mixer"].getTrackPan(127)


def test_klt_config_switches_can_be_set_per_load(host, tmp_path):
    folder = write_scripts(tmp_path / "s", "import KLTConfig\nX = KLTConfig.FLAG\n", helpers={"KLTConfig.py": "FLAG = 1\nLOG_PATH = 'C:\\\\x.log'\n"})
    ss = host.load(folder)
    assert sys.modules["KLTConfig"].LOG_PATH == host.log_path        # never a Windows path on the Linux test box
    host.set_config(FLAG=5)
    assert sys.modules["KLTConfig"].FLAG == 5 and ss.entry.module.X == 1
    with pytest.raises(AttributeError, match="NOPE"):
        host.set_config(NOPE=1)
    host.load(folder)
    assert sys.modules["KLTConfig"].FLAG == 1                          # a reload starts from the file's defaults


def test_midi_module_is_the_real_fl_file_when_present(host):
    midi = host.modules["midi"]
    assert midi.MIDI_NOTEON == 0x90 and midi.FPT_Undo == 20 and midi.widChannelRack == 1
    if os.path.isfile(os.environ.get("FL_MIDI_PY", DEFAULT_MIDI_PY)):
        assert midi.__flsim_source__.startswith("real:")


def test_midi_falls_back_to_the_recorded_constants(host_factory):
    h = host_factory(midi_py="/nonexistent/midi.py")
    midi = h.modules["midi"]
    assert midi.__flsim_source__ == "surface-constants"
    assert midi.MIDI_NOTEON == 0x90 and midi.PME_System == 2 and midi.FPT_Metronome == 110
    assert h.modules["utils"].KnobAccelToRes2(1) == 1
    assert h.modules["utils"].KnobAccelToRes2(8) == pytest.approx(8 ** 0.75)
    with pytest.raises(AttributeError):
        h.modules["utils"].HSVtoRGB


# ================================================================================================ crash emulation

class _FakeScript:
    def __init__(self, role):
        self.role = role


def test_flcrash_is_a_baseexception_that_except_exception_cannot_swallow():
    assert issubclass(FLCrash, BaseException) and not issubclass(FLCrash, Exception)
    swallowed = False
    try:
        try:
            raise FLCrash("boom")
        except Exception:
            swallowed = True
    except FLCrash:
        pass
    assert not swallowed


def test_unassigned_output_makes_midioutsysex_crash(host_factory):
    h = host_factory(output_assigned=False)
    dev = h.modules["device"]
    h.current = _FakeScript("entry")
    assert dev.isAssigned() is False and dev.isMidiOutAssigned() is False and dev.getPortNumber() == -1
    with pytest.raises(FLCrash, match="midiOutSysex"):
        dev.midiOutSysex(bytes([0xF0, 0x00, 0xF7]))
    with pytest.raises(FLCrash):
        dev.midiOutMsg(0x90)
    assert h.sysex == []
    try:
        dev.midiOutSysex(b"\xf0\xf7")
    except Exception:  # noqa: BLE001
        pytest.fail("a script's `except Exception` swallowed the emulated FL crash")
    except FLCrash:
        pass


def test_assigned_output_records_sysex_with_timestamps(host):
    dev = host.modules["device"]
    host.current = _FakeScript("entry")
    dev.midiOutSysex(bytes([0xF0, 0x01, 0xF7]))
    host.advance(0.5)
    dev.midiOutSysex(bytes([0xF0, 0x02, 0xF7]))
    assert [m.data for m in host.sysex] == [b"\xf0\x01\xf7", b"\xf0\x02\xf7"]
    assert host.sysex[1].t - host.sysex[0].t == pytest.approx(0.5)
    assert all(m.valid and m.script == "entry" for m in host.sysex)
    assert dev.isAssigned() is True and dev.getPortNumber() == 0


def test_the_other_hypothesis_unassigned_output_is_a_silent_noop(host_factory):
    h = host_factory(output_assigned=False, crash_on_unassigned_output=False)
    h.current = _FakeScript("entry")
    h.modules["device"].midiOutSysex(b"\xf0\x01\xf7")
    assert h.sysex == [] and h.dropped_sysex == [b"\xf0\x01\xf7"]


def test_output_assignment_is_per_script_role(host):
    host.set_output_assigned("forward", False)
    dev = host.modules["device"]
    host.current = _FakeScript("entry")
    dev.midiOutSysex(b"\xf0\xf7")
    host.current = _FakeScript("forward")
    with pytest.raises(FLCrash):
        dev.midiOutSysex(b"\xf0\xf7")


def test_device_calls_outside_a_script_context_crash(host):
    with pytest.raises(FLCrash, match="not associated with a device"):
        host.modules["device"].isAssigned()


def test_device_call_at_import_time_crashes_and_can_be_allowed(host_factory, tmp_path):
    folder = write_scripts(tmp_path / "s", "import device\ndevice.isAssigned()\n")
    h = host_factory()
    with pytest.raises(FLCrash, match="import time"):
        h.load(folder)
    host_factory.close(h)
    h2 = host_factory(crash_on_import_device_calls=False)
    h2.load(folder)


def test_import_time_calls_are_recorded_for_purity_checks(host, tmp_path):
    folder = write_scripts(tmp_path / "s", "import ui, time\nui.getProgTitle()\ntime.sleep(0.25)\n")
    host.load(folder)
    assert [c.qual for c in host.calls] == ["ui.getProgTitle", "time.sleep"]
    assert all(c.phase == "import" for c in host.calls)


# ================================================================================================ virtual clock

def test_time_is_virtual_while_a_host_is_active_and_restored_after(host_factory):
    h = host_factory()
    t0 = time.monotonic()
    w0 = time.time()
    start = time.perf_counter()
    time.sleep(2.5)                                     # must not block
    assert time.perf_counter() - start == pytest.approx(2.5)
    assert time.monotonic() - t0 == pytest.approx(2.5) and time.time() - w0 == pytest.approx(2.5)
    assert h.clock.slept_total == pytest.approx(2.5)
    h.advance(1.0)
    assert time.monotonic() - t0 == pytest.approx(3.5)
    host_factory.close(h)
    assert time.monotonic is _REAL_MONOTONIC and time.sleep is _REAL_SLEEP and time.time is _REAL_TIME


def test_sleeps_are_recorded_with_the_callback_that_slept(host, tmp_path):
    folder = write_scripts(tmp_path / "s", """
        import time
        def OnInit():
            time.sleep(0.01); time.sleep(0.5)
        def OnIdle():
            time.sleep(0.001)
        """)
    s = host.load(folder).entry
    s.OnInit()
    s.OnIdle()
    assert [x.seconds for x in host.clock.sleeps_in("OnInit")] == [0.01, 0.5]
    assert host.clock.slept_total == pytest.approx(0.511)
    assert [c.qual for c in host.calls] == ["time.sleep"] * 3          # visible in the trace too
    with pytest.raises(ValueError):
        time.sleep(-1)


def test_one_active_host_at_a_time(host):
    with pytest.raises(RuntimeError, match="already active"):
        Host().__enter__()


def test_host_leaves_no_trace_in_sys_modules_or_cwd(tmp_path):
    sentinel = type(sys)("plugins")
    sys.modules["plugins"] = sentinel
    folder = write_scripts(tmp_path / "s", "import ui\n")
    cwd = os.getcwd()
    try:
        with Host() as h:
            assert sys.modules["plugins"] is not sentinel and "device" in sys.modules
            assert os.getcwd() == h.tmpdir != cwd
            h.load(folder)
            assert "device_Fake" in sys.modules and str(folder) in sys.path
        assert sys.modules["plugins"] is sentinel
        assert "device" not in sys.modules and "device_Fake" not in sys.modules and str(folder) not in sys.path
        assert os.getcwd() == cwd and not os.path.exists(h.tmpdir)
    finally:
        sys.modules.pop("plugins", None)


def test_script_prints_are_captured_as_script_output(host, tmp_path):
    folder = write_scripts(tmp_path / "s", "def OnInit():\n    print('hello from init')\n")
    host.load(folder).entry.OnInit()
    assert [(r, t) for _, r, t in host.script_output] == [("entry", "hello from init")]


# ================================================================================================ loader

ENTRY = """
    import ui
    COUNT = 0
    LOG = []
    def OnInit():
        global COUNT
        COUNT += 1
        LOG.append('init')
    def OnMidiMsg(event):
        LOG.append('msg')
        event.handled = event.data1 == 1
    def OnNoteOn(event):
        LOG.append('noteon')
    def OnControlChange(event):
        LOG.append('cc')
        raise ValueError('cc exploded')
    def OnSysEx(event):
        LOG.append('sysex')
"""
FORWARD = """
    import device_Fake as KL
    def OnMidiIn(event):
        KL.LOG.append('in:%d' % event.midiId)
    def OnInit():
        KL.OnInit()
"""


def test_detect_scripts_by_name(tmp_path):
    f = write_scripts(tmp_path / "s", ENTRY, FORWARD)
    e, fw = detect_scripts(f)
    assert e.name == "device_Fake.py" and fw.name == "device_FakeForward.py"
    assert header_value(fw, "receiveFrom") == "Fake forward" and header_value(e, "name") == "Fake entry"
    (f / "device_Other.py").write_text("# name=Other\n")
    with pytest.raises(RuntimeError, match="ambiguous"):
        detect_scripts(f)


def test_detect_scripts_knows_the_stock_and_tuned_layouts():
    from tests.conftest import STOCK_DIR, TUNED_DIR
    e, f = detect_scripts(TUNED_DIR)
    assert e.name == "device_KeyLabmk2Tuned.py" and f.name == "device_ForwardCCsPort10KeyLabMk2Tuned.py"
    if STOCK_DIR.is_dir():
        e, f = detect_scripts(STOCK_DIR)
        assert e.name == "device_KeyLabmkII.py" and f.name == "device_Forward CCs Port 10 KEYLAB MKII.py"


def test_one_shared_interpreter_and_fresh_state_per_load(host, tmp_path):
    folder = write_scripts(tmp_path / "s", ENTRY, FORWARD)
    ss = host.load(folder)
    ss.boot()
    kl = sys.modules["device_Fake"]
    assert ss.forward.module.KL is kl and kl.COUNT == 2       # the Forward script shares the entry module's state
    ss2 = host.load(folder)                                    # a reload starts from clean module state
    assert sys.modules["device_Fake"].COUNT == 0 and sys.modules["device_Fake"] is not kl
    assert ss2.entry.module is sys.modules["device_Fake"]


def test_callbacks_missing_from_a_script_are_ignored_like_fl(host, tmp_path):
    s = host.load(write_scripts(tmp_path / "s", "x = 1\n")).entry
    assert s.OnIdle() is None and s.OnDeInit() is None and not s.has("OnIdle")
    with pytest.raises(AttributeError):
        s.NotACallback()
    with pytest.raises(AttributeError):
        s.invoke("OnBanana")


def test_event_pipeline_order_and_short_circuit(host, tmp_path):
    ss = host.load(write_scripts(tmp_path / "s", ENTRY, FORWARD))
    kl = ss.entry.module
    d = ss.entry.deliver_midi(0x90, 5, 100)                    # not handled by OnMidiMsg -> typed callback runs
    assert [c for c, _ in d.stages] == ["OnMidiIn", "OnMidiMsg", "OnNoteOn"] and not d.handled and d.forwarded_to_fl
    d = ss.entry.deliver_midi(0x90, 1, 100)                    # handled=True stops the pipeline
    assert [c for c, _ in d.stages] == ["OnMidiIn", "OnMidiMsg"] and d.handled and not d.forwarded_to_fl
    d = ss.entry.deliver_sysex(b"\xf0\x01\xf7")
    assert [c for c, _ in d.stages] == ["OnMidiIn", "OnSysEx"]
    assert kl.LOG == ["msg", "noteon", "msg", "sysex"]


def test_exceptions_are_caught_like_fl_and_recorded(host, tmp_path):
    ss = host.load(write_scripts(tmp_path / "s", ENTRY))
    d = ss.entry.deliver_midi(0xB0, 7, 1)
    assert [type(e) for e in d.exceptions] == [ValueError]
    (err,) = host.errors
    assert (err.script, err.callback) == ("entry", "OnControlChange") and "device_Fake.py" in err.site and "OnControlChange" in err.site
    with pytest.raises(ValueError):
        ss.entry.deliver_midi(0xB0, 7, 1, raise_errors=True)
    with pytest.raises(ValueError):
        ss.entry.invoke("OnControlChange", host.make_event(0xB0, 7, 1))


def test_flcrash_propagates_through_the_fl_like_catch(host_factory, tmp_path):
    h = host_factory(output_assigned=False)
    ss = h.load(write_scripts(tmp_path / "s", "import device\ndef OnInit():\n    device.midiOutSysex(b'\\xf0\\xf7')\n"))
    with pytest.raises(FLCrash):
        ss.entry.call("OnInit")


def test_midiin_populated_switch_models_h1_and_h2(host, tmp_path):
    ss = host.load(write_scripts(tmp_path / "s", ENTRY, FORWARD))
    ss.forward.deliver_midi(0xB0, 60, 1, populated=True)
    ss.forward.deliver_midi(0xB0, 60, 1, populated=False)
    host.midi_in_populated = False
    ss.forward.deliver_midi(0xB0, 60, 1)
    assert [x for x in ss.entry.module.LOG if x.startswith("in:")] == ["in:176", "in:0", "in:0"]


# ================================================================================================ FlEvent

def test_event_aliases_shadow_data_bytes():
    e = FlEvent(0xB0, 16, 65)
    assert (e.controlNum, e.note, e.pressure, e.progNum) == (16, 16, 16, 16)
    assert (e.controlVal, e.velocity) == (65, 65)
    e.controlNum = 20
    e.velocity = 99
    assert (e.data1, e.data2) == (20, 99)
    assert (e.midiId, e.midiChan) == (0xB0, 0)
    e2 = FlEvent(0xE5, 0, 64)
    assert (e2.midiId, e2.midiChan) == (0xE0, 5)


def test_event_populated_false_zeroes_the_derived_fields_only():
    e = FlEvent(0x99, 36, 100, populated=False)
    assert (e.midiId, e.midiChan, e.midiChanEx) == (0, 0, 0)
    assert (e.status, e.data1, e.data2, e.controlNum) == (0x99, 36, 100, 36)
    e.populate()
    assert (e.midiId, e.midiChan) == (0x90, 9)


def test_event_assignments_are_type_checked_and_range_checked(host):
    e = host.make_event(0x99, 36, 100)
    with pytest.raises(TypeError, match="data1"):
        e.data1 = None
    with pytest.raises(TypeError):
        e.data2 = 1.5
    assert host.violations == []
    e.data2 = 144                                                # F-05: out of the 7-bit range
    assert e.data2 == 144
    (v,) = host.violations
    assert v.kind == "event-range" and "data2" in v.message
    e.status = 300
    assert host.violations[-1].kind == "event-range"


def test_event_read_only_fields_and_unmodelled_fields():
    e = FlEvent(0x90, 1, 2)
    for name in ("timestamp", "port", "pmeFlags"):
        with pytest.raises(AttributeError):
            setattr(e, name, 1)
    with pytest.raises(NotImplementedError, match="pitchBend"):
        e.pitchBend
    with pytest.raises(AttributeError):
        e.notAField = 1
    s = FlEvent(b"\xf0\x01\xf7")
    assert s.status == 0xF0 and s.sysex == b"\xf0\x01\xf7"
    with pytest.raises(TypeError):
        s.sysex = "text"


# ================================================================================================ SysEx decoding + device model

WELCOME = bytes.fromhex("F0 00 20 6B 7F 42 04 00 60 01 4B 65 79 4C 61 62 20 6D 6B 49 49 00 02 46 4C 20 53 74 75 64 69 6F 20 32 30 32 35 00 7F F7")


def test_decode_the_documented_message_kinds():
    f = decode(WELCOME)
    assert f.kind == "lcd" and f.fields == {"line1": "KeyLab mkII", "line2": "FL Studio 2025"}
    assert decode(led_mono_frame(0x6D, 0x7F)).fields == {"id": 0x6D, "value": 0x7F}
    r = decode(led_rgb_frame(0x70, 0x7F, 0, 0))
    assert r.kind == "led_rgb" and r.fields["rgb"] == (0x7F, 0, 0) and r.fields["trailer"] == 0x7F
    assert decode(HEADER + bytes([0x02, 0x7D, 0x7D, 0x0B, 0x00]) + b"\xf7").kind == "deinit"
    assert decode(HEADER + bytes([0x09, 0x01]) + b"\xf7").kind == "unknown"
    assert decode(bytes([0xF0, 0x01, 0x80, 0xF7])).kind == "invalid"
    assert decode(b"\x01\x02").kind == "invalid"
    assert lcd_frame("KeyLab mkII", "FL Studio 2025") == WELCOME


def test_bad_framing_is_flagged_as_a_violation(host):
    host.current = _FakeScript("entry")
    d = host.modules["device"]
    d.midiOutSysex(bytes([0xF0, 0x00, 0x80, 0xF7]))            # data byte >= 0x80
    d.midiOutSysex(bytes([0x01, 0xF7]))
    d.midiOutSysex(bytes([0xF0, 0x01]))
    assert [v.kind for v in host.violations] == ["sysex-framing"] * 3
    assert [m.valid for m in host.sysex] == [False] * 3


def test_device_model_keeps_the_last_value_per_led_and_the_lcd(host):
    host.current = _FakeScript("entry")
    dev = host.modules["device"]
    for frame in (led_mono_frame(0x6D, 0x09), lcd_frame("A", "B"), led_mono_frame(0x6D, 0x7F), led_rgb_frame(0x70, 1, 2, 3),
                  lcd_frame("C", "D"), HEADER + bytes([1, 2, 3]) + b"\xf7"):
        host.advance(0.1)
        dev.midiOutSysex(frame)
    m = host.device_model()
    assert m.mono == {0x6D: 0x7F} and m.rgb == {0x70: (1, 2, 3)} and m.lcd == ("C", "D") and m.lcd_text() == "C|D"
    assert m.counts["lcd"] == 2 and len(m.unknown) == 1 and m.invalid == []
    assert [round(t - m.lcd_frames[0][0], 1) for t, *_ in m.lcd_frames] == [0.0, 0.3]
    assert m.mono_history[0x6D][0][1] == 0x09
    assert host.device_model(role="forward").total == 0
    assert isinstance(DeviceModel().state(), tuple)


# ================================================================================================ driver / streams / fuzz / diffreplay

def test_session_driver_plays_beat_callbacks_at_the_tempo(host, tmp_path):
    folder = write_scripts(tmp_path / "s", """
        BEATS = []
        IDLES = [0]
        def OnUpdateBeatIndicator(value):
            BEATS.append(value)
        def OnIdle():
            IDLES[0] += 1
        """)
    ss = host.load(folder)
    host.state.playing = True
    host.state.tempo = 120.0
    SessionDriver(ss).run(10.0)
    beats = ss.entry.module.BEATS
    assert ss.entry.module.IDLES[0] == 500
    assert beats.count(0) == pytest.approx(20, abs=1)                    # every beat is switched on then off
    assert beats[0] == 1 and beats[2] == 2 and beats.count(1) == 5 and host.state.song_tick_pos > 0


def test_streams_are_deterministic_and_host_independent():
    a = [(e.index, e.midi_in_populated, e.ops) for e in streams.episodes(5, 1500)]
    b = [(e.index, e.midi_in_populated, e.ops) for e in streams.episodes(5, 1500)]
    c = [(e.index, e.midi_in_populated, e.ops) for e in streams.episodes(6, 1500)]
    assert a == b and a != c
    n = sum(1 for e in streams.episodes(5, 1500) for op in e.ops if op[0] != "state")
    assert n == 1500
    kinds = {op[0] for e in streams.episodes(5, 5000) for op in e.ops}
    assert {"midi", "idle", "refresh", "beat", "sysex", "state", "wait"} <= kinds


def test_every_state_op_applies_cleanly():
    st = FLState()
    names = set()
    for e in streams.episodes(11, 20000):
        for op in e.ops:
            if op[0] == "state":
                streams.apply_state_op(st, op[1], op[2])
                names.add(op[1])
    assert len(names) >= 15 and st.channel_count() == len(st.channel_plugins)


def test_fuzz_runner_reports_exception_sites_and_flcrash(tmp_path):
    from tests.flsim.fuzz import run_fuzz
    bad = write_scripts(tmp_path / "bad", """
        def OnMidiMsg(event):
            if event.data1 == 60:
                raise KeyError('boom')
        def OnIdle():
            pass
        """)
    good = write_scripts(tmp_path / "good", "def OnMidiMsg(event):\n    event.handled = True\n")
    crashy = write_scripts(tmp_path / "crashy", "import device\ndef OnInit():\n    device.midiOutSysex(b'\\xf0\\xf7')\n")
    r = run_fuzz(bad, 4000, seed=3)
    assert r.exception_count > 0 and any(k[2] == "KeyError" for k in r.exceptions) and not r.flcrashes
    assert "KeyError" in r.report()
    r2 = run_fuzz(bad, 4000, seed=3)
    assert dict(r.exceptions) == dict(r2.exceptions)                    # reproducible
    assert run_fuzz(good, 2000, seed=3).exception_count == 0
    assert run_fuzz(crashy, 1000, seed=3, output_assigned=False).flcrashes
    assert not run_fuzz(crashy, 1000, seed=3, output_assigned=True).flcrashes


def test_diffreplay_categorizes_differences(tmp_path, capsys):
    from tests.flsim import diffreplay
    a = write_scripts(tmp_path / "a", """
        import ui
        def OnMidiMsg(event):
            ui.setFocused(1)
            event.handled = True
        """)
    b = write_scripts(tmp_path / "b", """
        import ui, transport
        def OnMidiMsg(event):
            if event.data1 == 60:
                raise KeyError('x')
            transport.start()
            event.handled = False
        """)
    code = diffreplay.main([str(a), str(b), "--events", "1500", "--seed", "2", "--fail-on-regression"])
    out = capsys.readouterr().out
    assert code == 1                                                     # b raises where a does not
    assert "REGRESSION" in out and "api-calls" in out and "handled/event" in out
    assert "-[ui.setFocused] +[transport.start]" in out
    assert diffreplay.main([str(a), str(a), "--events", "600", "--seed", "2", "--fail-on-regression"]) == 0
    assert "api-calls            0" in capsys.readouterr().out
