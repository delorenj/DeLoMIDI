"""Review: functional acceptance of the tuned DEFAULT config against the official guide, under the official wiring.

Wiring (docs/analysis/01 section 1.3, 02 section 3.1):
    DAW port  (MIDIIN2/MIDIOUT2, port 0) -> the DAW script      role "entry"    (buttons, jog, encoders, faders)
    main port (KeyLab mkII 88,  port 1) -> the Forward script  role "forward"  (keybed, wheels, pads, Analog Lab CCs)
Every row runs on Arturia's stock scripts and on the tuned folder, under H1 (midiId populated in OnMidiIn) and H2
(it reads 0), and the FL actions are compared. Part A asserts "the tuned default does what stock did" for every guide
control, with every difference named and tied to a finding. Part B pins the documented action in absolute terms
(so a row cannot pass just because both scripts are broken the same way). Part C reproduces the defects this review
found (strict xfail: the day one is fixed its test must be flipped to a plain assert).

Nothing here says anything about real FL or the real keyboard: see docs/tuned/TESTING.md "What is NOT modelled".
"""
from __future__ import annotations

import functools
import os
import re
import sys

import pytest

from tests import kl
from tests.conftest import STOCK_DIR
from tests.flsim import Host, FLCrash
from tests.flsim.rig import Rig
from tests.test_input_helpers import tuned_only

WID_MIXER, WID_CR, WID_PLAYLIST, WID_BROWSER, WID_PLUGIN = 0, 1, 2, 4, 5
POPS = [pytest.param(True, id="H1"), pytest.param(False, id="H2")]


# ==================================================================================================================
# scenario DSL: ("midi", role, status, d1, d2) and ("st", fn(state)); only `stim` steps are recorded
# ==================================================================================================================

def D(st, d1, d2):
    return ("midi", "entry", st, d1, d2)


def K(st, d1, d2):
    return ("midi", "forward", st, d1, d2)


def btn(note, role="entry"):
    return [("midi", role, 0x90, note, 127), ("midi", role, 0x90, note, 0)]


def st(fn):
    return ("st", fn)


def focus_plugin(name):
    def f(s):
        s.select_channel_plugin(name)
        s.focus(WID_PLUGIN, name)
    return f


def sel_plugin(name):
    return st(lambda s: s.select_channel_plugin(name))


MIXER_MODE = btn(51)
SEQ_MODE = btn(74)
SCEN: dict = {}


def scen(name, setup, stim):
    SCEN[name] = (setup, stim)


for _nm, _n in (("rewind", 91), ("forward", 92), ("stop", 93), ("play", 94), ("record", 95), ("loop", 86)):
    scen("transport/%s" % _nm, [], btn(_n))
scen("transport/rewind-in-seq", SEQ_MODE, btn(91))
scen("transport/forward-in-seq", SEQ_MODE, btn(92) + btn(92))
scen("fn/solo-CR", [], btn(8))
scen("fn/mute-CR", [], btn(16))
scen("fn/solo-mixer", [st(lambda s: s.focus(WID_MIXER))], btn(8))
scen("fn/mute-mixer", [st(lambda s: s.focus(WID_MIXER))], btn(16))
scen("fn/snap", [], btn(0) + btn(7))
scen("fn/tap-tempo", [], btn(56))
scen("fn/cut", [], btn(57))
scen("fn/save-seq-toggle", [], btn(74) + btn(74))
scen("fn/in-browser-toggle", [], btn(87) + btn(87))
scen("fn/out-overdub", [], btn(88))
scen("fn/metro", [], btn(89))
scen("fn/undo", [], btn(81))
scen("fn/mode-toggle-bank51", [], btn(51) + btn(51))
scen("bank/next-prev-CR", [st(lambda s: s.resize_channels(20))], btn(47) + btn(47) + btn(46))
scen("bank/next-prev-mixer", MIXER_MODE, btn(47) + btn(46))
scen("bank/select-after-bank-CR", [st(lambda s: s.resize_channels(20))] + btn(47), btn(24) + btn(31))
scen("pattern/prev", [st(lambda s: setattr(s, "pattern", 2))], btn(98))
scen("pattern/next", [st(lambda s: setattr(s, "pattern", 2))], btn(99))
scen("pattern/prev-at-1", [], btn(98))
scen("pattern/next-at-last", [st(lambda s: setattr(s, "pattern", 3))], btn(99))
scen("pattern/prev-plugin-focused", [st(focus_plugin("FLEX"))], btn(98))
scen("pattern/next-plugin-focused", [st(focus_plugin("FLEX"))], btn(99))
for _nm, _setup in (("CR", []), ("mixer", [st(lambda s: s.focus(WID_MIXER))]), ("browser", [st(lambda s: s.focus(WID_BROWSER))]),
                    ("plugin", [st(focus_plugin("FLEX"))]), ("playlist", [st(lambda s: s.focus(WID_PLAYLIST))])):
    scen("jog/turn-cw-%s" % _nm, _setup, [D(0xB0, 60, 1)])
    scen("jog/turn-ccw-%s" % _nm, _setup, [D(0xB0, 60, 65)])
