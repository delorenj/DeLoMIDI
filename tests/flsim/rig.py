"""A small convenience layer over Host + ScriptSet for tests and tools: send controls, capture what each action did."""
from __future__ import annotations

from typing import NamedTuple, Optional

from .driver import SessionDriver
from .host import Host
from .loader import ScriptInstance, ScriptSet


class Action(NamedTuple):
    """Everything one stimulus caused."""
    delivery: Optional[object]     # loader.Delivery for MIDI/SysEx stimuli, else None
    calls: list                    # every recorded Call (queries and sysex included)
    effects: list                  # Calls that change FL/device state (no queries, no sysex, no sleep)
    sysex: list                    # SysexMsg sent
    violations: list
    errors: list                   # ScriptError: exceptions that escaped a callback (FL-like catch)
    result: object = None

    @property
    def event(self):
        return self.delivery.event if self.delivery else None

    @property
    def handled(self):
        return self.delivery.handled if self.delivery else None

    @property
    def names(self) -> list:
        return [c.qual for c in self.effects]

    @property
    def lines(self) -> list:
        return [c.short() for c in self.effects]

    def called(self, qual: str, *args) -> bool:
        """True if an effect call `qual` was made whose first positional args equal `args` (none = any args)."""
        return any(c.qual == qual and tuple(c.args[:len(args)]) == args for c in self.effects)

    def calls_to(self, qual: str) -> list:
        return [c for c in self.calls if c.qual == qual]

    def kinds(self, kind: str) -> list:
        return [v for v in self.violations if v.kind == kind]


class Rig:
    def __init__(self, host: Host, scripts: ScriptSet):
        self.host = host
        self.scripts = scripts
        self.state = host.state
        self.driver = SessionDriver(scripts)

    @property
    def entry(self) -> ScriptInstance:
        return self.scripts.entry

    @property
    def forward(self) -> Optional[ScriptInstance]:
        return self.scripts.forward

    # ---- capture -----------------------------------------------------------------------------------------------------
    def capture(self, fn) -> Action:
        h = self.host
        m = h.mark()
        r = fn()
        v = h.since(m)
        return Action(r if hasattr(r, "stages") else None, v.calls, h.effects(v.calls), v.sysex, v.violations,
                      v.errors, None if hasattr(r, "stages") else r)

    def midi(self, status, d1=0, d2=0, role="entry", **kw) -> Action:
        s = getattr(self.scripts, role)
        return self.capture(lambda: s.deliver_midi(status, d1, d2, **kw))

    # ---- controls (DAW port unless role says otherwise) --------------------------------------------------------------
    def button(self, note: int, pressed: bool = True, role: str = "entry", **kw) -> Action:
        """Note-on channel 1, velocity 127 = press, velocity 0 = release (the contract the stock script assumes)."""
        return self.midi(0x90, note, 127 if pressed else 0, role, **kw)

    def tap(self, note: int) -> list:
        return [self.button(note, True), self.button(note, False)]

    def cc(self, cc: int, value: int, role: str = "entry", **kw) -> Action:
        return self.midi(0xB0, cc, value, role, **kw)

    def fader(self, n: int, value: int, role: str = "entry") -> Action:
        """Fader n (0..8) = pitch bend on channel n+1; only the MSB (data2) matters to the scripts."""
        return self.midi(0xE0 + n, 0, value, role)

    def pad_on(self, note: int, velocity: int = 100, role: str = "entry", **kw) -> Action:
        return self.midi(0x99, note, velocity, role, **kw)

    def pad_off(self, note: int, velocity: int = 0, role: str = "entry", **kw) -> Action:
        return self.midi(0x89, note, velocity, role, **kw)

    # ---- time ------------------------------------------------------------------------------------------------------------
    def idle(self, seconds: float = 0.0, ticks: Optional[int] = None) -> Action:
        if ticks is not None:
            return self.capture(lambda: self.driver.tick(ticks, playback=False))
        return self.capture(lambda: self.driver.run(seconds, playback=False))

    def settle(self, seconds: float = 3.0) -> Action:
        """Let the scripts idle long enough for pending LCD/LED updates (rate limits, keep-alives) to land."""
        return self.idle(seconds)

    def refresh(self, flags: int = 256 | 1) -> Action:
        return self.capture(lambda: self.driver.refresh(flags))
