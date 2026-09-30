"""The 15-plugin parameter database (knobs 1-8 = CC16..23, faders 1-8 = pitch bend ch1..8) in Channel Rack mode.

tests/data/plugin_db.json records which plugin parameter index each control drives in Arturia's stock script
(regenerate with `python -m tests.flsim.gen_plugin_golden`). It is Arturia's data: the tuned scripts keep it."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import kl

GOLDEN = json.loads((Path(__file__).parent / "data" / "plugin_db.json").read_text())

# stock quirks the database is known to have (docs/analysis/02 5.3): controls that share a parameter index.
KNOWN_DUPLICATES = {("FL Keys", "knobs", 5), ("FL Keys", "knobs", 6), ("Fruity DX10", "knobs", 5), ("Fruity DX10", "faders", 3),
                    ("Harmless", "knobs", 2), ("Harmless", "faders", 7)}


def focus(rig, plugin):
    rig.state.select_channel_plugin(plugin)
    rig.state.focus(kl.WID_PLUGIN, plugin)


def drive(rig, kind, i):
    return rig.cc(16 + i, 1) if kind == "knobs" else rig.fader(i, 100)


def param_set(action):
    return [c.args[1] for c in action.effects if c.qual == "plugins.setParamValue"]


def test_the_golden_file_covers_every_database_plugin():
    assert sorted(GOLDEN) == sorted(kl.DB_PLUGINS)
    assert all(len(v["knobs"]) == 8 and len(v["faders"]) == 8 for v in GOLDEN.values())


@pytest.mark.parametrize("plugin", kl.DB_PLUGINS)
def test_every_mapped_control_drives_its_documented_parameter(rig, plugin):
    focus(rig, plugin)
    for kind in ("knobs", "faders"):
        for i, want in enumerate(GOLDEN[plugin][kind]):
            if want is None:
                continue
            a = drive(rig, kind, i)
            assert param_set(a) == [want], "%s %s %d: expected parameter %d, got %s" % (plugin, kind, i + 1, want, a.lines)
            assert a.errors == []


@pytest.mark.parametrize("plugin", kl.DB_PLUGINS)
def test_unmapped_controls_do_not_set_any_parameter(rig, plugin):
    focus(rig, plugin)
    for kind in ("knobs", "faders"):
        for i, want in enumerate(GOLDEN[plugin][kind]):
            if want is None:
                a = drive(rig, kind, i)
                assert param_set(a) == [], (plugin, kind, i + 1, a.lines)
                assert a.errors == []


@pytest.mark.parametrize("plugin", ["FPC", "Sytrus", "MiniSynth"])
def test_faders_set_the_parameter_absolutely(rig, plugin):
    focus(rig, plugin)
    p = GOLDEN[plugin]["faders"][0]
    for v in (0, 1, 64, 100, 127):
        a = rig.fader(0, v)
        (c,) = [x for x in a.effects if x.qual == "plugins.setParamValue"]
        assert c.args[0] == pytest.approx(v / 127) and c.args[1] == p and c.args[2] == 0


@pytest.mark.parametrize("plugin", ["FPC", "Sytrus", "MiniSynth"])
def test_knobs_turn_the_parameter_up_clockwise_and_down_counter_clockwise(rig, plugin):
    focus(rig, plugin)
    p = GOLDEN[plugin]["knobs"][0]
    rig.state.param_values[(0, p)] = 0.5
    (up,) = [c for c in rig.cc(16, 1).effects if c.qual == "plugins.setParamValue"]
    rig.state.param_values[(0, p)] = 0.5
    (dn,) = [c for c in rig.cc(16, 65).effects if c.qual == "plugins.setParamValue"]
    assert up.args[0] > 0.5 > dn.args[0]


def test_controls_do_nothing_for_a_plugin_that_is_not_in_the_database(rig):
    focus(rig, "Serum")
    for kind in ("knobs", "faders"):
        for i in range(8):
            a = drive(rig, kind, i)
            assert param_set(a) == [] and a.errors == []
    rig.idle(0.1)
    assert rig.host.device_model().lcd == ("This control", "is not mapped !")


def test_plugin_name_and_percentage_appear_on_the_lcd(rig):
    focus(rig, "FPC")
    rig.state.param_names[(0, 0)] = "Master Vol"
    rig.fader(0, 127)
    rig.idle(0.1)
    assert rig.host.device_model().lcd == ("Master Vol", "100%")


def test_database_names_are_matched_exactly(rig):
    """'FPC' matches, 'fpc' and 'FPC ' do not (the odd casing of 'BASSDRUM' / 'Fruit kick' is deliberate)."""
    for name in ("fpc", "FPC ", "Fpc"):
        focus(rig, name)
        assert param_set(rig.fader(0, 100)) == [], name
    focus(rig, "BASSDRUM")
    assert param_set(rig.fader(0, 100)) == [GOLDEN["BASSDRUM"]["faders"][0]]


def test_the_known_duplicate_controls_are_exactly_the_ones_documented():
    """Controls that share a parameter index inside one plugin (F-16): recorded, not fixed (the intended parameter
    is unknown without the plugins' parameter lists from the host)."""
    dups = set()
    for plugin, d in GOLDEN.items():
        where = {}
        for kind in ("knobs", "faders"):
            for i, p in enumerate(d[kind]):
                if p is not None:
                    where.setdefault(p, []).append((kind, i))
        for p, controls in where.items():
            if len(controls) > 1:
                dups.update((plugin, kind, i) for kind, i in controls)
    assert dups == KNOWN_DUPLICATES


def test_the_golden_file_is_what_the_stock_scripts_do():
    """Guards tests/data/plugin_db.json against hand edits: regenerate it from the stock folder and compare."""
    from tests.conftest import STOCK_DIR
    if not STOCK_DIR.is_dir():
        pytest.skip("stock folder not found: %s" % STOCK_DIR)
    from tests.flsim.gen_plugin_golden import drive
    assert drive(STOCK_DIR) == GOLDEN