scen("jog/fast-cw-3-CR", [], [D(0xB0, 60, 3)])
scen("jog/fast-ccw-66-CR", [], [D(0xB0, 60, 66)])
scen("jog/push-CR", [], btn(84))
scen("jog/push-plugin", [st(focus_plugin("FLEX"))], btn(84))
scen("jog/push-mixer", [st(lambda s: s.focus(WID_MIXER))], btn(84))
scen("jog/push-browser", [st(lambda s: s.focus(WID_BROWSER))], btn(84))
scen("select/CR-1", [], btn(24))
scen("select/CR-8", [], btn(31))
scen("select/mixer-1", MIXER_MODE, btn(24))
scen("select/mixer-8", MIXER_MODE, btn(31))
scen("select/9th-button-note32", [], btn(32))
for _n in range(9):
    scen("fader/CR-noplugin-%d" % (_n + 1), [], [D(0xE0 + _n, 0, 64)])
    scen("fader/CR-FPC-%d" % (_n + 1), [st(focus_plugin("FPC"))], [D(0xE0 + _n, 0, 64)])
    scen("fader/mixer-%d" % (_n + 1), MIXER_MODE, [D(0xE0 + _n, 0, 100)])
for _i in range(9):
    scen("encoder/CR-FPC-%d-cw" % (_i + 1), [st(focus_plugin("FPC"))], [D(0xB0, 16 + _i, 1)])
    scen("encoder/CR-FPC-%d-ccw" % (_i + 1), [st(focus_plugin("FPC"))], [D(0xB0, 16 + _i, 65)])
    scen("encoder/CR-noplugin-%d-cw" % (_i + 1), [], [D(0xB0, 16 + _i, 1)])
    scen("encoder/mixer-%d-cw" % (_i + 1), MIXER_MODE, [D(0xB0, 16 + _i, 1)])
    scen("encoder/mixer-%d-ccw" % (_i + 1), MIXER_MODE, [D(0xB0, 16 + _i, 65)])
for _role in ("forward", "entry"):
    scen("pad/drum-FPC-36-%s" % _role, [sel_plugin("FPC")], [("midi", _role, 0x99, 36, 100), ("midi", _role, 0x89, 36, 64)])
    scen("pad/drum-FPC-51-%s" % _role, [sel_plugin("FPC")], [("midi", _role, 0x99, 51, 127), ("midi", _role, 0x89, 51, 0)])
    scen("pad/drum-sampler-36-%s" % _role, [sel_plugin("Sampler")], [("midi", _role, 0x99, 36, 100), ("midi", _role, 0x89, 36, 64)])
    scen("pad/seq-press-release-%s" % _role, SEQ_MODE, [("midi", _role, 0x99, 36, 100), ("midi", _role, 0x89, 36, 0)])
    scen("pad/seq-16steps-%s" % _role, SEQ_MODE,
         sum([[("midi", _role, 0x99, 36 + i, 100), ("midi", _role, 0x89, 36 + i, 0)] for i in (0, 5, 15)], []))
    scen("pad/seq-next-bar-%s" % _role, SEQ_MODE + btn(92),
         [("midi", _role, 0x99, 36, 100), ("midi", _role, 0x89, 36, 0)])
    scen("pad/seq-hold-encoders-%s" % _role, SEQ_MODE + [("midi", _role, 0x99, 36, 100)],
         [D(0xB0, 16, 1), D(0xB0, 17, 1), D(0xB0, 20, 1), D(0xB0, 23, 1), ("midi", _role, 0x89, 36, 0)])
    scen("pad/song-mode-%s" % _role, SEQ_MODE + [st(lambda s: setattr(s, "loop_mode", 1))],
         [("midi", _role, 0x99, 36, 100), ("midi", _role, 0x89, 36, 0)])
