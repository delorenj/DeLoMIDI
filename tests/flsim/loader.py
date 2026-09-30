"""Load a KeyLab script folder the way FL does, and drive its callbacks.

FL model implemented here:

* one Python interpreter for every device script (the stock Forward script does `import device_KeyLabmkII as KL`
  and shares KL._processor; module state is shared between the two scripts);
* the script folder is on sys.path, every helper module is a plain import, module state is fresh at every load;
* each device script has its own MIDI output (host.outputs) and port; device.* calls act for the script whose
  callback (or import) is running (host.current);
* an event goes OnMidiIn -> (unless handled) OnMidiMsg (OnSysEx for SysEx) -> (unless handled) the typed callback
  (OnNoteOn, OnControlChange, OnPitchBend, ...), as documented in the FL manual (midi_scripting, Script events).
  Exceptions inside a callback are caught and reported by `deliver_*` like FL's Script output does; `invoke`
  lets them propagate so a test can assert on them.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import NamedTuple, Optional

from . import surface
from .events import FlEvent

_TYPED = {0x80: "OnNoteOff", 0x90: "OnNoteOn", 0xA0: "OnKeyPressure", 0xB0: "OnControlChange",
          0xC0: "OnProgramChange", 0xD0: "OnChannelPressure", 0xE0: "OnPitchBend"}
DEFAULT_BOOT_ORDER = ("entry", "forward")
HW_ALL = 0x1FFFF   # plausible "everything is dirty" flags for the first OnRefresh after init


def detect_scripts(folder: Path) -> tuple[Optional[Path], Optional[Path]]:
    """(entry, forward) device script of a KeyLab folder. Works for the stock names and the tuned names."""
    cands = sorted(p for p in folder.glob("device_*.py"))
    fwd = [p for p in cands if "forward" in p.name.lower()]
    rest = [p for p in cands if p not in fwd]
    if len(rest) > 1:
        named = [p for p in rest if re.search(r"^#\s*name\s*=", p.read_text(encoding="utf-8", errors="replace"), re.M)]
        rest = named or rest
    if len(rest) > 1 or len(fwd) > 1:
        raise RuntimeError("ambiguous device scripts in %s: entry=%s forward=%s" % (folder, rest, fwd))
    return (rest[0] if rest else None), (fwd[0] if fwd else None)


def header_value(path: Path, key: str) -> Optional[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^#\s*%s\s*=\s*(.*?)\s*$" % re.escape(key), text, re.M)
    return m.group(1) if m else None


def _module_name(path: Path) -> str:
    return re.sub(r"\W", "_", path.stem)


class Delivery(NamedTuple):
    event: FlEvent
    stages: list          # [(callback, exception or None)] in order
    handled: bool         # final event.handled
    exceptions: list      # exceptions that escaped a callback (FL would print them in Script output)

    @property
    def forwarded_to_fl(self) -> bool:
        """True when no script consumed the event, i.e. FL's default routing would still process it."""
        return not self.handled


