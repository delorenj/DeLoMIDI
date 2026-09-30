"""midi and utils: the two plain-Python modules in FL's Shared/Python/Lib.

midi is loaded at run time from Image-Line's real file (never copied into the repo):
    $FL_MIDI_PY, default /home/delorenj/.wine/drive_c/Program Files/Image-Line/FL Studio 2025/Shared/Python/Lib/midi.py
If it is absent the constants recorded in tests/fl_api_surface.json (constants.midi_fl_real, generated from that same
file) are used, and `midi.__flsim_source__` says which source is in effect. utils is loaded from the file next to
midi.py, with a small built-in fallback.
"""
from __future__ import annotations

import importlib.util
import math
import os
import types
from pathlib import Path

from .. import surface
from .base import FakeModule

DEFAULT_MIDI_PY = ("/home/delorenj/.wine/drive_c/Program Files/Image-Line/FL Studio 2025/Shared/Python/Lib/midi.py")


def midi_py_path(explicit=None) -> str:
    return explicit or os.environ.get("FL_MIDI_PY") or DEFAULT_MIDI_PY


def _exec_file(name: str, path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_midi(explicit=None) -> types.ModuleType:
    path = midi_py_path(explicit)
    if os.path.isfile(path):
        mod = _exec_file("midi", path)
        mod.__flsim_source__ = "real:" + path
        return mod
    mod = types.ModuleType("midi")
    for k, v in surface.midi_constants().items():
        setattr(mod, k, v)

    def EncodeRemoteControlID(PortNum, ChanNum, CCNum):
        return (PortNum << 24) + (ChanNum << 16) + CCNum
    mod.EncodeRemoteControlID = EncodeRemoteControlID
    mod.__flsim_source__ = "surface-constants"
    return mod


def _fallback_utils() -> types.ModuleType:
    mod = FakeModule("utils")

    def Limited(Value, Min, Max):
        return Min if Value <= Min else (Max if Value > Max else Value)

    def KnobAccelToRes2(Value):
        n = abs(Value)
        return n ** 0.75 if n > 1 else 1

    def SignOf(value):
        return -1 if value < 0 else 1

    def Sign(value):
        return 0 if value == 0 else (-1 if value < 0 else 1)

    for fn in (Limited, KnobAccelToRes2, SignOf, Sign):
        mod.__dict__[fn.__name__] = fn
    mod.math = math
    mod.__flsim_source__ = "builtin-fallback"
    return mod


def load_utils(midi_path=None) -> types.ModuleType:
    p = Path(midi_py_path(midi_path)).with_name("utils.py")
    if p.is_file():
        mod = _exec_file("utils", str(p))
        mod.__flsim_source__ = "real:" + str(p)
        return mod
    return _fallback_utils()