scen("kb/pitch-wheel-center", [], [K(0xE0, 0, 64)])
scen("kb/pitch-wheel-up", [], [K(0xE0, 127, 127)])
scen("kb/pitch-wheel-down", [], [K(0xE0, 0, 0)])
scen("kb/pitch-wheel-VCOL-plugin", [st(lambda s: s.set_channels(["Kick"] + ["x"] * 4, selected=0)), st(focus_plugin("Analog Lab V"))],
     [K(0xE0, 0, 100)])
scen("kb/modwheel-noplugin", [], [K(0xB0, 1, 90)])
scen("kb/modwheel-minisynth", [st(focus_plugin("MiniSynth"))], [K(0xB0, 1, 90)])
scen("kb/modwheel-mixer-mode", MIXER_MODE, [K(0xB0, 1, 90)])
scen("kb/cc28-cc29-plugin", [st(focus_plugin("FPC"))], [K(0xB0, 28, 127), K(0xB0, 28, 0), K(0xB0, 29, 127)])
scen("kb/cc28-no-plugin", [], [K(0xB0, 28, 127), K(0xB0, 29, 127)])
ANALOG_LAB_CCS = (74, 71, 76, 77, 93, 18, 19, 16, 73, 75, 79, 72, 80, 81, 82, 83, 17)
for _cc in ANALOG_LAB_CCS:
    scen("kb/AL-cc%d-VCOL" % _cc, [st(focus_plugin("Analog Lab V"))], [K(0xB0, _cc, 50)])
    scen("kb/AL-cc%d-FLEX" % _cc, [st(focus_plugin("FLEX"))], [K(0xB0, _cc, 50)])
scen("kb/AL-pitchbend-VCOL", [st(focus_plugin("Analog Lab V"))], [K(0xE0, 0, 90)])
scen("kb/other-cc-sustain64", [], [K(0xB0, 64, 127), K(0xB0, 64, 0)])
scen("kb/other-cc-expression11", [], [K(0xB0, 11, 100)])
KEYBED_ACTING_UNDER_H1 = (46, 47, 51, 56, 74, 84, 86, 87, 91, 92, 93, 94, 95, 98, 99)      # docs/analysis/02 3.3
for _note in (21, 60, 108) + KEYBED_ACTING_UNDER_H1:
    scen("kb/keybed-note-%d" % _note, [], [K(0x90, _note, 100), K(0x80, _note, 0)])
scen("kb/aftertouch", [], [K(0xD0, 40, 0), K(0xA0, 60, 30)])
# DAW-mode traffic that would arrive on the MAIN port if the keyboard's DAW preset routed it there (UNVERIFIED which port)
scen("kb/DAW-buttons-on-main-port", [], [K(0x90, 94, 127), K(0x90, 94, 0)])
scen("kb/jog-cc-on-main-port", [], [K(0xB0, 60, 1)])
scen("kb/encoder-cc-on-main-port", [st(focus_plugin("FPC"))], [K(0xB0, 20, 1)])
scen("kb/fader-2-on-main-port", [], [K(0xE1, 0, 90)])
for _nm, _s, _a, _b in (("note-104-fader-touch", 0x90, 104, 127), ("note-32-enc-push", 0x90, 32, 127),
                        ("note-96-cursor", 0x90, 96, 127), ("note-48-channel-left", 0x90, 48, 127),
                        ("cc-64", 0xB0, 64, 127), ("cc-7", 0xB0, 7, 100), ("cc-1", 0xB0, 1, 60),
                        ("bend-ch10", 0xE9, 0, 64)):
    scen("dawport/unmapped-%s" % _nm, [], [D(_s, _a, _b)])
scen("dawport/unmapped-touch-release-vel0", [], [D(0x90, 104, 127), D(0x90, 104, 0)])


def _norm(a):
    ev = a.event
    # names_nn: effect names without F-14's editor closes (stock looped showEditor(i, 0) over every channel)
    nn = [c.qual for c in a.effects if not (c.qual == "channels.showEditor" and len(c.args) >= 2 and c.args[1] == 0)]
    return {"effects": [c.short() for c in a.effects], "names": [c.qual for c in a.effects], "names_nn": nn,
            "handled": bool(a.handled),
            "event": (ev.status, ev.data1, ev.data2) if ev is not None else None,
            "errors": [type(e.exc).__name__ for e in a.errors], "viol": [v.kind for v in a.violations]}


