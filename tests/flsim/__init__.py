"""flsim: a strict, virtual-time simulator of the FL Studio MIDI-scripting host, for the KeyLab mkII scripts.

    from tests.flsim import Host, FLCrash

    with Host(output_assigned=False) as host:
        scripts = host.load("scripts/KeyLab mkII tuned")
        try:
            scripts.boot()
        except FLCrash: ...

See docs/tuned/TESTING.md for what is and is not modelled.
"""
from .clock import VirtualClock  # noqa: F401
from .driver import SessionDriver, sysex_per_second  # noqa: F401
from .events import FlEvent  # noqa: F401
from .host import Call, FLCrash, Host, RuleViolation, SysexMsg, Violation  # noqa: F401
from .loader import Delivery, ScriptInstance, ScriptSet, detect_scripts  # noqa: F401
from .state import FLState  # noqa: F401
from .sysex import DeviceModel, decode  # noqa: F401
