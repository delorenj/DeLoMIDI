"""Strict fakes of every FL API module the KeyLab scripts (and their likely fixes) use."""
from __future__ import annotations

from .. import surface
from .base import FakeModule, Impl, build_native_module  # noqa: F401
from .channels import ChannelsImpl
from .device import DeviceImpl
from .general import GeneralImpl
from .mixer import MixerImpl
from .patterns import PatternsImpl
from .playlist import PlaylistImpl
from .plugins import PluginsImpl
from .pylib import load_midi, load_utils
from .transport import TransportImpl
from .ui import UiImpl

IMPLS = {
    "channels": ChannelsImpl, "device": DeviceImpl, "general": GeneralImpl, "mixer": MixerImpl,
    "patterns": PatternsImpl, "playlist": PlaylistImpl, "plugins": PluginsImpl, "transport": TransportImpl,
    "ui": UiImpl,
    # in the surface, no behaviour modelled: every function raises NotImplementedError naming itself
    "arrangement": None, "screen": None, "launchMapPages": None,
}


def build_modules(host) -> dict:
    """All modules a script can import, keyed by name."""
    mods = {}
    for name in surface.NATIVE_MODULES:
        impl_cls = IMPLS.get(name)
        mods[name] = build_native_module(host, name, impl_cls(host) if impl_cls else None)
    mods["midi"] = load_midi(host.midi_py)
    mods["utils"] = load_utils(host.midi_py)
    return mods