def _run_scenario(folder, populated, name):
    setup, stim = SCEN[name]
    with Host(midi_in_populated=populated) as host:
        scripts = host.load(folder)
        scripts.boot(order=("forward", "entry"))
        rig = Rig(host, scripts)
        for op in setup:
            if op[0] == "st":
                op[1](host.state)
            else:
                rig.midi(op[2], op[3], op[4], role=op[1])
        out = []
        for op in stim:
            if op[0] == "st":
                op[1](host.state)
            else:
                out.append(_norm(rig.midi(op[2], op[3], op[4], role=op[1])))
        return out


@functools.lru_cache(maxsize=None)
def _matrix(folder: str, populated: bool):
    return {n: _run_scenario(folder, populated, n) for n in SCEN}


def _stock_or_skip(target):
    if target.is_stock:
        pytest.skip("compares the stock folder against the folder under test; nothing to compare on --stock")
    if not STOCK_DIR.is_dir():
        pytest.skip("stock folder not available: %s" % STOCK_DIR)


# ==================================================================================================================
# Part A: the tuned default performs the same FL actions as stock, every difference named
# ==================================================================================================================

def _names(steps):
    return [s["names_nn"] for s in steps]


def known_action_difference(name, populated):
    """The finding that explains why the FL actions of `name` differ between stock and tuned (None = must be identical)."""
    if name.startswith("jog/fast"):
        return "F-10: stock dropped every jog value except 1/65; tuned steps by the tick count"
    if name == "pattern/prev-at-1":
        return "F-21: stock jumped to pattern 0"
    if name.startswith("kb/keybed-note-") and populated and int(name.rsplit("-", 1)[1]) in KEYBED_ACTING_UNDER_H1:
        return "F-01: under H1 stock turned 15 keybed keys into transport/window/pattern buttons"
    if name == "kb/modwheel-minisynth" and populated:
        return "F-01/F-02: under H1 stock never reached the mod-wheel row (id dispatcher); tuned drives the parameter"
    if name == "kb/cc28-cc29-plugin" and populated:
        return "F-01/F-02: under H1 stock never reached the preset buttons; tuned steps the preset (H2 behaviour)"
    if re.fullmatch(r"kb/AL-cc(16|17|18|19)-FLEX", name) and populated:
        return "F-01/F-02: under H1 stock let Analog Lab CC16..19 drive the FLEX encoder rows (id dispatcher)"
    if name in ("kb/pitch-wheel-VCOL-plugin", "kb/AL-pitchbend-VCOL"):
        return "F-15: an Arturia instrument is recognised by the plugin it hosts, not only by the channel name"
    if name.startswith("pad/seq-hold-encoders"):
        return "F-11: encoder 8 = step Shift (guide p.15 Fig.31); stock did nothing"
    if name.startswith("pad/song-mode"):
        return "F-04: the song-mode pad release is routed (closes the graph editor, clears the held pad)"
    if populated and name in ("kb/DAW-buttons-on-main-port", "kb/jog-cc-on-main-port", "kb/encoder-cc-on-main-port"):
        return "RA-08: DAW-mode traffic on the keyboard port under H1 acted in stock; the tuned default path ignores it"
    return None


def _diff_report(pop):
    stock, tuned = _matrix(str(STOCK_DIR), pop), _matrix(str(_TUNED_PATH[0]), pop)
    unexplained, explained_but_equal, explained = [], [], set()
    for name in SCEN:
        same = _names(stock[name]) == _names(tuned[name])
        why = known_action_difference(name, pop)
        if not same and why is None:
            unexplained.append((name, _names(stock[name]), _names(tuned[name])))
        if same and why is not None:
            explained_but_equal.append(name)
        if not same and why is not None:
            explained.add(name)
    return unexplained, explained_but_equal, explained


_TUNED_PATH = [None]


@pytest.fixture(scope="module", autouse=True)
def _pin_target(request):
    # the folder under test is decided by conftest's `target` fixture; remember it for the module-level helpers
    tgt = request.getfixturevalue("target")
    _TUNED_PATH[0] = tgt.path
    yield


@pytest.mark.parametrize("populated", POPS)
def test_a_the_tuned_default_performs_the_same_fl_actions_as_stock(target, populated):
    _stock_or_skip(target)
    unexplained, _, _ = _diff_report(populated)
    assert not unexplained, "\n".join("%s\n   stock %s\n   tuned %s" % u for u in unexplained)


@pytest.mark.parametrize("populated", POPS)
def test_a_every_named_difference_is_real(target, populated):
    """The allow-list above must not go stale: an entry whose scenario no longer differs is a finding that was fixed
    (or a row that stopped testing anything)."""
    _stock_or_skip(target)
    _, explained_but_equal, _ = _diff_report(populated)
    assert not explained_but_equal, explained_but_equal


