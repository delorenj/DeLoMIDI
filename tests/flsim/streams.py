"""Seeded, host-independent streams of FL events, idle ticks and FL state changes.

The stream depends only on the seed, never on what a script did, so the very same stream can be replayed through the
stock and the tuned scripts (diffreplay.py) and used for fuzzing (tests/test_fuzz.py).

An op is a tuple:
    ('midi', role, status, data1, data2)     role = 'entry' (DAW port) | 'forward' (keyboard port)
    ('sysex', role, bytes)
    ('idle',)                                one OnIdle period (20 ms of virtual time)
    ('wait', seconds)                        time passes (no callback), then one OnIdle
    ('refresh', flags)
    ('beat', value)
    ('state', name, arg)                     a change of FL state (not counted as an event)
"""
from __future__ import annotations

import random
from typing import Iterator, NamedTuple

from .state import PLUGIN_WINDOWS

PLUGINS = ["", "FLEX", "FPC", "FL Keys", "Sytrus", "GMS", "Harmless", "Harmor", "Morphine", "3x Osc", "Fruity DX10",
           "BASSDRUM", "Fruit kick", "MiniSynth", "PoiZone", "Sakura", "Sampler", "Analog Lab V", "Mini V3", "Serum"]
NAMES = ["Kick", "Snare", "Hat", "Clap", "808 Bass", "Lead 1", "", "A" * 40, "Café", "Kick ♪",
         "ドラム", "tab\there", "nul\x00byte", "line\nbreak", "über – pad"]
TITLES = ["FL Studio 2026", "FL Studio 2026 - Café Sessions", "My Project", "", "T" * 60]
BUTTON_IDS = [0, 1, 7, 8, 12, 15, 16, 20, 23, 24, 27, 31, 32, 39, 46, 47, 51, 56, 57, 74, 81, 84, 86, 87, 88, 89,
              91, 92, 93, 94, 95, 98, 99, 104, 112]
ENCODER_CCS = list(range(16, 25)) + [60]
OTHER_CCS = [1, 7, 10, 11, 28, 29, 64, 71, 72, 73, 74, 75, 76, 77, 79, 80, 82, 83, 91, 93]
TICKS = [0, 1, 2, 3, 5, 10, 32, 63, 64, 65, 66, 67, 70, 100, 126, 127]
FLAGS = [0, 1, 4, 32, 256, 4096, 16384, 65536, 0x1FFFF, 1024, 2048]
SYSEX_MEMORY_SWITCH = b"\xf0\x00 k\x7fB\x02\x00\x00\x15\x00\xf7"   # the message the entry script's OnSysEx recognises


class Episode(NamedTuple):
    index: int
    midi_in_populated: bool
    ops: list


def _midi_entry(r: random.Random):
    k = r.random()
    if k < 0.36:                                   # buttons: note-on ch1, press/release, plus some note-off
        d1 = r.choice(BUTTON_IDS) if r.random() < 0.8 else r.randrange(128)
        st = 0x90 if r.random() < 0.92 else 0x80
        return ("midi", "entry", st, d1, r.choice([0, 127, 127, r.randrange(128)]))
    if k < 0.58:                                   # encoders / jog
        cc = r.choice(ENCODER_CCS) if r.random() < 0.85 else r.choice(OTHER_CCS)
        return ("midi", "entry", 0xB0, cc, r.choice(TICKS + [r.randrange(128)]))
    if k < 0.72:                                   # faders (pitch bend ch1..9) and stray channels
        return ("midi", "entry", 0xE0 + r.randrange(9) if r.random() < 0.95 else 0xE0 + r.randrange(16),
                r.randrange(128), r.randrange(128))
    if k < 0.94:                                   # pads
        st = r.choice([0x99, 0x99, 0x89, 0x89, 0x99, 0x89])
        note = r.randrange(36, 52) if r.random() < 0.85 else r.choice([0, 20, 35, 52, 60, 100, 127])
        return ("midi", "entry", st, note, r.choice([0, 1, 64, 100, 127, r.randrange(128)]))
    st = r.choice([0xA0, 0xC0, 0xD0, 0xB1, 0x91, 0x81, 0xF8, 0xFE, 0xB9, 0x9F])
    return ("midi", "entry", st, r.randrange(128), r.randrange(128))


