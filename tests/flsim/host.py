"""The simulated FL Studio host.

A Host owns: the mutable FL state (state.py), a virtual clock (clock.py), strict fakes of every FL API module
(fakes/), and a record of everything scripts do to it: every API call, every SysEx sent through device.midiOutSysex
(with a virtual timestamp), every rule violation and every exception a callback let escape.

    with Host() as host:                       # installs the fakes + virtual time, restores everything on exit
        scripts = host.load("scripts/KeyLab mkII tuned")
        scripts.boot()
        scripts.entry.deliver_midi(0x90, 94, 127)      # press Play
        assert [c.qual for c in host.effects()][-1] == "transport.start"

Crash emulation (docs/incidents/2026-09-29-fl-crash-kl-probe.crash.txt): FLCrash is a BaseException, so no script
`except Exception:` can swallow it by accident. It is raised when

* the script's MIDI output is unassigned (Host(output_assigned=False) or host.set_output_assigned(role, False)) and
  it calls device.midiOutSysex / device.midiOutMsg  (leading hypothesis for the tom crash), or
* any device.* function is called at import time or from outside every script callback
  ("calling device functions in an interpreter not associated with a device causes FL Studio to crash",
  stubs device/__device.py:53) -- Host(crash_on_import_device_calls=False) turns the import-time rule off.

What is NOT modelled: FL's own processing after a script (default routing, link system), real FL threading, the real
idle rate, and every internal of FL. See docs/tuned/TESTING.md.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
import types
from typing import Any, NamedTuple, Optional

from . import surface
from .clock import TimePatch, VirtualClock
from .events import FlEvent
from .state import FLState

_ACTIVE: Optional["Host"] = None


class FLCrash(BaseException):
    """FL Studio itself would have crashed (access violation in FLEngine). Not an Exception: cannot be swallowed by
    a script's `except Exception`."""

    def __init__(self, reason: str, qual: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.qual = qual


class RuleViolation(IndexError):
    """Raised instead of recording when Host(on_violation='raise')."""


class Violation(NamedTuple):
    kind: str        # 'index' | 'event-range' | 'value' | 'param-index' | 'sysex-framing'
    where: str
    message: str
    script: Optional[str]
    callback: Optional[str]
    t: float


class ScriptError(NamedTuple):
    script: str
    callback: str
    exc: BaseException
    site: str        # 'file.py:123 in func' of the innermost frame
    t: float


class Call:
    """One FL API call (or the pseudo call time.sleep) as scripts made it."""
    __slots__ = ("seq", "t", "qual", "args", "kwargs", "result", "exc", "script", "cb", "phase")

    def __init__(self, seq, t, qual, args, kwargs, script, cb, phase):
        self.seq, self.t, self.qual, self.args, self.kwargs = seq, t, qual, args, kwargs
        self.result = None
        self.exc = None
        self.script, self.cb, self.phase = script, cb, phase

    @property
    def is_query(self) -> bool:
        return self.qual == "time.sleep" or surface.is_query(self.qual)

    def short(self) -> str:
        a = ", ".join(_fmt(x) for x in self.args)
        if self.kwargs:
            a += (", " if a else "") + ", ".join("%s=%s" % (k, _fmt(v)) for k, v in self.kwargs.items())
        return "%s(%s)" % (self.qual, a)

    def __repr__(self):
        return "<Call %s t=%.3f %s/%s%s>" % (self.short(), self.t, self.script, self.cb,
                                             " EXC=%s" % type(self.exc).__name__ if self.exc else "")


def _fmt(v) -> str:
    if isinstance(v, float):
        return "%.4g" % v
    if isinstance(v, (bytes, bytearray)):
        return "b'%s'" % bytes(v).hex()
    if isinstance(v, FlEvent):
        return "ev(0x%02X,%d,%d)" % (v.status, v.data1, v.data2)
    return repr(v)


class SysexMsg(NamedTuple):
    t: float
    data: bytes          # the whole message as passed to device.midiOutSysex
    valid: bool          # framing ok: F0 ... F7, all interior bytes < 0x80
    script: Optional[str]
    callback: Optional[str]


class Mark(NamedTuple):
    calls: int
    sysex: int
    violations: int
    errors: int
    sleeps: int


class View(NamedTuple):
    calls: list
    sysex: list
    violations: list
    errors: list


def check_framing(data: bytes) -> Optional[str]:
    if len(data) < 2:
        return "message shorter than 2 bytes"
    if data[0] != 0xF0:
        return "does not start with F0"
    if data[-1] != 0xF7:
        return "does not end with F7"
    bad = [i for i, b in enumerate(data[1:-1], 1) if b >= 0x80]
    if bad:
        return "data byte >= 0x80 at offset %d (0x%02X)" % (bad[0], data[bad[0]])
    return None


def exception_site(exc: BaseException, folder=None) -> str:
    """'file.py:123 in func' of the innermost frame inside the script folder (falls back to the last frame), so an
    error raised by a strict fake is attributed to the script line that provoked it."""
    tb = traceback.extract_tb(exc.__traceback__)
    if not tb:
        return "?"
    fr = tb[-1]
    if folder is not None:
        for f in reversed(tb):
            if os.path.dirname(os.path.abspath(f.filename)) == str(folder):
                fr = f
                break
    return "%s:%d in %s" % (os.path.basename(fr.filename), fr.lineno, fr.name)


class _ScriptStdout:
    """Stands in for sys.stdout while a Host is active: scripts' print() lands in host.script_output."""

    def __init__(self, host):
        self._host = host
        self._buf = ""

    def write(self, text):
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            h = self._host
            h.script_output.append((h.clock.now, h.current.role if h.current else None, line))
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return False

    encoding = "utf-8"


class Host:
    def __init__(self, *, output_assigned: bool = True, crash_on_unassigned_output: bool = True,
                 crash_on_import_device_calls: bool = True, strict_types: bool = True,
                 on_violation: str = "record", midi_in_populated: bool = True, record_calls: bool = True,
                 state: Optional[FLState] = None, midi_py: Optional[str] = None, capture_prints: bool = True):
        if on_violation not in ("record", "raise"):
            raise ValueError("on_violation must be 'record' or 'raise'")
        self.state = state or FLState()
        self.clock = VirtualClock()
        self.clock.context = lambda: (self.current.role if self.current else None, self.cb)
        self.clock.on_sleep = self._record_sleep
        self.crash_on_unassigned_output = crash_on_unassigned_output
        self.crash_on_import_device_calls = crash_on_import_device_calls
        self.strict_types = strict_types
        self.on_violation = on_violation
        self.midi_in_populated = midi_in_populated      # H1 (True) / H2 (False) for OnMidiIn events
        self.record_calls = record_calls
        self.capture_prints = capture_prints
        self.script_output: list[tuple] = []     # (t, script, text) lines the scripts print (FL: Script output)
        self.tmpdir: Optional[str] = None
        self.log_path: Optional[str] = None
        self._orig_cwd: Optional[str] = None
        self._stdout = _ScriptStdout(self)      # swapped in around script code only (pytest re-captures sys.stdout per phase)
        self.midi_py = midi_py
        self.default_output_assigned = output_assigned
        self.outputs: dict[str, bool] = {}
        self.port_numbers: dict[str, int] = {"entry": 0, "forward": 1}
        # what scripts did
        self.calls: list[Call] = []
        self.sysex: list[SysexMsg] = []
        self.violations: list[Violation] = []
        self.errors: list[ScriptError] = []
        self.dropped_sysex: list[bytes] = []     # sent while unassigned with crash_on_unassigned_output=False
        self.midi_out: list[tuple] = []
        self.forwarded: list[tuple] = []
        self.processed: list[tuple] = []
        self.dispatched: list[tuple] = []
        self.call_count = 0
        self._faults: dict = {}
        self._seq = 0
        # execution context
        self.current = None          # ScriptInstance whose callback/import is running
        self.phase = "test"          # 'import' | callback name | 'test'
        self.cb: Optional[str] = None
        # installation
        self.modules: dict[str, types.ModuleType] = {}
        self.script_set = None
        self._saved_modules: dict[str, Any] = {}
        self._loaded_names: set[str] = set()
        self._path_entry: Optional[str] = None
        self._script_folder = None
        self._cfg_seen = None
        self._timepatch: Optional[TimePatch] = None
        self._saved_bytecode = False
        self._entered = False

    # ---- installation ---------------------------------------------------------------------------------------
    def __enter__(self) -> "Host":
        global _ACTIVE
        if _ACTIVE is not None:
            raise RuntimeError("another flsim Host is already active (only one interpreter-wide host at a time)")
        from .fakes import build_modules
        self.modules = build_modules(self)
        for name, mod in self.modules.items():
            if name in sys.modules:
                self._saved_modules[name] = sys.modules[name]
            sys.modules[name] = mod
        self._timepatch = TimePatch(self.clock)
        self._timepatch.__enter__()
        self._saved_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True     # never write __pycache__ next to (stock) scripts
        # run inside a scratch directory: a script that logs to a Windows path (C:\ProgramData\...) would otherwise
        # create a file with that literal name in the current directory on Linux
        self._orig_cwd = os.getcwd()
        self.tmpdir = tempfile.mkdtemp(prefix="flsim-")
        self.log_path = os.path.join(self.tmpdir, "klt.log")
        os.chdir(self.tmpdir)
        _ACTIVE = self
        self._entered = True
        return self

    def __exit__(self, *exc):
        global _ACTIVE
        try:
            self.unload()
        finally:
            for name in self.modules:
                sys.modules.pop(name, None)
            sys.modules.update(self._saved_modules)
            self._saved_modules.clear()
            if self._timepatch is not None:
                self._timepatch.__exit__(*exc)
                self._timepatch = None
            sys.dont_write_bytecode = self._saved_bytecode
            if self._orig_cwd is not None:
                os.chdir(self._orig_cwd)
            if self.tmpdir:
                shutil.rmtree(self.tmpdir, ignore_errors=True)
            _ACTIVE = None
            self._entered = False
        return False

    # ---- loading -----------------------------------------------------------------------------------------------
    def load(self, folder, **kw):
        from .loader import load_scripts
        if not self._entered:
            raise RuntimeError("use `with Host() as host:` before loading scripts")
        self.unload()
        p = os.fspath(folder)
        if not os.path.isabs(p) and self._orig_cwd:
            p = os.path.join(self._orig_cwd, p)
        self.script_set = load_scripts(self, p, **kw)
        self.apply_config_overrides()
        return self.script_set

    def apply_config_overrides(self) -> None:
        """Point the tuned scripts' log file at the scratch dir (KLTConfig.LOG_PATH is a Windows path). Applied once
        per KLTConfig module object, after load and after any callback that imported it lazily."""
        cfg = sys.modules.get("KLTConfig")
        if cfg is not None and cfg is not self._cfg_seen and hasattr(cfg, "LOG_PATH"):
            cfg.LOG_PATH = self.log_path
            self._cfg_seen = cfg

    def set_config(self, **overrides) -> None:
        """Set switches of the tuned scripts (KLTConfig attributes) for the rest of this load, e.g.
        host.set_config(LOG_ENABLED=False). The module must be loaded and the switch must exist (a typo fails)."""
        cfg = sys.modules.get("KLTConfig")
        if cfg is None:
            raise RuntimeError("KLTConfig is not loaded (stock folder, or nothing loaded yet)")
        for k, v in overrides.items():
            if not hasattr(cfg, k):
                raise AttributeError("KLTConfig has no switch %s" % k)
            setattr(cfg, k, v)

    def read_log(self) -> str:
        """Contents of the tuned scripts' klt.log written during this host's life ('' if none)."""
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    def track_script_modules(self) -> None:
        """Remember every imported module that lives in the script folder (helpers included)."""
        folder = self._script_folder
        if folder is None:
            return
        for name, mod in list(sys.modules.items()):
            f = getattr(mod, "__file__", None)
            if f and os.path.dirname(os.path.abspath(f)) == str(folder):
                self._loaded_names.add(name)

    def unload(self) -> None:
        self.track_script_modules()     # also catches helpers imported lazily inside callbacks
        for name in list(self._loaded_names):
            sys.modules.pop(name, None)
        self._loaded_names.clear()
        self._script_folder = None
        self._cfg_seen = None
        if self._path_entry is not None:
            try:
                sys.path.remove(self._path_entry)
            except ValueError:
                pass
            self._path_entry = None
        self.script_set = None
        self.current = None
        self.phase = "test"
        self.cb = None

    # ---- output assignment ----------------------------------------------------------------------------------------
    def set_output_assigned(self, role: str, assigned: bool) -> None:
        self.outputs[role] = bool(assigned)

    def output_assigned(self, role: Optional[str]) -> bool:
        return self.outputs.get(role, self.default_output_assigned)

    # ---- recording -----------------------------------------------------------------------------------------------
    def _begin_call(self, qual: str, args: tuple, kwargs: dict) -> Optional[Call]:
        self.call_count += 1
        if not self.record_calls:
            return None
        self._seq += 1
        c = Call(self._seq, self.clock.now, qual, args, kwargs,
                 self.current.role if self.current else None, self.cb, self.phase)
        self.calls.append(c)
        return c

    def _record_sleep(self, seconds: float) -> None:
        if self.record_calls:
            self._seq += 1
            self.calls.append(Call(self._seq, self.clock.now, "time.sleep", (seconds,), {},
                                   self.current.role if self.current else None, self.cb, self.phase))

    def violation(self, kind: str, where: str, message: str) -> None:
        v = Violation(kind, where, message, self.current.role if self.current else None, self.cb, self.clock.now)
        if self.on_violation == "raise":
            raise RuleViolation("%s: %s (%s)" % (kind, message, where))
        self.violations.append(v)

    def record_sysex(self, data: bytes) -> SysexMsg:
        bad = check_framing(data)
        msg = SysexMsg(self.clock.now, bytes(data), bad is None,
                       self.current.role if self.current else None, self.cb)
        self.sysex.append(msg)
        if bad is not None:
            self.violation("sysex-framing", "device.midiOutSysex", "%s: %s" % (bad, bytes(data).hex()))
        return msg

    # ---- fault injection ------------------------------------------------------------------------------------------
    def inject_fault(self, qual: str, exc=RuntimeError, times: Optional[int] = None) -> None:
        """Make an API function raise `exc` (class or instance) when called, `times` times (None = until cleared).
        For partial-init and 'FL API misbehaves' tests."""
        self._faults[qual] = [exc, times]

    def clear_faults(self) -> None:
        self._faults.clear()

    def _maybe_fail(self, qual: str) -> None:
        f = self._faults.get(qual)
        if f is None:
            return
        exc, left = f
        if left is not None:
            if left <= 0:
                del self._faults[qual]
                return
            f[1] = left - 1
        raise exc("injected fault in %s" % qual) if isinstance(exc, type) else exc

    def record_error(self, script: str, callback: str, exc: BaseException) -> ScriptError:
        e = ScriptError(script, callback, exc, exception_site(exc, self._script_folder), self.clock.now)
        self.errors.append(e)
        return e

    def make_event(self, status, data1=0, data2=0, **kw) -> FlEvent:
        kw.setdefault("timestamp", int(self.clock.now * 1000) & 0x7FFFFFFF)
        return FlEvent(status, data1, data2, sink=self.violation, **kw)

    # ---- trace views ------------------------------------------------------------------------------------------------
    def mark(self) -> Mark:
        return Mark(len(self.calls), len(self.sysex), len(self.violations), len(self.errors), len(self.clock.sleeps))

    def since(self, mark: Mark) -> View:
        return View(self.calls[mark.calls:], self.sysex[mark.sysex:], self.violations[mark.violations:],
                    self.errors[mark.errors:])

    def clear_trace(self) -> None:
        self.calls.clear()
        self.sysex.clear()
        self.violations.clear()
        self.errors.clear()
        self.midi_out.clear()
        self.dropped_sysex.clear()
        self.forwarded.clear()
        self.processed.clear()
        self.dispatched.clear()
        self.clock.sleeps.clear()

    def api_calls(self, calls=None) -> list[Call]:
        """Every FL API call (the pseudo call time.sleep is excluded, see clock.sleeps)."""
        return [c for c in (self.calls if calls is None else calls) if c.qual != "time.sleep"]

    def effects(self, calls=None, include_sysex: bool = False) -> list[Call]:
        """API calls that change FL / the device: queries (get*/is*/counts) are dropped; sysex sends only on request."""
        out = []
        for c in (self.calls if calls is None else calls):
            if c.qual == "time.sleep" or surface.is_query(c.qual):
                continue
            if not include_sysex and c.qual == "device.midiOutSysex":
                continue
            out.append(c)
        return out

    def calls_to(self, prefix: str, calls=None) -> list[Call]:
        """Calls whose qualified name equals `prefix` or starts with it (e.g. 'transport.' or 'ui.setFocused')."""
        return [c for c in (self.calls if calls is None else calls)
                if c.qual == prefix or (prefix.endswith(".") and c.qual.startswith(prefix))]

    def trace_lines(self, calls=None, include_queries: bool = False, include_sysex: bool = False) -> list[str]:
        out = []
        for c in (self.calls if calls is None else calls):
            if c.qual == "device.midiOutSysex" and not include_sysex:
                continue
            if not include_queries and c.is_query:
                continue
            out.append(c.short())
        return out

    def device_model(self, role: Optional[str] = None, since: Optional[Mark] = None):
        """What the keyboard would be showing after the recorded SysEx (see flsim/sysex.py)."""
        from .sysex import DeviceModel
        msgs = self.sysex[(since.sysex if since else 0):]
        if role is not None:
            msgs = [m for m in msgs if m.script == role]
        return DeviceModel.from_messages(msgs)

    # ---- time -----------------------------------------------------------------------------------------------------------
    def advance(self, seconds: float) -> None:
        self.clock.advance(seconds)