@pytest.mark.parametrize("populated", POPS)
def test_a_the_tuned_default_never_raises_or_violates_on_a_guide_control(target, populated):
    tuned_only(target)
    bad = [(n, s["errors"], s["viol"]) for n, steps in _matrix(str(target.path), populated).items() for s in steps
           if s["errors"] or s["viol"]]
    assert not bad, bad


def test_a_the_tuned_default_does_not_depend_on_h1_or_h2(target):
    """The claim of docs/tuned/CHANGES-input.md design principle 2, checked over the whole guide matrix."""
    tuned_only(target)
    h1, h2 = _matrix(str(target.path), True), _matrix(str(target.path), False)
    assert [n for n in SCEN if h1[n] != h2[n]] == []


# ---- (d) event.handled: every place the default leaks to FL or swallows differently than stock -----------------------

_LEAKS = re.compile(r"dawport/unmapped-|select/9th-button|kb/AL-cc\d+-FLEX")                 # stock swallowed, tuned passes
_SWALLOWS = re.compile(r"fader/(CR-FPC|mixer)-|encoder/(CR-FPC|mixer)-|pad/seq-[a-z0-9-]+-forward|pad/song-mode-(forward|entry)")   # reverse


@pytest.mark.parametrize("populated", POPS)
def test_d_handled_differs_from_stock_only_where_documented(target, populated):
    _stock_or_skip(target)
    stock, tuned = _matrix(str(STOCK_DIR), populated), _matrix(str(target.path), populated)
    unexpected = []
    for name in SCEN:
        for i, (a, b) in enumerate(zip(stock[name], tuned[name])):
            if a["handled"] == b["handled"]:
                continue
            leak = a["handled"] and not b["handled"]
            if not ((_LEAKS if leak else _SWALLOWS).search(name)):
                unexpected.append((name, i, "now leaks to FL" if leak else "now swallowed", a["event"], b["event"]))
    assert not unexpected, unexpected


# ==================================================================================================================
# Part B: the documented FL action, in absolute terms, on the script the wiring delivers it to
# ==================================================================================================================

def _effects(steps):
    return [e for s in steps for e in s["effects"]]


ABSOLUTE_ROWS = [
    # (row, scenario, an effect string that must be among the effects of the scenario)
    ("Play/Pause", "transport/play", "transport.start()"),
    ("Stop", "transport/stop", "transport.stop()"),
    ("Record", "transport/record", "transport.record()"),
    ("Rewind", "transport/rewind", "transport.continuousMove(-1, 2)"),
    ("Rewind release stops", "transport/rewind", "transport.continuousMove(-1, 0)"),
    ("Fast forward", "transport/forward", "transport.continuousMove(1, 2)"),
    ("Snap", "fn/snap", "ui.snapMode(1)"),
    ("Cut", "fn/cut", "ui.cut()"),
    ("Solo in the Channel Rack", "fn/solo-CR", "channels.soloChannel(0)"),
    ("Mute in the Channel Rack", "fn/mute-CR", "channels.muteChannel(0)"),
    ("Solo in the Mixer", "fn/solo-mixer", "mixer.soloTrack(1)"),
    ("Mute in the Mixer", "fn/mute-mixer", "mixer.muteTrack(1)"),
    ("Next pattern", "pattern/next", "patterns.jumpToPattern(3)"),
    ("Previous pattern", "pattern/prev", "patterns.jumpToPattern(1)"),
    ("Jog, Channel Rack", "jog/turn-cw-CR", "ui.next()"),
    ("Jog, Mixer", "jog/turn-cw-mixer", "ui.next()"),
    ("Jog push, Channel Rack", "jog/push-CR", "channels.showEditor(0)"),
    ("Jog push, Mixer = arm", "jog/push-mixer", "mixer.armTrack(1)"),
    ("Select 1", "select/CR-1", "channels.selectOneChannel(0)"),
    ("Select 8", "select/CR-8", "channels.selectOneChannel(7)"),
    ("Select 1 in the Mixer", "select/mixer-1", "mixer.setTrackNumber(1, 3)"),
    ("Fader 1 in the Mixer = track 1 volume", "fader/mixer-1", "mixer.setTrackVolume(1, 0.6299)"),
    ("Fader 9 in the Mixer = master volume", "fader/mixer-9", "mixer.setTrackVolume(0, 0.6299)"),
    ("Fader 9 in the Channel Rack = current track volume", "fader/CR-noplugin-9", "mixer.setTrackVolume(1, 0.4031)"),
    ("Fader 1 controls the focused FPC", "fader/CR-FPC-1", "plugins.setParamValue(0.5039, 0, 0)"),
    ("Encoder 9 in the Channel Rack = current track pan", "encoder/CR-noplugin-9-cw", "mixer.setTrackPan(1, 0.05)"),
    ("Encoder 1 in the Mixer = track 1 pan", "encoder/mixer-1-cw", "mixer.setTrackPan(1, 0.05)"),
    ("Encoder 9 in the Mixer = master pan", "encoder/mixer-9-ccw", "mixer.setTrackPan(0, -0.05)"),
    ("Pad in Sequencer mode toggles step 1 (keyboard port)", "pad/seq-press-release-forward", "channels.setGridBit(0, 0, 1)"),
    ("Pad in Sequencer mode toggles step 1 (DAW port)", "pad/seq-press-release-entry", "channels.setGridBit(0, 0, 1)"),
    ("`>>` moves the step window one bar", "pad/seq-next-bar-forward", "channels.setGridBit(0, 16, 1)"),
    ("Analog Lab CC74 is forwarded to port 10", "kb/AL-cc74-VCOL", "device.forwardMIDICC(%d, 2)" % kl.forward_cc_message(0xB0, 74, 50)),
    ("Analog Lab fader CC83 is forwarded to port 10", "kb/AL-cc83-VCOL", "device.forwardMIDICC(%d, 2)" % kl.forward_cc_message(0xB0, 83, 50)),
    ("Pitch bend is forwarded to port 10", "kb/AL-pitchbend-VCOL", "device.forwardMIDICC(%d, 2)" % kl.forward_cc_message(0xE0, 0, 90)),
    ("Pitch wheel bends the selected channel", "kb/pitch-wheel-down", "channels.setChannelPitch(0, -1, 0)"),
]


