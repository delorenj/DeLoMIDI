"""Review (functional acceptance, second file): multi-step flows, drum-pad remap in absolute terms, the PASS_UNMAPPED
switch as a switch, boot-order independence, and three defects found after tests/test_review_acceptance_matrix.py.

Same wiring as the matrix file (docs/analysis/01 section 1.3): DAW port (port 0) -> the DAW script ("entry"), keyboard
port (port 1) -> the Forward script ("forward"). Every flow runs on Arturia's stock folder and on the tuned folder under H1
(midiId filled in OnMidiIn) and H2 (it reads 0). Nothing here says anything about real FL or the real keyboard.

Part C is strict xfail: the day a defect is fixed its test must be flipped to a plain assert.
"""
from __future__ import annotations

import functools

import pytest

from tests import kl
from tests.conftest import STOCK_DIR
from tests.flsim import Host
from tests.flsim.rig import Rig
from tests.test_input_helpers import tuned_only

POPS = [pytest.param(True, id="H1"), pytest.param(False, id="H2")]


def B(n, role="entry"):
    return [("midi", role, 0x90, n, 127), ("midi", role, 0x90, n, 0)]


def M(st, d1, d2, role="entry"):
    return [("midi", role, st, d1, d2)]


def S(fn):
    return [("st", fn)]


def _fpc(s):
    s.select_channel_plugin("FPC")
    s.focus(kl.WID_PLUGIN, "FPC")


def _flex(s):
    s.select_channel_plugin("FLEX")
    s.focus(kl.WID_PLUGIN, "FLEX")


PAD = lambda n, role="entry": [("midi", role, 0x99, n, 100), ("midi", role, 0x89, n, 0)]   # noqa: E731

FLOWS = {
    "A rack of 20: Next, Select 1, Next, Select 8, Prev, Select 1":
        (S(lambda s: s.resize_channels(20)), B(47) + B(24) + B(47) + B(31) + B(46) + B(24)),
    "B mixer: Next, fader 1, encoder 1, fader 9, Select 1, Prev, fader 1, encoder 1 ccw":
        (B(51), B(47) + M(0xE0, 0, 100) + M(0xB0, 16, 1) + M(0xE8, 0, 100) + B(24) + B(46) + M(0xE0, 0, 100) + M(0xB0, 16, 65)),
    "C sequencer (DAW-port pads): step, >>, step, <<, step, leave, drum pad, enter, step":
        (B(74), PAD(36) + B(92) + PAD(41) + B(91) + PAD(41) + B(74) + PAD(36) + B(74) + PAD(36)),
    "C2 sequencer (keyboard-port pads)":
        (B(74), PAD(36, "forward") + B(92) + PAD(41, "forward") + B(74) + PAD(36, "forward")),
    "D jog x2, push (editor), jog (closes), push, push":
        ([], M(0xB0, 60, 1) + M(0xB0, 60, 1) + B(84) + M(0xB0, 60, 1) + B(84) + B(84)),
    "E In -> Browser, jog, push, jog back, In -> rack, jog":
        ([], B(87) + M(0xB0, 60, 1) + B(84) + M(0xB0, 60, 65) + B(87) + M(0xB0, 60, 1)),
    "F loop, metro, out, undo, cut, tap, snap x2":
        ([], B(86) + B(89) + B(88) + B(81) + B(57) + B(56) + B(0) + B(3)),
    "G solo/mute in the rack, then in the mixer":
        ([], B(8) + B(16) + B(51) + B(8) + B(16) + B(51) + B(8)),
    "H select 3, fader 9, encoder 9 cw/ccw":
        ([], B(26) + M(0xE8, 0, 80) + M(0xB0, 24, 1) + M(0xB0, 24, 65)),
    "I FPC focused: faders, encoders, Next":
        (S(_fpc), M(0xE0, 0, 64) + M(0xE7, 0, 64) + M(0xB0, 16, 1) + M(0xB0, 23, 65) + M(0xE8, 0, 64) + B(47) + M(0xE0, 0, 64)),
    "J cursor left/right with a plugin focused = previous/next preset":
        (S(_flex), B(98) + B(99)),
}
# what a flow may legitimately differ in (finding id): the effect NAMES must always be identical, these lines may differ
ARG_DIFFERENCES = {
    "F loop, metro, out, undo, cut, tap, snap x2": "F-22: Undo passes value 2 instead of 20",
    "I FPC focused: faders, encoders, Next": "F-10: encoder ticks move the live value (0.5157 vs stock 0.5118)",
}


