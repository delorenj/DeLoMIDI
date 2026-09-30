"""The 2x16 LCD text path (O-03, O-04, O-18): any text FL can hand us ends up as at most 16 printable ASCII bytes per
line, never raises, never poisons the display state, and the main page copes with an empty rack, a -1 selection, empty
names and a pattern number of 0. Stock encoded with strict 'ascii' and stored the text before encoding."""
from __future__ import annotations

import random

import pytest

from tests import kl
from tests.flsim.sysex import decode
from tests.test_output_support import boot, module, sent, tuned_only  # noqa: F401

WEIRD = [None, "", " ", "x" * 200, "Café", "Kick ♪", "ドラム", "😀 emoji", "tab\there", "line\nbreak", "nul\x00in", "del\x7fchar",
         "nbsp here", "en–dash — em", "“quoted” ‘text’", "wait…", "Ω≈ç√∫", "a" * 15 + "é", "\x1b[31mred", "ß", "ǅ", "①②③",
         b"bytes", b"\xff\xfe", 12, 3.5, ["list"], "\ud800"]


def _ok_line(line):
    return len(line) <= 16 and all(0x20 <= ord(c) < 0x7F for c in line)


# ================================================================================================ the sanitiser itself

@pytest.mark.parametrize("text", WEIRD, ids=lambda t: repr(t)[:20])
def test_ascii_line_returns_printable_ascii_for_anything(host, scripts, text):
    fold = module("KLTDisplay").ascii_line
    out = fold(text)
    assert isinstance(out, str) and all(0x20 <= ord(c) < 0x7F for c in out)


def test_accents_fold_punctuation_maps_and_the_rest_is_a_question_mark(host, scripts):
    fold = module("KLTDisplay").ascii_line
    assert fold("Café Zoë Ñandú") == "Cafe Zoe Nandu"
    assert fold("“a” ‘b’ – — …") == '"a" \'b\' - - ...'
    assert fold("Kick ♪ ドラム") == "Kick ? ???"
    assert fold("a\tb\nc\x00d\x7fe") == "a b c d e"
    assert fold(None) == "" and fold(42) == "42" and fold(b"caf\xc3\xa9") == "cafe"


def test_without_unicodedata_non_ascii_becomes_a_question_mark(host, scripts):
    """The fold needs unicodedata (part of FL's embedded Python 3.12); without it the text still comes out ASCII."""
    mod = module("KLTDisplay")
    mod.unicodedata, saved = None, mod.unicodedata
    try:
        assert mod.ascii_line("Café ♪") == "Caf? ?"
    finally:
        mod.unicodedata = saved


def test_lcd_bytes_never_exceed_16_printable_bytes(host, scripts):
    mod = module("KLTDisplay")
    rnd = random.Random(20260929)
    pool = [chr(c) for c in list(range(0, 300)) + [0x2013, 0x2026, 0x266A, 0x3042, 0x1F600, 0xD7FF, 0xE000, 0xFFFF]]
    for _ in range(3000):
        text = "".join(rnd.choice(pool) for _ in range(rnd.randint(0, 60)))
        b = mod._lcd_bytes(text)
        assert len(b) <= 16 and all(0x20 <= x < 0x7F for x in b), repr(text)


# ================================================================================================ the display never breaks

def test_no_text_can_poison_the_display_state(host, scripts):
    """The stock stored the raw text and encoded it later; one bad string then made every refresh raise until the text
    happened to change. Any text, then normal text: the display recovers and never raises."""
    scripts.boot(order=("forward", "entry"))
    d = module("device_KeyLabmk2Tuned")._mk2.display()
    host.current, host.phase, host.cb = scripts.entry, "OnIdle", "OnIdle"      # device.* is only legal inside a callback
    try:
        for text in WEIRD:
            d.SetLines(line1=text, line2=text)
            d.SetLines(line1=text, line2=text, expires=200)
            d.Refresh()
        d.SetLines(line1="Kick", line2="Pattern 1")
        host.advance(2.0)
        d.Refresh()
    finally:
        host.current, host.phase, host.cb = None, "test", None
    assert host.errors == []
    for f in sent(host):
        if f.kind == "lcd":
            assert _ok_line(f.fields["line1"]) and _ok_line(f.fields["line2"])