@pytest.mark.parametrize("populated", POPS)
@pytest.mark.parametrize("row,scenario,expected", [pytest.param(*r, id=r[0]) for r in ABSOLUTE_ROWS])
def test_b_the_documented_action_happens(target, populated, row, scenario, expected):
    tuned_only(target)
    effects = _effects(_matrix(str(target.path), populated)[scenario])
    assert expected in effects, "%s: %s not among %s" % (row, expected, effects)


@pytest.mark.parametrize("populated", POPS)
def test_b_the_wheel_center_moves_nothing_and_the_end_stops_are_the_full_range(target, populated):
    tuned_only(target)
    m = _matrix(str(target.path), populated)
    assert "channels.setChannelPitch(0, 0, 0)" in _effects(m["kb/pitch-wheel-center"])
    assert "channels.setChannelPitch(0, -1, 0)" in _effects(m["kb/pitch-wheel-down"])


@pytest.mark.parametrize("populated", POPS)
def test_b_keybed_notes_reach_fl_untouched_and_make_no_fl_call(target, populated):
    tuned_only(target)
    m = _matrix(str(target.path), populated)
    for name in [n for n in SCEN if n.startswith("kb/keybed-note-")]:
        for s in m[name]:
            assert s["effects"] == [] and s["handled"] is False, (name, populated, s)


# ==================================================================================================================
# (b) quantification, (e) log volume
# ==================================================================================================================

MAPPED_NOTES = set(range(0, 32)) | {46, 47, 51, 56, 57, 74, 81, 84, 86, 87, 88, 89, 91, 92, 93, 94, 95, 98, 99}


def test_b_no_channel_1_note_id_on_the_daw_port_is_left_to_fl_by_default(make_rig, target):
    """RA-01 (was: 77 of 128 ids left to FL with PASS_UNMAPPED=True; stock swallowed all of them). Now the DAW-port default is
    stock's: every id is either mapped or swallowed. Which of the unclaimed ids the real DAW preset sends is UNVERIFIED; the
    manual (4.6) and the guide (p.12) say at least Next/Previous with the Bank button OFF, Button 9 and the two navigation
    buttons do send something the scripts do not know: UNMAPPED lines in klt.log name each one."""
    rig = make_rig()
    left_to_fl = {n for n in range(128) if rig.midi(0x90, n, 127, role="entry").handled is False}
    assert left_to_fl == set()
    if not target.is_stock:
        rig.host.set_config(PASS_UNMAPPED=True)
        opted_in = {n for n in range(128) if rig.midi(0x90, n, 127, role="entry").handled is False}
        assert set(range(128)) - opted_in == MAPPED_NOTES and len(opted_in) == 77         # the old default, one switch away


