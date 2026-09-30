"""Replay one identical seeded stream through two script sets and print a categorized behavioural diff.

    python -m tests.flsim.diffreplay <stock_dir> <tuned_dir> [--events N] [--seed S] [--unassigned]
                                     [--show K] [--fail-on-regression]

The stream (MIDI events on both ports, idle ticks, refreshes, beat callbacks, SysEx, FL state changes, script
reloads) is generated from the seed alone (streams.py), so both sides see exactly the same input. After every op the
script set's observable behaviour is recorded:

  api-calls      FL API calls that change something (queries, SysEx and time.sleep excluded)
  handled/event  the event's handled flag and any mutation of status/data1/data2/midiId
  exceptions     exceptions a callback let escape (FL would print them in Script output), and FLCrash
  sysex          number and kind (LED / RGB / LCD) of SysEx sent per op kind (raw messages legitimately differ once
                 the tuned script de-duplicates; what matters is the settled result, next line)
  device-state   what the keyboard would show after every episode plus 3 s of idle (LED/LCD content)
  violations     rule violations recorded by the strict fakes (index/value/event-range/...)

Output: a summary table, then groups (op kind x category x what changed) with counts and one example each, so
"only intended behaviour changed" can be checked by reading the groups.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from typing import NamedTuple, Optional

from . import streams
from .host import FLCrash, Host
from .state import FLState
from .sysex import DeviceModel, decode

STATUS_NAMES = {0x80: "note-off", 0x90: "note-on", 0xA0: "key-aftertouch", 0xB0: "CC", 0xC0: "program", 0xD0: "chan-aftertouch",
                0xE0: "pitch-bend", 0xF0: "system"}
SETTLE_TICKS = 150     # 3 s of idle at 50 Hz


class OpRecord(NamedTuple):
    effects: tuple
    sysex: tuple            # the exact SysEx messages sent (bytes), in order
    handled: Optional[bool]
    event: Optional[tuple]  # snapshot after the op (status, d1, d2, handled, midiId, midiChan, sysex)
    exceptions: tuple       # ((callback, type, site), ...)
    crash: Optional[str]
    slept: float
    violations: tuple       # ((kind, where), ...)


class SideResult:
    def __init__(self, folder):
        self.folder = folder
        self.ops: list = []          # OpRecord per op, aligned across sides
        self.settled: list = []      # (episode, DeviceModel.state())
        self.settled_lcd: list = []
        self.crashed_episodes = 0
        self.load_errors: list = []


def op_desc(op) -> str:
    k = op[0]
    if k == "midi":
        _, role, st, d1, d2 = op
        base = STATUS_NAMES.get(st & 0xF0, "0x%02X" % st)
        ch = st & 0x0F
        d = ""
        if st & 0xF0 in (0x80, 0x90, 0xB0):
            d = " %d" % d1
        return "%s %s%s ch%d" % (role, base, d, ch + 1)
    if k == "sysex":
        return "sysex %s" % op[1]
    if k == "refresh":
        return "refresh"
    if k in ("idle", "wait", "beat"):
        return k
    return k


def _run_side(folder, episodes_, output_assigned, boot_order=("forward", "entry"), midi_py=None) -> SideResult:
    res = SideResult(folder)
    with Host(output_assigned=output_assigned, midi_py=midi_py) as host:
        for ep in episodes_:
            host.state = FLState()
            host.clear_trace()
            host.midi_in_populated = ep.midi_in_populated
            try:
                scripts = host.load(folder)
            except Exception as e:  # noqa: BLE001
                res.load_errors.append("%s: %s" % (type(e).__name__, e))
                for op in ep.ops:
                    res.ops.append(_blank())
                continue
            model = DeviceModel()      # what the keyboard has been told since this episode's load
            # boot counts as an op so its effects are compared too
            res.ops.append(_observe(host, lambda: scripts.boot(order=boot_order), None, model))
            crashed = res.ops[-1].crash
            for op in ep.ops:
                if crashed:
                    res.ops.append(_blank(crash="(episode aborted after FLCrash)"))
                    continue
                res.ops.append(_observe(host, lambda: streams.apply_op(scripts, op), op, model))
                crashed = res.ops[-1].crash
            if crashed:
                res.crashed_episodes += 1
                res.settled.append((ep.index, None))
                res.settled_lcd.append(None)
                continue
            host.clear_trace()
            try:
                for _ in range(SETTLE_TICKS):
                    streams.apply_op(scripts, ("idle",))
            except FLCrash:
                res.settled.append((ep.index, None))
                res.settled_lcd.append(None)
                continue
            for m in host.sysex:
                model.apply(m)
            res.settled.append((ep.index, model.state()))
            res.settled_lcd.append(model.lcd)
    return res


def _blank(crash=None):
    return OpRecord((), (), None, None, (), crash, 0.0, ())


def _observe(host, fn, op, model) -> OpRecord:
    host.clear_trace()
    slept_before = host.clock.slept_total
    crash = None
    delivered = {"ev": None}
    if op is not None and op[0] == "midi":
        s = getattr(host.script_set, op[1])
        if s is None:
            return _blank()

        def run():
            d = s.deliver_midi(op[2], op[3], op[4])
            delivered["ev"] = d.event
        fn = run
    try:
        fn()
    except FLCrash as c:
        crash = "%s [%s]" % (c.reason.split(":")[0][:90], c.qual)
    effects = tuple(host.trace_lines())
    sysex = tuple(m.data for m in host.sysex)
    ev = delivered["ev"]
    excs = tuple((e.callback, type(e.exc).__name__, norm_site(e.site)) for e in host.errors)
    for m in host.sysex:
        model.apply(m)
    return OpRecord(effects, sysex, ev.handled if ev is not None else None, ev.snapshot() if ev is not None else None,
                    excs, crash, host.clock.slept_total - slept_before, tuple((v.kind, v.where) for v in host.violations))


_MODULE_RENAMES = [
    (re.compile(r"^device_Forward\w*"), "device_forward"),
    (re.compile(r"^device_KeyLab\w*"), "device_entry"),
    (re.compile(r"^ArturiaCrossKeyboardKLmk2$|^KLTCrossKeyboard$"), "CrossKeyboard"),
    (re.compile(r"^ArturiaVCOL$|^KLTVCOL$"), "VCOL"),
    (re.compile(r"^KeyLabmk2(\w+)$|^KLT(\w+)$"), lambda m: m.group(1) or m.group(2)),
]


def norm_site(site: str) -> str:
    """'KLTReturn.py:201 in SelectedChannel' and 'KeyLabmk2Return.py:118 in SelectedChannel' -> 'Return.SelectedChannel':
    stock and tuned files are named differently and line numbers move, so neither may take part in the comparison."""
    m = re.match(r"^(.*?)\.py:\d+ in (.*)$", site)
    if not m:
        return site
    mod, func = m.group(1), m.group(2)
    for rx, repl in _MODULE_RENAMES:
        if rx.match(mod):
            mod = rx.sub(repl, mod)
            break
    return "%s.%s" % (mod, func)


def _norm(line: str) -> str:
    """API call without arguments, for grouping."""
    return line.split("(", 1)[0]


class Diff(NamedTuple):
    category: str
    group: str
    example: str


def compare(stock: SideResult, tuned: SideResult, ops_flat: list) -> tuple[list, Counter, dict]:
    diffs: list = []
    totals: Counter = Counter()
    sysex_by_op: dict = {}
    for i, (a, b) in enumerate(zip(stock.ops, tuned.ops)):
        desc = ops_flat[i]
        d = op_desc(desc) if desc is not None else "boot"
        totals["ops"] += 1
        if a.effects != b.effects:
            ca, cb = Counter(a.effects), Counter(b.effects)
            only_a, only_b = ca - cb, cb - ca
            key = "%s: -[%s] +[%s]" % (d, ", ".join(sorted({_norm(x) for x in only_a})),
                                       ", ".join(sorted({_norm(x) for x in only_b})))
            if not only_a and not only_b:
                key = "%s: same calls, different order" % d
            diffs.append(Diff("api-calls", key, "stock=%s\n         tuned=%s" % (list(a.effects)[:8], list(b.effects)[:8])))
        if a.handled != b.handled or (a.event and b.event and a.event[:3] != b.event[:3]):
            what = []
            if a.handled != b.handled:
                what.append("handled %s -> %s" % (a.handled, b.handled))
            if a.event and b.event and a.event[:3] != b.event[:3]:
                what.append("event %s -> %s" % (a.event[:3], b.event[:3]))
            diffs.append(Diff("handled/event", "%s: %s" % (d, what[0].split(" ")[0]),
                              "%s (%s)" % (", ".join(what), desc)))
        if a.exceptions != b.exceptions or a.crash != b.crash:
            sa, sb = bool(a.exceptions or a.crash), bool(b.exceptions or b.crash)
            kind = ("fixed (stock raised, tuned does not)" if sa and not sb else
                    "REGRESSION (tuned raises, stock does not)" if sb and not sa else "both raise, differently")
            diffs.append(Diff("exceptions", "%s: %s" % (d, kind),
                              "stock=%s crash=%s | tuned=%s crash=%s (%s)" % (a.exceptions[:2], a.crash, b.exceptions[:2],
                                                                            b.crash, desc)))
        if a.violations != b.violations:
            ca, cb = Counter(a.violations), Counter(b.violations)
            only_a, only_b = sorted(set(ca - cb)), sorted(set(cb - ca))
            diffs.append(Diff("violations", "%s: -%s +%s" % (d, sorted({k for k, _ in only_a}), sorted({k for k, _ in only_b})),
                              "stock=%s tuned=%s (%s)" % (only_a[:3], only_b[:3], desc)))
        if (a.slept > 0) != (b.slept > 0):
            diffs.append(Diff("sleep", "%s: %s" % (d, "stock sleeps, tuned does not" if a.slept > 0 else "tuned sleeps, stock does not"),
                              "slept %.2fs -> %.2fs" % (a.slept, b.slept)))
        totals["sysex-stock"] += len(a.sysex)
        totals["sysex-tuned"] += len(b.sysex)
        if a.sysex != b.sysex:
            totals["sysex-ops-differ"] += 1
        row = sysex_by_op.setdefault(d, [0, 0, 0, 0, 0, 0, 0])      # ops, stock msgs, tuned msgs, stock lcd, tuned lcd, ops differing
        row[0] += 1
        row[1] += len(a.sysex)
        row[2] += len(b.sysex)
        row[3] += sum(1 for x in a.sysex if decode(x).kind == "lcd")
        row[4] += sum(1 for x in b.sysex if decode(x).kind == "lcd")
        row[5] += 1 if a.sysex != b.sysex else 0
    return diffs, totals, sysex_by_op


def report(stock: SideResult, tuned: SideResult, episodes_, args, show: int) -> tuple[str, bool]:
    ops_flat = []
    for ep in episodes_:
        ops_flat.append(None)          # boot
        ops_flat.extend(ep.ops)
    n = min(len(stock.ops), len(tuned.ops), len(ops_flat))
    diffs, totals, sysex_by_op = compare(stock, tuned, ops_flat[:n])
    L = []
    L.append("diffreplay: stock=%s\n            tuned=%s\n            events=%d seed=%d output_assigned=%s boot-order=%s (%d ops replayed)" % (
        stock.folder, tuned.folder, args.events, args.seed, not args.unassigned, args.boot_order, n))
    by_cat = Counter(d.category for d in diffs)
    L.append("\n== summary: ops that differ per category (of %d ops) ==" % n)
    for cat in ("api-calls", "handled/event", "exceptions", "violations", "sleep"):
        L.append("  %-14s %7d" % (cat, by_cat.get(cat, 0)))
    L.append("  %-14s %7d ops send a different SysEx sequence (stock sent %d messages, tuned %d)" % (
        "sysex", totals["sysex-ops-differ"], totals["sysex-stock"], totals["sysex-tuned"]))
    sa = sum(1 for _, s in stock.settled if s is not None)
    same = sum(1 for (i, s), (j, t) in zip(stock.settled, tuned.settled) if s is not None and s == t)
    L.append("  %-14s %d of %d episodes end with identical keyboard LED+LCD state after 3 s idle (%d stock episodes "
             "aborted by FLCrash, %d tuned)" % ("device-state", same, sa, stock.crashed_episodes, tuned.crashed_episodes))
    if stock.load_errors or tuned.load_errors:
        L.append("  LOAD ERRORS stock=%s tuned=%s" % (stock.load_errors[:2], tuned.load_errors[:2]))

    L.append("\n== SysEx per op kind (largest differences first): ops, stock msgs -> tuned msgs, LCD frames stock -> tuned, "
             "ops whose sequence differs ==")
    rows = sorted(sysex_by_op.items(), key=lambda kv: -abs(kv[1][1] - kv[1][2]))
    for d, (nops, sa, sb, la, lb, nd, _) in rows[:min(show, 12)]:
        if sa or sb:
            L.append("  %-30s %6d ops  %8d -> %-8d LCD %5d -> %-5d  %6d differ" % (d, nops, sa, sb, la, lb, nd))

    exc_stock = Counter((e[0], e[1], e[2]) for r in stock.ops for e in r.exceptions)
    exc_tuned = Counter((e[0], e[1], e[2]) for r in tuned.ops for e in r.exceptions)
    L.append("\n== exceptions escaping callbacks (stock %d, tuned %d) ==" % (sum(exc_stock.values()), sum(exc_tuned.values())))
    for label, c in (("stock", exc_stock), ("tuned", exc_tuned)):
        for (cb, t, site), k in c.most_common(6):
            L.append("  %-5s %6d x %s: %s @ %s" % (label, k, cb, t, site))
    crashes_s = sum(1 for r in stock.ops if r.crash and not r.crash.startswith("("))
    crashes_t = sum(1 for r in tuned.ops if r.crash and not r.crash.startswith("("))
    L.append("  FLCrash: stock %d, tuned %d" % (crashes_s, crashes_t))

    dev_diff = [(i, s, t, a, b) for (i, s), (_, t), a, b in zip(stock.settled, tuned.settled, stock.settled_lcd, tuned.settled_lcd)
                if s is not None and s != t]
    if dev_diff:
        L.append("\n== device-state differences after settle (first %d of %d episodes) ==" % (min(4, len(dev_diff)), len(dev_diff)))
        for i, s, t, a, b in dev_diff[:4]:
            mono_a, rgb_a, _ = s
            mono_b, rgb_b, _ = t
            leds = sorted({k for k, _ in set(mono_a) ^ set(mono_b)} | {k for k, _ in set(rgb_a) ^ set(rgb_b)})
            L.append("  episode %d: LEDs that differ %s; stock LCD=%r  tuned LCD=%r" % (
                i, ["0x%02X" % k for k in leds][:10], a, b))

    groups = defaultdict(list)
    for d in diffs:
        groups[(d.category, d.group)].append(d)
    L.append("\n== groups (category / what changed): count, one example ==")
    for cat in ("exceptions", "api-calls", "handled/event", "violations", "sleep"):
        items = sorted(((k, v) for k, v in groups.items() if k[0] == cat), key=lambda kv: -len(kv[1]))
        if not items:
            continue
        L.append("\n[%s] %d groups" % (cat, len(items)))
        for (c, g), v in items[:show]:
            L.append("  %5d x %s" % (len(v), g))
            L.append("         e.g. %s" % v[0].example)
        if len(items) > show:
            L.append("  ... %d more groups (use --show)" % (len(items) - show))
    regression = any("REGRESSION" in d.group for d in diffs) or crashes_t > crashes_s
    return "\n".join(L), regression


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tests.flsim.diffreplay", description=__doc__.split("\n")[0])
    ap.add_argument("stock_dir")
    ap.add_argument("tuned_dir")
    ap.add_argument("--events", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--unassigned", action="store_true", help="replay with the MIDI output unassigned")
    ap.add_argument("--boot-order", default="forward,entry", choices=["forward,entry", "entry,forward"],
                    help="which device script FL initialises first (unverified; the stock Forward script's OnInit "
                         "replaces the DAW script's display objects when it runs second: F-17/O-09)")
    ap.add_argument("--show", type=int, default=25, help="groups to print per category (default 25)")
    ap.add_argument("--fail-on-regression", action="store_true",
                    help="exit 1 if tuned raises where stock does not, or FLCrashes more often")
    a = ap.parse_args(argv)
    eps = list(streams.episodes(a.seed, a.events))
    order = tuple(a.boot_order.split(","))
    stock = _run_side(a.stock_dir, eps, not a.unassigned, order)
    tuned = _run_side(a.tuned_dir, eps, not a.unassigned, order)
    text, regression = report(stock, tuned, eps, a, a.show)
    print(text)
    return 1 if (a.fail_on_regression and regression) else 0


if __name__ == "__main__":
    sys.exit(main())