class ScriptInstance:
    def __init__(self, host, role: str, path: Path):
        self.host = host
        self.role = role
        self.path = path
        self.name = header_value(path, "name") or path.stem
        self.receive_from = header_value(path, "receiveFrom")
        self.module_name = _module_name(path)
        self.module = None

    # ---- import ----------------------------------------------------------------------------------------------------
    def load(self) -> None:
        h = self.host
        prev = (h.current, h.phase, h.cb)
        h.current, h.phase, h.cb = self, "import", "import"
        saved_out = sys.stdout
        if h.capture_prints:
            sys.stdout = h._stdout
        try:
            spec = importlib.util.spec_from_file_location(self.module_name, str(self.path))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[self.module_name] = mod
            h._loaded_names.add(self.module_name)
            self.module = mod
            spec.loader.exec_module(mod)
        finally:
            sys.stdout = saved_out
            h.current, h.phase, h.cb = prev

    # ---- callbacks -------------------------------------------------------------------------------------------------
    def has(self, callback: str) -> bool:
        return callable(getattr(self.module, callback, None))

    def invoke(self, callback: str, *args):
        """Call a callback the script defines (no-op returning None if it does not, like FL). Exceptions propagate."""
        if callback not in surface.load_surface()["callbacks"]:
            raise AttributeError("'%s' is not an FL script callback" % callback)
        fn = getattr(self.module, callback, None)
        if not callable(fn):
            return None
        h = self.host
        prev = (h.current, h.phase, h.cb)
        h.current, h.phase, h.cb = self, callback, callback
        saved_out = sys.stdout
        if h.capture_prints:
            sys.stdout = h._stdout
        try:
            return fn(*args)
        finally:
            sys.stdout = saved_out
            h.current, h.phase, h.cb = prev
            h.apply_config_overrides()

    def call(self, callback: str, *args):
        """Like invoke, but an Exception is caught and recorded in host.errors (what FL does). Returns
        (result, exception or None). FLCrash is a BaseException and always propagates."""
        try:
            return self.invoke(callback, *args), None
        except Exception as e:  # noqa: BLE001 - this is exactly FL's catch-all
            self.host.record_error(self.role, callback, e)
            return None, e

    def __getattr__(self, name):
        if name.startswith("On") and name in surface.load_surface()["callbacks"]:
            return lambda *a: self.invoke(name, *a)
        raise AttributeError(name)

    # ---- events -----------------------------------------------------------------------------------------------------
    def deliver_midi(self, status: int, data1: int = 0, data2: int = 0, *, populated: Optional[bool] = None,
                     port: Optional[int] = None, pme: int = 0b101110, raise_errors: bool = False) -> Delivery:
        """Run one short MIDI event through OnMidiIn -> OnMidiMsg -> typed callback.

        populated=None uses host.midi_in_populated (H1 True / H2 False) for the OnMidiIn stage; OnMidiMsg always
        sees midiId/midiChan filled."""
        h = self.host
        pop = h.midi_in_populated if populated is None else populated
        ev = h.make_event(status, data1, data2, populated=pop, pmeFlags=pme,
                          port=h.port_numbers.get(self.role, 0) if port is None else port)
        return self._pipeline(ev, sysex=False, raise_errors=raise_errors)

    def deliver_sysex(self, data: bytes, *, raise_errors: bool = False) -> Delivery:
        ev = self.host.make_event(bytes(data), populated=False, port=self.host.port_numbers.get(self.role, 0))
        return self._pipeline(ev, sysex=True, raise_errors=raise_errors)

    def deliver_event(self, ev: FlEvent, *, sysex: bool = False, raise_errors: bool = False) -> Delivery:
        return self._pipeline(ev, sysex=sysex, raise_errors=raise_errors)

    def _stage(self, cb, ev, stages, excs, raise_errors):
        if raise_errors:
            self.invoke(cb, ev)
            stages.append((cb, None))
            return
        _, e = self.call(cb, ev)
        stages.append((cb, e))
        if e is not None:
            excs.append(e)

    def _pipeline(self, ev: FlEvent, sysex: bool, raise_errors: bool) -> Delivery:
        stages, excs = [], []
        self._stage("OnMidiIn", ev, stages, excs, raise_errors)
        if not ev.handled:
            ev.populate()
            self._stage("OnSysEx" if sysex else "OnMidiMsg", ev, stages, excs, raise_errors)
            if not ev.handled and not sysex:
                typed = _TYPED.get(ev.status & 0xF0)
                if typed:
                    self._stage(typed, ev, stages, excs, raise_errors)
        return Delivery(ev, stages, ev.handled, excs)

    # ---- lifecycle helpers ----------------------------------------------------------------------------------------
    def boot(self, refresh_flags: Optional[int] = HW_ALL, raise_errors: bool = False):
        """OnInit, then the full OnRefresh FL sends when a controller is attached (assumption: FL refreshes after
        init; flags value is a plausible 'everything dirty')."""
        if raise_errors:
            self.invoke("OnInit")
            if refresh_flags is not None:
                self.invoke("OnRefresh", refresh_flags)
            return
        self.call("OnInit")
        if refresh_flags is not None:
            self.call("OnRefresh", refresh_flags)


class ScriptSet:
    """The device scripts of one folder, sharing one interpreter and one Host."""

    def __init__(self, host, folder: Path, entry: Optional[ScriptInstance], forward: Optional[ScriptInstance]):
        self.host = host
        self.folder = folder
        self.entry = entry
        self.forward = forward

    @property
    def scripts(self) -> list:
        return [s for s in (self.entry, self.forward) if s is not None]

    def boot(self, order=DEFAULT_BOOT_ORDER, **kw) -> "ScriptSet":
        """OnInit + OnRefresh of every script. FL's init order between the two device scripts is UNVERIFIED and it
        matters: the stock Forward script's OnInit re-runs KL.init(), replacing the DAW script's display and
        processor objects (F-17/O-09). `order` names the roles in the order they are initialised."""
        for role in order:
            s = getattr(self, role)
            if s is not None:
                s.boot(**kw)
        return self

    def deinit(self) -> None:
        for s in self.scripts:
            s.call("OnDeInit")


def load_scripts(host, folder, *, entry: bool = True, forward: bool = True) -> ScriptSet:
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise FileNotFoundError("script folder not found: %s" % folder)
    epath, fpath = detect_scripts(folder)
    if entry and epath is None:
        raise RuntimeError("no entry device_*.py in %s" % folder)
    # fresh state: forget anything left over from an earlier load of this or another folder
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if f and Path(f).resolve().parent == folder:
            sys.modules.pop(name, None)
    importlib.invalidate_caches()
    host._path_entry = str(folder)
    sys.path.insert(0, host._path_entry)
    e = ScriptInstance(host, "entry", epath) if (entry and epath) else None
    f = ScriptInstance(host, "forward", fpath) if (forward and fpath) else None
    host._script_folder = folder
    try:
        for s in (e, f):
            if s is not None:
                s.load()
    finally:
        host.track_script_modules()
    return ScriptSet(host, folder, e, f)