def test_e_a_normal_session_writes_a_short_log(make_rig, target):
    """~2,500 events over 10 virtual minutes (keybed, wheels, faders, encoders, jog, pads, buttons, a few unmapped ids):
    the log stays small and FL's Script output gets only the OnInit lines."""
    tuned_only(target)
    import random
    rnd = random.Random(3)
    rig = make_rig(midi_in_populated=False)
    rig.state.select_channel_plugin("FPC")
    rig.state.focus(WID_PLUGIN, "FPC")
    for _ in range(600):
        r = rnd.random()
        if r < 0.3:
            rig.midi(0x90, rnd.randint(36, 96), 90, role="forward")
            rig.midi(0x80, 60, 0, role="forward")
        elif r < 0.45:
            rig.midi(0xE0, rnd.randint(0, 127), rnd.randint(0, 127), role="forward")
        elif r < 0.6:
            for _k in range(20):
                rig.midi(0xE0 + rnd.randint(0, 8), 0, rnd.randint(0, 127), role="entry")
        elif r < 0.7:
            for _k in range(10):
                rig.midi(0xB0, 16 + rnd.randint(0, 8), rnd.choice((1, 65, 2, 66)), role="entry")
        elif r < 0.8:
            rig.midi(0x99, rnd.randint(36, 51), 100, role="forward")
            rig.midi(0x89, 40, 0, role="forward")
        elif r < 0.9:
            rig.midi(0xB0, rnd.choice((1, 64, 11, 7, 74)), rnd.randint(0, 127), role="forward")
        else:
            rig.midi(0x90, rnd.choice((104, 96, 32, 48)), 127, role="entry")
        rig.idle(1.0)
    log = rig.host.read_log()
    assert len(log.splitlines()) < 120 and len(log) < 40_000, (len(log.splitlines()), len(log))
    assert len(rig.host.script_output) <= 6, rig.host.script_output


# ==================================================================================================================
# Part C: defects found by this review (strict xfail: flip to a plain assert when fixed)
# ==================================================================================================================

# RA-01 fixed (review round 1): PASS_UNMAPPED defaults to False on the DAW port; the strict xfail became a plain assert
@pytest.mark.parametrize("note", [32, 48, 49, 96, 104])
def test_c_ra01_an_unclaimed_button_note_on_the_daw_port_is_not_played_by_fl(make_rig, target, note):
    tuned_only(target)
    rig = make_rig()
    assert rig.button(note, True, role="entry").handled is True
    assert rig.button(note, False, role="entry").handled is True


# RA-04 fixed (review round 1): the Forward script never swallows an unmapped event; the strict xfail became a plain assert
def test_c_ra04_pass_unmapped_false_must_not_swallow_sustain_and_expression_on_the_keyboard_port(make_rig, target):
    tuned_only(target)
    rig = make_rig(midi_in_populated=False)
    rig.host.set_config(FORWARD_USE_PROCESSOR=True, PASS_UNMAPPED=False)
    for cc in (64, 11, 7):
        assert rig.midi(0xB0, cc, 100, role="forward").handled is False, cc


@pytest.mark.xfail(strict=True, reason="RA-02: MODE_FOLLOWS_FOCUS=True undoes the Bank/mode toggle when ui.getFocused does not follow ui.setFocused at once")
def test_c_ra02_the_mode_toggle_survives_a_focus_that_does_not_move(monkeypatch, make_rig, target):
    tuned_only(target)
    from tests.flsim.fakes.ui import UiImpl
    monkeypatch.setattr(UiImpl, "setFocused", lambda self, index: self.s.visible.add(index))      # focus stays where it was
    rig = make_rig()
    rig.tap(kl.BTN_MIXER_TOGGLE)
    assert rig.fader(0, 100).called("mixer.setTrackVolume", 1)          # stock: mixer mode is the script's own state


@pytest.mark.xfail(strict=True, reason="RA-02: visiting the Browser from Mixer mode and coming back silently switches the faders to Channel Rack mode (stock stays in Mixer mode)")
def test_c_ra02_mixer_mode_survives_a_round_trip_through_the_browser(make_rig, target):
    tuned_only(target)
    rig = make_rig()
    rig.tap(kl.BTN_MIXER_TOGGLE)
    rig.tap(kl.BTN_BROWSER)
    rig.tap(kl.BTN_BROWSER)
    assert rig.fader(0, 100).called("mixer.setTrackVolume", 1)