def _norm(effects):
    return [e for e in effects if not (e.startswith("channels.showEditor(") and e.endswith(", 0)"))]   # F-14: editor closes


@functools.lru_cache(maxsize=None)
def _flow(folder: str, populated: bool, name: str, order=("forward", "entry")):
    setup, stim = FLOWS[name]
    with Host(midi_in_populated=populated) as host:
        scripts = host.load(folder)
        scripts.boot(order=order)
        rig = Rig(host, scripts)
        for op in setup:
            if op[0] == "st":
                op[1](host.state)
            else:
                rig.midi(op[2], op[3], op[4], role=op[1])
        out = []
        for op in stim:
            a = rig.midi(op[2], op[3], op[4], role=op[1])
            out.append({"lines": _norm(a.lines), "names": [n for n in a.names if n != "channels.showEditor"]})
        return out


def _stock_or_skip(target):
    if target.is_stock:
        pytest.skip("compares the stock folder against the folder under test")
    if not STOCK_DIR.is_dir():
        pytest.skip("stock folder not available: %s" % STOCK_DIR)


# ==================================================================================================================
# Part A: flows -- stock and tuned do the same FL things, step by step
# ==================================================================================================================

@pytest.mark.parametrize("populated", POPS)
@pytest.mark.parametrize("name", list(FLOWS), ids=[n.split(" ")[0] for n in FLOWS])
def test_a_a_flow_does_the_same_fl_actions_as_stock(target, populated, name):
    _stock_or_skip(target)
    stock, tuned = _flow(str(STOCK_DIR), populated, name), _flow(str(target.path), populated, name)
    key = "lines" if name not in ARG_DIFFERENCES else "names"
    diff = [(i, a[key], b[key]) for i, (a, b) in enumerate(zip(stock, tuned)) if a[key] != b[key]]
    assert not diff, "\n".join("step %d\n   stock %s\n   tuned %s" % d for d in diff)


@pytest.mark.parametrize("populated", POPS)
def test_a_the_flows_do_not_depend_on_which_script_fl_initialises_first(target, populated):
    """Forward-first and DAW-first boots end in the same behaviour on every flow (F-17: the Forward OnInit no longer
    rebuilds the DAW script's objects)."""
    tuned_only(target)
    bad = [n for n in FLOWS
           if _flow(str(target.path), populated, n, ("forward", "entry")) != _flow(str(target.path), populated, n, ("entry", "forward"))]
    assert bad == []


# ==================================================================================================================
# Part B: absolute rows the matrix compares only by call names
# ==================================================================================================================

@pytest.mark.parametrize("populated", POPS)
@pytest.mark.parametrize("role", ["forward", "entry"])
def test_b_drum_mode_fpc_pads_are_remapped_to_the_fpc_layout_with_the_real_velocity(make_rig, target, populated, role):
    """Guide p.13-14: 'They are mapped by default to the 16 pads of FPC.' The FL action of a drum pad is the event FL plays
    after the script, so the note and velocity are asserted (the matrix compares FL calls, and a drum pad makes none)."""
    rig = make_rig(midi_in_populated=populated)
    _fpc(rig.state)
    for pad, fpc in kl.FPC_MAP.items():
        on = rig.midi(0x99, pad, 96, role=role)
        off = rig.midi(0x89, pad, 0, role=role)
        assert (on.event.status, on.event.data1, on.handled) == (0x99, fpc, False), (pad, on.event)
        assert (off.event.status, off.event.data1, off.handled) == (0x89, fpc, False), (pad, off.event)
        if not target.is_stock:
            assert (on.event.data2, off.event.data2) == (96, 0)          # F-05: stock wrote 144 / 128 here
        else:
            assert (on.event.data2, off.event.data2) == (144, 128)


