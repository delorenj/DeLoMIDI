"""Regenerate tests/data/plugin_db.json: which plugin parameter each knob/fader of the stock parameter database drives.

    python -m tests.flsim.gen_plugin_golden [STOCK_DIR] > tests/data/plugin_db.json

The stock script is driven through its public entry (OnMidiMsg) with each of the 15 database plugins focused; the
parameter index that reaches plugins.setParamValue is recorded (null = the control is unmapped). The file is the
"characterization" of Arturia's data (docs/analysis/02-input-audit.md 5.3): the tuned scripts must keep it.
"""
from __future__ import annotations

import json
import os
import sys

from . import Host
from .rig import Rig

DB_PLUGINS = ["FLEX", "FPC", "FL Keys", "Sytrus", "GMS", "Harmless", "Harmor", "Morphine", "3x Osc", "Fruity DX10",
              "BASSDRUM", "Fruit kick", "MiniSynth", "PoiZone", "Sakura"]
DEFAULT_STOCK = os.environ.get("KL_STOCK_DIR",
                               "/home/delorenj/Documents/Image-Line/FL Studio/Settings/Hardware/Arturia KeyLab MKII")


def _param_of(action):
    sets = [c for c in action.effects if c.qual == "plugins.setParamValue"]
    return sets[0].args[1] if sets else None


def drive(folder) -> dict:
    out = {}
    with Host() as host:
        scripts = host.load(folder)
        scripts.boot(order=("forward", "entry"))
        rig = Rig(host, scripts)
        for name in DB_PLUGINS:
            host.state.select_channel_plugin(name, 0)
            host.state.focus(5, name)
            knobs = [_param_of(rig.cc(16 + i, 1)) for i in range(8)]
            faders = [_param_of(rig.fader(i, 100)) for i in range(8)]
            out[name] = {"knobs": knobs, "faders": faders}
    return out


def main(argv=None) -> int:
    folder = (argv or sys.argv[1:] or [DEFAULT_STOCK])[0]
    json.dump(drive(folder), sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