def _midi_forward(r: random.Random):
    k = r.random()
    if k < 0.55:                                   # keybed
        return ("midi", "forward", r.choice([0x90, 0x90, 0x80]), r.randrange(21, 109), r.randrange(1, 128))
    if k < 0.75:                                   # mod wheel / Analog Lab CCs / preset buttons
        return ("midi", "forward", 0xB0, r.choice(OTHER_CCS + [16, 17, 18, 19, 60]), r.choice(TICKS))
    if k < 0.9:                                    # pitch wheel
        return ("midi", "forward", 0xE0, r.randrange(128), r.randrange(128))
    if k < 0.95:                                   # pads / button ids also arriving on the keyboard port
        return ("midi", "forward", r.choice([0x99, 0x89, 0x90]), r.choice(BUTTON_IDS + list(range(36, 52))),
                r.choice([0, 100, 127]))
    return ("midi", "forward", r.choice([0xA0, 0xD0, 0xC0]), r.randrange(128), r.randrange(128))


def _state_op(r: random.Random):
    # NB: no "tracks" op: real FL always has 127 mixer tracks (master + 125 inserts + "current"), see fakes/mixer.py
    k = r.choice(["focus", "focus", "channels", "select", "mute", "solo", "loop", "popup", "node",
                  "track", "pattern", "transport", "flags", "tempo", "songpos", "title", "names", "step", "plugin"])
    if k == "focus":
        w = r.choice([0, 1, 1, 2, 3, 4, 5, 6, 7])
        return ("state", "focus", (w, r.choice(PLUGINS) if w in PLUGIN_WINDOWS else ""))
    if k == "channels":
        return ("state", "channels", r.choice([0, 1, 5, 8, 9, 16, 17, 40, 300]))
    if k in ("select", "mute", "solo", "track"):
        return ("state", k, r.random())
    if k == "loop":
        return ("state", "loop", r.choice([0, 1]))
    if k == "popup":
        return ("state", "popup", r.random() < 0.5)
    if k == "node":
        return ("state", "node", r.choice([-1, -100, -101, 0, 5]))
    if k == "pattern":
        return ("state", "pattern", (r.choice([1, 2, 3, 99]), r.choice([1, 3, 99])))
    if k == "transport":
        return ("state", "transport", (r.random() < 0.5, r.random() < 0.3))
    if k == "flags":
        return ("state", "flags", (r.random() < 0.5, r.random() < 0.5, r.random() < 0.5))
    if k == "tempo":
        return ("state", "tempo", r.choice([60.0, 99.5, 120.0, 140.0, 174.0, 999.0]))
    if k == "songpos":
        return ("state", "songpos", (r.randrange(0, 5000), r.randrange(0, 200)))
    if k == "title":
        return ("state", "title", r.choice(TITLES))
    if k == "names":
        return ("state", "names", r.choice(NAMES))
    if k == "step":
        return ("state", "step", r.choice([None, None, None, -1]))
    return ("state", "plugin", r.choice(PLUGINS[1:]))