@pytest.mark.parametrize("field", ["channel_name", "pattern_name", "prog_title"])
def test_every_lcd_frame_of_a_session_with_hostile_names_is_ascii_and_short(make_rig, field):
    rig = make_rig(boot=False)
    st = rig.state
    hostile = "Ünïcödé ♪ — “naïve” ドラム " + "x" * 40
    if field == "channel_name":
        st.channel_names = [hostile] * len(st.channel_names)
    elif field == "pattern_name":
        st.pattern_names = {i: hostile for i in range(1, 10)}
    else:
        st.prog_title = hostile
    rig.scripts.boot(order=("forward", "entry"))
    rig.settle(5.0)
    rig.tap(kl.BTN_PLAY)
    rig.tap(kl.BTN_LOOP)
    rig.fader(1, 77)
    rig.cc(60, 1)
    rig.settle(3.0)
    assert rig.host.errors == []
    frames = [f for f in sent(rig.host) if f.kind == "lcd"]
    assert frames and all(_ok_line(f.fields["line1"]) and _ok_line(f.fields["line2"]) for f in frames)
    assert all(f.raw == f.raw for f in frames) and rig.host.violations == []


# ================================================================================================ the main page (Sync)

def _main_page(rig):
    rig.settle(4.0)                                     # past the splash
    return rig.host.device_model().lcd


def test_main_page_of_an_empty_rack_says_so_and_asks_fl_for_no_channel(make_rig):
    rig = make_rig(boot=False)
    rig.state.set_channels([])
    rig.scripts.boot(order=("forward", "entry"))
    assert _main_page(rig) == ("No channel", "Pattern 1")
    assert [v for v in rig.host.violations if v.kind == "index"] == [] and rig.host.errors == []


@pytest.mark.parametrize("selected", [-1, 10, 99])
def test_main_page_with_a_selection_outside_the_rack(make_rig, selected):
    rig = make_rig(boot=False)
    rig.state.selected_channel = selected
    rig.scripts.boot(order=("forward", "entry"))
    assert _main_page(rig)[0] == "No selection"
    assert [v for v in rig.host.violations if v.kind == "index"] == [] and rig.host.errors == []


def test_main_page_with_an_empty_channel_name(make_rig):
    rig = make_rig(boot=False)
    rig.state.channel_names[0] = ""
    rig.scripts.boot(order=("forward", "entry"))
    assert _main_page(rig) == ("1 - ", "Pattern 1")


def test_main_page_with_pattern_number_zero_asks_for_no_pattern_name(make_rig):
    rig = make_rig(boot=False)
    rig.state.pattern = 0
    rig.scripts.boot(order=("forward", "entry"))
    assert _main_page(rig) == ("1 - Kick", "")
    assert [v for v in rig.host.violations if v.kind == "index"] == []


def test_a_failing_name_query_keeps_the_last_good_text(rig):
    rig.settle(4.0)
    rig.state.channel_names[0] = "Kick2"
    rig.refresh()
    rig.settle(0.5)
    assert rig.host.device_model().lcd[0] == "1 - Kick2"
    rig.host.inject_fault("channels.getChannelName", RuntimeError)
    rig.state.pattern_names[1] = "Verse"
    a = rig.refresh()
    rig.settle(1.5)
    assert a.errors == [] and rig.host.errors == []
    assert rig.host.device_model().lcd == ("1 - Kick2", "Verse")           # line 1 kept, line 2 updated


# ================================================================================================ scrolling (O-18)

def _scroll_times(rig, name):
    rig.state.channel_names[0] = name
    rig.refresh()
    rig.settle(4.0)
    m0 = rig.host.mark()
    rig.idle(6.0)
    return [t for t, l1, _ in rig.host.device_model(since=m0).lcd_frames if l1 != "1 - Kick"]


def test_long_names_scroll_every_lcd_scroll_ms(make_rig):
    rig = boot(make_rig, cfg={"LCD_SCROLL_MS": 500})
    times = _scroll_times(rig, "A very long channel name for scrolling")
    gaps = [round(b - a, 2) for a, b in zip(times, times[1:])]
    assert len(times) >= 8 and set(gaps) <= {0.5, 0.52, 0.48}, gaps


def test_the_stock_scroll_speed_is_a_switch(make_rig):
    rig = boot(make_rig, cfg={"LCD_SCROLL_MS": 1500})
    times = _scroll_times(rig, "A very long channel name for scrolling")
    gaps = [round(b - a, 2) for a, b in zip(times, times[1:])]
    assert 2 <= len(times) <= 6 and all(1.4 <= g <= 1.6 for g in gaps), gaps


def test_short_names_never_scroll_and_never_resend(rig):
    rig.settle(4.0)
    m0 = rig.host.mark()
    rig.idle(5.0)                                       # inside the keep-alive interval: not one LCD frame
    assert rig.host.device_model(since=m0).lcd_frames == []


def test_a_broken_scroll_switch_falls_back_to_the_stock_speed(make_rig):
    rig = boot(make_rig, cfg={"LCD_SCROLL_MS": "fast"})
    times = _scroll_times(rig, "A very long channel name for scrolling")
    assert rig.host.errors == [] and len(times) >= 2