# RA-03 (folder + latch half) fixed with R-HS-03 (review round 1): KLTLog creates the folder and never latches dead
def test_c_ra03_the_log_is_written_even_if_its_folder_did_not_exist(make_rig, target):
    tuned_only(target)
    rig = make_rig(boot=False)
    path = os.path.join(rig.host.tmpdir, "ProgramData", "DeLoMIDI", "klt.log")
    sys.modules["KLTConfig"].LOG_PATH = path
    rig.scripts.boot(order=("forward", "entry"))
    rig.button(104)
    assert os.path.exists(path)


@pytest.mark.xfail(strict=True, reason="RA-03: the logger's _dead latch and every one-shot diagnostic (PROBE samples, PROBE-VERDICT, UNMAPPED first-seen) survive OnDeInit/OnInit, so a Reload re-capture is incomplete")
def test_c_ra03_a_script_reload_starts_a_fresh_diagnostic_capture(make_rig, target):
    tuned_only(target)
    rig = make_rig(midi_in_populated=False)
    rig.button(104)
    rig.midi(0x99, 36, 100, role="forward")
    first = [l for l in rig.host.read_log().splitlines() if "PROBE-VERDICT" in l or "UNMAPPED" in l]
    assert first
    for s in (rig.entry, rig.forward):
        s.call("OnDeInit")
    os.remove(rig.host.log_path)
    rig.host.advance(5)
    for s in (rig.forward, rig.entry):
        s.call("OnInit")
    rig.button(104)
    rig.midi(0x99, 36, 100, role="forward")
    again = [l for l in rig.host.read_log().splitlines() if "PROBE-VERDICT" in l or "UNMAPPED" in l]
    assert len(again) == len(first)


@pytest.mark.xfail(strict=True, reason="RA-05: the raw OnMidiIn path reads the derived aliases controlNum/controlVal; the FL manual lists only data1/data2 as available in OnMidiIn")
def test_c_ra05_the_keyboard_port_raw_path_needs_only_status_data1_data2(monkeypatch, make_rig, target):
    tuned_only(target)
    from tests.flsim import loader
    from tests.flsim.events import FlEvent
    raw = [False]

    def gated(name):
        orig = getattr(FlEvent, name)
        return property(lambda self: 0 if raw[0] else orig.fget(self), orig.fset)
    for n in ("controlNum", "controlVal", "note", "velocity", "pressure", "progNum"):
        monkeypatch.setattr(FlEvent, n, gated(n))
    orig_stage = loader.ScriptInstance._stage

    def stage(self, cb, ev, stages, excs, raise_errors):
        raw[0] = cb == "OnMidiIn"
        try:
            return orig_stage(self, cb, ev, stages, excs, raise_errors)
        finally:
            raw[0] = False
    monkeypatch.setattr(loader.ScriptInstance, "_stage", stage)
    rig = make_rig(midi_in_populated=False)
    rig.tap(kl.BTN_SEQ_TOGGLE)
    rig.midi(0x99, 36, 100, role="forward")
    assert rig.midi(0x89, 36, 0, role="forward").called("channels.setGridBit", 0, 0, 1)


# RA-06 fixed with RA-04 (review round 1): the UNMAPPED line names the real disposition
def test_c_ra06_the_unmapped_log_line_of_the_keyboard_port_tells_the_truth(make_rig, target):
    tuned_only(target)
    rig = make_rig(midi_in_populated=False)
    rig.host.set_config(PASS_UNMAPPED=False)
    a = rig.midi(0xB0, 64, 127, role="forward")
    assert a.handled is False
    assert not [l for l in rig.host.read_log().splitlines() if "forward-cc" in l and "swallowed" in l]


@pytest.mark.xfail(strict=True, reason="RA-07 (premise UNVERIFIED, F-17): if FL gives each device script its own module instances, Save on the DAW port never puts the keyboard-port pads into Sequencer mode; FL's documented cross-script route is device.dispatch / # receiveFrom")
def test_c_ra07_sequencer_pads_on_the_keyboard_port_do_not_rely_on_shared_module_state(make_rig, target):
    tuned_only(target)
    rig = make_rig(midi_in_populated=False)
    sys.modules.pop("KLTProcess", None)                 # the Forward script's lazy `import KLTProcess` now builds its own copy
    rig.forward.module._process_module = None
    rig.tap(kl.BTN_SEQ_TOGGLE)
    assert rig.midi(0x99, 36, 100, role="forward").handled is True