@pytest.mark.parametrize("role", ["forward", "entry"])
def test_b_a_non_fpc_instrument_gets_the_notes_untouched_by_default(make_rig, target, role):
    """F-07 (default PADS_REMAP_ONLY_FOR_FPC=True) is a deliberate deviation from the guide sentence 'all pads trigger a MIDI
    note mapped to fit FPC': stock scrambled every other instrument as well. Pinned so nobody 'fixes' it back by accident."""
    tuned_only(target)
    rig = make_rig(midi_in_populated=False)
    rig.state.select_channel_plugin("Sampler")
    on = rig.midi(0x99, 36, 100, role=role)
    assert on.event.data1 == 36 and on.handled is False
    rig.host.set_config(PADS_REMAP_ONLY_FOR_FPC=False)
    assert rig.midi(0x99, 36, 100, role=role).event.data1 == kl.FPC_MAP[36]


# ==================================================================================================================
# (b) PASS_UNMAPPED as a switch: what it changes on which port
# ==================================================================================================================

KEYBOARD_PORT_TRAFFIC = [("note", 0x90, 60, 100), ("note-off", 0x80, 60, 0), ("sustain", 0xB0, 64, 127),
                         ("expression", 0xB0, 11, 90), ("volume", 0xB0, 7, 90), ("aftertouch", 0xD0, 40, 0),
                         ("mod wheel", 0xB0, 1, 50), ("wheel", 0xE0, 0, 100)]
DAW_PORT_STRAYS = [("note 48 (Next/Prev with Bank OFF, MCU channel +-1)", 0x90, 48, 127), ("note 49", 0x90, 49, 127),
                   ("note 96 (cursor up)", 0x90, 96, 127), ("note 97 (cursor down)", 0x90, 97, 127),
                   ("note 32", 0x90, 32, 127), ("note 104 (fader touch)", 0x90, 104, 127), ("cc 64", 0xB0, 64, 127)]


@pytest.mark.parametrize("populated", POPS)
def test_b_the_default_keyboard_port_path_ignores_pass_unmapped_entirely(make_rig, target, populated):
    """With FORWARD_USE_PROCESSOR at its default (False) the Forward script never consumes an unmapped event, so the switch can
    be turned off for the DAW port without changing one byte of what the keyboard port does."""
    tuned_only(target)
    rig = make_rig(midi_in_populated=populated)
    seen = {}
    for pu in (True, False):
        rig.host.set_config(PASS_UNMAPPED=pu)               # read at event time
        seen[pu] = [rig.midi(st, d1, d2, role="forward").handled for _n, st, d1, d2 in KEYBOARD_PORT_TRAFFIC]
    assert seen[True] == seen[False]
    assert seen[True] == [False, False, False, False, False, False, False, True]     # only the wheel is consumed (OnPitchBend)


@pytest.mark.parametrize("populated", POPS)
def test_b_pass_unmapped_false_on_the_daw_port_is_exactly_arturias_behaviour(make_rig, target, populated):
    """The one-line fix for RA-01: with PASS_UNMAPPED=False every stray button/CC on the DAW port is swallowed as in stock."""
    tuned_only(target)
    rig = make_rig(midi_in_populated=populated)
    rig.host.set_config(PASS_UNMAPPED=False)
    assert [rig.midi(st, d1, d2, role="entry").handled for _n, st, d1, d2 in DAW_PORT_STRAYS] == [True] * len(DAW_PORT_STRAYS)