def apply_state_op(state, name, arg) -> None:
    """Mutate an FLState according to a ('state', name, arg) op. Deterministic, host-independent."""
    n = state.channel_count()
    if name == "focus":
        state.focus(arg[0], arg[1] or None)
    elif name == "channels":
        state.resize_channels(arg)
    elif name == "select" and n:
        state.selected_channel = min(n - 1, int(arg * n))
    elif name == "mute" and n:
        state.muted_channels ^= {min(n - 1, int(arg * n))}
        state.muted_tracks ^= {min(state.track_count - 1, int(arg * state.track_count))}
    elif name == "solo" and n:
        state.solo_channels ^= {min(n - 1, int(arg * n))}
        state.solo_tracks ^= {min(state.track_count - 1, int(arg * state.track_count))}
    elif name == "loop":
        state.loop_mode = arg
    elif name == "popup":
        state.in_popup_menu = arg
    elif name == "node":
        state.node_file_type = arg
    elif name == "tracks":
        state.track_count = arg
        state.current_track = min(state.current_track, arg - 1)
    elif name == "track":
        state.current_track = min(state.track_count - 1, int(arg * state.track_count))
    elif name == "pattern":
        state.pattern, state.pattern_count = min(arg[0], max(arg[1], 1)), max(arg[1], 1)
    elif name == "transport":
        state.playing, state.recording = arg
        if not state.playing:
            state.song_tick_pos = state.song_step_pos = 0
    elif name == "flags":
        state.metronome, state.loop_rec, state.precount = arg
    elif name == "tempo":
        state.tempo = arg
    elif name == "songpos":
        state.song_tick_pos, state.song_step_pos = arg
    elif name == "title":
        state.prog_title = arg
    elif name == "names" and n:
        i = min(n - 1, int(state.selected_channel))
        state.channel_names[i] = arg
        state.pattern_names[state.pattern] = arg
    elif name == "step":
        state.step_param_forced = arg
    elif name == "plugin" and n:
        state.select_channel_plugin(arg)


def episodes(seed: int, n_events: int, episode_len: int = 250) -> Iterator[Episode]:
    """Yield Episodes (fresh script load + boot each) covering `n_events` events in total."""
    rng = random.Random(seed)
    made = 0
    idx = 0
    while made < n_events:
        r = random.Random(rng.randrange(1 << 62))
        ops = []
        events = 0
        target = min(episode_len, n_events - made)
        # random starting state
        for _ in range(r.randrange(0, 4)):
            ops.append(_state_op(r))
        while events < target:
            x = r.random()
            if x < 0.62:
                ops.append(_midi_entry(r) if r.random() < 0.78 else _midi_forward(r))
            elif x < 0.80:
                ops.append(("wait", r.choice([0.3, 1.0, 2.0, 5.0])) if r.random() < 0.06 else ("idle",))
            elif x < 0.86:
                ops.append(("refresh", r.choice(FLAGS)))
            elif x < 0.90:
                ops.append(("beat", r.choice([0, 1, 2])))
            elif x < 0.92:
                ops.append(("sysex", "entry", SYSEX_MEMORY_SWITCH if r.random() < 0.6 else
                            bytes([0xF0]) + bytes(r.randrange(128) for _ in range(r.randrange(0, 12))) + b"\xf7"))
            else:
                ops.append(_state_op(r))
                continue
            events += 1
        made += events
        yield Episode(idx, r.random() < 0.5, ops)
        idx += 1


def apply_op(scripts, op) -> None:
    """Run one op against a booted ScriptSet (FL-like: exceptions in callbacks are caught into host.errors)."""
    kind = op[0]
    host = scripts.host
    if kind == "midi":
        s = getattr(scripts, op[1])
        if s is not None:
            s.deliver_midi(op[2], op[3], op[4])
    elif kind == "sysex":
        s = getattr(scripts, op[1])
        if s is not None:
            s.deliver_sysex(op[2])
    elif kind in ("idle", "wait"):
        host.advance(0.02 if kind == "idle" else op[1])
        for s in scripts.scripts:
            if s.has("OnIdle"):
                s.call("OnIdle")
    elif kind == "refresh":
        for s in scripts.scripts:
            if s.has("OnRefresh"):
                s.call("OnRefresh", op[1])
    elif kind == "beat":
        for s in scripts.scripts:
            if s.has("OnUpdateBeatIndicator"):
                s.call("OnUpdateBeatIndicator", op[1])
    elif kind == "state":
        apply_state_op(host.state, op[1], op[2])
    else:
        raise ValueError("unknown op %r" % (op,))
