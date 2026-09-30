"""Shared helpers of the tests/test_input_*.py files (input side of the tuned KeyLab mkII scripts).

No tests here. Everything is a plain function so a test module can use it without fixtures."""
from __future__ import annotations

import sys

import pytest

from tests import kl


def tuned_only(target):
    """Skip on Arturia's stock folder: the test is about a tuned-only feature (KLTConfig switch, KLTLog line, ...)."""
    if target.is_stock:
        pytest.skip("tuned-only feature: %s has no KLTConfig/KLTLog" % target.path.name)


def log_lines(rig, needle=None):
    text = rig.host.read_log()
    lines = [l for l in text.splitlines() if l.strip()]
    return [l for l in lines if needle in l] if needle else lines


def fresh_second(rig):
    """Boot and setup lines may have used up KLTLog's flood guard (50 lines per second of the virtual clock)."""
    rig.host.advance(2.0)
    rig.host.set_config(LOG_MAX_LINES_PER_SEC=100000)


def module(name):
    """A module of the loaded script folder (KLTProcess, KLTCrossKeyboard, ...)."""
    return sys.modules[name]


def focus_plugin(rig, name):
    rig.state.select_channel_plugin(name)
    rig.state.focus(kl.WID_PLUGIN, name)


def fwd(rig, status, d1, d2, populated=False):
    """An event on the keyboard port (Forward script). populated=False = H2: midiId is 0 inside OnMidiIn."""
    return rig.midi(status, d1, d2, role="forward", populated=populated)


def set_params(action):
    return [(c.args[1], round(c.args[0], 4)) for c in action.effects if c.qual == "plugins.setParamValue"]
