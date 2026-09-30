"""Decoder for the Arturia KeyLab mkII SysEx the scripts send, and a model of what the keyboard is showing.

Grammar (docs/analysis/03-output-audit.md section 2; reverse-engineered, not an official Arturia spec):

    frame        F0 00 20 6B 7F 42 <payload> F7
    mono LED     02 00 10 <id> <v>                       12 bytes on the wire
    RGB LED      02 00 16 <id> <R> <G> <B> 7F            15 bytes (the trailing 7F is Arturia's; keep it)
    LCD          04 00 60 01 <line1> 00 02 <line2> 00 7F   lines <= 16 ASCII bytes
    deinit       02 7D 7D 0B 00                          (meaning UNVERIFIED)
"""
from __future__ import annotations

from collections import Counter
from typing import NamedTuple, Optional

from .host import check_framing

HEADER = bytes([0xF0, 0x00, 0x20, 0x6B, 0x7F, 0x42])
DEINIT_PAYLOAD = bytes([0x02, 0x7D, 0x7D, 0x0B, 0x00])
LCD_LINE_MAX = 16


class Frame(NamedTuple):
    kind: str           # 'led_mono' | 'led_rgb' | 'lcd' | 'deinit' | 'unknown' | 'invalid'
    fields: dict
    raw: bytes


def led_mono_frame(led_id: int, value: int) -> bytes:
    return HEADER + bytes([0x02, 0x00, 0x10, led_id, value]) + b"\xF7"


def led_rgb_frame(led_id: int, r: int, g: int, b: int) -> bytes:
    return HEADER + bytes([0x02, 0x00, 0x16, led_id, r, g, b, 0x7F]) + b"\xF7"


def lcd_frame(line1: str, line2: str) -> bytes:
    return (HEADER + bytes([0x04, 0x00, 0x60, 0x01]) + line1.encode("ascii") + bytes([0x00, 0x02])
            + line2.encode("ascii") + bytes([0x00, 0x7F]) + b"\xF7")


def decode(msg: bytes) -> Frame:
    msg = bytes(msg)
    bad = check_framing(msg)
    if bad is not None:
        return Frame("invalid", {"why": bad}, msg)
    if msg[:6] != HEADER:
        return Frame("invalid", {"why": "not an Arturia header"}, msg)
    p = msg[6:-1]
    if p[:3] == b"\x02\x00\x10" and len(p) == 5:
        return Frame("led_mono", {"id": p[3], "value": p[4]}, msg)
    if p[:3] == b"\x02\x00\x16" and len(p) in (7, 8):
        return Frame("led_rgb", {"id": p[3], "rgb": tuple(p[4:7]), "trailer": p[7] if len(p) == 8 else None}, msg)
    if p[:4] == b"\x04\x00\x60\x01" and p.endswith(b"\x00\x7f"):
        body = p[4:-2]
        i = body.find(b"\x00\x02")
        if i >= 0:
            return Frame("lcd", {"line1": body[:i].decode("ascii", "replace"),
                                 "line2": body[i + 2:].decode("ascii", "replace")}, msg)
    if p == DEINIT_PAYLOAD:
        return Frame("deinit", {}, msg)
    return Frame("unknown", {"payload": p}, msg)


class DeviceModel:
    """Replays SysEx and keeps the last value per LED / the LCD, i.e. what the keyboard would display."""

    def __init__(self):
        self.mono: dict[int, int] = {}
        self.rgb: dict[int, tuple] = {}
        self.lcd: Optional[tuple] = None                 # (line1, line2)
        self.lcd_frames: list[tuple] = []                # (t, line1, line2)
        self.mono_history: dict[int, list] = {}          # led id -> [(t, value)]
        self.rgb_history: dict[int, list] = {}
        self.unknown: list = []
        self.invalid: list = []
        self.deinit_times: list = []
        self.counts: Counter = Counter()

    @classmethod
    def from_messages(cls, msgs) -> "DeviceModel":
        m = cls()
        for msg in msgs:
            m.apply(msg)
        return m

    def apply(self, msg) -> Frame:
        t, data = msg.t, msg.data
        f = decode(data)
        self.counts[f.kind] += 1
        if f.kind == "led_mono":
            self.mono[f.fields["id"]] = f.fields["value"]
            self.mono_history.setdefault(f.fields["id"], []).append((t, f.fields["value"]))
        elif f.kind == "led_rgb":
            self.rgb[f.fields["id"]] = f.fields["rgb"]
            self.rgb_history.setdefault(f.fields["id"], []).append((t, f.fields["rgb"]))
        elif f.kind == "lcd":
            self.lcd = (f.fields["line1"], f.fields["line2"])
            self.lcd_frames.append((t, f.fields["line1"], f.fields["line2"]))
        elif f.kind == "deinit":
            self.deinit_times.append(t)
        elif f.kind == "unknown":
            self.unknown.append(f)
        else:
            self.invalid.append(f)
        return f

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def lcd_text(self) -> str:
        return "%s|%s" % self.lcd if self.lcd else ""

    def state(self) -> tuple:
        """Hashable snapshot for comparing what two script sets leave on the keyboard."""
        return (tuple(sorted(self.mono.items())), tuple(sorted(self.rgb.items())), self.lcd)