def test_b_stock_swallowed_every_stray_on_the_daw_port(make_rig, target):
    if not target.is_stock:
        pytest.skip("stock-only baseline")
    rig = make_rig(midi_in_populated=True)
    assert [rig.midi(st, d1, d2, role="entry").handled for _n, st, d1, d2 in DAW_PORT_STRAYS] == [True] * len(DAW_PORT_STRAYS)


def test_b_the_default_swallows_every_stray_on_the_daw_port(make_rig, target):
    """RA-01 fixed (review round 1): this is what a user gets out of the box now. Before, each of these ids was a note on the
    selected channel in FL (PASS_UNMAPPED=True was the default); PASS_UNMAPPED=True still gives that back."""
    tuned_only(target)
    rig = make_rig(midi_in_populated=True)
    assert [rig.midi(st, d1, d2, role="entry").handled for _n, st, d1, d2 in DAW_PORT_STRAYS] == [True] * len(DAW_PORT_STRAYS)
    rig.host.set_config(PASS_UNMAPPED=True)
    assert [rig.midi(st, d1, d2, role="entry").handled for _n, st, d1, d2 in DAW_PORT_STRAYS] == [False] * len(DAW_PORT_STRAYS)


# ==================================================================================================================
# Part C: defects found by this file (strict xfail)
# ==================================================================================================================

# RA-04b fixed (review round 1): the Forward script never swallows an unmapped event; the strict xfail became a plain assert
def test_c_ra04b_the_mod_wheel_survives_pass_unmapped_false_on_the_processor_path(make_rig, target):
    tuned_only(target)
    rig = make_rig(midi_in_populated=False)
    rig.host.set_config(FORWARD_USE_PROCESSOR=True, PASS_UNMAPPED=False)
    assert rig.midi(0xB0, 1, 60, role="forward").handled is False


@pytest.mark.xfail(strict=True, reason="RA-09: PROBE keeps 3 samples per (callback, port, KIND): the documented first-run protocol (encoder before jog) leaves no line that shows the jog's real values, which the docs promise")
def test_c_ra09_the_documented_first_run_protocol_shows_the_jog_encoding(make_rig, target):
    tuned_only(target)
    rig = make_rig(midi_in_populated=False)
    rig.midi(0x90, 60, 100, role="forward")
    rig.midi(0x99, 40, 90, role="forward")
    for v in range(0, 127, 12):
        rig.fader(3, v)
    for _ in range(6):
        rig.cc(19, 2)                                  # one encoder turn
    rig.button(94)
    for _ in range(6):
        rig.cc(60, 3)                                  # the jog
    lines = [l for l in rig.host.read_log().splitlines() if " PROBE " in l and " cc " in l and "d1=60 " in l and "port=0" in l]
    assert lines, "no PROBE line for CC60 on the DAW port"


# RA-10 fixed (review round 1): the minimal profile is the default; the strict xfail became a plain assert
def test_c_ra10_the_default_config_asks_fl_only_for_isassigned(make_rig, target):
    tuned_only(target)
    rig = make_rig(boot=False)                           # output assigned = the official wiring
    m = rig.host.mark()
    rig.scripts.boot(order=("forward", "entry"))
    rig.idle(2.0)
    quals = {c.qual for c in rig.host.since(m).calls if c.qual.startswith(("device.", "general."))}
    assert quals <= {"device.isAssigned", "device.midiOutSysex"}, sorted(quals)


# RA-10b fixed (review round 1): frames leave from the first OnIdle tick; the strict xfail became a plain assert
def test_c_ra10b_no_sysex_is_sent_from_oninit(make_rig, target):
    tuned_only(target)
    rig = make_rig(boot=False)
    m = rig.host.mark()
    rig.scripts.boot(order=("forward", "entry"))
    in_oninit = [c for c in rig.host.since(m).calls if c.qual == "device.midiOutSysex" and c.cb == "OnInit"]
    assert not in_oninit, "%d midiOutSysex call(s) inside OnInit" % len(in_oninit)
