"""Seeded fuzz of every callback of a script folder: random events x random FL states, FL-like exception catching.

    python -m tests.flsim.fuzz <script_dir> [--events N] [--seed S] [--unassigned]

Reports the unique exception sites (callback, exception type, file:line, message) with counts and one reproducer each,
FLCrash occurrences, and rule violations recorded by the strict fakes.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter

from .host import FLCrash, Host
from .state import FLState
from . import streams


class FuzzResult:
    def __init__(self, folder, n_events, seed, output_assigned):
        self.folder, self.n_events, self.seed, self.output_assigned = folder, n_events, seed, output_assigned
        self.events = 0
        self.episodes = 0
        self.exceptions: dict = {}          # key -> [count, example]
        self.flcrashes: list = []           # (episode, op index, reason)
        self.violations: Counter = Counter()
        self.load_errors: list = []
        self.sysex_sent = 0
        self.seconds = 0.0

    def add_exception(self, key, example):
        e = self.exceptions.setdefault(key, [0, example])
        e[0] += 1

    @property
    def exception_count(self) -> int:
        return sum(v[0] for v in self.exceptions.values())

    def violation_kinds(self, kind: str) -> int:
        return sum(n for (k, _), n in self.violations.items() if k == kind)

    def report(self, limit=15) -> str:
        lines = ["fuzz %s: %d events in %d episodes, seed %d, output_assigned=%s, %.1fs, %d SysEx sent" % (
            self.folder, self.events, self.episodes, self.seed, self.output_assigned, self.seconds, self.sysex_sent)]
        lines.append("  FLCrash: %d" % len(self.flcrashes))
        for ep, i, why in self.flcrashes[:5]:
            lines.append("     episode %d op %d: %s" % (ep, i, why))
        lines.append("  exception sites: %d (%d exceptions)" % (len(self.exceptions), self.exception_count))
        for key, (n, ex) in sorted(self.exceptions.items(), key=lambda kv: -kv[1][0])[:limit]:
            lines.append("    %6d x %s.%s: %s @ %s: %s" % ((n,) + key))
            lines.append("           e.g. %s" % ex)
        if self.load_errors:
            lines.append("  load errors: %s" % self.load_errors[:3])
        if self.violations:
            lines.append("  violations: " + ", ".join("%s %s x%d" % (k, w, n) for (k, w), n in
                                                     self.violations.most_common(8)))
        return "\n".join(lines)


def run_fuzz(folder, n_events: int = 100_000, seed: int = 1, output_assigned: bool = True,
             episode_len: int = 250, midi_py=None) -> FuzzResult:
    res = FuzzResult(str(folder), n_events, seed, output_assigned)
    t0 = time.perf_counter()
    with Host(output_assigned=output_assigned, record_calls=False, midi_py=midi_py) as host:
        for ep in streams.episodes(seed, n_events, episode_len):
            res.episodes += 1
            host.state = FLState()
            host.clear_trace()
            host.midi_in_populated = ep.midi_in_populated
            try:
                scripts = host.load(folder)
            except Exception as e:  # noqa: BLE001
                res.load_errors.append("%s: %s" % (type(e).__name__, e))
                continue
            crashed = _guarded(res, ep, -1, lambda: scripts.boot())
            for i, op in enumerate(ep.ops):
                if crashed:
                    break
                if op[0] != "state":
                    res.events += 1
                crashed = _guarded(res, ep, i, lambda: streams.apply_op(scripts, op))
                _drain(res, host, ep, i, op)
            if not crashed:
                _guarded(res, ep, len(ep.ops), lambda: scripts.deinit())
                _drain(res, host, ep, len(ep.ops), ("deinit",))
            res.sysex_sent += len(host.sysex)
            for v in host.violations:
                res.violations[(v.kind, v.where)] += 1
    res.seconds = time.perf_counter() - t0
    return res


def _guarded(res, ep, i, fn) -> bool:
    try:
        fn()
    except FLCrash as c:
        res.flcrashes.append((ep.index, i, "%s [%s]" % (c.reason, c.qual)))
        return True
    return False


def _drain(res, host, ep, i, op):
    if host.errors:
        for e in host.errors:
            res.add_exception((e.script, e.callback, type(e.exc).__name__, e.site, str(e.exc)[:80]),
                              "episode %d op %d %r (seed %d)" % (ep.index, i, op, res.seed))
        host.errors.clear()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("script_dir")
    ap.add_argument("--events", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--unassigned", action="store_true", help="MIDI output not assigned (FLCrash emulation)")
    a = ap.parse_args(argv)
    r = run_fuzz(a.script_dir, a.events, a.seed, not a.unassigned)
    print(r.report())
    return 1 if (r.exceptions or r.flcrashes or r.load_errors) else 0


if __name__ == "__main__":
    sys.exit(main())
